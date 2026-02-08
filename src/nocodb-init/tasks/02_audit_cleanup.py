"""
Task: Clean up NocoDB audit and log tables

When NC_DISABLE_AUDIT=true is set (default), NocoDB does not write new
audit entries. However, historical data remains and can bloat the database.

This task cleans up audit tables on container start when enabled.

Environment variables:
  INIT_AUDIT_CLEANUP=true/false  - Enable/disable cleanup (default: true)

Tables cleaned:
  - nc_audit_v2           - Main audit log (user actions)
  - nc_hook_logs_v2       - Webhook execution logs
  - nc_sync_logs_v2       - Sync logs
  - nc_automation_executions - Automation logs (if exists)

Note: Only tables that exist will be cleaned. This is safe on first start.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg
    from rich.console import Console

# Task metadata
TASK_NAME = "Audit Cleanup"
TASK_DESCRIPTION = "Clean up audit and log tables"
ENABLED_VAR = "INIT_AUDIT_CLEANUP"  # Set to "false" to disable (default: enabled)

# Tables to clean (in order)
AUDIT_TABLES = [
    "nc_audit_v2",
    "nc_hook_logs_v2",
    "nc_sync_logs_v2",
    "nc_automation_executions",
]


def _table_exists(conn: "psycopg.Connection", table_name: str) -> bool:
    """Check if a table exists in the public schema."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = %s
            )
        """, (table_name,))
        return cur.fetchone()[0]


def _get_row_count(conn: "psycopg.Connection", table_name: str) -> int:
    """Get approximate row count for a table."""
    with conn.cursor() as cur:
        # Use reltuples for fast approximate count (good enough for display)
        cur.execute("""
            SELECT COALESCE(reltuples::bigint, 0)
            FROM pg_class
            WHERE relname = %s
        """, (table_name,))
        result = cur.fetchone()
        return result[0] if result else 0


def _truncate_table(conn: "psycopg.Connection", table_name: str) -> bool:
    """Truncate a table. Returns True on success."""
    try:
        with conn.cursor() as cur:
            cur.execute(f'TRUNCATE TABLE "{table_name}"')
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False


def run(conn: "psycopg.Connection", console: "Console") -> dict:
    """Clean up audit and log tables.

    Args:
        conn: Database connection.
        console: Rich console for output.

    Returns:
        Dict with 'changed', 'skipped', and 'message' keys.
    """
    # Find existing tables
    existing_tables = []
    for table in AUDIT_TABLES:
        if _table_exists(conn, table):
            existing_tables.append(table)

    if not existing_tables:
        return {
            "changed": False,
            "skipped": True,
            "message": "No audit tables exist yet (first start)"
        }

    # Check row counts
    tables_with_data = []
    total_rows = 0
    for table in existing_tables:
        count = _get_row_count(conn, table)
        if count > 0:
            tables_with_data.append((table, count))
            total_rows += count

    if not tables_with_data:
        return {
            "changed": False,
            "skipped": False,
            "message": "Audit tables already empty"
        }

    # Report what we found
    console.print(f"    [cyan]Found {len(tables_with_data)} table(s) with ~{total_rows:,} rows:[/]")
    for table, count in tables_with_data:
        console.print(f"    [dim]  - {table}: ~{count:,} rows[/]")

    # Truncate tables
    console.print()
    console.print("    [cyan]Cleaning up...[/]")

    cleaned_count = 0
    failed_count = 0

    for table, count in tables_with_data:
        if _truncate_table(conn, table):
            console.print(f"    [green]✓ {table}[/]")
            cleaned_count += 1
        else:
            console.print(f"    [red]✗ {table}[/]")
            failed_count += 1

    if failed_count == 0:
        return {
            "changed": True,
            "skipped": False,
            "message": f"Cleaned {cleaned_count} table(s), ~{total_rows:,} rows removed"
        }
    elif cleaned_count > 0:
        return {
            "changed": True,
            "skipped": False,
            "message": f"Cleaned {cleaned_count}, failed {failed_count} table(s)"
        }
    else:
        return {
            "changed": False,
            "skipped": False,
            "message": f"Failed to clean {failed_count} table(s)"
        }
