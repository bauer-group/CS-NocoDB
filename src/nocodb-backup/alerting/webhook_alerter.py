"""
NocoDB Backup - Generic Webhook Alerter
"""

import hashlib
import hmac
import json
from typing import TYPE_CHECKING

import httpx

from alerting.base import Alerter, BackupAlert
from ui.console import backup_logger

if TYPE_CHECKING:
    from config import Settings


class WebhookAlerter(Alerter):
    """Sends alerts via generic webhook."""

    def is_configured(self) -> bool:
        """Check if webhook is configured."""
        return bool(self.settings.webhook_url)

    def get_configuration_errors(self) -> list[str]:
        """Get configuration errors."""
        if not self.settings.webhook_url:
            return ["Webhook: WEBHOOK_URL not configured"]
        return []

    def send(self, alert: BackupAlert) -> bool:
        """Send webhook alert."""
        try:
            payload = {
                "backup_id": alert.backup_id,
                "status": alert.status,
                "message": alert.message,
                "instance_name": alert.instance_name,
                "bases_count": alert.bases_count,
                "tables_count": alert.tables_count,
                "records_count": alert.records_count,
                "total_size": alert.total_size,
                "duration_seconds": alert.duration_seconds,
                "local_path": alert.local_path,
                "s3_path": alert.s3_path,
                "database_dump_size": alert.database_dump_size,
                "file_backup_size": alert.file_backup_size,
                "error_messages": alert.error_messages,
            }

            headers = {"Content-Type": "application/json"}

            # Add HMAC signature if secret is configured
            if self.settings.webhook_secret:
                payload_bytes = json.dumps(payload, sort_keys=True).encode()
                signature = hmac.new(
                    self.settings.webhook_secret.encode(),
                    payload_bytes,
                    hashlib.sha256,
                ).hexdigest()
                headers["X-Signature-256"] = f"sha256={signature}"

            response = httpx.post(
                self.settings.webhook_url,
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()

            backup_logger.debug("Webhook alert sent")
            return True

        except Exception as e:
            backup_logger.error(f"Failed to send webhook alert: {e}")
            return False
