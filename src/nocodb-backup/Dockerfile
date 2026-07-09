# =============================================================================
#  CS-NocoDB · NocoDB-Backup — meta image on the central BackupHelper engine
# -----------------------------------------------------------------------------
#  Thin wrapper: FROM the central BackupHelper engine + the NocoDB extension
#  plugin. The generic backup logic (pg_dump plain SQL, deterministic tar of the
#  NocoDB data volume, retention, sha256 manifest, off-site S3, alerting, the
#  restore CLI, off-site DR hydration) lives in the engine, which ships the
#  postgres 18 client, a non-root user, tini and a functional healthcheck.
#
#  The NocoDB-specific parts are the `nocodb_backup_ext` plugin (see ./plugin):
#    * `nocodb-rest` Source  — REST-API export (bases/tables/schema/records/
#                              attachments) as one snapshot component.
#    * `nocodb` command group — restore-schema / restore-records /
#                              restore-attachments, mounted under the engine CLI.
#  The engine discovers both via entry points at runtime. The raw DB dump and
#  data-file restores are inherited generically:
#    backuphelper restore <id> --only database    (pg_dump restore)
#    backuphelper restore <id> --only nocodb-data (data-file extract)
#
#  See docs/migration.md in the BackupHelper repo.
# =============================================================================
ARG BACKUPHELPER_VERSION=latest

# -------------------------------------------------------------------------------
# Stage 1: Test — plugin tests gate the image build (composable test gate)
# -------------------------------------------------------------------------------
FROM ghcr.io/bauer-group/cs-backuphelper/backuphelper:${BACKUPHELPER_VERSION} AS test

USER root
COPY plugin /opt/nocodb-plugin
# httpx comes from the plugin's own dependencies; backuphelper is already present
# in the engine image (it is deliberately NOT a plugin dependency).
RUN pip install --no-cache-dir /opt/nocodb-plugin pytest \
    && python -m pytest /opt/nocodb-plugin/tests -q

# -------------------------------------------------------------------------------
# Stage 2: Production — engine + plugin only
# -------------------------------------------------------------------------------
FROM ghcr.io/bauer-group/cs-backuphelper/backuphelper:${BACKUPHELPER_VERSION} AS prod

USER root
COPY plugin /opt/nocodb-plugin
RUN pip install --no-cache-dir /opt/nocodb-plugin \
    && rm -rf /opt/nocodb-plugin/tests

# Fail the build unless the test stage passed (creates a dependency on it).
COPY --from=test /opt/nocodb-plugin/pyproject.toml /tmp/plugin-tests-passed
RUN rm -f /tmp/plugin-tests-passed

# ── OCI / BAUER GROUP labels ───────────────────────────────────────────────
LABEL vendor="BAUER GROUP"
LABEL maintainer="Karl Bauer <karl.bauer@bauer-group.com>"
LABEL org.opencontainers.image.title="NocoDB Backup"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="BAUER GROUP"
LABEL org.opencontainers.image.authors="Karl Bauer <karl.bauer@bauer-group.com>"
LABEL org.opencontainers.image.source="https://github.com/bauer-group/CS-NocoDB"
LABEL org.opencontainers.image.url="https://github.com/bauer-group/CS-NocoDB"
LABEL org.opencontainers.image.documentation="https://github.com/bauer-group/CS-NocoDB#readme"
LABEL org.opencontainers.image.description="NocoDB backup (PostgreSQL + data files + REST-API export) via the central BackupHelper engine - BAUER GROUP Edition"
LABEL com.bauer-group.image.component="backup"
LABEL com.bauer-group.image.stack="nocodb"
LABEL org.opencontainers.image.version="0.7.3"

# Drop back to the engine's non-root user; inherit ENTRYPOINT + HEALTHCHECK.
USER backup

# Sources / destinations / schedule come from BACKUP_CONFIG_JSON in compose.
# Restore: `docker compose run --rm nocodb-backup nocodb restore-schema <id>` etc.
