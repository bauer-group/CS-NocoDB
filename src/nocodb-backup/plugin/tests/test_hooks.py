"""The post_restore hook empties NocoDB's Redis cache after a database restore.

The flush is checked on the wire: a minimal Redis stand-in (RESP over TCP)
records the commands the real redis client sends.
"""

import logging
import socket
import threading
from importlib.metadata import entry_points

import pytest
from backuphelper.archive.manifest import Component, Manifest

from nocodb_backup_ext import hooks


class _FakeRedis:
    """Records each command's arguments. HELLO (redis-py opens with RESP3)
    gets the handshake map a Redis server sends, every other command +OK."""

    _HELLO = b"%2\r\n$6\r\nserver\r\n$5\r\nredis\r\n$5\r\nproto\r\n:3\r\n"

    def __init__(self):
        self.commands: list[list[str]] = []
        self._server = socket.create_server(("127.0.0.1", 0))
        self.port = self._server.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        with conn, conn.makefile("rb") as rfile:
            while header := rfile.readline():
                count = int(header[1:])  # "*<n>\r\n", then n "$<len>\r\n<arg>\r\n"
                args = []
                for _ in range(count):
                    size = int(rfile.readline()[1:])
                    args.append(rfile.read(size + 2)[:-2].decode())
                self.commands.append(args)
                conn.sendall(self._HELLO if args[0].upper() == "HELLO" else b"+OK\r\n")

    def close(self):
        self._server.close()


@pytest.fixture
def fake_redis():
    server = _FakeRedis()
    yield server
    server.close()


def _context(*components: Component) -> dict:
    manifest = Manifest(snapshot_id="2026-10-09_05-15-00", instance_name="nocodb",
                        created_at="2026-10-09T05:15:00+00:00", components=list(components))
    return {"job": "main", "snapshot_id": manifest.snapshot_id, "manifest": manifest, "ok": True}


DATABASE = Component(name="database", kind="postgres", size=10, sha256="x")
FILES = Component(name="nocodb-data", kind="filesystem", size=10, sha256="y")


def _names(server) -> list[str]:
    return [args[0].upper() for args in server.commands]


def test_flushes_the_configured_database_after_a_database_restore(fake_redis, monkeypatch):
    monkeypatch.setenv(hooks.REDIS_URL_ENV, f"redis://127.0.0.1:{fake_redis.port}/2")
    hooks.flush_cache_after_restore(_context(DATABASE, FILES))
    assert ["SELECT", "2"] in fake_redis.commands
    assert _names(fake_redis)[-1] == "FLUSHDB"


@pytest.mark.parametrize("components", [
    (FILES,),  # no database in the snapshot
    (Component(name="database", kind="postgres", size=0, sha256="", error="pg_dump failed"), FILES),
])
def test_no_flush_without_a_restorable_database(fake_redis, monkeypatch, components):
    monkeypatch.setenv(hooks.REDIS_URL_ENV, f"redis://127.0.0.1:{fake_redis.port}")
    hooks.flush_cache_after_restore(_context(*components))
    assert "FLUSHDB" not in _names(fake_redis)


def test_inactive_without_redis_url(monkeypatch):
    # Single-instance stacks have no Redis: the hook must not try to reach one.
    monkeypatch.delenv(hooks.REDIS_URL_ENV, raising=False)

    def unexpected(*args, **kwargs):
        raise AssertionError("no Redis connection expected")

    monkeypatch.setattr(hooks.redis.Redis, "from_url", unexpected)
    hooks.flush_cache_after_restore(_context(DATABASE))


def test_unreachable_redis_warns_instead_of_failing_the_restore(monkeypatch, caplog):
    with socket.create_server(("127.0.0.1", 0)) as probe:
        port = probe.getsockname()[1]  # closed again below: nothing listens there
    monkeypatch.setenv(hooks.REDIS_URL_ENV, f"redis://127.0.0.1:{port}")
    with caplog.at_level(logging.WARNING, logger="backuphelper.plugin.nocodb"):
        hooks.flush_cache_after_restore(_context(DATABASE))
    assert "was not emptied" in caplog.text
    assert "Restart every NocoDB instance" in caplog.text


def test_registers_only_post_restore():
    registered = []

    class Registry:
        def register(self, phase, hook):
            registered.append((phase, hook))

    hooks.register(Registry())
    assert registered == [("post_restore", hooks.flush_cache_after_restore)]


def test_engine_discovers_the_hook():
    eps = entry_points(group="backuphelper.hooks")
    assert any(ep.value == "nocodb_backup_ext.hooks:register" for ep in eps)
