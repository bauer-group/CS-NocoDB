"""
NocoDB Backup - NocoDB API Exporter

Exports NocoDB data via the REST API:
- Bases (workspaces)
- Tables with schema
- Records as JSON
- Attachments (downloaded)

This provides a portable backup format that can be restored
independently of the database dump.
"""

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from config import Settings

from ui.console import backup_logger


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    bases_count: int = 0
    tables_count: int = 0
    records_count: int = 0
    attachments_count: int = 0
    total_size: int = 0
    error: str | None = None


class NocoDBExporter:
    """Exports NocoDB data via the REST API."""

    def __init__(self, settings: "Settings"):
        """Initialize the exporter.

        Args:
            settings: Application settings with API configuration.
        """
        self.settings = settings
        self.api_url = settings.nocodb_api_url.rstrip("/")
        self.api_token = settings.nocodb_api_token
        self.include_records = settings.backup_include_records
        self.include_attachments = settings.backup_include_attachments

        # HTTP client with auth headers
        self.client = httpx.Client(
            base_url=self.api_url,
            headers={
                "xc-token": self.api_token,
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    def _api_get(self, endpoint: str, params: dict | None = None) -> dict | list | None:
        """Make a GET request to the NocoDB API.

        Args:
            endpoint: API endpoint path.
            params: Optional query parameters.

        Returns:
            JSON response or None on error.
        """
        try:
            response = self.client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            backup_logger.error(f"API error {e.response.status_code}: {endpoint}")
            return None
        except Exception as e:
            backup_logger.error(f"API request failed: {e}")
            return None

    def _download_file(self, url: str, target_path: Path) -> bool:
        """Download a file from URL.

        Args:
            url: URL to download.
            target_path: Local path to save file.

        Returns:
            True if download succeeded.
        """
        try:
            # Handle both absolute and relative URLs
            if url.startswith("/"):
                full_url = f"{self.api_url}{url}"
            elif url.startswith("http"):
                full_url = url
            else:
                full_url = f"{self.api_url}/{url}"

            response = self.client.get(full_url, follow_redirects=True)
            response.raise_for_status()

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(response.content)
            return True

        except Exception as e:
            backup_logger.warning(f"Failed to download {url}: {e}")
            return False

    def _get_bases(self) -> list[dict]:
        """Get all bases (workspaces).

        Returns:
            List of base objects.
        """
        # NocoDB API v2: GET /api/v2/meta/bases
        response = self._api_get("/api/v2/meta/bases")
        if response and isinstance(response, dict):
            return response.get("list", [])
        return []

    def _get_tables(self, base_id: str) -> list[dict]:
        """Get all tables in a base.

        Args:
            base_id: Base ID.

        Returns:
            List of table objects.
        """
        # NocoDB API v2: GET /api/v2/meta/bases/{baseId}/tables
        response = self._api_get(f"/api/v2/meta/bases/{base_id}/tables")
        if response and isinstance(response, dict):
            return response.get("list", [])
        return []

    def _get_table_records(self, table_id: str, limit: int = 1000, offset: int = 0) -> tuple[list[dict], int]:
        """Get records from a table.

        Args:
            table_id: Table ID.
            limit: Maximum records per request.
            offset: Offset for pagination.

        Returns:
            Tuple of (records list, total count).
        """
        # NocoDB API v2: GET /api/v2/tables/{tableId}/records
        response = self._api_get(
            f"/api/v2/tables/{table_id}/records",
            params={"limit": limit, "offset": offset}
        )
        if response and isinstance(response, dict):
            return response.get("list", []), response.get("pageInfo", {}).get("totalRows", 0)
        return [], 0

    def _extract_attachments(self, records: list[dict], fields: list[dict]) -> list[dict]:
        """Extract attachment URLs from records.

        Args:
            records: List of record objects.
            fields: List of field definitions.

        Returns:
            List of attachment info dicts.
        """
        attachments = []

        # Find attachment fields
        attachment_fields = [
            f["title"] for f in fields
            if f.get("uidt") == "Attachment"
        ]

        for record in records:
            for field_name in attachment_fields:
                field_value = record.get(field_name)
                if field_value and isinstance(field_value, list):
                    for attachment in field_value:
                        if isinstance(attachment, dict) and "url" in attachment:
                            attachments.append({
                                "url": attachment.get("url"),
                                "path": attachment.get("path"),
                                "title": attachment.get("title", ""),
                                "mimetype": attachment.get("mimetype", ""),
                                "size": attachment.get("size", 0),
                                "field": field_name,
                            })

        return attachments

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize a string to be used as a filename.

        Args:
            name: Original name.

        Returns:
            Safe filename.
        """
        # Replace problematic characters
        safe = name.replace("/", "_").replace("\\", "_").replace(":", "_")
        safe = safe.replace("<", "_").replace(">", "_").replace('"', "_")
        safe = safe.replace("|", "_").replace("?", "_").replace("*", "_")
        return safe[:100]  # Limit length

    def export_all(self, output_dir: Path) -> ExportResult:
        """Export all NocoDB data.

        Args:
            output_dir: Directory to save exported data.

        Returns:
            ExportResult with statistics.
        """
        bases_count = 0
        tables_count = 0
        records_count = 0
        attachments_count = 0
        total_size = 0
        manifest = {
            "version": "1.0",
            "nocodb_url": self.api_url,
            "bases": [],
        }

        try:
            # Get all bases
            bases = self._get_bases()
            backup_logger.debug(f"Found {len(bases)} base(s)")

            for base in bases:
                base_id = base.get("id")
                base_title = base.get("title", "untitled")

                if not base_id:
                    continue

                bases_count += 1
                base_dir = output_dir / "bases" / self._sanitize_filename(base_title)
                base_dir.mkdir(parents=True, exist_ok=True)

                base_manifest = {
                    "id": base_id,
                    "title": base_title,
                    "tables": [],
                }

                # Save base metadata
                meta_file = base_dir / "metadata.json"
                meta_file.write_text(json.dumps(base, indent=2))
                total_size += meta_file.stat().st_size

                # Get tables
                tables = self._get_tables(base_id)
                backup_logger.debug(f"Base '{base_title}': {len(tables)} table(s)")

                for table in tables:
                    table_id = table.get("id")
                    table_title = table.get("title", "untitled")

                    if not table_id:
                        continue

                    tables_count += 1
                    table_dir = base_dir / "tables" / self._sanitize_filename(table_title)
                    table_dir.mkdir(parents=True, exist_ok=True)

                    table_manifest = {
                        "id": table_id,
                        "title": table_title,
                    }

                    # Save table schema
                    schema_file = table_dir / "schema.json"
                    schema_file.write_text(json.dumps(table, indent=2))
                    total_size += schema_file.stat().st_size

                    # Export records if enabled
                    if self.include_records:
                        all_records = []
                        offset = 0
                        limit = 1000

                        while True:
                            records, total = self._get_table_records(table_id, limit, offset)
                            if not records:
                                break
                            all_records.extend(records)
                            offset += len(records)
                            if offset >= total:
                                break

                        records_count += len(all_records)
                        table_manifest["records_count"] = len(all_records)

                        # Save records (gzip-compressed)
                        records_file = table_dir / "records.json.gz"
                        records_data = json.dumps(all_records, indent=2).encode("utf-8")
                        with gzip.open(records_file, "wb", compresslevel=6) as gz:
                            gz.write(records_data)
                        total_size += records_file.stat().st_size

                        # Extract and download attachments if enabled
                        if self.include_attachments:
                            fields = table.get("columns", [])
                            attachments = self._extract_attachments(all_records, fields)

                            if attachments:
                                attachments_dir = table_dir / "attachments"
                                for attachment in attachments:
                                    url = attachment.get("url")
                                    title = attachment.get("title") or attachment.get("path", "").split("/")[-1]

                                    if url and title:
                                        field_dir = attachments_dir / self._sanitize_filename(attachment.get("field", "unknown"))
                                        target = field_dir / self._sanitize_filename(title)

                                        if self._download_file(url, target):
                                            attachments_count += 1
                                            if target.exists():
                                                total_size += target.stat().st_size

                                table_manifest["attachments_count"] = attachments_count

                    base_manifest["tables"].append(table_manifest)

                manifest["bases"].append(base_manifest)

            # Save manifest
            manifest_file = output_dir / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2))
            total_size += manifest_file.stat().st_size

            return ExportResult(
                success=True,
                bases_count=bases_count,
                tables_count=tables_count,
                records_count=records_count,
                attachments_count=attachments_count,
                total_size=total_size,
            )

        except Exception as e:
            backup_logger.error(f"Export failed: {e}")
            return ExportResult(success=False, error=str(e))

        finally:
            self.client.close()
