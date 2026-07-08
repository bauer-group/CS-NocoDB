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
        try:
            resp = client.get(endpoint, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            log.error("NocoDB API error %s: %s", e.response.status_code, endpoint)
            return None
        except Exception as e:  # noqa: BLE001 - soft-fail per request, export continues
            log.error("NocoDB API request failed: %s", e)
            return None

    def _download_file(self, client: httpx.Client, url: str, target_path: Path) -> bool:
        try:
            if url.startswith("/"):
                full_url = f"{self.api_url}{url}"
            elif url.startswith("http"):
                full_url = url
            else:
                full_url = f"{self.api_url}/{url}"
            resp = client.get(full_url, follow_redirects=True)
            resp.raise_for_status()
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(resp.content)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to download %s: %s", url, e)
            return False

    def _get_bases(self, client: httpx.Client) -> list[dict]:
        resp = self._api_get(client, "/api/v2/meta/bases")
        if resp and isinstance(resp, dict):
            return resp.get("list", [])
        return []

    def _get_tables(self, client: httpx.Client, base_id: str) -> list[dict]:
        resp = self._api_get(client, f"/api/v2/meta/bases/{base_id}/tables")
        if not resp or not isinstance(resp, dict):
            return []
        detailed = []
        for table in resp.get("list", []):
            table_id = table.get("id")
            if not table_id:
                continue
            detail = self._api_get(client, f"/api/v2/meta/tables/{table_id}")
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
        if resp and isinstance(resp, dict):
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
                        if isinstance(att, dict) and "url" in att:
                            attachments.append({
                                "url": att.get("url"), "path": att.get("path"),
                                "title": att.get("title", ""), "mimetype": att.get("mimetype", ""),
                                "size": att.get("size", 0), "field": field_name,
                            })
        return attachments

    # ── export (ported export_all) ───────────────────────────────────────────
    def _export_all(self, client: httpx.Client, output_dir: Path) -> dict:
        bases_count = tables_count = records_count = attachments_count = total_size = 0
        manifest = {"version": "1.0", "nocodb_url": self.api_url, "bases": []}

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

            for table in self._get_tables(client, base_id):
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
                        recs, total = self._get_table_records(client, table_id, limit, offset)
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
                        for att in self._extract_attachments(all_records, fields):
                            url = att.get("url")
                            title = att.get("title") or att.get("path", "").split("/")[-1]
                            if url and title:
                                field_dir = table_dir / "attachments" / _sanitize_filename(att.get("field", "unknown"))
                                target = field_dir / _sanitize_filename(title)
                                if self._download_file(client, url, target):
                                    attachments_count += 1
                                    if target.exists():
                                        total_size += target.stat().st_size
                        table_manifest["attachments_count"] = attachments_count

                base_manifest["tables"].append(table_manifest)
            manifest["bases"].append(base_manifest)

        manifest_file = output_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2))
        total_size += manifest_file.stat().st_size
        return {"bases": bases_count, "tables": tables_count, "records": records_count,
                "attachments": attachments_count, "total_size": total_size}

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
