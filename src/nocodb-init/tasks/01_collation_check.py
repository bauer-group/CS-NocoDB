"""
Task: Check and optionally fix collation version mismatches

After PostgreSQL minor updates or glibc changes, collation versions
may become mismatched. This task checks for mismatches and can
optionally fix them automatically.

Environment variables:
  INIT_COLLATION_CHECK=true/false     - Enable/disable this task (default: true)
  INIT_COLLATION_AUTO_FIX=true/false  - Auto-fix mismatches (default: false)

Note: On first start, NocoDB tables may not exist yet. This task will
skip gracefully and let NocoDB initialize the database first.
"""

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg
    from rich.console import Console

# Task metadata
TASK_NAME = "Collation Check"
TASK_DESCRIPTION = "Check for collation version mismatches"
ENABLED_VAR = "INIT_COLLATION_CHECK"  # Set to "false" to disable

# Auto-fix setting
AUTO_FIX_VAR = "INIT_COLLATION_AUTO_FIX"


def _get_auto_fix_enabled() -> bool:
    """Check if auto-fix is enabled via environment variable."""
    return os.environ.get(AUTO_FIX_VAR, "false").lower() in ("true", "1", "yes")


def run(conn: "psycopg.Connection", console: "Console") -> dict:
    """Check for collation version mismatches.

    Args:
        conn: Database connection.
        console: Rich console for output.

    Returns:
        Dict with 'changed', 'skipped', and 'message' keys.
    """
    with conn.cursor() as cur:
        # First check if NocoDB has initialized any tables
        # Use a simple check for the nc_bases_v2 table (NocoDB's base table)
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'nc_bases_v2'
            )
        """)
        tables_exist = cur.fetchone()[0]

        if not tables_exist:
            # NocoDB hasn't created tables yet - skip gracefully
            return {
                "changed": False,
                "skipped": True,
                "message": "NocoDB tables not yet initialized (first start)"
            }

        # Check for DATABASE-LEVEL collation version mismatches
        # This is what PostgreSQL warns about: "database X has a collation version mismatch"
        cur.execute("""
            SELECT
                datname,
                datcollversion,
                pg_database_collation_actual_version(oid) as actual_version
            FROM pg_database
            WHERE datcollversion IS NOT NULL
              AND datcollversion != pg_database_collation_actual_version(oid)
        """)
        db_mismatches = cur.fetchall()

        # Check for COLLATION-LEVEL version mismatches (individual collations)
        # This query finds collations where the stored version differs from current
        cur.execute("""
            SELECT
                collname,
                collversion,
                pg_collation_actual_version(oid) as actual_version
            FROM pg_collation
            WHERE collversion IS NOT NULL
              AND collversion != pg_collation_actual_version(oid)
        """)

        coll_mismatches = cur.fetchall()

    # End implicit transaction so connection returns to IDLE state.
    # Without this, psycopg3 refuses to set autocommit (INTRANS error).
    conn.commit()

    # Combine all mismatches
    total_mismatches = len(db_mismatches) + len(coll_mismatches)

    if total_mismatches == 0:
        return {
            "changed": False,
            "skipped": False,
            "message": "No collation version mismatches detected"
        }

    # Report database-level mismatches
    if db_mismatches:
        console.print(f"    [yellow]Found {len(db_mismatches)} database collation mismatch(es):[/]")
        for dbname, stored_ver, actual_ver in db_mismatches:
            console.print(f"    [yellow]  - database '{dbname}': stored={stored_ver}, actual={actual_ver}[/]")

    # Report collation-level mismatches
    if coll_mismatches:
        console.print(f"    [yellow]Found {len(coll_mismatches)} collation mismatch(es):[/]")
        for collname, stored_ver, actual_ver in coll_mismatches:
            console.print(f"    [yellow]  - collation '{collname}': stored={stored_ver}, actual={actual_ver}[/]")

    # Check if auto-fix is enabled
    auto_fix = _get_auto_fix_enabled()

    if auto_fix:
        console.print()
        console.print(f"    [cyan]Auto-fix enabled ({AUTO_FIX_VAR}=true)[/]")

        fixed_db_count = 0
        failed_db_count = 0
        fixed_coll_count = 0
        failed_coll_count = 0

        # Fix database-level mismatches - each database independently
        if db_mismatches:
            console.print("    [cyan]Fixing database collation versions...[/]")
            for dbname, stored_ver, actual_ver in db_mismatches:
                try:
                    conn.autocommit = True
                    with conn.cursor() as fix_cur:
                        fix_cur.execute(f"ALTER DATABASE \"{dbname}\" REFRESH COLLATION VERSION")
                    console.print(f"    [green]✓ database '{dbname}'[/]")
                    fixed_db_count += 1
                except Exception as e:
                    console.print(f"    [red]✗ database '{dbname}': {e}[/]")
                    failed_db_count += 1
                finally:
                    conn.autocommit = False

        # Fix collation-level mismatches - each collation independently
        if coll_mismatches:
            console.print("    [cyan]Fixing collation versions...[/]")
            for collname, stored_ver, actual_ver in coll_mismatches:
                try:
                    conn.autocommit = True
                    with conn.cursor() as fix_cur:
                        fix_cur.execute(f"ALTER COLLATION \"{collname}\" REFRESH VERSION")
                    console.print(f"    [green]✓ collation '{collname}'[/]")
                    fixed_coll_count += 1
                except Exception as e:
                    console.print(f"    [red]✗ collation '{collname}': {e}[/]")
                    failed_coll_count += 1
                finally:
                    conn.autocommit = False

        total_fixed = fixed_db_count + fixed_coll_count
        total_failed = failed_db_count + failed_coll_count

        if total_fixed > 0 and total_failed == 0:
            return {
                "changed": True,
                "skipped": False,
                "message": f"Fixed {total_fixed} collation mismatch(es)"
            }
        elif total_fixed > 0 and total_failed > 0:
            return {
                "changed": True,
                "skipped": False,
                "message": f"Fixed {total_fixed}, failed {total_failed} collation mismatch(es)"
            }
        else:
            return {
                "changed": False,
                "skipped": False,
                "message": f"Could not fix {total_failed} collation mismatch(es)"
            }
    else:
        # Manual intervention required
        console.print()
        console.print(f"    [dim]Auto-fix disabled. Set {AUTO_FIX_VAR}=true to enable.[/]")
        console.print("    [yellow]To fix manually, run:[/]")
        if db_mismatches:
            console.print("    [dim]REINDEX DATABASE CONCURRENTLY <dbname>;[/]")
            console.print("    [dim]ALTER DATABASE <dbname> REFRESH COLLATION VERSION;[/]")
        if coll_mismatches:
            console.print("    [dim]ALTER COLLATION ... REFRESH VERSION;[/]")

        return {
            "changed": False,
            "skipped": False,
            "message": f"Found {total_mismatches} collation mismatch(es) - manual intervention recommended"
        }
