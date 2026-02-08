"""
NocoDB Backup - File Backup Module

Creates a tar.gz archive of the NocoDB data directory (uploads/attachments).
This provides a 1:1 copy of the filesystem that can be restored directly,
preserving the original paths referenced in the database.
"""

import tarfile
from dataclasses import dataclass
from pathlib import Path

from ui.console import backup_logger


@dataclass
class FileBackupResult:
    """Result of a file backup operation."""

    success: bool
    path: Path | None = None
    size: int = 0
    file_count: int = 0
    error: str | None = None


class FileBackup:
    """Creates tar.gz archives of NocoDB data files."""

    ARCHIVE_NAME = "nocodb-data.tar.gz"

    def __init__(self, nocodb_data_path: str):
        self.data_path = Path(nocodb_data_path)

    def backup_files(self, backup_dir: Path) -> FileBackupResult:
        """Create a tar.gz archive of the NocoDB data directory.

        Args:
            backup_dir: Directory to save the archive.

        Returns:
            FileBackupResult with statistics.
        """
        if not self.data_path.exists():
            backup_logger.warning(
                f"NocoDB data path '{self.data_path}' not found - skipping file backup"
            )
            return FileBackupResult(
                success=False,
                error=f"Path not found: {self.data_path}",
            )

        archive_path = backup_dir / self.ARCHIVE_NAME
        file_count = 0

        try:
            with tarfile.open(archive_path, "w:gz", compresslevel=6) as tar:
                for file_path in sorted(self.data_path.rglob("*")):
                    if file_path.is_file():
                        arcname = str(file_path.relative_to(self.data_path))
                        tar.add(str(file_path), arcname=arcname)
                        file_count += 1

            if file_count == 0:
                archive_path.unlink(missing_ok=True)
                backup_logger.debug("No files found in NocoDB data directory")
                return FileBackupResult(success=True, file_count=0)

            size = archive_path.stat().st_size
            backup_logger.debug(
                f"File backup: {file_count} file(s), {size / (1024*1024):.1f} MB"
            )

            return FileBackupResult(
                success=True,
                path=archive_path,
                size=size,
                file_count=file_count,
            )

        except Exception as e:
            backup_logger.error(f"File backup failed: {e}")
            archive_path.unlink(missing_ok=True)
            return FileBackupResult(success=False, error=str(e))

    @staticmethod
    def restore_files(archive_path: Path, target_path: Path) -> tuple[int, str | None]:
        """Extract a file backup archive to the target directory.

        Args:
            archive_path: Path to nocodb-data.tar.gz.
            target_path: Directory to extract to (NocoDB data path).

        Returns:
            Tuple of (file_count, error_message).
        """
        try:
            target_path.mkdir(parents=True, exist_ok=True)

            with tarfile.open(archive_path, "r:gz") as tar:
                # Filter out unsafe paths (path traversal prevention)
                safe_members = []
                for member in tar.getmembers():
                    if member.name.startswith("/") or ".." in member.name.split("/"):
                        backup_logger.warning(f"Skipping unsafe path: {member.name}")
                        continue
                    safe_members.append(member)

                tar.extractall(path=target_path, members=safe_members)
                file_count = sum(1 for m in safe_members if m.isfile())

            return file_count, None

        except Exception as e:
            return 0, str(e)
