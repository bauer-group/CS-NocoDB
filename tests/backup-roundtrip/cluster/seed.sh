#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip, cluster stack - seed
# =============================================================================
# The single-instance seed (../seed.sh) on a fresh cluster, set up the way the
# README prescribes for a new cluster (cluster mode, first user):
#
#   1. the seed through nocodb-server-1 directly: the first user, the API
#      token for the sidecar, a base with a table and the record with its two
#      attachments
#   2. a restart of every other instance. NocoDB reads the id of its default
#      workspace once per process, at start, and on a fresh database there is
#      none yet. The instance that signs up the first user creates it and
#      keeps it; every other instance that is already running answers each
#      workspace-scoped request - listing or creating bases - with 403 until
#      it restarts (Noco.ncDefaultWorkspaceId, verifyDefaultWorkspace).
# =============================================================================
set -euo pipefail
# shellcheck source=tests/backup-roundtrip/cluster/common.sh
source "$(dirname "$0")/common.sh"

NOCODB_API_SERVICE=nocodb-server-1 bash "$(dirname "$0")/../seed.sh"

INSTANCES=$(nocodb_instances)
OTHERS=$(grep -vx 'nocodb-server-1' <<< "$INSTANCES" || true)
if [ -n "$OTHERS" ]; then
  mapfile -t OTHER_LIST <<< "$OTHERS"
  docker compose restart "${OTHER_LIST[@]}"
  docker compose up -d --no-deps --wait --wait-timeout 300 "${OTHER_LIST[@]}"
  echo "restarted ${OTHER_LIST[*]} after the first user: every instance knows the default workspace"
fi
