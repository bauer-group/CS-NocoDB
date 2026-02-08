#!/usr/bin/env python3
"""
NocoDB Init - Database Initialization

Runs one-time database initialization tasks before NocoDB starts.
Designed to be idempotent - safe to run multiple times.

Gracefully handles first-start scenarios where NocoDB tables don't exist yet.
"""

import os
import sys
import time
from importlib import import_module
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console()


def get_db_config() -> dict:
    """Get database configuration from environment variables."""
    return {
        "host": os.environ.get("DB_HOST", "database-server"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "dbname": os.environ.get("DB_NAME", "nocodb"),
        "user": os.environ.get("DB_USER", "nocodb"),
        "password": os.environ.get("DB_PASSWORD", os.environ.get("DATABASE_PASSWORD", "")),
    }


def wait_for_database(config: dict, timeout: int = 60) -> bool:
    """Wait for database to become available.

    Args:
        config: Database configuration dict.
        timeout: Maximum seconds to wait.

    Returns:
        True if database is available, False on timeout.
    """
    import psycopg

    console.print("[dim]Waiting for database...[/]")

    start_time = time.time()
    last_error = None

    while time.time() - start_time < timeout:
        try:
            with psycopg.connect(**config, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    console.print("[green]Database connection established[/]")
                    return True
        except Exception as e:
            last_error = e
            time.sleep(2)

    console.print(f"[red]Database connection timeout after {timeout}s: {last_error}[/]")
    return False


def discover_tasks() -> list:
    """Discover available initialization tasks.

    Returns:
        List of task modules with run() function.
    """
    tasks_dir = Path(__file__).parent / "tasks"
    tasks = []

    for task_file in sorted(tasks_dir.glob("*.py")):
        if task_file.name.startswith("_"):
            continue

        module_name = f"tasks.{task_file.stem}"
        try:
            module = import_module(module_name)
            if hasattr(module, "run"):
                tasks.append({
                    "name": getattr(module, "TASK_NAME", task_file.stem),
                    "description": getattr(module, "TASK_DESCRIPTION", ""),
                    "enabled_var": getattr(module, "ENABLED_VAR", None),
                    "module": module,
                })
        except Exception as e:
            console.print(f"[yellow]Warning: Failed to load task {task_file.name}: {e}[/]")

    return tasks


def is_task_enabled(task: dict) -> bool:
    """Check if a task is enabled via environment variable.

    Args:
        task: Task dict with optional enabled_var.

    Returns:
        True if task should run.
    """
    enabled_var = task.get("enabled_var")
    if not enabled_var:
        return True  # No env var = always enabled

    value = os.environ.get(enabled_var, "true").lower()
    return value in ("true", "1", "yes", "on")


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    console.print(Panel.fit(
        "[bold blue]NocoDB Init[/]\n"
        "[dim]Database Initialization[/]",
        border_style="blue"
    ))
    console.print()

    # Get database configuration
    config = get_db_config()

    if not config["password"]:
        console.print("[red]Error: DB_PASSWORD or DATABASE_PASSWORD not set[/]")
        return 1

    console.print(f"[dim]Database: {config['host']}:{config['port']}/{config['dbname']}[/]")
    console.print()

    # Wait for database
    timeout = int(os.environ.get("DB_WAIT_TIMEOUT", "60"))
    if not wait_for_database(config, timeout):
        return 1

    console.print()

    # Discover and run tasks
    tasks = discover_tasks()

    if not tasks:
        console.print("[yellow]No initialization tasks found[/]")
        return 0

    console.print(f"[bold]Found {len(tasks)} initialization task(s)[/]")
    console.print()

    failed = 0
    skipped = 0

    for task in tasks:
        task_name = task["name"]

        if not is_task_enabled(task):
            console.print(f"[dim]- {task_name}: Skipped (disabled)[/]")
            skipped += 1
            continue

        console.print(f"[bold]> {task_name}[/]")
        if task["description"]:
            console.print(f"  [dim]{task['description']}[/]")

        try:
            import psycopg
            with psycopg.connect(**config) as conn:
                result = task["module"].run(conn, console)

                if result.get("skipped"):
                    # Task skipped itself (e.g., tables don't exist yet)
                    console.print(f"  [dim]- Skipped: {result.get('message', 'Not applicable')}[/]")
                    skipped += 1
                elif result.get("changed"):
                    console.print(f"  [green]+ Applied: {result.get('message', 'Done')}[/]")
                else:
                    console.print(f"  [blue]= No changes: {result.get('message', 'Already configured')}[/]")

        except Exception as e:
            console.print(f"  [red]! Failed: {e}[/]")
            failed += 1

        console.print()

    # Summary
    console.print("-" * 50)
    total = len(tasks)
    success = total - failed - skipped

    if failed == 0:
        console.print(f"[green]+ Initialization complete ({success} applied, {skipped} skipped)[/]")
        return 0
    else:
        console.print(f"[red]! Initialization failed ({failed} errors, {success} applied, {skipped} skipped)[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
