#!/usr/bin/env python3
"""
NocoDB Backup - Main Entry Point

Automated backup of NocoDB data to local storage and S3.
"""

import shutil
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from config import Settings
from backup.file_backup import FileBackup
from backup.nocodb_exporter import NocoDBExporter
from backup.pg_dump import PostgresDumper
from storage.s3_client import S3Storage
from alerting.manager import AlertManager
from scheduler import setup_scheduler, run_scheduler
from ui.console import (
    backup_logger,
    console,
    format_size,
    print_banner,
    print_completion,
    print_error,
    print_info,
    print_success,
    print_summary,
    print_warning,
    setup_logging,
)


class ShutdownHandler:
    """Handles graceful shutdown on SIGTERM/SIGINT."""

    def __init__(self):
        self._shutdown_requested = threading.Event()

    def request_shutdown(self, signum: int, frame) -> None:
        """Signal handler for shutdown requests."""
        console.print("\n[yellow]Shutdown requested...[/]")
        self._shutdown_requested.set()

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested.is_set()


shutdown_handler = ShutdownHandler()


def run_backup(settings: Settings, db_only: bool = False) -> bool:
    """Execute a backup of NocoDB data.

    Args:
        settings: Application settings.
        db_only: If True, only run database dump (skip API export).

    Returns:
        True if backup completed successfully.
    """
    start_time = time.time()
    backup_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_dir = Path(settings.data_dir) / backup_id

    # Initialize components
    alert_manager = AlertManager(settings)

    # Initialize S3 if configured
    s3_storage = None
    if settings.s3_enabled:
        s3_storage = S3Storage(settings)

    # Statistics
    bases_count = 0
    tables_count = 0
    records_count = 0
    total_size = 0
    errors: list[str] = []

    try:
        # Print banner
        print_banner(backup_id)

        # Create backup directory
        backup_dir.mkdir(parents=True, exist_ok=True)

        # ---------------------------------------------------------------------
        # PostgreSQL Database Dump (optional but enabled by default)
        # ---------------------------------------------------------------------
        dump_file = None
        dump_size = None
        if settings.backup_database_dump:
            print_info("Creating database dump...")
            dumper = PostgresDumper(settings)
            dump_result = dumper.dump_database(backup_dir)

            if dump_result.success:
                dump_file = dump_result.path
                dump_size = dump_result.size
                total_size += dump_result.size
                print_success(f"Database dump created ({format_size(dump_result.size)})")
            else:
                errors.append(f"Database dump failed: {dump_result.error}")
                print_warning(f"Database dump failed: {dump_result.error}")

        # ---------------------------------------------------------------------
        # NocoDB Data Files (uploads/attachments tar.gz)
        # ---------------------------------------------------------------------
        file_backup_size = None
        if settings.backup_include_files and not db_only:
            print_info("Backing up NocoDB data files...")
            file_backup = FileBackup(settings.nocodb_data_path)
            file_result = file_backup.backup_files(backup_dir)

            if file_result.success and file_result.file_count > 0:
                file_backup_size = file_result.size
                total_size += file_result.size
                print_success(
                    f"Data files archived ({file_result.file_count} file(s), "
                    f"{format_size(file_result.size)})"
                )
            elif file_result.success:
                print_info("No data files found in NocoDB data directory")
            else:
                errors.append(f"File backup failed: {file_result.error}")
                print_warning(f"File backup failed: {file_result.error}")

        # ---------------------------------------------------------------------
        # NocoDB API Export (optional)
        # ---------------------------------------------------------------------
        if settings.backup_api_export and not db_only:
            if not settings.nocodb_api_token:
                print_warning("API export enabled but NOCODB_API_TOKEN not set - skipping")
                errors.append("API export skipped: NOCODB_API_TOKEN not configured")
            else:
                print_info("Exporting via NocoDB API...")
                exporter = NocoDBExporter(settings)
                export_result = exporter.export_all(backup_dir)

                if export_result.success:
                    bases_count = export_result.bases_count
                    tables_count = export_result.tables_count
                    records_count = export_result.records_count
                    total_size += export_result.total_size
                    print_success(
                        f"Exported {bases_count} base(s), "
                        f"{tables_count} table(s), "
                        f"{records_count} record(s)"
                    )
                else:
                    errors.append(f"API export failed: {export_result.error}")
                    print_warning(f"API export failed: {export_result.error}")

        # ---------------------------------------------------------------------
        # Upload to S3 (if configured)
        # ---------------------------------------------------------------------
        s3_path = None
        if s3_storage:
            print_info("Uploading to S3...")

            try:
                if not s3_storage.ensure_bucket_exists():
                    errors.append("Failed to access S3 bucket")
                    print_warning("Failed to access S3 bucket")
                else:
                    # Upload entire backup directory
                    s3_storage.upload_backup(backup_dir, backup_id)

                    # Include endpoint URL for clarity in notifications
                    if s3_storage.endpoint_url:
                        s3_path = f"{s3_storage.endpoint_url}/{s3_storage.bucket}/{s3_storage.prefix}/{backup_id}/"
                    else:
                        s3_path = f"s3://{s3_storage.bucket}/{s3_storage.prefix}/{backup_id}/"
                    print_success(f"Uploaded to {s3_path}")

                    # Delete local files after successful S3 upload (optional)
                    if settings.backup_delete_local_after_s3:
                        shutil.rmtree(backup_dir)
                        backup_logger.debug(f"Deleted local backup: {backup_dir}")
                        print_info("Deleted local backup (S3 only)")

            except Exception as e:
                errors.append(f"S3 upload failed: {e}")
                print_warning(f"S3 upload failed: {e}")

        # ---------------------------------------------------------------------
        # Cleanup Old Backups
        # ---------------------------------------------------------------------
        print_info("Cleaning up old backups...")

        # Local cleanup
        local_deleted = cleanup_local_backups(settings)
        if local_deleted > 0:
            backup_logger.debug(f"Deleted {local_deleted} old local backup(s)")

        # S3 cleanup
        if s3_storage:
            s3_deleted = s3_storage.cleanup_old_backups()
            if s3_deleted > 0:
                backup_logger.debug(f"Deleted {s3_deleted} old S3 backup(s)")

        # ---------------------------------------------------------------------
        # Print Summary
        # ---------------------------------------------------------------------
        duration = time.time() - start_time
        local_path = str(backup_dir) if backup_dir.exists() else None

        print_summary(
            bases_count=bases_count,
            tables_count=tables_count,
            records_count=records_count,
            total_size=total_size,
            duration=duration,
            local_path=local_path,
            s3_path=s3_path,
            database_dump_size=dump_size,
            file_backup_size=file_backup_size,
            errors=errors if errors else None,
        )

        success = len(errors) == 0
        print_completion(success)

        # ---------------------------------------------------------------------
        # Send Alerts
        # ---------------------------------------------------------------------
        if success:
            alert_results = alert_manager.send_backup_success(
                backup_id=backup_id,
                bases_count=bases_count,
                tables_count=tables_count,
                records_count=records_count,
                total_size=total_size,
                duration_seconds=duration,
                local_path=local_path,
                s3_path=s3_path,
                database_dump_size=dump_size or 0,
                file_backup_size=file_backup_size or 0,
            )
        elif bases_count > 0 or dump_file:
            # Partial success
            alert_results = alert_manager.send_backup_warning(
                backup_id=backup_id,
                message="Backup completed with some errors.",
                bases_count=bases_count,
                tables_count=tables_count,
                records_count=records_count,
                total_size=total_size,
                duration_seconds=duration,
                error_messages=errors,
                local_path=local_path,
                s3_path=s3_path,
                database_dump_size=dump_size or 0,
                file_backup_size=file_backup_size or 0,
            )
        else:
            # Complete failure
            alert_results = alert_manager.send_backup_error(
                backup_id=backup_id,
                message="Backup failed.",
                error_messages=errors,
                duration_seconds=duration,
            )

        # Show alert results
        for channel, sent in alert_results.items():
            if sent:
                print_success(f"Alert sent via {channel}")
            else:
                print_warning(f"Alert failed via {channel}")

        return success

    except Exception as e:
        print_error("Backup failed", e)
        duration = time.time() - start_time

        # Send error alert
        alert_manager.send_backup_error(
            backup_id=backup_id,
            message=f"Backup failed with exception: {e}",
            error_messages=[str(e)],
            duration_seconds=duration,
        )

        return False


def _get_dir_size(path: Path) -> int:
    """Get total size of all files in a directory."""
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def cleanup_local_backups(settings: Settings) -> int:
    """Remove old local backups exceeding retention count."""
    data_dir = Path(settings.data_dir)
    retention = settings.backup_retention_count

    # List backup directories (format: YYYY-MM-DD_HH-MM-SS)
    backups = []
    for path in data_dir.iterdir():
        if path.is_dir() and len(path.name) == 19:  # YYYY-MM-DD_HH-MM-SS
            try:
                datetime.strptime(path.name, "%Y-%m-%d_%H-%M-%S")
                backups.append(path)
            except ValueError:
                continue

    # Sort by name (newest first)
    backups.sort(key=lambda p: p.name, reverse=True)

    # Delete oldest backups exceeding retention
    deleted = 0
    if len(backups) > retention:
        for backup in backups[retention:]:
            try:
                shutil.rmtree(backup)
                deleted += 1
            except Exception as e:
                backup_logger.warning(f"Failed to delete {backup}: {e}")

    return deleted


def main() -> int:
    """Main entry point."""
    # Check for CLI mode
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from cli import app
        app()
        return 0

    # Register signal handlers
    signal.signal(signal.SIGTERM, shutdown_handler.request_shutdown)
    signal.signal(signal.SIGINT, shutdown_handler.request_shutdown)

    try:
        # Load settings
        settings = Settings()

        # Setup logging
        setup_logging(settings.log_level)

        # Print startup info
        console.print("[bold]NocoDB Backup Service[/]")
        console.print()

        # Show storage mode
        if settings.s3_enabled:
            console.print(f"[dim]Storage: Local ({settings.data_dir}) + S3 ({settings.s3_bucket})[/]")
        else:
            console.print(f"[dim]Storage: Local only ({settings.data_dir})[/]")
            console.print("[yellow]Hint: Configure S3_* variables to enable cloud backup[/]")

        console.print()

        # Validate alerting configuration
        if settings.alert_enabled:
            alert_manager = AlertManager(settings)
            config_errors = alert_manager.get_configuration_errors()
            if config_errors:
                console.print("[yellow]Alerting configuration warnings:[/]")
                for error in config_errors:
                    console.print(f"  [yellow]- {error}[/]")
                console.print()

        # Check for --now flag (immediate execution)
        if "--now" in sys.argv:
            db_only = "--db-only" in sys.argv
            console.print("[bold]Running backup immediately...[/]")
            console.print()
            success = run_backup(settings, db_only=db_only)
            return 0 if success else 1

        # Check if scheduler is disabled
        if not settings.backup_schedule_enabled:
            console.print("[yellow]Scheduler is disabled (BACKUP_SCHEDULE_ENABLED=false)[/]")
            console.print("[dim]Use --now flag to run a single backup[/]")
            return 0

        # Start scheduler
        scheduler = setup_scheduler(settings, lambda: run_backup(settings))
        run_scheduler(scheduler)

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/]")
        return 0

    except Exception as e:
        print_error("Failed to start", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
