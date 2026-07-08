"""NocoDB extension for the BAUER GROUP BackupHelper engine.

Ships two engine extension points:

* a ``nocodb-rest`` **Source** (``rest_source.NocoDBRestSource``) that captures
  the NocoDB REST-API export (bases/tables/schema/records/attachments) as one
  snapshot component, and
* a ``nocodb`` **command group** (``commands.app``) mounting the REST-specific
  restore commands (restore-schema / restore-records / restore-attachments).

Both are wired via entry points in ``pyproject.toml``; nothing here needs to be
imported manually — the engine discovers them at runtime.
"""

__version__ = "0.1.0"
