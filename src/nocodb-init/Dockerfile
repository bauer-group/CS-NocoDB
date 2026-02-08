# ===============================================================================
# NocoDB Init - Database Initialization Container
# ===============================================================================
# One-shot container that runs database initialization tasks before NocoDB starts.
#
# Tasks:
#   - Check for collation version mismatches (with optional auto-fix)
#   - Clean up audit and log tables (when NC_DISABLE_AUDIT=true)
#   - Extensible for future initialization tasks
#
# Usage:
#   docker compose -f docker-compose.local.yml up nocodb-init
#   (Runs automatically before nocodb-server via depends_on)
# ===============================================================================

FROM python:3.13-alpine

# =============================================================================
# Labels
# =============================================================================

LABEL vendor="BAUER GROUP"
LABEL maintainer="Karl Bauer <karl.bauer@bauer-group.com>"

LABEL org.opencontainers.image.title="NocoDB Init"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="BAUER GROUP"
LABEL org.opencontainers.image.authors="Karl Bauer <karl.bauer@bauer-group.com>"
LABEL org.opencontainers.image.source="https://github.com/bauer-group/CS-NocoDB"
LABEL org.opencontainers.image.url="https://github.com/bauer-group/CS-NocoDB"
LABEL org.opencontainers.image.documentation="https://github.com/bauer-group/CS-NocoDB#readme"
LABEL org.opencontainers.image.description="Database initialization for NocoDB Stack"
LABEL org.opencontainers.image.version="0.6.0"

# Python unbuffered output - ensures immediate visibility in Docker logs
ENV PYTHONUNBUFFERED=1

# =============================================================================
# Dependencies
# =============================================================================

# Install runtime dependencies + build dependencies for psycopg
RUN apk add --no-cache \
    libpq \
    tini \
    && apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    libpq-dev \
    && pip install --no-cache-dir psycopg[binary] rich \
    && apk del .build-deps \
    && rm -rf /var/cache/apk/*

# =============================================================================
# Application
# =============================================================================

WORKDIR /app

# Copy application code
COPY main.py .
COPY tasks/ ./tasks/

# Non-root user
RUN addgroup -g 1000 init \
    && adduser -u 1000 -G init -h /app -D init \
    && chown -R init:init /app

USER init

# =============================================================================
# Entrypoint
# =============================================================================

# Tini as init process for proper signal handling
ENTRYPOINT ["/sbin/tini", "--", "python", "main.py"]
