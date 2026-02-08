"""
NocoDB Backup - PostgreSQL Database Dump

Creates a full database dump using pg_dump for complete disaster recovery.
The dump is compressed with gzip to save space.

This creates a complete PostgreSQL backup including:
- All tables (NocoDB metadata, user data, etc.)
- Database schema
- Sequences and their current values

This provides an additional recovery option if API-based restore fails
or if you need to restore the entire database state.
"""

import gzip
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings

from ui.console import backup_logger


@dataclass
class DumpResult:
    """Result of a database dump operation."""

    success: bool
    path: Path | None = None
    size: int = 0
    error: str | None = None


class PostgresDumper:
    """Creates PostgreSQL database dumps using pg_dump."""

    def __init__(self, settings: "Settings"):
        """Initialize the dumper.

        Args:
            settings: Application settings with database configuration.
        """
        self.settings = settings

    def dump_database(self, output_dir: Path) -> DumpResult:
        """Create a compressed PostgreSQL dump.

        Creates a dump file named 'database.sql.gz' in the output directory.
        Uses plain SQL format with compression for maximum compatibility.

        Args:
            output_dir: Directory to save the dump file.

        Returns:
            DumpResult with success status and file path.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        dump_file = output_dir / "database.sql.gz"

        # Build pg_dump command
        cmd = [
            "pg_dump",
            "--host", self.settings.db_host,
            "--port", str(self.settings.db_port),
            "--username", self.settings.db_user,
            "--dbname", self.settings.db_name,
            "--no-password",  # Use PGPASSWORD env var
            "--format", "plain",  # SQL format for readability
            "--no-owner",  # Don't include ownership commands
            "--no-acl",  # Don't include access privileges
            "--verbose",
        ]

        # Set password via environment
        env = {
            **os.environ,
            "PGPASSWORD": self.settings.database_password,
        }

        try:
            backup_logger.debug(f"Running pg_dump for {self.settings.db_name}...")

            # Run pg_dump and capture output
            timeout = self.settings.backup_database_dump_timeout
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                error_msg = result.stderr.decode("utf-8", errors="replace").strip()
                backup_logger.error(f"pg_dump failed: {error_msg}")
                return DumpResult(success=False, error=error_msg)

            # Compress the output with gzip
            with gzip.open(dump_file, "wb", compresslevel=6) as f:
                f.write(result.stdout)

            # Get file size
            size = dump_file.stat().st_size

            backup_logger.debug(
                f"Database dump created: {dump_file} ({size / (1024*1024):.1f} MB)"
            )

            return DumpResult(success=True, path=dump_file, size=size)

        except subprocess.TimeoutExpired:
            timeout_min = self.settings.backup_database_dump_timeout // 60
            backup_logger.error(f"pg_dump timed out after {timeout_min} minutes")
            return DumpResult(success=False, error=f"Database dump timed out after {timeout_min} minutes")

        except Exception as e:
            backup_logger.error(f"pg_dump error: {e}")
            return DumpResult(success=False, error=str(e))

    def restore_database(self, dump_file: Path) -> bool:
        """Restore database from a dump file.

        WARNING: This will overwrite ALL data in the target database!
        Use with caution.

        Args:
            dump_file: Path to the dump file (.sql.gz or .sql)

        Returns:
            True if restore succeeded.
        """
        if not dump_file.exists():
            backup_logger.error(f"Dump file not found: {dump_file}")
            return False

        backup_logger.debug(f"Restoring database from {dump_file}...")

        # Set password via environment
        env = {
            **os.environ,
            "PGPASSWORD": self.settings.database_password,
        }

        try:
            # Decompress if gzipped
            if dump_file.suffix == ".gz":
                with gzip.open(dump_file, "rb") as f:
                    sql_data = f.read()
            else:
                sql_data = dump_file.read_bytes()

            # Run psql to restore
            cmd = [
                "psql",
                "--host", self.settings.db_host,
                "--port", str(self.settings.db_port),
                "--username", self.settings.db_user,
                "--dbname", self.settings.db_name,
                "--no-password",
                "--quiet",
            ]

            result = subprocess.run(
                cmd,
                env=env,
                input=sql_data,
                capture_output=True,
                timeout=3600,  # 1 hour timeout for large databases
            )

            if result.returncode != 0:
                error_msg = result.stderr.decode("utf-8", errors="replace").strip()
                backup_logger.error(f"Database restore failed: {error_msg}")
                return False

            backup_logger.debug("Database restored successfully")
            return True

        except subprocess.TimeoutExpired:
            backup_logger.error("Database restore timed out after 1 hour")
            return False

        except Exception as e:
            backup_logger.error(f"Database restore error: {e}")
            return False
