#!/bin/bash
# Frees disk on the CI machine while a volume is filling, instead of waiting for the daily prunes.
#
# Measured on 15/10/2026: `/var/lib/docker` reached 100% (7.7 MB free) with 58 containers running, and every
# job that started MariaDB or Postgres would have failed with a disk error that reads like a code defect. The
# biggest items were not the SHVIA suites: two runner volumes of another repository (`tura-ci-1`, `tura-ci-2`)
# held 12 and 13 GB, almost all of it `_work/<repo>/<repo>/target/debug`. A self-hosted runner keeps its work
# folder between jobs, so build output only grows: on 13/10 those two volumes were 5.7 GB each, two days
# later 12 and 13. The daily prunes (containers 03:30, cache 03:40) and the hourly volume prune never touch a
# runner's work folder, and a day is longer than the fill took.
#
# It does not look for one project. It looks at TWO places, whatever fills them:
#   - ALVO (`/var/lib/docker`): Docker's leftovers, and the work folders of runners that live in Docker volumes;
#   - RUNNERS (`/srv/runners`): the work folders of the runners installed on the machine (web, code, sshvterm-*…).
# Every INTERVAL the timer runs this. Below ALTO percent in a place it does nothing there. Above it, it frees
# space in order, the cheapest and most certainly safe first, and stops as soon as the place is below ALTO:
#   1. (Docker only) `docker volume prune`, `docker image prune` (dangling), `docker builder prune` (24 h old);
#   2. `target/debug/incremental` of each idle runner's checkout (a Rust build's cache: never correctness);
#   3. only from CRITICO percent: `git clean -fdX` of each idle runner's checkout, the biggest first. It removes
#      exactly what the project's own `.gitignore` names (target, node_modules, build, caches), never a tracked
#      file and never an untracked file the project did not ignore. The next job rebuilds from zero.
# A runner is idle when no `Runner.Worker` is running for it: that process exists for exactly as long as a job
# runs. If the question cannot be answered the runner counts as busy. A path is touched only when it is its own
# canonical form: a link anywhere in it (a `target/debug` that points elsewhere) and the glob's reach through
# it are left alone.
# If a place is still at CRITICO percent after everything, it exits 1 and names what holds the space, so the
# owner does not have to start with `du`: the journal and `systemctl --failed` show it.
#
# ⚠️ For the CI machine only. It deletes build output inside runners' work folders.
#
# Usage: cicd-disk-guard.sh [--dry-run]
#        (ALVO=/var/lib/docker RUNNERS=/srv/runners ALTO=75 CRITICO=85 cicd-disk-guard.sh)
set -uo pipefail

ALVO="${ALVO:-/var/lib/docker}"
RUNNERS="${RUNNERS:-/srv/runners}"
ALTO="${ALTO:-75}"
CRITICO="${CRITICO:-85}"
SECO=0
[[ "${1:-}" == "--dry-run" ]] && SECO=1

uso() { df --output=pcent "$1" 2>/dev/null | tail -1 | tr -dc '0-9'; }
abaixo() { [[ "$(uso "$1")" -lt "$ALTO" ]]; }

acao() {
  # Runs a command, or only says it would, in a dry run.
  if [[ $SECO -eq 1 ]]; then echo "dry run: $*"; else "$@" >/dev/null 2>&1 || true; fi
}

# --- Is the runner of this work folder running a job? 0 = idle, 1 = busy or unknown.
ocioso_docker() {
  # $1 = the Docker volume name.
  local ids id saida
  ids="$(docker ps -q --filter "volume=${1}" 2>/dev/null)" || return 1
  for id in $ids; do
    # `docker top` needs the pid column: with only `comm` it answers "Couldn't find PID field in ps output".
    if saida="$(docker top "$id" -eo pid,comm 2>/dev/null)"; then
      grep -q 'Runner\.Worker' <<<"$saida" && return 1
    else
      return 1
    fi
  done
  return 0
}

ocioso_nativo() {
  # $1 = the runner's folder, e.g. /srv/runners/web.
  local saida
  saida="$(ps -eo args= 2>/dev/null)" || return 1
  grep -qF "${1}/bin/Runner.Worker" <<<"$saida" && return 1
  return 0
}

ocioso() {
  # $1 = docker|nativo, $2 = a checkout path. The unit is the first folder below the place's root.
  local resto
  if [[ "$1" == docker ]]; then
    resto="${2#"${ALVO}"/volumes/}"
    ocioso_docker "${resto%%/*}"
  else
    resto="${2#"${RUNNERS}"/}"
    ocioso_nativo "${RUNNERS}/${resto%%/*}"
  fi
}

# --- The checkouts of a place: `.git` present, not a link, and its own canonical form.
checkouts() {
  # $1 = docker|nativo. Prints one path per line.
  local d raiz real
  shopt -s nullglob
  if [[ "$1" == docker ]]; then
    raiz="$(realpath -e -- "$ALVO")" || return 0
    for d in "${ALVO}"/volumes/*/_data/_work/*/*; do
      [[ -d "$d/.git" && ! -L "$d" ]] || continue
      real="$(realpath -e -- "$d")" || continue
      [[ "$real" == "${raiz}/${d#"${ALVO}"/}" ]] || { echo "cicd-disk-guard: ${d#"${ALVO}"/volumes/} goes through a link, leaving it alone" >&2; continue; }
      echo "$d"
    done
  else
    raiz="$(realpath -e -- "$RUNNERS")" || return 0
    for d in "${RUNNERS}"/*/_work/*/*; do
      [[ -d "$d/.git" && ! -L "$d" ]] || continue
      real="$(realpath -e -- "$d")" || continue
      [[ "$real" == "${raiz}/${d#"${RUNNERS}"/}" ]] || { echo "cicd-disk-guard: ${d#"${RUNNERS}"/} goes through a link, leaving it alone" >&2; continue; }
      echo "$d"
    done
  fi
}

podar_incremental() {
  # $1 = kind, $2 = the place's root. Returns 0 as soon as the place is below ALTO.
  local d alvo real
  while IFS= read -r d; do
    alvo="${d}/target/debug/incremental"
    [[ -d "$alvo" && ! -L "$alvo" ]] || continue
    # The glob and the checkout test do not see a link INSIDE the checkout (`target/debug` pointing elsewhere).
    real="$(realpath -e -- "$alvo")" || continue
    [[ "$real" == "$(realpath -e -- "$d")/target/debug/incremental" ]] || { echo "cicd-disk-guard: ${alvo#"${2}"/} goes through a link, leaving it alone" >&2; continue; }
    if ! ocioso "$1" "$d"; then
      echo "cicd-disk-guard: ${d#"${2}"/} has a job running, leaving it alone"
      continue
    fi
    echo "cicd-disk-guard: removing ${alvo#"${2}"/}"
    if [[ $SECO -eq 1 ]]; then echo "dry run: rm -rf ${alvo}"; else rm -rf -- "$alvo"; fi
    abaixo "$2" && return 0
  done < <(checkouts "$1")
  return 1
}

limpar_ignorados() {
  # $1 = kind, $2 = the place's root. `git clean -fdX`, the biggest idle checkout first.
  local d
  while IFS= read -r d; do
    if ! ocioso "$1" "$d"; then
      echo "cicd-disk-guard: ${d#"${2}"/} has a job running, leaving it alone"
      continue
    fi
    echo "cicd-disk-guard: cleaning what is ignored in ${d#"${2}"/}"
    if [[ $SECO -eq 1 ]]; then
      echo "dry run: git -C ${d} clean -fdX"
    else
      git -c safe.directory='*' -C "$d" clean -fdXq >/dev/null 2>&1 || true
    fi
    abaixo "$2" && return 0
  done < <(checkouts "$1" | while IFS= read -r d; do printf '%s\t%s\n' "$(du -xs "$d" 2>/dev/null | cut -f1)" "$d"; done | sort -rn | cut -f2-)
  return 1
}

quem_ocupa() {
  # What holds the space, for the owner: the five biggest folders of the place.
  if [[ "$1" == docker ]]; then
    du -xsh "${ALVO}"/volumes/* 2>/dev/null | sort -rh | head -5
  else
    du -xsh "${RUNNERS}"/*/_work 2>/dev/null | sort -rh | head -5
  fi
}

cuidar() {
  # $1 = docker|nativo, $2 = the place's root. Returns 0 ok, 1 still critical, 2 could not measure.
  local kind="$1" raiz="$2" ini fim
  if [[ ! -d "$raiz" ]]; then
    echo "cicd-disk-guard: ${raiz} does not exist here, skipping"
    return 0
  fi
  ini="$(uso "$raiz")"
  if [[ -z "$ini" ]]; then
    echo "cicd-disk-guard: could not read the usage of ${raiz}" >&2
    return 2
  fi
  if [[ "$ini" -lt "$ALTO" ]]; then
    echo "cicd-disk-guard: ${raiz} at ${ini}% (below ${ALTO}%), nothing to do"
    return 0
  fi
  echo "cicd-disk-guard: ${raiz} at ${ini}% (limit ${ALTO}%), freeing space"

  if [[ "$kind" == docker ]]; then
    acao docker volume prune -f
    abaixo "$raiz" && { echo "cicd-disk-guard: ${raiz} at $(uso "$raiz")% after the volume prune"; return 0; }
    acao docker image prune -f
    abaixo "$raiz" && { echo "cicd-disk-guard: ${raiz} at $(uso "$raiz")% after the image prune"; return 0; }
    acao docker builder prune -f --filter until=24h
    abaixo "$raiz" && { echo "cicd-disk-guard: ${raiz} at $(uso "$raiz")% after the build cache prune"; return 0; }
  fi

  podar_incremental "$kind" "$raiz" && { echo "cicd-disk-guard: ${raiz} at $(uso "$raiz")% after the incremental builds"; return 0; }
  if [[ "$(uso "$raiz")" -ge "$CRITICO" ]]; then
    limpar_ignorados "$kind" "$raiz" && { echo "cicd-disk-guard: ${raiz} at $(uso "$raiz")% after cleaning what the projects ignore"; return 0; }
  fi

  fim="$(uso "$raiz")"
  if [[ $SECO -eq 1 ]]; then
    echo "cicd-disk-guard: dry run finished, nothing was removed (${raiz} at ${fim}%)"
    return 0
  fi
  if [[ "$fim" -ge "$CRITICO" ]]; then
    {
      echo "cicd-disk-guard: ${raiz} is still at ${fim}% after everything it may remove. What holds it:"
      quem_ocupa "$kind" | sed 's/^/    /'
      if [[ "$kind" == docker ]]; then
        echo "  Grow the volume (sudo lvextend -r -L +20G /dev/vg_cicd/docker) or look at: docker system df -v"
      else
        echo "  Grow the volume or look at the folders above."
      fi
    } >&2
    return 1
  fi
  echo "cicd-disk-guard: ${raiz} at ${fim}%, still above ${ALTO}% but below ${CRITICO}%"
  return 0
}

pior=0
cuidar docker "$ALVO"; r=$?; [[ $r -gt $pior ]] && pior=$r
cuidar nativo "$RUNNERS"; r=$?; [[ $r -gt $pior ]] && pior=$r
exit "$pior"
