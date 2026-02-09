# ===============================================================================
# NocoDB Backup - Dockerfile
# ===============================================================================
# Multi-stage build with integrated testing
#
# Stages:
#   1. builder    - Install Python dependencies
#   2. test       - Run pytest (build fails if tests fail)
#   3. prod       - Minimal production image
#
# Build without tests:  docker build --target prod -t nocodb-backup .
# Build with tests:     docker build -t nocodb-backup .
# ===============================================================================

# -------------------------------------------------------------------------------
# Stage 1: Builder - Install Python Dependencies
# -------------------------------------------------------------------------------
FROM python:3.14-alpine AS builder

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# -------------------------------------------------------------------------------
# Stage 2: Test - Run Tests During Build
# -------------------------------------------------------------------------------
FROM python:3.14-alpine AS test

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev

WORKDIR /app

# Install production + test dependencies
COPY requirements.txt requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-test.txt

# Copy application code
COPY . .

# Run tests - build fails if tests fail
RUN pytest tests/ -v --tb=short \
    && echo "==============================================================================="

# -------------------------------------------------------------------------------
# Stage 3: Production - Minimal Runtime Image
# -------------------------------------------------------------------------------
FROM python:3.14-alpine AS prod

# =============================================================================
# Labels
# =============================================================================

LABEL vendor="BAUER GROUP"
LABEL maintainer="Karl Bauer <karl.bauer@bauer-group.com>"

LABEL org.opencontainers.image.title="NocoDB Backup"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.vendor="BAUER GROUP"
LABEL org.opencontainers.image.authors="Karl Bauer <karl.bauer@bauer-group.com>"
LABEL org.opencontainers.image.source="https://github.com/bauer-group/CS-NocoDB"
LABEL org.opencontainers.image.url="https://github.com/bauer-group/CS-NocoDB"
LABEL org.opencontainers.image.documentation="https://github.com/bauer-group/CS-NocoDB#readme"
LABEL org.opencontainers.image.description="Automated NocoDB backup to S3-compatible storage"
LABEL org.opencontainers.image.version="0.6.3"

# Python unbuffered output - prevents duplicate lines in Docker logs
ENV PYTHONUNBUFFERED=1

# Runtime dependencies: tzdata + tini + procps (for pgrep) + postgresql-client (for pg_dump)
RUN apk add --no-cache \
    tzdata \
    tini \
    procps \
    postgresql18-client \
    && rm -rf /var/cache/apk/*

# Python packages from builder
COPY --from=builder /install /usr/local

# Ensure test stage passed (creates dependency on test stage)
COPY --from=test /app/pytest.ini /tmp/test-passed
RUN rm /tmp/test-passed

# Non-root user
RUN addgroup -g 1000 backup \
    && adduser -u 1000 -G backup -h /app -D backup

WORKDIR /app

# Application code (exclude tests in production)
COPY --chown=backup:backup *.py ./
COPY --chown=backup:backup backup/ ./backup/
COPY --chown=backup:backup storage/ ./storage/
COPY --chown=backup:backup alerting/ ./alerting/
COPY --chown=backup:backup ui/ ./ui/

# Data directory for local backups
RUN mkdir -p /data && chown backup:backup /data

USER backup

VOLUME ["/data"]

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "python main.py" || exit 1

# Tini as init process for proper signal handling
ENTRYPOINT ["/sbin/tini", "--", "python", "main.py"]

# -------------------------------------------------------------------------------
# Usage
# -------------------------------------------------------------------------------
# Build (with tests):        docker build -t nocodb-backup .
# Build (skip tests):        docker build --target prod -t nocodb-backup .
# Run tests only:            docker build --target test -t nocodb-backup-test .
#
# Scheduler mode (default):  docker run ... nocodb-backup
# Immediate backup:          docker run ... nocodb-backup --now
# CLI commands:              docker run ... nocodb-backup cli <command>
