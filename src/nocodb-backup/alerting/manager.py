"""
NocoDB Backup - Alert Manager
"""

from typing import TYPE_CHECKING

from alerting.base import BackupAlert
from alerting.email_alerter import EmailAlerter
from alerting.teams_alerter import TeamsAlerter
from alerting.webhook_alerter import WebhookAlerter
from ui.console import backup_logger, format_size

if TYPE_CHECKING:
    from config import Settings


class AlertManager:
    """Manages alert channels and dispatches alerts."""

    def __init__(self, settings: "Settings"):
        """Initialize alert manager.

        Args:
            settings: Application settings.
        """
        self.settings = settings
        self.enabled = settings.alert_enabled
        self.level = settings.alert_level

        # Initialize alerters
        self.alerters = {
            "email": EmailAlerter(settings),
            "teams": TeamsAlerter(settings),
            "webhook": WebhookAlerter(settings),
        }

        self.active_channels = settings.get_alert_channels()

    def should_send_alert(self, status: str) -> bool:
        """Check if an alert should be sent based on level.

        Args:
            status: Alert status ("success", "warning", "error").

        Returns:
            True if alert should be sent.
        """
        if not self.enabled:
            return False

        if self.level == "all":
            return True
        elif self.level == "warnings":
            return status in ("warning", "error")
        elif self.level == "errors":
            return status == "error"

        return False

    def get_configuration_errors(self) -> list[str]:
        """Get list of configuration errors for active channels.

        Returns:
            List of error messages.
        """
        errors = []

        for channel in self.active_channels:
            alerter = self.alerters.get(channel)
            if alerter:
                if not alerter.is_configured():
                    errors.extend(alerter.get_configuration_errors())

        return errors

    def _send_alert(self, alert: BackupAlert) -> dict[str, bool]:
        """Send alert to all active channels.

        Args:
            alert: Alert data.

        Returns:
            Dict of channel name to success status.
        """
        results = {}

        if not self.should_send_alert(alert.status):
            return results

        for channel in self.active_channels:
            alerter = self.alerters.get(channel)
            if alerter and alerter.is_configured():
                try:
                    results[channel] = alerter.send(alert)
                except Exception as e:
                    backup_logger.error(f"Failed to send alert via {channel}: {e}")
                    results[channel] = False

        return results

    def send_backup_success(
        self,
        backup_id: str,
        bases_count: int,
        tables_count: int,
        records_count: int,
        total_size: int,
        duration_seconds: float,
        local_path: str | None,
        s3_path: str | None,
        database_dump_size: int,
    ) -> dict[str, bool]:
        """Send success alert."""
        alert = BackupAlert(
            backup_id=backup_id,
            status="success",
            message="Backup completed successfully",
            instance_name=self.settings.instance_name,
            bases_count=bases_count,
            tables_count=tables_count,
            records_count=records_count,
            total_size=total_size,
            duration_seconds=duration_seconds,
            local_path=local_path,
            s3_path=s3_path,
            database_dump_size=database_dump_size,
        )
        return self._send_alert(alert)

    def send_backup_warning(
        self,
        backup_id: str,
        message: str,
        bases_count: int,
        tables_count: int,
        records_count: int,
        total_size: int,
        duration_seconds: float,
        error_messages: list[str],
        local_path: str | None,
        s3_path: str | None,
        database_dump_size: int,
    ) -> dict[str, bool]:
        """Send warning alert."""
        alert = BackupAlert(
            backup_id=backup_id,
            status="warning",
            message=message,
            instance_name=self.settings.instance_name,
            bases_count=bases_count,
            tables_count=tables_count,
            records_count=records_count,
            total_size=total_size,
            duration_seconds=duration_seconds,
            error_messages=error_messages,
            local_path=local_path,
            s3_path=s3_path,
            database_dump_size=database_dump_size,
        )
        return self._send_alert(alert)

    def send_backup_error(
        self,
        backup_id: str,
        message: str,
        error_messages: list[str],
        duration_seconds: float,
    ) -> dict[str, bool]:
        """Send error alert."""
        alert = BackupAlert(
            backup_id=backup_id,
            status="error",
            message=message,
            instance_name=self.settings.instance_name,
            duration_seconds=duration_seconds,
            error_messages=error_messages,
        )
        return self._send_alert(alert)
