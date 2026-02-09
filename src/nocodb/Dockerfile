# ═══════════════════════════════════════════════════════════════════════════════
# NocoDB - Open Source Airtable Alternative
# ═══════════════════════════════════════════════════════════════════════════════
# Base Image: https://hub.docker.com/r/nocodb/nocodb
# Documentation: https://docs.nocodb.com/getting-started/self-hosted/installation/docker/
# ═══════════════════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────────────────
# Build Arguments (Base Image)
# ───────────────────────────────────────────────────────────────────────────────
# These ARGs define the BASE image to build FROM.
# Default: Official NocoDB image from Docker Hub.
# Override via: docker build --build-arg BASE_NOCODB_IMAGE=... --build-arg BASE_NOCODB_VERSION=...
ARG BASE_NOCODB_IMAGE=nocodb/nocodb
ARG BASE_NOCODB_VERSION=latest

FROM ${BASE_NOCODB_IMAGE}:${BASE_NOCODB_VERSION}

# Re-declare ARGs after FROM (without defaults to inherit passed values)
ARG BASE_NOCODB_IMAGE
ARG BASE_NOCODB_VERSION

# ───────────────────────────────────────────────────────────────────────────────
# Metadata Labels (Legacy)
# ───────────────────────────────────────────────────────────────────────────────
LABEL vendor="BAUER GROUP"
LABEL maintainer="Karl Bauer <karl.bauer@bauer-group.com>"

# ───────────────────────────────────────────────────────────────────────────────
# OCI Image Spec Labels
# https://github.com/opencontainers/image-spec/blob/main/annotations.md
# ───────────────────────────────────────────────────────────────────────────────
LABEL org.opencontainers.image.title="NocoDB"
LABEL org.opencontainers.image.description="NocoDB - Open Source Airtable Alternative - BAUER GROUP Edition"
LABEL org.opencontainers.image.version="0.6.3"
LABEL org.opencontainers.image.vendor="BAUER GROUP"
LABEL org.opencontainers.image.authors="Karl Bauer <karl.bauer@bauer-group.com>"
LABEL org.opencontainers.image.licenses="AGPL-3.0"
LABEL org.opencontainers.image.source="https://github.com/bauer-group/CS-NocoDB"
LABEL org.opencontainers.image.url="https://github.com/bauer-group/CS-NocoDB"
LABEL org.opencontainers.image.documentation="https://github.com/bauer-group/CS-NocoDB#readme"
LABEL org.opencontainers.image.base.name="${BASE_NOCODB_IMAGE}:${BASE_NOCODB_VERSION}"

# ───────────────────────────────────────────────────────────────────────────────
# Customizations
# ───────────────────────────────────────────────────────────────────────────────
# Currently no customizations - using base image as-is
# Add custom configurations, scripts, or packages here if needed

# ───────────────────────────────────────────────────────────────────────────────
# Health Check
# ───────────────────────────────────────────────────────────────────────────────
# NocoDB API exposes /api/v1/health on port 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -q --spider http://localhost:8080/api/v1/health || exit 1
