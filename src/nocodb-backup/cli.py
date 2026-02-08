"""
NocoDB Backup - CLI Module

Command-line interface for backup management.
"""

import gzip
import json
import shutil
from datetime import datetime
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.tree import Tree

from config import Settings
from backup.pg_dump import PostgresDumper
from storage.s3_client import S3Storage
from ui.console import format_size

# ===============================================================================
# CLI App
# ===============================================================================

app = typer.Typer(
    name="nocodb-backup",
    help="NocoDB Backup CLI - Manage backups",
    no_args_is_help=True,
)

console = Console()


# -------------------------------------------------------------------------------
# List Command
# -------------------------------------------------------------------------------
@app.command("list")
def list_backups():
    """List all available backups (local and S3)."""
    settings = Settings()

    # Get local backups
    local_backups = _list_local_backups(settings)

    # Get S3 backups if configured
    s3_backups = []
    if settings.s3_enabled:
        s3 = S3Storage(settings)
        s3_backups = s3.list_backups()

    # Combine and deduplicate
    all_backup_ids = sorted(set(local_backups + s3_backups), reverse=True)

    if not all_backup_ids:
        console.print("[yellow]No backups found.[/]")
        return

    table = Table(title="Available Backups", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Backup ID", style="cyan")
    table.add_column("Local", justify="center")
    table.add_column("S3", justify="center")
    table.add_column("Size", justify="right", style="green")

    for idx, backup_id in enumerate(all_backup_ids, 1):
        has_local = backup_id in local_backups
        has_s3 = backup_id in s3_backups

        # Get size
        size = 0
        if has_local:
            size = _get_local_backup_size(settings, backup_id)
        elif has_s3 and settings.s3_enabled:
            s3 = S3Storage(settings)
            size = s3.get_backup_size(backup_id)

        table.add_row(
            str(idx),
            backup_id,
            "[green]+[/]" if has_local else "[dim]-[/]",
            "[green]+[/]" if has_s3 else "[dim]-[/]",
            format_size(size),
        )

    console.print(table)


# -------------------------------------------------------------------------------
# Show Command
# -------------------------------------------------------------------------------
@app.command("show")
def show_backup(backup_id: str = typer.Argument(..., help="Backup ID to show details for")):
    """Show details of a specific backup."""
    settings = Settings()

    # Check local
    local_path = Path(settings.data_dir) / backup_id
    has_local = local_path.exists()

    # Check S3
    has_s3 = False
    if settings.s3_enabled:
        s3 = S3Storage(settings)
        s3_size = s3.get_backup_size(backup_id)
        has_s3 = s3_size > 0

    if not has_local and not has_s3:
        console.print(f"[red]Backup '{backup_id}' not found.[/]")
        raise typer.Exit(1)

    # Build details table
    table = Table(title=f"Backup: {backup_id}", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Backup ID", backup_id)
    table.add_row("Local", "[green]+[/]" if has_local else "[red]-[/]")
    table.add_row("S3", "[green]+[/]" if has_s3 else "[red]-[/]")

    if has_local:
        table.add_row("Local Path", str(local_path))
        size = _get_local_backup_size(settings, backup_id)
        table.add_row("Local Size", format_size(size))

        # Check for database dump
        dump_file = local_path / "database.sql.gz"
        if dump_file.exists():
            table.add_row("Database Dump", format_size(dump_file.stat().st_size))

        # Check for bases directory
        bases_dir = local_path / "bases"
        if bases_dir.exists():
            base_count = len(list(bases_dir.iterdir()))
            table.add_row("Bases", str(base_count))

        # Check for manifest
        manifest_file = local_path / "manifest.json"
        if manifest_file.exists():
            table.add_row("Manifest", "[green]+[/]")

    if has_s3 and settings.s3_enabled:
        s3 = S3Storage(settings)
        s3_size = s3.get_backup_size(backup_id)
        table.add_row("S3 Path", f"s3://{s3.bucket}/{s3.prefix}/{backup_id}/")
        table.add_row("S3 Size", format_size(s3_size))

    console.print(table)


# -------------------------------------------------------------------------------
# Delete Command
# -------------------------------------------------------------------------------
@app.command("delete")
def delete_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    local_only: bool = typer.Option(False, "--local-only", help="Delete only local backup"),
    s3_only: bool = typer.Option(False, "--s3-only", help="Delete only S3 backup"),
):
    """Delete a backup from local storage and/or S3."""
    settings = Settings()

    # Check existence
    local_path = Path(settings.data_dir) / backup_id
    has_local = local_path.exists()

    has_s3 = False
    if settings.s3_enabled and not local_only:
        s3 = S3Storage(settings)
        s3_size = s3.get_backup_size(backup_id)
        has_s3 = s3_size > 0

    if not has_local and not has_s3:
        console.print(f"[red]Backup '{backup_id}' not found.[/]")
        raise typer.Exit(1)

    # Confirm deletion
    if not force:
        console.print(f"\nBackup: [cyan]{backup_id}[/]")
        if has_local and not s3_only:
            size = _get_local_backup_size(settings, backup_id)
            console.print(f"Local: [green]{format_size(size)}[/]")
        if has_s3 and not local_only:
            s3 = S3Storage(settings)
            size = s3.get_backup_size(backup_id)
            console.print(f"S3: [green]{format_size(size)}[/]")

        if not Confirm.ask("\n[yellow]Delete this backup?[/]"):
            console.print("[dim]Cancelled.[/]")
            return

    # Delete
    if has_local and not s3_only:
        shutil.rmtree(local_path)
        console.print(f"[green]+ Deleted local backup '{backup_id}'[/]")

    if has_s3 and not local_only and settings.s3_enabled:
        s3 = S3Storage(settings)
        deleted = s3.delete_backup(backup_id)
        console.print(f"[green]+ Deleted S3 backup '{backup_id}' ({deleted} objects)[/]")


# -------------------------------------------------------------------------------
# Download Command
# -------------------------------------------------------------------------------
@app.command("download")
def download_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to download from S3"),
):
    """Download a backup from S3 to local storage."""
    settings = Settings()

    if not settings.s3_enabled:
        console.print("[red]S3 is not configured.[/]")
        raise typer.Exit(1)

    s3 = S3Storage(settings)

    # Check if backup exists in S3
    s3_size = s3.get_backup_size(backup_id)
    if s3_size == 0:
        console.print(f"[red]Backup '{backup_id}' not found in S3.[/]")
        raise typer.Exit(1)

    # Check if already exists locally
    local_path = Path(settings.data_dir) / backup_id
    if local_path.exists():
        console.print(f"[yellow]Backup '{backup_id}' already exists locally.[/]")
        if not Confirm.ask("[yellow]Overwrite local copy?[/]"):
            console.print("[dim]Cancelled.[/]")
            return
        shutil.rmtree(local_path)

    console.print(f"Downloading backup [cyan]{backup_id}[/] ({format_size(s3_size)})...")

    local_path.mkdir(parents=True, exist_ok=True)
    downloaded = s3.download_backup(backup_id, local_path)

    console.print(f"[green]+ Downloaded {downloaded} file(s) to {local_path}[/]")


# -------------------------------------------------------------------------------
# Inspect Command
# -------------------------------------------------------------------------------
@app.command("inspect")
def inspect_backup(
    backup_id: str = typer.Argument(..., help="Backup ID to inspect"),
):
    """Show detailed contents of a backup (bases, tables, record counts)."""
    settings = Settings()

    local_path = Path(settings.data_dir) / backup_id
    if not local_path.exists():
        console.print(f"[red]Backup '{backup_id}' not found locally.[/]")
        console.print("[dim]Use 'download' command to fetch from S3 first.[/]")
        raise typer.Exit(1)

    # Build tree view
    tree = Tree(f"[bold cyan]{backup_id}[/]")

    # Database dump
    dump_file = local_path / "database.sql.gz"
    if dump_file.exists():
        tree.add(f"[green]database.sql.gz[/] ({format_size(dump_file.stat().st_size)})")

    # NocoDB data files archive
    data_archive = local_path / "nocodb-data.tar.gz"
    if data_archive.exists():
        tree.add(f"[green]nocodb-data.tar.gz[/] ({format_size(data_archive.stat().st_size)})")

    # Manifest
    manifest_file = local_path / "manifest.json"
    manifest = None
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text())
        tree.add("[green]manifest.json[/]")

    # Bases
    bases_dir = local_path / "bases"
    if bases_dir.exists():
        bases_branch = tree.add("[bold]bases/[/]")

        for base_path in sorted(bases_dir.iterdir()):
            if not base_path.is_dir():
                continue

            base_branch = bases_branch.add(f"[cyan]{base_path.name}/[/]")

            # Base metadata
            meta_file = base_path / "metadata.json"
            if meta_file.exists():
                base_branch.add("metadata.json")

            # Tables
            tables_dir = base_path / "tables"
            if tables_dir.exists():
                for table_path in sorted(tables_dir.iterdir()):
                    if not table_path.is_dir():
                        continue

                    # Count records from compressed file
                    records_info = ""
                    records_file = table_path / "records.json.gz"
                    if records_file.exists():
                        try:
                            with gzip.open(records_file, "rb") as gz:
                                records = json.loads(gz.read())
                            records_info = f" ({len(records)} records, {format_size(records_file.stat().st_size)})"
                        except Exception:
                            records_info = f" ({format_size(records_file.stat().st_size)})"

                    table_branch = base_branch.add(
                        f"[yellow]{table_path.name}/[/]{records_info}"
                    )

                    # Attachments
                    attachments_dir = table_path / "attachments"
                    if attachments_dir.exists():
                        att_count = sum(1 for _ in attachments_dir.rglob("*") if _.is_file())
                        att_size = sum(f.stat().st_size for f in attachments_dir.rglob("*") if f.is_file())
                        table_branch.add(
                            f"[dim]attachments/ ({att_count} files, {format_size(att_size)})[/]"
                        )

    console.print()
    console.print(tree)
    console.print()

    # Summary
    total_size = _get_local_backup_size(settings, backup_id)
    console.print(f"[dim]Total size: {format_size(total_size)}[/]")


# -------------------------------------------------------------------------------
# Restore Schema Command
# -------------------------------------------------------------------------------
@app.command("restore-schema")
def restore_schema(
    backup_id: str = typer.Argument(..., help="Backup ID containing the API export"),
    base: str = typer.Option(None, "--base", "-b", help="Base name to restore (optional, restores all if not set)"),
    table: str = typer.Option(None, "--table", "-t", help="Table name to restore (requires --base)"),
    skip_existing: bool = typer.Option(False, "--skip-existing", help="Skip tables that already exist"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Recreate table schemas from backup on a (fresh) NocoDB instance.

    Creates bases (if needed) and tables with their column definitions
    from the backed-up schema.json files. Use this to set up an empty
    NocoDB from a backup before importing records with restore-records.

    System columns (Id, CreatedAt, UpdatedAt) are auto-created by NocoDB.
    Virtual columns (Links, Lookup, Rollup, Formula) are skipped with a
    warning and must be recreated manually in the NocoDB UI if needed.
    """
    settings = Settings()

    if not settings.nocodb_api_token:
        console.print("[red]NOCODB_API_TOKEN is required for schema restore.[/]")
        raise typer.Exit(1)

    if table and not base:
        console.print("[red]--table requires --base to be specified.[/]")
        raise typer.Exit(1)

    local_path = Path(settings.data_dir) / backup_id
    bases_dir = local_path / "bases"

    if not bases_dir.exists():
        console.print(f"[red]No API export found in backup '{backup_id}'.[/]")
        console.print("[dim]Use 'download' command to fetch from S3 first.[/]")
        raise typer.Exit(1)

    # Collect schemas to restore: (base_name, base_meta, table_name, schema)
    restore_targets: list[tuple[str, dict, str, dict]] = []

    for base_path in sorted(bases_dir.iterdir()):
        if not base_path.is_dir():
            continue
        if base and base_path.name != base:
            continue

        base_meta: dict = {}
        meta_file = base_path / "metadata.json"
        if meta_file.exists():
            base_meta = json.loads(meta_file.read_text())

        tables_dir = base_path / "tables"
        if not tables_dir.exists():
            continue

        for table_path in sorted(tables_dir.iterdir()):
            if not table_path.is_dir():
                continue
            if table and table_path.name != table:
                continue

            schema_file = table_path / "schema.json"
            if schema_file.exists():
                schema = json.loads(schema_file.read_text())
                restore_targets.append((base_path.name, base_meta, table_path.name, schema))

    if not restore_targets:
        console.print("[yellow]No matching tables with schemas found.[/]")
        raise typer.Exit(1)

    # Preview
    preview_table = Table(title="Tables to Create", show_header=True, header_style="bold cyan")
    preview_table.add_column("Base", style="cyan")
    preview_table.add_column("Table", style="yellow")
    preview_table.add_column("Columns", justify="right", style="green")
    preview_table.add_column("Skipped", justify="right", style="dim")

    all_skipped: dict[tuple[str, str], list[str]] = {}
    for base_name, _, table_name, schema in restore_targets:
        columns = schema.get("columns", [])
        creatable, skipped = _prepare_columns_for_create(columns)
        all_skipped[(base_name, table_name)] = skipped
        preview_table.add_row(
            base_name, table_name,
            str(len(creatable)),
            str(len(skipped)) if skipped else "-",
        )

    console.print()
    console.print(preview_table)

    # Show skipped virtual columns
    has_skipped = any(s for s in all_skipped.values())
    if has_skipped:
        console.print()
        console.print("[dim]Skipped virtual columns (must be recreated manually):[/]")
        for (bname, tname), skipped in all_skipped.items():
            if skipped:
                console.print(f"[dim]  {bname}/{tname}: {', '.join(skipped)}[/]")

    if not force:
        console.print()
        console.print(Panel(
            "[yellow]Tables will be created via NocoDB API.[/]\n"
            "[dim]Bases will be created if they don't exist.[/]\n"
            "[dim]System columns (Id, CreatedAt, UpdatedAt) are auto-created by NocoDB.[/]",
            title="Schema Restore",
            border_style="cyan",
        ))

        if not Confirm.ask("[yellow]Proceed with schema restore?[/]"):
            console.print("[dim]Cancelled.[/]")
            return

    # Execute restore
    api_url = settings.nocodb_api_url.rstrip("/")
    headers = {"xc-token": settings.nocodb_api_token, "Content-Type": "application/json"}

    with httpx.Client(base_url=api_url, headers=headers, timeout=60.0) as client:
        # Get existing bases
        resp = client.get("/api/v2/meta/bases")
        resp.raise_for_status()
        existing_bases = {b["title"]: b["id"] for b in resp.json().get("list", [])}

        tables_created = 0
        tables_skipped = 0
        errors = 0

        # Group targets by base
        targets_by_base: dict[str, tuple[dict, list[tuple[str, dict]]]] = {}
        for base_name, base_meta, table_name, schema in restore_targets:
            if base_name not in targets_by_base:
                targets_by_base[base_name] = (base_meta, [])
            targets_by_base[base_name][1].append((table_name, schema))

        for base_name, (base_meta, tables) in targets_by_base.items():
            # Create base if it doesn't exist
            base_id = existing_bases.get(base_name)
            if not base_id:
                try:
                    resp = client.post("/api/v2/meta/bases", json={"title": base_name})
                    resp.raise_for_status()
                    base_id = resp.json().get("id")
                    console.print(f"[green]  + Created base '{base_name}'[/]")
                except httpx.HTTPStatusError as e:
                    console.print(f"[red]  ! Failed to create base '{base_name}': {e.response.status_code}[/]")
                    errors += len(tables)
                    continue

            if not base_id:
                console.print(f"[red]  ! No base ID for '{base_name}' - skipping[/]")
                errors += len(tables)
                continue

            # Get existing tables in this base
            resp = client.get(f"/api/v2/meta/bases/{base_id}/tables")
            resp.raise_for_status()
            existing_tables = {t["title"]: t["id"] for t in resp.json().get("list", [])}

            for table_name, schema in tables:
                original_title = schema.get("title", table_name)

                # Check if table already exists
                if original_title in existing_tables:
                    if skip_existing:
                        console.print(f"[dim]  - {base_name}/{original_title}: already exists, skipping[/]")
                        tables_skipped += 1
                        continue
                    else:
                        console.print(
                            f"[red]  ! Table '{base_name}/{original_title}' already exists. "
                            f"Use --skip-existing to skip.[/]"
                        )
                        errors += 1
                        continue

                # Prepare columns
                columns = schema.get("columns", [])
                creatable, _ = _prepare_columns_for_create(columns)

                if not creatable:
                    console.print(f"[yellow]  ! {base_name}/{original_title}: no creatable columns found[/]")
                    errors += 1
                    continue

                # Create table via API
                try:
                    resp = client.post(
                        f"/api/v2/meta/bases/{base_id}/tables",
                        json={
                            "title": original_title,
                            "columns": creatable,
                        },
                    )
                    resp.raise_for_status()
                    tables_created += 1
                    console.print(f"[green]  + {base_name}/{original_title}: created ({len(creatable)} columns)[/]")
                except httpx.HTTPStatusError as e:
                    error_detail = ""
                    try:
                        error_detail = e.response.json().get("msg", "")
                    except Exception:
                        pass
                    console.print(
                        f"[red]  ! Failed to create '{base_name}/{original_title}': "
                        f"{e.response.status_code} {error_detail}[/]"
                    )
                    errors += 1

    # Summary
    console.print()
    summary = f"{tables_created} table(s) created"
    if tables_skipped:
        summary += f", {tables_skipped} skipped"
    if errors:
        console.print(f"[yellow]Completed with {errors} error(s). {summary}.[/]")
    else:
        console.print(f"[green]+ {summary}.[/]")

    if tables_created > 0 and has_skipped:
        console.print()
        console.print("[dim]Note: Virtual columns (Links, Lookup, Rollup, Formula) were skipped.[/]")
        console.print("[dim]These must be recreated manually in the NocoDB UI.[/]")


# -------------------------------------------------------------------------------
# Restore Records Command
# -------------------------------------------------------------------------------
@app.command("restore-records")
def restore_records(
    backup_id: str = typer.Argument(..., help="Backup ID containing the API export"),
    base: str = typer.Option(None, "--base", "-b", help="Base name to restore (optional, restores all if not set)"),
    table: str = typer.Option(None, "--table", "-t", help="Table name to restore (requires --base)"),
    with_attachments: bool = typer.Option(False, "--with-attachments", "-a", help="Also upload and restore attachments"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Restore records from API export back into NocoDB via the REST API.

    Imports records from the backup JSON files into existing tables.
    Tables must already exist in NocoDB with matching schema.
    Use --with-attachments to also upload and link attachment files.
    """
    settings = Settings()

    if not settings.nocodb_api_token:
        console.print("[red]NOCODB_API_TOKEN is required for record restore.[/]")
        raise typer.Exit(1)

    if table and not base:
        console.print("[red]--table requires --base to be specified.[/]")
        raise typer.Exit(1)

    local_path = Path(settings.data_dir) / backup_id
    bases_dir = local_path / "bases"

    if not bases_dir.exists():
        console.print(f"[red]No API export found in backup '{backup_id}'.[/]")
        console.print("[dim]Only database dump available. Use 'restore-dump' instead.[/]")
        raise typer.Exit(1)

    # Collect tables to restore: (base_name, table_name, records_path, table_dir)
    restore_targets: list[tuple[str, str, Path, Path]] = []

    for base_path in sorted(bases_dir.iterdir()):
        if not base_path.is_dir():
            continue
        if base and base_path.name != base:
            continue

        tables_dir = base_path / "tables"
        if not tables_dir.exists():
            continue

        for table_path in sorted(tables_dir.iterdir()):
            if not table_path.is_dir():
                continue
            if table and table_path.name != table:
                continue

            records_file = table_path / "records.json.gz"
            if records_file.exists():
                restore_targets.append((base_path.name, table_path.name, records_file, table_path))

    if not restore_targets:
        console.print("[yellow]No matching tables with records found.[/]")
        raise typer.Exit(1)

    # Show what will be restored
    restore_table = Table(title="Tables to Restore", show_header=True, header_style="bold cyan")
    restore_table.add_column("Base", style="cyan")
    restore_table.add_column("Table", style="yellow")
    restore_table.add_column("Records", justify="right", style="green")
    if with_attachments:
        restore_table.add_column("Attachments", justify="right", style="dim")

    total_records = 0
    for base_name, table_name, records_path, table_dir in restore_targets:
        try:
            with gzip.open(records_path, "rb") as gz:
                records = json.loads(gz.read())
            count = len(records)
        except Exception:
            count = -1
        total_records += max(count, 0)

        att_info = ""
        if with_attachments:
            att_dir = table_dir / "attachments"
            if att_dir.exists():
                att_count = sum(1 for _ in att_dir.rglob("*") if _.is_file())
                att_info = str(att_count)
            else:
                att_info = "0"

        row = [base_name, table_name, str(count) if count >= 0 else "?"]
        if with_attachments:
            row.append(att_info)
        restore_table.add_row(*row)

    console.print()
    console.print(restore_table)
    console.print(f"\n[dim]Total: {total_records} record(s) in {len(restore_targets)} table(s)[/]")

    if not force:
        msg = "[yellow]Records will be INSERTED into existing tables via NocoDB API.[/]\n"
        msg += "[dim]Duplicate records may be created if the table already contains data.[/]\n"
        msg += "[dim]Tables must already exist with a compatible schema.[/]"
        if with_attachments:
            msg += "\n[dim]Attachments will be uploaded to NocoDB storage and linked to records.[/]"

        console.print(Panel(msg, title="Record Restore", border_style="yellow"))

        if not Confirm.ask("[yellow]Proceed with restore?[/]"):
            console.print("[dim]Cancelled.[/]")
            return

    # Resolve table IDs via API
    api_url = settings.nocodb_api_url.rstrip("/")
    json_headers = {"xc-token": settings.nocodb_api_token, "Content-Type": "application/json"}
    upload_headers = {"xc-token": settings.nocodb_api_token}

    with (
        httpx.Client(base_url=api_url, headers=json_headers, timeout=60.0) as client,
        httpx.Client(base_url=api_url, headers=upload_headers, timeout=120.0) as upload_client,
    ):
        # Get bases
        resp = client.get("/api/v2/meta/bases")
        resp.raise_for_status()
        api_bases = {b["title"]: b["id"] for b in resp.json().get("list", [])}

        restored = 0
        att_uploaded = 0
        errors = 0

        for base_name, table_name, records_path, table_dir in restore_targets:
            base_id = api_bases.get(base_name)
            if not base_id:
                console.print(f"[red]  ! Base '{base_name}' not found in NocoDB - skipping[/]")
                errors += 1
                continue

            # Get tables for this base
            resp = client.get(f"/api/v2/meta/bases/{base_id}/tables")
            resp.raise_for_status()
            api_tables = {t["title"]: t["id"] for t in resp.json().get("list", [])}

            table_id = api_tables.get(table_name)
            if not table_id:
                console.print(f"[red]  ! Table '{base_name}/{table_name}' not found in NocoDB - skipping[/]")
                errors += 1
                continue

            # Load records
            try:
                with gzip.open(records_path, "rb") as gz:
                    all_records = json.loads(gz.read())
            except Exception as e:
                console.print(f"[red]  ! Failed to read {records_path}: {e}[/]")
                errors += 1
                continue

            if not all_records:
                console.print(f"[dim]  - {base_name}/{table_name}: no records[/]")
                continue

            # Determine attachment fields from schema
            attachment_fields = []
            schema_file = table_dir / "schema.json"
            if schema_file.exists():
                schema = json.loads(schema_file.read_text())
                attachment_fields = _get_attachment_fields(schema)

            # Remove system fields; only strip attachment fields when --with-attachments
            # is used (they get re-uploaded with new paths). Otherwise keep original
            # references - the files may still exist at their original location.
            system_fields = {"Id", "nc_id", "CreatedAt", "UpdatedAt", "created_at", "updated_at"}
            strip_fields = system_fields
            if with_attachments and attachment_fields:
                strip_fields = strip_fields | set(attachment_fields)

            clean_records = []
            for record in all_records:
                clean = {k: v for k, v in record.items() if k not in strip_fields}
                clean_records.append(clean)

            # Insert in batches of 100
            batch_size = 100
            table_restored = 0
            new_record_ids: list[str | int] = []

            for i in range(0, len(clean_records), batch_size):
                batch = clean_records[i:i + batch_size]
                try:
                    resp = client.post(
                        f"/api/v2/tables/{table_id}/records",
                        json=batch,
                    )
                    resp.raise_for_status()
                    table_restored += len(batch)

                    # Collect new record IDs for attachment linking
                    if with_attachments and attachment_fields:
                        created = resp.json()
                        if isinstance(created, list):
                            for rec in created:
                                new_record_ids.append(rec.get("Id") or rec.get("id", ""))
                        elif isinstance(created, dict) and "list" in created:
                            for rec in created["list"]:
                                new_record_ids.append(rec.get("Id") or rec.get("id", ""))

                except httpx.HTTPStatusError as e:
                    console.print(
                        f"[red]  ! Batch error in {base_name}/{table_name} "
                        f"(records {i}-{i + len(batch)}): {e.response.status_code}[/]"
                    )
                    errors += 1

            restored += table_restored
            console.print(f"[green]  + {base_name}/{table_name}: {table_restored} record(s) restored[/]")

            # Upload attachments and link to new records
            if with_attachments and attachment_fields and new_record_ids:
                storage_path = f"nc/{base_id}/{table_id}"
                up, err = _restore_attachments_for_table(
                    client, upload_client, table_id, table_dir,
                    all_records, attachment_fields, new_record_ids, storage_path,
                )
                att_uploaded += up
                errors += err
                if up > 0:
                    console.print(f"[green]    + {up} attachment(s) uploaded[/]")
                if err > 0:
                    console.print(f"[yellow]    ! {err} attachment error(s)[/]")

    console.print()
    summary = f"{restored} record(s) restored"
    if with_attachments:
        summary += f", {att_uploaded} attachment(s) uploaded"
    if errors > 0:
        console.print(f"[yellow]Completed with {errors} error(s). {summary}.[/]")
    else:
        console.print(f"[green]+ {summary}.[/]")


# -------------------------------------------------------------------------------
# Restore Attachments Command (standalone - after restore-dump)
# -------------------------------------------------------------------------------
@app.command("restore-attachments")
def restore_attachments(
    backup_id: str = typer.Argument(..., help="Backup ID containing the API export with attachments"),
    base: str = typer.Option(None, "--base", "-b", help="Base name (optional, restores all if not set)"),
    table: str = typer.Option(None, "--table", "-t", help="Table name (requires --base)"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Restore attachments from backup into existing NocoDB records.

    Use this after restore-dump to re-upload attachment files.
    Matches records by their original ID (preserved in pg_dump restore).
    """
    settings = Settings()

    if not settings.nocodb_api_token:
        console.print("[red]NOCODB_API_TOKEN is required for attachment restore.[/]")
        raise typer.Exit(1)

    if table and not base:
        console.print("[red]--table requires --base to be specified.[/]")
        raise typer.Exit(1)

    local_path = Path(settings.data_dir) / backup_id
    bases_dir = local_path / "bases"

    if not bases_dir.exists():
        console.print(f"[red]No API export found in backup '{backup_id}'.[/]")
        raise typer.Exit(1)

    # Collect tables with attachments: (base_name, table_name, table_dir, att_count)
    restore_targets: list[tuple[str, str, Path, int]] = []

    for base_path in sorted(bases_dir.iterdir()):
        if not base_path.is_dir():
            continue
        if base and base_path.name != base:
            continue

        tables_dir = base_path / "tables"
        if not tables_dir.exists():
            continue

        for table_path in sorted(tables_dir.iterdir()):
            if not table_path.is_dir():
                continue
            if table and table_path.name != table:
                continue

            att_dir = table_path / "attachments"
            if att_dir.exists():
                att_count = sum(1 for _ in att_dir.rglob("*") if _.is_file())
                if att_count > 0:
                    restore_targets.append((base_path.name, table_path.name, table_path, att_count))

    if not restore_targets:
        console.print("[yellow]No tables with attachments found in backup.[/]")
        raise typer.Exit(1)

    # Show what will be restored
    total_files = 0
    restore_table = Table(title="Attachments to Restore", show_header=True, header_style="bold cyan")
    restore_table.add_column("Base", style="cyan")
    restore_table.add_column("Table", style="yellow")
    restore_table.add_column("Files", justify="right", style="green")

    for base_name, table_name, _, att_count in restore_targets:
        total_files += att_count
        restore_table.add_row(base_name, table_name, str(att_count))

    console.print()
    console.print(restore_table)
    console.print(f"\n[dim]Total: {total_files} attachment file(s) in {len(restore_targets)} table(s)[/]")

    if not force:
        console.print(Panel(
            "[yellow]Attachments will be uploaded to NocoDB storage and linked to existing records.[/]\n"
            "[dim]Records are matched by their original ID (from pg_dump restore).[/]\n"
            "[dim]Existing attachment references on records will be overwritten.[/]",
            title="Attachment Restore",
            border_style="yellow",
        ))

        if not Confirm.ask("[yellow]Proceed with attachment restore?[/]"):
            console.print("[dim]Cancelled.[/]")
            return

    api_url = settings.nocodb_api_url.rstrip("/")
    json_headers = {"xc-token": settings.nocodb_api_token, "Content-Type": "application/json"}
    upload_headers = {"xc-token": settings.nocodb_api_token}

    with (
        httpx.Client(base_url=api_url, headers=json_headers, timeout=60.0) as client,
        httpx.Client(base_url=api_url, headers=upload_headers, timeout=120.0) as upload_client,
    ):
        resp = client.get("/api/v2/meta/bases")
        resp.raise_for_status()
        api_bases = {b["title"]: b["id"] for b in resp.json().get("list", [])}

        total_uploaded = 0
        total_errors = 0

        for base_name, table_name, table_dir, _ in restore_targets:
            base_id = api_bases.get(base_name)
            if not base_id:
                console.print(f"[red]  ! Base '{base_name}' not found in NocoDB - skipping[/]")
                total_errors += 1
                continue

            resp = client.get(f"/api/v2/meta/bases/{base_id}/tables")
            resp.raise_for_status()
            api_tables = {t["title"]: t["id"] for t in resp.json().get("list", [])}

            table_id = api_tables.get(table_name)
            if not table_id:
                console.print(f"[red]  ! Table '{base_name}/{table_name}' not found - skipping[/]")
                total_errors += 1
                continue

            # Load backup records (for attachment metadata and record IDs)
            records_file = table_dir / "records.json.gz"
            if not records_file.exists():
                console.print(f"[yellow]  ! No records.json.gz for '{base_name}/{table_name}' - skipping[/]")
                total_errors += 1
                continue

            try:
                with gzip.open(records_file, "rb") as gz:
                    backup_records = json.loads(gz.read())
            except Exception as e:
                console.print(f"[red]  ! Failed to read records: {e}[/]")
                total_errors += 1
                continue

            # Get attachment fields from schema
            schema_file = table_dir / "schema.json"
            if not schema_file.exists():
                console.print(f"[yellow]  ! No schema.json for '{base_name}/{table_name}' - skipping[/]")
                total_errors += 1
                continue

            schema = json.loads(schema_file.read_text())
            attachment_fields = _get_attachment_fields(schema)

            if not attachment_fields:
                continue

            # Use original record IDs from backup (preserved by pg_dump restore)
            record_ids = []
            for record in backup_records:
                rid = record.get("Id") or record.get("id")
                if rid:
                    record_ids.append(rid)

            if not record_ids:
                console.print(f"[yellow]  ! No record IDs found in backup for '{base_name}/{table_name}'[/]")
                total_errors += 1
                continue

            storage_path = f"nc/{base_id}/{table_id}"
            up, err = _restore_attachments_for_table(
                client, upload_client, table_id, table_dir,
                backup_records, attachment_fields, record_ids, storage_path,
            )
            total_uploaded += up
            total_errors += err

            if up > 0:
                console.print(f"[green]  + {base_name}/{table_name}: {up} attachment(s) uploaded[/]")
            if err > 0:
                console.print(f"[yellow]  ! {base_name}/{table_name}: {err} error(s)[/]")

    console.print()
    if total_errors > 0:
        console.print(f"[yellow]Completed with {total_errors} error(s). {total_uploaded} attachment(s) uploaded.[/]")
    else:
        console.print(f"[green]+ {total_uploaded} attachment(s) restored successfully.[/]")


# -------------------------------------------------------------------------------
# Restore Database Command
# -------------------------------------------------------------------------------
@app.command("restore-dump")
def restore_database_dump(
    backup_id: str = typer.Argument(..., help="Backup ID containing the database dump"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Restore the PostgreSQL database from a pg_dump backup.

    WARNING: This will restore the entire database, overwriting existing data!
    """
    settings = Settings()
    dumper = PostgresDumper(settings)

    # Find dump file
    local_path = Path(settings.data_dir) / backup_id / "database.sql.gz"

    if not local_path.exists():
        console.print(f"[red]Database dump not found in backup '{backup_id}'[/]")
        console.print(f"[dim]Expected file: {local_path}[/]")
        raise typer.Exit(1)

    # Get file size
    dump_size = local_path.stat().st_size

    if not force:
        console.print(Panel(
            f"[bold red]! DATABASE RESTORE[/]\n\n"
            f"Backup: {backup_id}\n"
            f"Dump file: database.sql.gz ({format_size(dump_size)})\n\n"
            "[bold red]WARNING: This will OVERWRITE the entire database![/]\n"
            "[yellow]All existing data will be replaced.[/]",
            title="Dangerous Operation",
            border_style="red",
        ))

        if not Confirm.ask("[bold red]Are you ABSOLUTELY sure?[/]"):
            console.print("[dim]Cancelled.[/]")
            return

        if not Confirm.ask("[red]Type 'yes' again to confirm[/]"):
            console.print("[dim]Cancelled.[/]")
            return

    console.print(f"[yellow]Restoring database from {local_path}...[/]")

    if dumper.restore_database(local_path):
        console.print("[green]+ Database restored successfully[/]")
        console.print()
        console.print("[yellow]IMPORTANT: Restart NocoDB to apply the restored database![/]")
    else:
        console.print("[red]! Database restore failed[/]")
        raise typer.Exit(1)


# -------------------------------------------------------------------------------
# Restore Files Command (NocoDB data directory)
# -------------------------------------------------------------------------------
@app.command("restore-files")
def restore_files(
    backup_id: str = typer.Argument(..., help="Backup ID containing the file backup"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Restore NocoDB data files (uploads/attachments) from backup archive.

    Extracts nocodb-data.tar.gz back to the NocoDB data volume,
    restoring attachment files to their original paths.
    Use this after restore-dump for a complete disaster recovery.

    WARNING: NocoDB must be stopped during this operation!
    """
    settings = Settings()

    archive_path = Path(settings.data_dir) / backup_id / "nocodb-data.tar.gz"

    if not archive_path.exists():
        console.print(f"[red]File backup not found in backup '{backup_id}'[/]")
        console.print(f"[dim]Expected file: {archive_path}[/]")
        console.print("[dim]Was BACKUP_INCLUDE_FILES enabled during backup?[/]")
        raise typer.Exit(1)

    target_path = Path(settings.nocodb_data_path)
    archive_size = archive_path.stat().st_size

    if not force:
        console.print(Panel(
            f"[bold yellow]! FILE RESTORE[/]\n\n"
            f"Backup: {backup_id}\n"
            f"Archive: nocodb-data.tar.gz ({format_size(archive_size)})\n"
            f"Target: {target_path}\n\n"
            "[bold yellow]WARNING: Existing files in the NocoDB data directory will be overwritten![/]\n"
            "[yellow]NocoDB server must be stopped during this operation.[/]",
            title="File Restore",
            border_style="yellow",
        ))

        if not Confirm.ask("[yellow]Proceed with file restore?[/]"):
            console.print("[dim]Cancelled.[/]")
            return

    console.print(f"[yellow]Extracting {format_size(archive_size)} to {target_path}...[/]")

    from backup.file_backup import FileBackup
    file_count, error = FileBackup.restore_files(archive_path, target_path)

    if error:
        console.print(f"[red]! File restore failed: {error}[/]")
        raise typer.Exit(1)

    console.print(f"[green]+ Restored {file_count} file(s) to {target_path}[/]")
    console.print()
    console.print("[yellow]IMPORTANT: Restart NocoDB to pick up the restored files![/]")


# -------------------------------------------------------------------------------
# Schema Helpers
# -------------------------------------------------------------------------------

# System/auto-created column types (NocoDB adds these automatically)
_SYSTEM_UIDTS = {"ID", "CreatedTime", "LastModifiedTime", "CreatedBy", "LastModifiedBy"}

# Virtual column types that reference other tables/columns
_VIRTUAL_UIDTS = {"Links", "LinkToAnotherRecord", "Lookup", "Rollup", "Formula", "Button"}

# Column properties to preserve for table creation
_CREATE_PROPS = {"title", "column_name", "uidt", "dtxp", "dtxs", "rqd", "cdf", "pv", "meta"}


def _prepare_columns_for_create(columns: list[dict]) -> tuple[list[dict], list[str]]:
    """Filter and clean columns from schema.json for table creation via API.

    Args:
        columns: Column definitions from schema.json.

    Returns:
        Tuple of (creatable column dicts, skipped column descriptions).
    """
    creatable = []
    skipped = []

    for col in columns:
        uidt = col.get("uidt", "")
        title = col.get("title", "?")

        # Skip system columns
        if uidt in _SYSTEM_UIDTS or col.get("system"):
            continue

        # Skip primary key (auto-created by NocoDB)
        if col.get("pk"):
            continue

        # Skip virtual/relation columns (need manual recreation)
        if uidt in _VIRTUAL_UIDTS:
            skipped.append(f"{title} ({uidt})")
            continue

        # Build clean column definition with only relevant properties
        clean: dict = {}
        for key in _CREATE_PROPS:
            val = col.get(key)
            if val is not None:
                clean[key] = val

        if "title" not in clean or "uidt" not in clean:
            continue

        # For Select fields: ensure options are included from colOptions
        if uidt in ("SingleSelect", "MultiSelect"):
            col_options = col.get("colOptions")
            if col_options and isinstance(col_options, dict):
                options = col_options.get("options", [])
                if options and not clean.get("dtxp"):
                    # Convert to dtxp format: 'opt1','opt2'
                    clean["dtxp"] = ",".join(
                        f"'{opt['title']}'"
                        for opt in options
                        if isinstance(opt, dict) and "title" in opt
                    )

        creatable.append(clean)

    return creatable, skipped


# -------------------------------------------------------------------------------
# Attachment Helpers
# -------------------------------------------------------------------------------
def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as filename (must match exporter logic)."""
    safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
    safe = safe.replace("<", "_").replace(">", "_").replace('"', "_")
    safe = safe.replace("|", "_").replace("?", "_").replace("*", "_")
    return safe[:100]


def _get_attachment_fields(schema: dict) -> list[str]:
    """Get attachment field names from a table schema."""
    return [
        f["title"] for f in schema.get("columns", [])
        if f.get("uidt") == "Attachment"
    ]


def _upload_attachment(
    client: httpx.Client,
    file_path: Path,
    storage_path: str = "",
) -> list[dict] | None:
    """Upload a file to NocoDB storage API.

    Returns list of uploaded file info dicts, or None on error.
    """
    try:
        with open(file_path, "rb") as f:
            resp = client.post(
                "/api/v2/storage/upload",
                files={"files": (file_path.name, f)},
                params={"path": storage_path} if storage_path else {},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        console.print(f"[dim]    Upload failed for {file_path.name}: {e}[/]")
        return None


def _find_backup_file(attachments_dir: Path, field_name: str, attachment_info: dict) -> Path | None:
    """Find an attachment file in the backup directory.

    Tries multiple strategies to match backup files to attachment metadata,
    since URLs/paths may differ between environments.
    """
    field_dir = attachments_dir / _sanitize_filename(field_name)
    if not field_dir.exists():
        return None

    # Strategy 1: Match by sanitized title
    title = attachment_info.get("title") or ""
    if title:
        target = field_dir / _sanitize_filename(title)
        if target.exists():
            return target

    # Strategy 2: Match by filename from path
    path_name = (attachment_info.get("path") or "").split("/")[-1]
    if path_name:
        target = field_dir / _sanitize_filename(path_name)
        if target.exists():
            return target

    # Strategy 3: Match by filename from URL (URLs change between environments)
    url = attachment_info.get("url") or ""
    if url:
        url_name = url.split("/")[-1].split("?")[0]  # Strip query params
        if url_name:
            target = field_dir / _sanitize_filename(url_name)
            if target.exists():
                return target

    # Strategy 4: Fuzzy match - if only one file in field dir, use it
    # (handles renamed files or encoding differences)
    files = list(field_dir.iterdir())
    if len(files) == 1 and files[0].is_file():
        return files[0]

    return None


def _restore_attachments_for_table(
    client: httpx.Client,
    upload_client: httpx.Client,
    table_id: str,
    table_dir: Path,
    records: list[dict],
    attachment_fields: list[str],
    record_ids: list[str | int],
    storage_path: str = "",
) -> tuple[int, int]:
    """Upload attachments and update records for a single table.

    Args:
        client: httpx client with JSON headers for record updates.
        upload_client: httpx client without Content-Type for file uploads.
        table_id: NocoDB table ID.
        table_dir: Backup table directory.
        records: Original backup records (with attachment data).
        attachment_fields: List of attachment field names.
        record_ids: NocoDB record IDs (same order as records).
        storage_path: NocoDB storage path prefix.

    Returns:
        Tuple of (uploaded_count, error_count).
    """
    attachments_dir = table_dir / "attachments"
    if not attachments_dir.exists():
        return 0, 0

    uploaded = 0
    errors = 0

    for idx, record in enumerate(records):
        if idx >= len(record_ids):
            break

        record_id = record_ids[idx]
        update_fields = {}

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

        # Update record with new attachment URLs
        if update_fields:
            update_fields["Id"] = record_id
            try:
                resp = client.patch(
                    f"/api/v2/tables/{table_id}/records",
                    json=[update_fields],
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                console.print(f"[dim]    Failed to update record {record_id}: {e.response.status_code}[/]")
                errors += 1

    return uploaded, errors


# -------------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------------
def _list_local_backups(settings: Settings) -> list[str]:
    """List local backup IDs."""
    data_dir = Path(settings.data_dir)
    if not data_dir.exists():
        return []

    backups = []
    for path in data_dir.iterdir():
        if path.is_dir() and len(path.name) == 19:
            try:
                datetime.strptime(path.name, "%Y-%m-%d_%H-%M-%S")
                backups.append(path.name)
            except ValueError:
                continue

    return sorted(backups, reverse=True)


def _get_local_backup_size(settings: Settings, backup_id: str) -> int:
    """Get total size of a local backup."""
    backup_path = Path(settings.data_dir) / backup_id
    if not backup_path.exists():
        return 0

    total = 0
    for f in backup_path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


# ===============================================================================
# Entry Point
# ===============================================================================
if __name__ == "__main__":
    app()
