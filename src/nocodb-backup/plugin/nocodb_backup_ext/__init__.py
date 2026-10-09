"""NocoDB extension for the BAUER GROUP BackupHelper engine.

Ships three engine extension points:

* a ``nocodb-rest`` **Source** (``rest_source.NocoDBRestSource``) that captures
  the NocoDB REST-API export (bases/tables/schema/records/attachments) as one
  snapshot component,
* a ``nocodb`` **command group** (``commands.app``) mounting the REST-specific
  restore commands (restore-schema / restore-records / restore-attachments), and
* a ``post_restore`` **hook** (``hooks.register``) that empties the NocoDB
  instances' Redis cache after a database restore in the cluster stacks.

All are wired via entry points in ``pyproject.toml``; nothing here needs to be
imported manually — the engine discovers them at runtime.
"""

__version__ = "0.1.0"
