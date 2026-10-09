"""NocoDB REST-API export as a BackupHelper Source plugin.

Ported 1:1 from the bespoke ``backup/nocodb_exporter.py``: walks the NocoDB v2
meta/data REST API and writes a portable, self-describing tree (bases →
metadata → tables → schema → paginated records → attachment binaries + a
top-level manifest). The engine owns everything around it (staging, sha256,
bundling, retention, off-site S3, encryption); this source only answers WHAT to
capture. Restore of this export is operator-driven via the ``nocodb`` command
group (restore-schema/records/attachments) — see ``commands.py`` — so
``restore()`` here is intentionally a no-op pointer.
"""

from __future__ import annotations

import gzip
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Mapping

import httpx

from backuphelper.archive.bundle import create_bundle
from backuphelper.sources.base import Source, StagedComponent

log = logging.getLogger("backuphelper.plugin.nocodb")

# Redirects followed per attachment download; each hop picks its client anew.
_MAX_REDIRECTS = 5
# Warnings kept in the component metadata; the rest is counted.
_MAX_WARNINGS = 20


class _RequestFailed(Exception):
    """A NocoDB API request that returned no usable JSON."""


def _summarize(warnings: list[str]) -> list[str]:
    if len(warnings) <= _MAX_WARNINGS:
        return warnings
    return warnings[:_MAX_WARNINGS] + [f"... and {len(warnings) - _MAX_WARNINGS} more"]


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default if value is None else bool(value)


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename (MUST match commands._sanitize_filename)."""
    safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe = safe.replace("<", "_").replace(">", "_").replace('"', "_")
    safe = safe.replace("|", "_").replace("?", "_").replace("*", "_")
    return safe[:100]


def _attachment_link(att: dict) -> str | None:
    """Where an attachment can be downloaded from.

    NocoDB's Local storage adapter (the default) stores an attachment as a
    NocoDB-relative ``path``, object storage as an absolute ``url``; read
    through the API, both come with a signed variant. The signed links go
    first: they also work with NC_SECURE_ATTACHMENTS and private buckets."""
    for key in ("signedPath", "path", "signedUrl", "url"):
        value = att.get(key)
        if isinstance(value, str) and value:
            return value
    return None


class NocoDBRestSource(Source):
    """Exports NocoDB data via the REST API into a snapshot component."""

    type = "nocodb-rest"

    def __init__(self, spec: Mapping[str, Any]):
        super().__init__(spec)
        self.api_url = str(spec.get("api_url") or "http://nocodb-server:8080").rstrip("/")
        self.api_token = spec.get("token") or spec.get("api_token") or ""
        self.include_records = _as_bool(spec.get("include_records"), True)
        self.include_attachments = _as_bool(spec.get("include_attachments"), True)
        self.enabled = _as_bool(spec.get("enabled"), True)
        self.name = str(spec.get("name") or "nocodb")

    # ── HTTP helpers (ported) ────────────────────────────────────────────────
    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.api_url,
            headers={"xc-token": self.api_token, "Content-Type": "application/json"},
            timeout=60.0,
        )

    def _api_get(self, client: httpx.Client, endpoint: str, params: dict | None = None):
        """GET a NocoDB API endpoint. A failed request raises _RequestFailed - the
        caller decides whether it ends the export or leaves a reported gap."""
        try:
            resp = client.get(endpoint, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise _RequestFailed(f"HTTP {e.response.status_code} for {endpoint}") from e
        except (httpx.HTTPError, ValueError) as e:
            raise _RequestFailed(f"{endpoint}: {e}") from e

    def _foreign_client(self) -> httpx.Client:
        """Client for hosts other than NocoDB: no API token, no NocoDB headers."""
        return httpx.Client(timeout=60.0)

    def _is_nocodb(self, url: httpx.URL) -> bool:
        api = httpx.URL(self.api_url)
        return (url.scheme, url.host, url.port) == (api.scheme, api.host, api.port)

    def _fetch(self, client: httpx.Client, url: httpx.URL) -> bytes:
        """GET ``url`` and follow redirects by hand: ``client`` carries the API
        token, and httpx would keep that header on a redirect to another host
        (only Authorization is dropped there). Object-storage links and any URL
        a user put into an attachment cell must never see the token."""
        for _ in range(_MAX_REDIRECTS + 1):
            if self._is_nocodb(url):
                resp = client.get(url, follow_redirects=False)
            else:
                with self._foreign_client() as foreign:
                    resp = foreign.get(url, follow_redirects=False)
            if resp.is_redirect and resp.next_request is not None:
                url = resp.next_request.url
                continue
            resp.raise_for_status()
            return resp.content
        raise httpx.TooManyRedirects(f"more than {_MAX_REDIRECTS} redirects")

    def _download_file(self, client: httpx.Client, url: str, target_path: Path) -> bool:
        try:
            if url.startswith(("http://", "https://")):
                full_url = httpx.URL(url)
            else:
                full_url = httpx.URL(f"{self.api_url}/{url.lstrip('/')}")
            content = self._fetch(client, full_url)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(content)
            return True
        except Exception as e:  # noqa: BLE001
            # The link itself is not logged: signed links carry their own token.
            log.warning("Failed to download attachment %s: %s", target_path.name, e)
            return False

    def _get_bases(self, client: httpx.Client) -> list[dict]:
        # Not caught: without the base list there is nothing to export - a
        # rejected or expired token must fail the component, not empty it.
        resp = self._api_get(client, "/api/v2/meta/bases")
        if isinstance(resp, dict):
            return resp.get("list", [])
        return []

    def _get_tables(self, client: httpx.Client, base_id: str, warnings: list[str]) -> list[dict]:
        resp = self._api_get(client, f"/api/v2/meta/bases/{base_id}/tables")
        if not isinstance(resp, dict):
            return []
        detailed = []
        for table in resp.get("list", []):
            table_id = table.get("id")
            if not table_id:
                continue
            try:
                detail = self._api_get(client, f"/api/v2/meta/tables/{table_id}")
            except _RequestFailed as e:
                detail = None
                warnings.append(f"table {table.get('title')}: schema incomplete, basic metadata only ({e})")
            if detail and isinstance(detail, dict):
                detailed.append(detail)
            else:
                log.warning("Could not fetch schema for table '%s', using basic metadata", table.get("title"))
                detailed.append(table)
        return detailed

    def _get_table_records(self, client: httpx.Client, table_id: str, limit: int, offset: int):
        resp = self._api_get(
            client, f"/api/v2/tables/{table_id}/records", params={"limit": limit, "offset": offset}
        )
        if isinstance(resp, dict):
            return resp.get("list", []), resp.get("pageInfo", {}).get("totalRows", 0)
        return [], 0

    def _extract_attachments(self, records: list[dict], fields: list[dict]) -> list[dict]:
        attachment_fields = [f["title"] for f in fields if f.get("uidt") == "Attachment"]
        attachments = []
        for record in records:
            for field_name in attachment_fields:
                value = record.get(field_name)
                if value and isinstance(value, list):
                    for att in value:
                        link = _attachment_link(att) if isinstance(att, dict) else None
                        if link:
                            attachments.append({
                                "url": att.get("url"), "path": att.get("path"), "link": link,
                                "title": att.get("title", ""), "mimetype": att.get("mimetype", ""),
                                "size": att.get("size", 0), "field": field_name,
                            })
        return attachments

    # ── export (ported export_all) ───────────────────────────────────────────
    def _export_all(self, client: httpx.Client, output_dir: Path) -> dict:
        bases_count = tables_count = records_count = attachments_count = total_size = 0
        manifest = {"version": "1.0", "nocodb_url": self.api_url, "bases": []}
        # Gaps the export leaves (a failed page, schema or download): reported as
        # metadata warnings, so the engine degrades the job and alerts.
        warnings: list[str] = []

        for base in self._get_bases(client):
            base_id = base.get("id")
            base_title = base.get("title", "untitled")
            if not base_id:
                continue
            bases_count += 1
            base_dir = output_dir / "bases" / _sanitize_filename(base_title)
            base_dir.mkdir(parents=True, exist_ok=True)
            base_manifest = {"id": base_id, "title": base_title, "tables": []}

            meta_file = base_dir / "metadata.json"
            meta_file.write_text(json.dumps(base, indent=2))
            total_size += meta_file.stat().st_size

            try:
                tables = self._get_tables(client, base_id, warnings)
            except _RequestFailed as e:
                warnings.append(f"{base_title}: tables not exported ({e})")
                tables = []
            for table in tables:
                table_id = table.get("id")
                table_title = table.get("title", "untitled")
                if not table_id:
                    continue
                tables_count += 1
                table_dir = base_dir / "tables" / _sanitize_filename(table_title)
                table_dir.mkdir(parents=True, exist_ok=True)
                table_manifest = {"id": table_id, "title": table_title}

                schema_file = table_dir / "schema.json"
                schema_file.write_text(json.dumps(table, indent=2))
                total_size += schema_file.stat().st_size

                if self.include_records:
                    all_records: list[dict] = []
                    offset, limit = 0, 1000
                    while True:
                        try:
                            recs, total = self._get_table_records(client, table_id, limit, offset)
                        except _RequestFailed as e:
                            warnings.append(f"{base_title}/{table_title}: records incomplete, "
                                            f"stopped after {offset} ({e})")
                            break
                        if not recs:
                            break
                        all_records.extend(recs)
                        offset += len(recs)
                        if offset >= total:
                            break
                    records_count += len(all_records)
                    table_manifest["records_count"] = len(all_records)

                    records_file = table_dir / "records.json.gz"
                    data = json.dumps(all_records, indent=2).encode("utf-8")
                    with gzip.open(records_file, "wb", compresslevel=6) as gz:
                        gz.write(data)
                    total_size += records_file.stat().st_size

                    if self.include_attachments:
                        fields = table.get("columns", [])
                        table_attachments = 0
                        for att in self._extract_attachments(all_records, fields):
                            stored = att.get("path") or att.get("url") or ""
                            title = att.get("title") or stored.split("/")[-1].split("?")[0]
                            if title:
                                field_dir = table_dir / "attachments" / _sanitize_filename(att.get("field", "unknown"))
                                target = field_dir / _sanitize_filename(title)
                                if self._download_file(client, att["link"], target):
                                    table_attachments += 1
                                    if target.exists():
                                        total_size += target.stat().st_size
                                else:
                                    warnings.append(f"{base_title}/{table_title}: attachment {title} "
                                                    "not downloaded")
                        attachments_count += table_attachments
                        table_manifest["attachments_count"] = table_attachments

                base_manifest["tables"].append(table_manifest)
            manifest["bases"].append(base_manifest)

        manifest_file = output_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))
        total_size += manifest_file.stat().st_size
        stats = {"bases": bases_count, "tables": tables_count, "records": records_count,
                 "attachments": attachments_count, "total_size": total_size}
        if warnings:
            stats["warnings"] = _summarize(warnings)
        return stats

    # ── Source contract ──────────────────────────────────────────────────────
    def produce(self, staging_dir: Path) -> list[StagedComponent]:
        # Config-activated: skip cleanly when disabled or no token (matches the
        # bespoke "if unset the whole API export is skipped").
        if not self.enabled or not self.api_token:
            log.info("nocodb-rest source not active (enabled=%s, token=%s) — skipping",
                     self.enabled, bool(self.api_token))
            return []
        staging_dir.mkdir(parents=True, exist_ok=True)
        out = staging_dir / f"{self.name}.tar.gz"
        client = self._client()
        try:
            with tempfile.TemporaryDirectory(dir=staging_dir) as td:
                export_dir = Path(td) / "export"
                export_dir.mkdir()
                stats = self._export_all(client, export_dir)
                create_bundle(export_dir, out)
        except Exception as e:  # noqa: BLE001 - one bad source degrades to partial
            log.error("NocoDB REST export failed: %s", e)
            return [StagedComponent(name=self.name, kind="nocodb", path=None, error=str(e))]
        finally:
            client.close()
        return [StagedComponent(name=self.name, kind="nocodb", path=out, metadata=stats)]

    def restore(self, staged_dir: Path) -> None:
        # Intentionally NOT auto-applied: the NocoDB REST export is restored
        # selectively by the operator via the `nocodb` command group
        # (restore-schema / restore-records / restore-attachments).
        log.info("nocodb-rest export is restored via `backuphelper nocodb "
                 "restore-schema|restore-records|restore-attachments`, not auto-restore")
