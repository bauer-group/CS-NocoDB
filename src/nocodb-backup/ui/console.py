"""
NocoDB Backup - Console UI Module

Provides console output and logging utilities.
"""

import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# ===============================================================================
# Console and Logger Setup
# ===============================================================================

_rich_console = Console(force_terminal=True)
console = _rich_console

# Logger
backup_logger = logging.getLogger("nocodb-backup")
_logging_initialized = False


def setup_logging(level: str = "INFO") -> None:
    """Setup logging with simple StreamHandler."""
    global _logging_initialized

    if _logging_initialized:
        return
    _logging_initialized = True

    # Clear all handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    backup_logger.handlers.clear()
    backup_logger.propagate = False

    # Simple handler with flush
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    backup_logger.setLevel(level.upper())
    backup_logger.addHandler(handler)


# ===============================================================================
# Formatting Utilities
# ===============================================================================


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ===============================================================================
# Output Functions
# ===============================================================================


def print_banner(backup_id: str) -> None:
    """Print backup banner with ID."""
    console.print()
    console.print(Panel(
        f"[bold]Backup ID:[/] [cyan]{backup_id}[/]",
        title="[bold cyan]NocoDB Backup[/]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()


def print_summary(
    bases_count: int,
    tables_count: int,
    records_count: int,
    total_size: int,
    duration: float,
    local_path: str | None = None,
    s3_path: str | None = None,
    database_dump_size: int | None = None,
    errors: list[str] | None = None,
) -> None:
    """Print backup summary."""
    table = Table(title="Backup Summary", show_header=False, border_style="dim")
    table.add_column("Property", style="bold")
    table.add_column("Value", style="cyan")

    table.add_row("Bases", str(bases_count))
    table.add_row("Tables", str(tables_count))
    table.add_row("Records", str(records_count))
    if database_dump_size is not None:
        table.add_row("Database Dump", format_size(database_dump_size))
    table.add_row("Total Size", format_size(total_size))
    table.add_row("Duration", f"{duration:.1f}s")
    if local_path:
        table.add_row("Local Path", local_path)
    if s3_path:
        table.add_row("S3 Path", s3_path)

    console.print()
    console.print(table)

    if errors:
        console.print()
        console.print(Panel(
            "\n".join(f"- {error}" for error in errors),
            title="[yellow]Errors[/]",
            border_style="yellow",
        ))


def print_completion(success: bool) -> None:
    """Print completion status."""
    console.print()
    if success:
        console.print(Panel(
            "[bold green]+ Backup completed successfully![/]",
            border_style="green",
            padding=(0, 2),
        ))
    else:
        console.print(Panel(
            "[bold red]! Backup completed with errors[/]",
            border_style="red",
            padding=(0, 2),
        ))
    console.print()


def print_error(message: str, exception: Exception | None = None) -> None:
    """Print error message."""
    console.print()
    console.print(f"[bold red]ERROR: {message}[/]")
    if exception:
        console.print(f"  [red]{exception}[/]")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[dim]{message}[/]")


def print_success(message: str) -> None:
    """Print success message."""
    console.print(f"[green]+ {message}[/]")


def print_warning(message: str) -> None:
    """Print warning message."""
    console.print(f"[yellow]! {message}[/]")
