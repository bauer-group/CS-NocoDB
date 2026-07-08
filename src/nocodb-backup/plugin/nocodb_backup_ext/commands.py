"""NocoDB REST-restore command group (mounted under the engine CLI).

Registered under the ``backuphelper.commands`` entry-point group, so these
subcommands appear as ``backuphelper nocodb restore-schema|restore-records|
restore-attachments``. Ported 1:1 from the bespoke ``cli.py``:

* restore-schema      — recreate bases + tables from backed-up schema.json,
                        skipping system/virtual/pk columns, carrying Select
                        options into dtxp (schema-aware).
* restore-records     — batched (100) record re-insert, strips system fields,
                        optional attachment re-upload + relink.
* restore-attachments — standalone attachment re-upload after a DB restore,
                        matching records by their original id, with the 4-strategy
                        backup-file finder.

The two *generic* restore paths the bespoke also had — the raw pg_dump restore
and the data-file extract — are provided by the engine itself:
``backuphelper restore <id> --only <db>`` and ``--only <files>``. Only the
NocoDB-REST-specific logic lives here.

Presentation uses ``typer.echo`` (not rich) so the plugin adds no dependency
beyond httpx; the backup/restore *logic* is unchanged.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Optional

import httpx
import typer

from ._snapshot import SnapshotError, open_export
from .rest_source import _sanitize_filename  # shared with the exporter — must match

app = typer.Typer(
    name="nocodb",
    help="NocoDB REST-API restore commands (schema / records / attachments).",
    no_args_is_help=True,
)


def _api() -> tuple[str, str]:
    """Return (api_url, token); abort with a clear message if the token is unset."""
    token = os.environ.get("NOCODB_API_TOKEN", "")
    if not token:
        typer.echo("NOCODB_API_TOKEN is required for NocoDB REST restore.", err=True)
        raise typer.Exit(1)
    url = os.environ.get("NOCODB_API_URL", "http://nocodb-server:8080").rstrip("/")
    return url, token


def _require_base_for_table(base: Optional[str], table: Optional[str]) -> None:
    if table and not base:
        typer.echo("--table requires --base to be specified.", err=True)
        raise typer.Exit(1)


# ── Schema helpers (ported 1:1) ──────────────────────────────────────────────
_SYSTEM_UIDTS = {"ID", "CreatedTime", "LastModifiedTime", "CreatedBy", "LastModifiedBy"}
_VIRTUAL_UIDTS = {"Links", "LinkToAnotherRecord", "Lookup", "Rollup", "Formula", "Button"}
_CREATE_PROPS = {"title", "column_name", "uidt", "dtxp", "dtxs", "rqd", "cdf", "pv", "meta"}


def _prepare_columns_for_create(columns: list[dict]) -> tuple[list[dict], list[str]]:
    """Filter/clean columns from schema.json for table creation via the API.

    Returns (creatable column dicts, skipped column descriptions).
    """
    creatable: list[dict] = []
    skipped: list[str] = []

    for col in columns:
        uidt = col.get("uidt", "")
        title = col.get("title", "?")

        if uidt in _SYSTEM_UIDTS or col.get("system"):
            continue  # NocoDB auto-creates system columns
        if col.get("pk"):
            continue  # primary key is auto-created
        if uidt in _VIRTUAL_UIDTS:
            skipped.append(f"{title} ({uidt})")  # relations need manual recreation
            continue

        clean: dict = {}
        for key in _CREATE_PROPS:
            val = col.get(key)
            if val is not None:
                clean[key] = val
        if "title" not in clean or "uidt" not in clean:
            continue

        if uidt in ("SingleSelect", "MultiSelect"):
            col_options = col.get("colOptions")
            if col_options and isinstance(col_options, dict):
                options = col_options.get("options", [])
                if options and not clean.get("dtxp"):
                    clean["dtxp"] = ",".join(
                        f"'{opt['title']}'"
                        for opt in options
                        if isinstance(opt, dict) and "title" in opt
                    )

        creatable.append(clean)

    return creatable, skipped


# ── Attachment helpers (ported 1:1) ──────────────────────────────────────────
def _get_attachment_fields(schema: dict) -> list[str]:
    return [f["title"] for f in schema.get("columns", []) if f.get("uidt") == "Attachment"]


def _upload_attachment(client: httpx.Client, file_path: Path, storage_path: str = "") -> Optional[list[dict]]:
    try:
        with open(file_path, "rb") as f:
            resp = client.post(
                "/api/v2/storage/upload",
                files={"files": (file_path.name, f)},
                params={"path": storage_path} if storage_path else {},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:  # noqa: BLE001
        typer.echo(f"    upload failed for {file_path.name}: {e}")
        return None


def _find_backup_file(attachments_dir: Path, field_name: str, attachment_info: dict) -> Optional[Path]:
    """Find an attachment file in the backup dir via 4 fallback strategies, since
    URLs/paths differ between environments."""
    field_dir = attachments_dir / _sanitize_filename(field_name)
    if not field_dir.exists():
        return None

    title = attachment_info.get("title") or ""
    if title:
        target = field_dir / _sanitize_filename(title)
        if target.exists():
            return target

    path_name = (attachment_info.get("path") or "").split("/")[-1]
    if path_name:
        target = field_dir / _sanitize_filename(path_name)
        if target.exists():
            return target

    url = attachment_info.get("url") or ""
    if url:
        url_name = url.split("/")[-1].split("?")[0]
        if url_name:
            target = field_dir / _sanitize_filename(url_name)
            if target.exists():
                return target

    files = list(field_dir.iterdir())
    if len(files) == 1 and files[0].is_file():
        return files[0]  # fuzzy: single file in the field dir

    return None


def _restore_attachments_for_table(
    client: httpx.Client,
    upload_client: httpx.Client,
    table_id: str,
    table_dir: Path,
    records: list[dict],
    attachment_fields: list[str],
    record_ids: list,
    storage_path: str = "",
) -> tuple[int, int]:
    """Upload attachments and relink them onto the restored records. Returns
    (uploaded_count, error_count)."""
    attachments_dir = table_dir / "attachments"
    if not attachments_dir.exists():
        return 0, 0

    uploaded = errors = 0
    for idx, record in enumerate(records):
        if idx >= len(record_ids):
            break
        record_id = record_ids[idx]
        update_fields: dict = {}

        for field_name in attachment_fields:
            field_value = record.get(field_name)
            if not field_value or not isinstance(field_value, list):
                continue
            new_attachments = []
            for att_info in field_value:
                if not isinstance(att_info, dict):
                    continue
                backup_file = _find_backup_file(attachments_dir, field_name, att_info)
                if not backup_file:
                    continue
                result = _upload_attachment(upload_client, backup_file, storage_path)
                if result and len(result) > 0:
                    new_attachments.append(result[0])
                    uploaded += 1
                else:
                    errors += 1
            if new_attachments:
                update_fields[field_name] = new_attachments

        if update_fields:
            update_fields["Id"] = record_id
            try:
                resp = client.patch(f"/api/v2/tables/{table_id}/records", json=[update_fields])
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                typer.echo(f"    failed to update record {record_id}: {e.response.status_code}")
                errors += 1

    return uploaded, errors


def _insert_records_batched(client, table_id, clean_records, orig_records, collect_ids, batch_size=100):
    """Insert clean_records into a table in batches. Returns
    (restored_count, inserted_orig_records, new_record_ids, errors).

    inserted_orig_records and new_record_ids are kept in **lockstep**: only rows
    from batches that actually succeeded are appended, each paired with the id
    NocoDB returned for it. A failed batch therefore never shifts the positional
    record<->new-id mapping the attachment relink relies on.
    """
    restored = 0
    inserted: list = []
    new_ids: list = []
    errs: list = []
    for i in range(0, len(clean_records), batch_size):
        batch = clean_records[i:i + batch_size]
        orig_batch = orig_records[i:i + batch_size]
        try:
            resp = client.post(f"/api/v2/tables/{table_id}/records", json=batch)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            errs.append((i, len(batch), e.response.status_code))
            continue
        restored += len(batch)
        if collect_ids:
            created = resp.json()
            rows = created if isinstance(created, list) else (
                created.get("list", []) if isinstance(created, dict) else [])
            for orig, rec in zip(orig_batch, rows):  # zip guards a short id response
                inserted.append(orig)
                new_ids.append(rec.get("Id") or rec.get("id", ""))
    return restored, inserted, new_ids, errs


def _iter_base_dirs(bases_dir: Path, base: Optional[str]):
    for base_path in sorted(bases_dir.iterdir()):
        if base_path.is_dir() and (not base or base_path.name == base):
            yield base_path


def _iter_table_dirs(base_path: Path, table: Optional[str]):
    tables_dir = base_path / "tables"
    if not tables_dir.exists():
        return
    for table_path in sorted(tables_dir.iterdir()):
        if table_path.is_dir() and (not table or table_path.name == table):
            yield table_path


# ── restore-schema ───────────────────────────────────────────────────────────
@app.command("restore-schema")
def restore_schema(
    snapshot_id: str = typer.Argument(..., help="Snapshot id containing the REST export"),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Base name to restore (all if unset)"),
    table: Optional[str] = typer.Option(None, "--table", "-t", help="Table name (requires --base)"),
    skip_existing: bool = typer.Option(False, "--skip-existing", help="Skip tables that already exist"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    job: Optional[str] = typer.Option(None, "--job", help="Job whose snapshot to use"),
):
    """Recreate table schemas from a snapshot on a (fresh) NocoDB instance.

    Creates bases (if needed) and tables from the backed-up schema.json. System
    columns are auto-created by NocoDB; virtual columns (Links/Lookup/Rollup/
    Formula) are skipped and must be recreated manually in the UI.
    """
    _require_base_for_table(base, table)
    api_url, token = _api()

    try:
        with open_export(snapshot_id, job_name=job) as export_dir:
            bases_dir = export_dir / "bases"
            if not bases_dir.exists():
                typer.echo(f"no REST export found in snapshot '{snapshot_id}'.", err=True)
                raise typer.Exit(1)

            # (base_name, base_meta, table_name, schema)
            targets: list[tuple[str, dict, str, dict]] = []
            for base_path in _iter_base_dirs(bases_dir, base):
                base_meta: dict = {}
                meta_file = base_path / "metadata.json"
                if meta_file.exists():
                    base_meta = json.loads(meta_file.read_text())
                for table_path in _iter_table_dirs(base_path, table):
                    schema_file = table_path / "schema.json"
                    if schema_file.exists():
                        targets.append((base_path.name, base_meta,
                                        table_path.name, json.loads(schema_file.read_text())))

            if not targets:
                typer.echo("no matching tables with schemas found.")
                raise typer.Exit(1)

            typer.echo("Tables to create:")
            all_skipped: dict[tuple[str, str], list[str]] = {}
            for base_name, _, table_name, schema in targets:
                creatable, skipped = _prepare_columns_for_create(schema.get("columns", []))
                all_skipped[(base_name, table_name)] = skipped
                typer.echo(f"  {base_name}/{table_name}: {len(creatable)} column(s)"
                           + (f", {len(skipped)} skipped" if skipped else ""))
            for (bname, tname), skipped in all_skipped.items():
                if skipped:
                    typer.echo(f"  skipped virtual columns in {bname}/{tname}: {', '.join(skipped)}")

            if not force and not typer.confirm("Proceed with schema restore?"):
                typer.echo("aborted")
                raise typer.Exit(0)

            headers = {"xc-token": token, "Content-Type": "application/json"}
            with httpx.Client(base_url=api_url, headers=headers, timeout=60.0) as client:
                resp = client.get("/api/v2/meta/bases")
                resp.raise_for_status()
                existing_bases = {b["title"]: b["id"] for b in resp.json().get("list", [])}

                created = skipped_n = errors = 0
                by_base: dict[str, tuple[dict, list[tuple[str, dict]]]] = {}
                for base_name, base_meta, table_name, schema in targets:
                    by_base.setdefault(base_name, (base_meta, []))[1].append((table_name, schema))

                for base_name, (_, tables) in by_base.items():
                    base_id = existing_bases.get(base_name)
                    if not base_id:
                        try:
                            resp = client.post("/api/v2/meta/bases", json={"title": base_name})
                            resp.raise_for_status()
                            base_id = resp.json().get("id")
                            typer.echo(f"  + created base '{base_name}'")
                        except httpx.HTTPStatusError as e:
                            typer.echo(f"  ! failed to create base '{base_name}': {e.response.status_code}")
                            errors += len(tables)
                            continue
                    if not base_id:
                        typer.echo(f"  ! no base id for '{base_name}' — skipping")
                        errors += len(tables)
                        continue

                    resp = client.get(f"/api/v2/meta/bases/{base_id}/tables")
                    resp.raise_for_status()
                    existing_tables = {t["title"]: t["id"] for t in resp.json().get("list", [])}

                    for table_name, schema in tables:
                        original_title = schema.get("title", table_name)
                        if original_title in existing_tables:
                            if skip_existing:
                                typer.echo(f"  - {base_name}/{original_title}: exists, skipping")
                                skipped_n += 1
                            else:
                                typer.echo(f"  ! {base_name}/{original_title} already exists "
                                           "(use --skip-existing)")
                                errors += 1
                            continue

                        creatable, _ = _prepare_columns_for_create(schema.get("columns", []))
                        if not creatable:
                            typer.echo(f"  ! {base_name}/{original_title}: no creatable columns")
                            errors += 1
                            continue
                        try:
                            resp = client.post(
                                f"/api/v2/meta/bases/{base_id}/tables",
                                json={"title": original_title, "columns": creatable},
                            )
                            resp.raise_for_status()
                            created += 1
                            typer.echo(f"  + {base_name}/{original_title}: created ({len(creatable)} columns)")
                        except httpx.HTTPStatusError as e:
                            detail = ""
                            try:
                                detail = e.response.json().get("msg", "")
                            except Exception:  # noqa: BLE001
                                pass
                            typer.echo(f"  ! failed to create '{base_name}/{original_title}': "
                                       f"{e.response.status_code} {detail}")
                            errors += 1

            summary = f"{created} table(s) created" + (f", {skipped_n} skipped" if skipped_n else "")
            typer.echo(f"{'completed with %d error(s). ' % errors if errors else '+ '}{summary}.")
    except SnapshotError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


# ── restore-records ──────────────────────────────────────────────────────────
@app.command("restore-records")
def restore_records(
    snapshot_id: str = typer.Argument(..., help="Snapshot id containing the REST export"),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Base name to restore (all if unset)"),
    table: Optional[str] = typer.Option(None, "--table", "-t", help="Table name (requires --base)"),
    with_attachments: bool = typer.Option(False, "--with-attachments", "-a", help="Also upload attachments"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    job: Optional[str] = typer.Option(None, "--job", help="Job whose snapshot to use"),
):
    """Re-insert records from the REST export into existing tables (batched by 100).

    Tables must already exist with a compatible schema (see restore-schema).
    --with-attachments also uploads attachment files and links them.
    """
    _require_base_for_table(base, table)
    api_url, token = _api()

    try:
        with open_export(snapshot_id, job_name=job) as export_dir:
            bases_dir = export_dir / "bases"
            if not bases_dir.exists():
                typer.echo(f"no REST export found in snapshot '{snapshot_id}'.", err=True)
                raise typer.Exit(1)

            # (base_name, table_name, records_path, table_dir)
            targets: list[tuple[str, str, Path, Path]] = []
            for base_path in _iter_base_dirs(bases_dir, base):
                for table_path in _iter_table_dirs(base_path, table):
                    records_file = table_path / "records.json.gz"
                    if records_file.exists():
                        targets.append((base_path.name, table_path.name, records_file, table_path))

            if not targets:
                typer.echo("no matching tables with records found.")
                raise typer.Exit(1)

            total = 0
            for base_name, table_name, records_path, _ in targets:
                try:
                    with gzip.open(records_path, "rb") as gz:
                        count = len(json.loads(gz.read()))
                except Exception:  # noqa: BLE001
                    count = -1
                total += max(count, 0)
                typer.echo(f"  {base_name}/{table_name}: {count if count >= 0 else '?'} record(s)")
            typer.echo(f"total: {total} record(s) in {len(targets)} table(s)")

            if not force and not typer.confirm("Records will be INSERTED into existing tables. Proceed?"):
                typer.echo("aborted")
                raise typer.Exit(0)

            json_headers = {"xc-token": token, "Content-Type": "application/json"}
            upload_headers = {"xc-token": token}
            with (
                httpx.Client(base_url=api_url, headers=json_headers, timeout=60.0) as client,
                httpx.Client(base_url=api_url, headers=upload_headers, timeout=120.0) as upload_client,
            ):
                resp = client.get("/api/v2/meta/bases")
                resp.raise_for_status()
                api_bases = {b["title"]: b["id"] for b in resp.json().get("list", [])}

                restored = att_uploaded = errors = 0
                for base_name, table_name, records_path, table_dir in targets:
                    base_id = api_bases.get(base_name)
                    if not base_id:
                        typer.echo(f"  ! base '{base_name}' not found — skipping")
                        errors += 1
                        continue
                    resp = client.get(f"/api/v2/meta/bases/{base_id}/tables")
                    resp.raise_for_status()
                    api_tables = {t["title"]: t["id"] for t in resp.json().get("list", [])}
                    table_id = api_tables.get(table_name)
                    if not table_id:
                        typer.echo(f"  ! table '{base_name}/{table_name}' not found — skipping")
                        errors += 1
                        continue

                    try:
                        with gzip.open(records_path, "rb") as gz:
                            all_records = json.loads(gz.read())
                    except Exception as e:  # noqa: BLE001
                        typer.echo(f"  ! failed to read {records_path}: {e}")
                        errors += 1
                        continue
                    if not all_records:
                        typer.echo(f"  - {base_name}/{table_name}: no records")
                        continue

                    attachment_fields: list[str] = []
                    schema_file = table_dir / "schema.json"
                    if schema_file.exists():
                        attachment_fields = _get_attachment_fields(json.loads(schema_file.read_text()))

                    system_fields = {"Id", "nc_id", "CreatedAt", "UpdatedAt", "created_at", "updated_at"}
                    strip_fields = system_fields
                    if with_attachments and attachment_fields:
                        strip_fields = strip_fields | set(attachment_fields)
                    clean_records = [{k: v for k, v in r.items() if k not in strip_fields}
                                     for r in all_records]

                    collect_ids = bool(with_attachments and attachment_fields)
                    table_restored, inserted_records, new_record_ids, batch_errs = _insert_records_batched(
                        client, table_id, clean_records, all_records, collect_ids)
                    for off, size, status in batch_errs:
                        typer.echo(f"  ! batch error in {base_name}/{table_name} "
                                   f"(records {off}-{off + size}): {status}")
                        errors += 1

                    restored += table_restored
                    typer.echo(f"  + {base_name}/{table_name}: {table_restored} record(s) restored")

                    if with_attachments and attachment_fields and new_record_ids:
                        storage_path = f"nc/{base_id}/{table_id}"
                        # inserted_records is in lockstep with new_record_ids (only rows
                        # from succeeded batches), so the positional relink stays correct.
                        up, err = _restore_attachments_for_table(
                            client, upload_client, table_id, table_dir,
                            inserted_records, attachment_fields, new_record_ids, storage_path)
                        att_uploaded += up
                        errors += err
                        if up:
                            typer.echo(f"    + {up} attachment(s) uploaded")
                        if err:
                            typer.echo(f"    ! {err} attachment error(s)")

            summary = f"{restored} record(s) restored"
            if with_attachments:
                summary += f", {att_uploaded} attachment(s) uploaded"
            typer.echo(f"{'completed with %d error(s). ' % errors if errors else '+ '}{summary}.")
    except SnapshotError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)


# ── restore-attachments ──────────────────────────────────────────────────────
@app.command("restore-attachments")
def restore_attachments(
    snapshot_id: str = typer.Argument(..., help="Snapshot id containing the REST export"),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Base name (all if unset)"),
    table: Optional[str] = typer.Option(None, "--table", "-t", help="Table name (requires --base)"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    job: Optional[str] = typer.Option(None, "--job", help="Job whose snapshot to use"),
):
    """Re-upload attachments into existing records (use after a DB restore).

    Matches records by their original id (preserved by the pg_dump restore) and
    overwrites their attachment references with the freshly uploaded files.
    """
    _require_base_for_table(base, table)
    api_url, token = _api()

    try:
        with open_export(snapshot_id, job_name=job) as export_dir:
            bases_dir = export_dir / "bases"
            if not bases_dir.exists():
                typer.echo(f"no REST export found in snapshot '{snapshot_id}'.", err=True)
                raise typer.Exit(1)

            # (base_name, table_name, table_dir, att_count)
            targets: list[tuple[str, str, Path, int]] = []
            for base_path in _iter_base_dirs(bases_dir, base):
                for table_path in _iter_table_dirs(base_path, table):
                    att_dir = table_path / "attachments"
                    if att_dir.exists():
                        att_count = sum(1 for p in att_dir.rglob("*") if p.is_file())
                        if att_count > 0:
                            targets.append((base_path.name, table_path.name, table_path, att_count))

            if not targets:
                typer.echo("no tables with attachments found in snapshot.")
                raise typer.Exit(1)

            total_files = 0
            for base_name, table_name, _, att_count in targets:
                total_files += att_count
                typer.echo(f"  {base_name}/{table_name}: {att_count} file(s)")
            typer.echo(f"total: {total_files} attachment file(s) in {len(targets)} table(s)")

            if not force and not typer.confirm("Attachments will be uploaded and relinked. Proceed?"):
                typer.echo("aborted")
                raise typer.Exit(0)

            json_headers = {"xc-token": token, "Content-Type": "application/json"}
            upload_headers = {"xc-token": token}
            with (
                httpx.Client(base_url=api_url, headers=json_headers, timeout=60.0) as client,
                httpx.Client(base_url=api_url, headers=upload_headers, timeout=120.0) as upload_client,
            ):
                resp = client.get("/api/v2/meta/bases")
                resp.raise_for_status()
                api_bases = {b["title"]: b["id"] for b in resp.json().get("list", [])}

                total_uploaded = total_errors = 0
                for base_name, table_name, table_dir, _ in targets:
                    base_id = api_bases.get(base_name)
                    if not base_id:
                        typer.echo(f"  ! base '{base_name}' not found — skipping")
                        total_errors += 1
                        continue
                    resp = client.get(f"/api/v2/meta/bases/{base_id}/tables")
                    resp.raise_for_status()
                    api_tables = {t["title"]: t["id"] for t in resp.json().get("list", [])}
                    table_id = api_tables.get(table_name)
                    if not table_id:
                        typer.echo(f"  ! table '{base_name}/{table_name}' not found — skipping")
                        total_errors += 1
                        continue

                    records_file = table_dir / "records.json.gz"
                    if not records_file.exists():
                        typer.echo(f"  ! no records.json.gz for '{base_name}/{table_name}' — skipping")
                        total_errors += 1
                        continue
                    try:
                        with gzip.open(records_file, "rb") as gz:
                            backup_records = json.loads(gz.read())
                    except Exception as e:  # noqa: BLE001
                        typer.echo(f"  ! failed to read records: {e}")
                        total_errors += 1
                        continue

                    schema_file = table_dir / "schema.json"
                    if not schema_file.exists():
                        typer.echo(f"  ! no schema.json for '{base_name}/{table_name}' — skipping")
                        total_errors += 1
                        continue
                    attachment_fields = _get_attachment_fields(json.loads(schema_file.read_text()))
                    if not attachment_fields:
                        continue

                    record_ids = [r.get("Id") or r.get("id") for r in backup_records
                                  if r.get("Id") or r.get("id")]
                    if not record_ids:
                        typer.echo(f"  ! no record ids in backup for '{base_name}/{table_name}'")
                        total_errors += 1
                        continue

                    storage_path = f"nc/{base_id}/{table_id}"
                    up, err = _restore_attachments_for_table(
                        client, upload_client, table_id, table_dir,
                        backup_records, attachment_fields, record_ids, storage_path)
                    total_uploaded += up
                    total_errors += err
                    if up:
                        typer.echo(f"  + {base_name}/{table_name}: {up} attachment(s) uploaded")
                    if err:
                        typer.echo(f"  ! {base_name}/{table_name}: {err} error(s)")

            typer.echo(f"{'completed with %d error(s). ' % total_errors if total_errors else '+ '}"
                       f"{total_uploaded} attachment(s) restored.")
    except SnapshotError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
