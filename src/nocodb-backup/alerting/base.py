"""
NocoDB Backup - Alerting Base Classes
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Settings


@dataclass
class BackupAlert:
    """Backup alert data."""

    backup_id: str
    status: str  # "success", "warning", "error"
    message: str
    instance_name: str = ""
    bases_count: int = 0
    tables_count: int = 0
    records_count: int = 0
    total_size: int = 0
    duration_seconds: float = 0
    local_path: str | None = None
    s3_path: str | None = None
    database_dump_size: int = 0
    error_messages: list[str] = field(default_factory=list)


class Alerter(ABC):
    """Base class for alert channels."""

    def __init__(self, settings: "Settings"):
        """Initialize alerter.

        Args:
            settings: Application settings.
        """
        self.settings = settings

    @abstractmethod
    def send(self, alert: BackupAlert) -> bool:
        """Send an alert.

        Args:
            alert: Alert data.

        Returns:
            True if alert was sent successfully.
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the alerter is properly configured.

        Returns:
            True if configured.
        """
        pass

    def get_configuration_errors(self) -> list[str]:
        """Get list of configuration errors.

        Returns:
            List of error messages.
        """
        return []
