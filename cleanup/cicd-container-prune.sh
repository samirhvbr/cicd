#!/bin/bash
# Removes the SHVIA test containers a cancelled or crashed CI job left running on `cicd`.
#
# Measured on 13/10/2026: 45 containers labelled `shvia.workspace` alive on the CI machine, the oldest
# 13 days, each a `tail -f /dev/null` with a 3 GB limit. The host-agent suite starts them and its sweeper
# removes only ids with the `test-` prefix; a test that used another id, or a job cancelled before its
# `afterAll`, left them behind. `docker container prune` does not help: they are RUNNING, and the weekly
# `/etc/cron.weekly/cicd-limpeza` (`docker system prune`) only removes stopped ones.
#
# Only containers carrying a `shvia.*` label are considered, and only those created more than
# IDADE_H hours ago (24 by default): a job that is running now started its containers minutes ago.
# ⚠️ For the CI machine only. On a host that serves real workspaces these labels name the users' own
# containers, and this would remove the ones older than a day.
#
# Usage: cicd-container-prune.sh [--dry-run]     (IDADE_H=48 cicd-container-prune.sh)
set -euo pipefail

IDADE_H="${IDADE_H:-24}"
SECO=0
[[ "${1:-}" == "--dry-run" ]] && SECO=1

corte=$(date -u -d "${IDADE_H} hours ago" +%Y-%m-%dT%H:%M:%S)

ids=$({ for rotulo in shvia.workspace shvia.role shvia.sandbox; do docker ps -aq --filter "label=${rotulo}"; done; } | sort -u)

velhos=()
total=0
for id in $ids; do
  total=$((total + 1))
  # `.Created` is UTC and ISO-8601, so comparing the first 19 characters as text orders by time. It is the
  # creation time, not the start time: these containers have restart policy `no`, so it does not move.
  criado=$(docker inspect -f '{{.Created}}' "$id" | cut -c1-19)
  if [[ "$criado" < "$corte" ]]; then
    velhos+=("$id")
  fi
done

echo "cicd-container-prune: ${#velhos[@]} of ${total} shvia.* containers are older than ${IDADE_H}h (cut ${corte}Z)"
if [[ ${#velhos[@]} -eq 0 ]]; then
  exit 0
fi
if [[ $SECO -eq 1 ]]; then
  echo "dry run: would remove ${velhos[*]}"
  exit 0
fi
docker rm -f "${velhos[@]}" >/dev/null
echo "removed ${#velhos[@]}"
