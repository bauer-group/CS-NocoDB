"""
NocoDB Backup - Configuration Module

Provides type-safe configuration using Pydantic Settings.
All configuration is loaded from environment variables.
"""

from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # Database Connection (REQUIRED)
    # =========================================================================
    # These must match the NocoDB server configuration for DB access

    db_host: str = Field(
        default="database-server",
        alias="DB_HOST",
        description="PostgreSQL host"
    )
    db_port: int = Field(
        default=5432,
        alias="DB_PORT",
        description="PostgreSQL port"
    )
    db_name: str = Field(
        default="nocodb",
        alias="DB_NAME",
        description="PostgreSQL database name"
    )
    db_user: str = Field(
        default="nocodb",
        alias="DB_USER",
        description="PostgreSQL user"
    )
    database_password: str = Field(
        alias="DATABASE_PASSWORD",
        description="PostgreSQL password (REQUIRED)"
    )

    # =========================================================================
    # NocoDB API Access (REQUIRED for API backup)
    # =========================================================================

    nocodb_api_token: Optional[str] = Field(
        default=None,
        alias="NOCODB_API_TOKEN",
        description="NocoDB API Token for API-based backup"
    )
    nocodb_api_url: str = Field(
        default="http://nocodb-server:8080",
        alias="NOCODB_API_URL",
        description="NocoDB API URL (internal)"
    )

    # =========================================================================
    # Backup Configuration
    # =========================================================================

    backup_retention_count: int = Field(
        default=30,
        ge=1,
        description="Number of backup copies to retain (locally and in S3)"
    )
    backup_database_dump: bool = Field(
        default=True,
        description="Include PostgreSQL database dump (pg_dump) in backup"
    )
    backup_database_dump_timeout: int = Field(
        default=1800,
        ge=60,
        le=7200,
        description="Timeout for pg_dump in seconds (default: 1800 = 30 minutes)"
    )
    backup_api_export: bool = Field(
        default=True,
        description="Export data via NocoDB API"
    )
    backup_include_records: bool = Field(
        default=True,
        description="Include table records in API export"
    )
    backup_include_attachments: bool = Field(
        default=True,
        description="Download attachments in API export. Set to false if attachments are stored on S3 (NC_S3_BUCKET_NAME)."
    )
    backup_include_files: bool = Field(
        default=True,
        description="Include NocoDB data files (uploads/attachments) as tar.gz archive"
    )
    backup_delete_local_after_s3: bool = Field(
        default=False,
        description="Delete local backup after successful S3 upload"
    )
    nocodb_data_path: str = Field(
        default="/nocodb-data",
        description="Path to NocoDB data volume mount (for file backup/restore)"
    )

    # =========================================================================
    # Scheduler Configuration
    # =========================================================================

    backup_schedule_enabled: bool = Field(
        default=True,
        description="Enable scheduled backups"
    )
    backup_schedule_mode: Literal["cron", "interval"] = Field(
        default="cron",
        description="Schedule mode: cron (fixed time) or interval (every n hours)"
    )
    backup_schedule_hour: int = Field(
        default=5,
        ge=0,
        le=23,
        description="Hour to run backup (0-23, for cron mode)"
    )
    backup_schedule_minute: int = Field(
        default=15,
        ge=0,
        le=59,
        description="Minute to run backup (0-59)"
    )
    backup_schedule_day_of_week: str = Field(
        default="*",
        description="Day of week for cron mode (0=Mon, 6=Sun, * for daily)"
    )
    backup_schedule_interval_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Hours between backups (for interval mode, 1-168)"
    )

    @field_validator("backup_schedule_day_of_week")
    @classmethod
    def validate_day_of_week(cls, v: str) -> str:
        """Validate day_of_week is valid cron format."""
        if v == "*":
            return v
        try:
            days = [int(d.strip()) for d in v.split(",")]
            if not all(0 <= d <= 6 for d in days):
                raise ValueError("Days must be 0-6")
            return v
        except ValueError:
            raise ValueError("day_of_week must be '*' or comma-separated days 0-6")

    # =========================================================================
    # S3/MinIO Configuration (OPTIONAL)
    # =========================================================================
    # If not configured, backups are stored locally only

    s3_endpoint_url: Optional[str] = Field(
        default=None,
        description="S3-compatible endpoint URL (None for AWS S3)"
    )
    s3_bucket: Optional[str] = Field(
        default=None,
        description="Bucket name for backups"
    )
    s3_access_key: Optional[str] = Field(
        default=None,
        description="S3 access key"
    )
    s3_secret_key: Optional[str] = Field(
        default=None,
        description="S3 secret key"
    )
    s3_region: str = Field(
        default="eu-north-1",
        description="S3 region"
    )
    s3_prefix: str = Field(
        default="nocodb-backup",
        description="Prefix/folder in S3 bucket"
    )
    s3_multipart_threshold: int = Field(
        default=100 * 1024 * 1024,
        description="File size threshold for multipart upload (default: 100MB)"
    )
    s3_multipart_chunk_size: int = Field(
        default=50 * 1024 * 1024,
        description="Chunk size for multipart upload (default: 50MB)"
    )

    @property
    def s3_enabled(self) -> bool:
        """Check if S3 is configured with all required credentials."""
        return bool(
            self.s3_bucket
            and self.s3_access_key
            and self.s3_secret_key
        )

    # =========================================================================
    # Alerting Configuration (OPTIONAL)
    # =========================================================================

    alert_enabled: bool = Field(
        default=False,
        description="Enable alerting system"
    )
    alert_level: Literal["errors", "warnings", "all"] = Field(
        default="warnings",
        description="Alert level: errors, warnings, or all"
    )
    alert_channels: str = Field(
        default="",
        description="Comma-separated list of alert channels: email,webhook,teams"
    )

    # SMTP Email Configuration
    smtp_host: Optional[str] = Field(
        default=None,
        description="SMTP server hostname"
    )
    smtp_port: int = Field(
        default=587,
        description="SMTP server port"
    )
    smtp_tls: bool = Field(
        default=True,
        description="Use TLS/STARTTLS for SMTP"
    )
    smtp_ssl: bool = Field(
        default=False,
        description="Use SSL for SMTP (port 465)"
    )
    smtp_user: Optional[str] = Field(
        default=None,
        description="SMTP username"
    )
    smtp_password: Optional[str] = Field(
        default=None,
        alias="SMTP_PASS",
        description="SMTP password"
    )
    smtp_from: Optional[str] = Field(
        default=None,
        alias="SMTP_SENDER",
        description="Email sender address"
    )
    smtp_from_name: str = Field(
        default="NocoDB Backup",
        description="Email sender display name"
    )
    smtp_to: str = Field(
        default="",
        description="Comma-separated list of recipient email addresses"
    )

    # Generic Webhook Configuration
    webhook_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for generic JSON POST alerts"
    )
    webhook_secret: Optional[str] = Field(
        default=None,
        description="Optional secret for webhook HMAC signature"
    )

    # Microsoft Teams Configuration
    teams_webhook_url: Optional[str] = Field(
        default=None,
        description="Microsoft Teams Webhook URL"
    )

    @field_validator("alert_channels")
    @classmethod
    def validate_alert_channels(cls, v: str) -> str:
        """Validate alert channels."""
        if not v:
            return v
        valid_channels = {"email", "webhook", "teams"}
        channels = [c.strip().lower() for c in v.split(",") if c.strip()]
        invalid = set(channels) - valid_channels
        if invalid:
            raise ValueError(f"Invalid alert channels: {invalid}. Valid: {valid_channels}")
        return ",".join(channels)

    def get_alert_channels(self) -> list[str]:
        """Get list of active alert channels."""
        if not self.alert_channels:
            return []
        return [c.strip().lower() for c in self.alert_channels.split(",") if c.strip()]

    def get_smtp_recipients(self) -> list[str]:
        """Get list of SMTP recipients."""
        if not self.smtp_to:
            return []
        return [r.strip() for r in self.smtp_to.split(",") if r.strip()]

    # =========================================================================
    # Application Configuration
    # =========================================================================

    instance_name: str = Field(
        default="nocodb",
        description="Instance name for identification in alerts"
    )
    tz: str = Field(
        default="Etc/UTC",
        alias="TZ",
        description="Timezone for logging"
    )
    log_level: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR)"
    )
    data_dir: str = Field(
        default="/data",
        description="Directory for local backup data"
    )
