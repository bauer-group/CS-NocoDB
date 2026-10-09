#!/usr/bin/env bash
# =============================================================================
# CS-NocoDB backup round trip, cluster stack - shared helpers (sourced)
# =============================================================================
# Used by seed.sh, mutate.sh and check.sh in this directory. The cluster round
# trip starts docker-compose.cluster.yml - HAProxy, nocodb-server-1..N and the
# Redis they share - with docker-compose.ci.yml from this directory merged over
# it, and restores while every instance keeps running.
#
# It reuses the single-instance scripts one directory up and points them at
# the cluster: API calls go through the load balancer, as users and the
# sidecar's REST export reach NocoDB, and the data volume is read through
# nocodb-server-1 - every instance mounts the same one.
# =============================================================================

export NOCODB_API_SERVICE=loadbalancer
export NOCODB_FILES_SERVICE=nocodb-server-1
# shellcheck source=tests/backup-roundtrip/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/../common.sh"

# The attachment field seed.sh creates. mutate.sh drops it: NocoDB keeps every
# table's column list in the Redis cache the instances share, so after the
# restore only an emptied cache makes running instances see the field again.
# shellcheck disable=SC2034
ATTACHMENT_FIELD="Files"

# What mutate.sh records for the check after the restore: the container and
# start time of every instance, and a key in the instances' Redis database
# (NC_REDIS_URL, database 0) that only a flush of that database removes.
# shellcheck disable=SC2034
INSTANCES_FILE="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/nocodb-roundtrip-${ROUNDTRIP_MARKER}.instances"
# shellcheck disable=SC2034
SENTINEL_KEY="roundtrip:${ROUNDTRIP_MARKER}"

# The NocoDB instances of the active configuration, one per line:
# nocodb-server-1 to -4, -6 or -8 depending on the scale profile.
nocodb_instances() {
  local services
  services=$(docker compose config --services)
  grep -E '^nocodb-server-[0-9]+$' <<< "$services" | sort -V
}

# One "service container-id started-at" line per instance. Recreating or
# restarting an instance changes its line.
instance_containers() {
  local instances service id started
  instances=$(nocodb_instances)
  while IFS= read -r service; do
    id=$(docker compose ps --quiet "$service" < /dev/null)
    [ -n "$id" ] || { echo "$service has no running container" >&2; return 1; }
    started=$(docker inspect --format '{{.State.StartedAt}}' "$id" < /dev/null)
    echo "$service $id $started"
  done <<< "$instances"
}

# redis-cli against the Redis the instances share.
nc_redis() {
  docker compose exec -T redis-server redis-cli "$@" < /dev/null
}
