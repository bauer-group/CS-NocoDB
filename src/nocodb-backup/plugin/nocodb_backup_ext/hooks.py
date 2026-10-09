"""Lifecycle hooks of the NocoDB plugin (``backuphelper.hooks`` entry point).

``post_restore`` empties NocoDB's Redis database after ``backuphelper restore``
of a snapshot that holds a database dump. In cluster mode the NocoDB instances
share their metadata cache (bases, tables, columns, views, ...) in that Redis.
A restored database leaves it describing the state before the restore, and an
instance that keeps running serves that state until the keys expire
(NC_REDIS_TTL, 3 days by default).

NocoDB empties the same Redis database whenever an instance starts
(RedisCacheMgr, unless NC_KEEP_CACHE or NC_WORKER_CONTAINER is set), so the
flush only does early what the documented restart does anyway: instances that
were stopped for the restore lose nothing, and running ones reload the metadata
from the restored database. Jobs queued in the same database (Bull) are dropped
as on every restart.

The hook is active only where ``NOCODB_REDIS_URL`` is set - the cluster compose
files point it at their redis-server. A failed flush never fails the restore,
which has already run: it is logged with what to do instead.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import redis

log = logging.getLogger("backuphelper.plugin.nocodb")

REDIS_URL_ENV = "NOCODB_REDIS_URL"
_TIMEOUT_SECONDS = 10


def _has_database(manifest: Any) -> bool:
    """Whether the snapshot carries a database dump the restore could apply."""
    components = getattr(manifest, "components", None) or []
    return any(getattr(c, "kind", None) == "postgres" and not getattr(c, "error", None)
               for c in components)


def flush_cache_after_restore(context: Any) -> None:
    url = os.environ.get(REDIS_URL_ENV, "").strip()
    if not url:
        return  # single-instance stack: NocoDB keeps its cache in memory
    if not _has_database((context or {}).get("manifest")):
        return
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=_TIMEOUT_SECONDS,
                                      socket_timeout=_TIMEOUT_SECONDS)
        try:
            client.flushdb()
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001 - the restore itself is done
        # The URL is not logged: it may carry a password.
        log.warning("NocoDB's Redis cache was not emptied after the restore (%s: %s). "
                    "Restart every NocoDB instance - each one empties it when it starts.",
                    type(e).__name__, e)
        return
    log.info("emptied NocoDB's Redis cache: the instances reload the metadata "
             "from the restored database")


def register(registry: Any) -> None:
    """Entry point of the ``backuphelper.hooks`` group."""
    registry.register("post_restore", flush_cache_after_restore)
