#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip, cluster stack - seed
# =============================================================================
# The single-instance seed (../seed.sh) through the load balancer: the first
# user, the API token for the sidecar, a base with a table and the record with
# its two attachments, each request served by whichever instance HAProxy picks.
# =============================================================================
set -euo pipefail
# shellcheck source=tests/backup-roundtrip/cluster/common.sh
source "$(dirname "$0")/common.sh"

exec bash "$(dirname "$0")/../seed.sh"
