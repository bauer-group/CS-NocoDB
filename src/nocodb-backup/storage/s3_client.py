"""
NocoDB Backup - S3 Storage Module

Provides S3-compatible storage operations for backup upload and retention management.
This module is optional - if S3 is not configured, backups are stored locally only.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from config import Settings

from ui.console import backup_logger


class MultipartUploader:
    """Handles multipart uploads with equal-sized chunks for S3 compatibility."""

    def __init__(
        self,
        s3_client,
        bucket: str,
        chunk_size: int,
        threshold: int,
    ):
        """Initialize multipart uploader."""
        self.s3 = s3_client
        self.bucket = bucket
        self.chunk_size = chunk_size
        self.threshold = threshold

    def upload_file(self, local_path: Path, key: str) -> None:
        """Upload file using multipart upload if above threshold."""
        file_size = local_path.stat().st_size

        if file_size < self.threshold:
            self.s3.upload_file(str(local_path), self.bucket, key)
            return

        backup_logger.debug(
            f"Using multipart upload for {local_path.name} "
            f"({file_size / (1024*1024):.1f} MB)"
        )

        response = self.s3.create_multipart_upload(Bucket=self.bucket, Key=key)
        upload_id = response["UploadId"]

        parts = []
        part_number = 1

        try:
            with open(local_path, "rb") as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break

                    part_response = self.s3.upload_part(
                        Bucket=self.bucket,
                        Key=key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=chunk,
                    )

                    parts.append({
                        "PartNumber": part_number,
                        "ETag": part_response["ETag"],
                    })

                    part_number += 1

            self.s3.complete_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

        except Exception as e:
            backup_logger.error(f"Multipart upload failed, aborting: {e}")
            self.s3.abort_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
            )
            raise


class S3Storage:
    """S3-compatible storage client for backup operations."""

    def __init__(self, settings: "Settings"):
        """Initialize S3 storage client."""
        self.settings = settings
        self.bucket = settings.s3_bucket or ""
        self.prefix = settings.s3_prefix
        self.retention = settings.backup_retention_count
        self.endpoint_url = settings.s3_endpoint_url

        # Configure boto3 for S3-compatible endpoints
        boto_config = BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        )

        self.s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=boto_config,
        )

        self.uploader = MultipartUploader(
            s3_client=self.s3,
            bucket=self.bucket,
            chunk_size=settings.s3_multipart_chunk_size,
            threshold=settings.s3_multipart_threshold,
        )

    def upload_file(self, local_path: Path, backup_id: str, subpath: str = "") -> str:
        """Upload a file to S3.

        Args:
            local_path: Path to the local file.
            backup_id: Backup identifier (timestamp).
            subpath: Optional subpath within the backup.

        Returns:
            S3 key of the uploaded file.
        """
        if subpath:
            key = f"{self.prefix}/{backup_id}/{subpath}/{local_path.name}"
        else:
            key = f"{self.prefix}/{backup_id}/{local_path.name}"

        backup_logger.debug(f"Uploading {local_path.name} to s3://{self.bucket}/{key}")

        try:
            self.uploader.upload_file(local_path, key)
            return key
        except ClientError as e:
            backup_logger.error(f"Failed to upload {local_path}: {e}")
            raise

    def upload_backup(self, backup_dir: Path, backup_id: str) -> int:
        """Upload entire backup directory to S3.

        Args:
            backup_dir: Local backup directory.
            backup_id: Backup identifier.

        Returns:
            Number of files uploaded.
        """
        if not backup_dir.exists():
            return 0

        uploaded = 0
        for file_path in backup_dir.rglob("*"):
            if file_path.is_file():
                # Calculate relative path within backup
                rel_path = file_path.relative_to(backup_dir)
                subpath = str(rel_path.parent) if rel_path.parent != Path(".") else ""

                self.upload_file(file_path, backup_id, subpath)
                uploaded += 1

        return uploaded

    def download_file(self, backup_id: str, filename: str, local_path: Path, subpath: str = "") -> bool:
        """Download a file from S3."""
        if subpath:
            key = f"{self.prefix}/{backup_id}/{subpath}/{filename}"
        else:
            key = f"{self.prefix}/{backup_id}/{filename}"

        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            self.s3.download_file(self.bucket, key, str(local_path))
            backup_logger.debug(f"Downloaded s3://{self.bucket}/{key} to {local_path}")
            return True
        except ClientError as e:
            backup_logger.error(f"Failed to download {key}: {e}")
            return False

    def download_backup(self, backup_id: str, local_dir: Path) -> int:
        """Download entire backup from S3 to local directory.

        Args:
            backup_id: Backup identifier.
            local_dir: Local directory to save files.

        Returns:
            Number of files downloaded.
        """
        prefix = f"{self.prefix}/{backup_id}/"
        downloaded = 0

        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    # Calculate relative path within backup
                    rel_path = key[len(prefix):]
                    if not rel_path:
                        continue

                    local_path = local_dir / rel_path
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    self.s3.download_file(self.bucket, key, str(local_path))
                    downloaded += 1

            backup_logger.debug(f"Downloaded {downloaded} files from S3 backup {backup_id}")
            return downloaded

        except ClientError as e:
            backup_logger.error(f"Failed to download backup {backup_id}: {e}")
            return downloaded

    def list_backups(self) -> list[str]:
        """List all backup IDs in S3."""
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=f"{self.prefix}/",
                Delimiter="/",
            )

            backup_ids = []
            for prefix_obj in response.get("CommonPrefixes", []):
                prefix = prefix_obj.get("Prefix", "")
                parts = prefix.strip("/").split("/")
                if len(parts) >= 2:
                    backup_ids.append(parts[-1])

            return sorted(backup_ids, reverse=True)

        except ClientError as e:
            backup_logger.error(f"Failed to list backups: {e}")
            return []

    def get_backup_size(self, backup_id: str) -> int:
        """Get total size of a backup in bytes."""
        try:
            prefix = f"{self.prefix}/{backup_id}/"
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
            )

            total_size = 0
            for obj in response.get("Contents", []):
                total_size += obj.get("Size", 0)

            return total_size

        except ClientError:
            return 0

    def delete_backup(self, backup_id: str) -> int:
        """Delete a backup from S3."""
        try:
            prefix = f"{self.prefix}/{backup_id}/"
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
            )

            objects = response.get("Contents", [])
            if not objects:
                return 0

            delete_keys = [{"Key": obj["Key"]} for obj in objects]
            self.s3.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": delete_keys, "Quiet": True},
            )

            backup_logger.debug(f"Deleted backup {backup_id} ({len(delete_keys)} objects)")
            return len(delete_keys)

        except ClientError as e:
            backup_logger.error(f"Failed to delete backup {backup_id}: {e}")
            return 0

    def cleanup_old_backups(self) -> int:
        """Remove backups older than the retention count."""
        backups = self.list_backups()
        deleted_count = 0

        if len(backups) <= self.retention:
            backup_logger.debug(
                f"No S3 cleanup needed: {len(backups)} backups <= {self.retention} retention"
            )
            return 0

        to_delete = backups[self.retention:]
        backup_logger.debug(f"Cleaning up {len(to_delete)} old S3 backup(s)")

        for backup_id in to_delete:
            self.delete_backup(backup_id)
            deleted_count += 1

        return deleted_count

    def ensure_bucket_exists(self) -> bool:
        """Ensure the target bucket exists."""
        try:
            self.s3.head_bucket(Bucket=self.bucket)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                backup_logger.debug(f"Bucket {self.bucket} does not exist, creating...")
                try:
                    self.s3.create_bucket(Bucket=self.bucket)
                    return True
                except ClientError as create_error:
                    backup_logger.error(f"Failed to create bucket: {create_error}")
                    return False
            else:
                backup_logger.error(f"Error checking bucket: {e}")
                return False
