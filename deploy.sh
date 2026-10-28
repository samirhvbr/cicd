#!/usr/bin/env bash
# Brings the cicd machine up to date with this repository (docs/operations.md, "Updating what is
# installed"). Same shape as the fleet's other deploy.sh: runs ON the machine, as root, from a clone of
# this repository; leaves early when there is nothing new; one deploy at a time; git runs as the clone's
# owner, never as root; a failure puts back what was installed before.
#
#   sudo bash /srv/cicd/deploy.sh                    # origin/master
#   sudo bash /srv/cicd/deploy.sh --branch <name>    # a pull request's branch, to see it before the merge
#   sudo bash /srv/cicd/deploy.sh --force            # reinstall even with nothing new
#
# First time on the machine (the repository is public, so no key is needed):
#   sudo install -d -o samir -g samir /srv/cicd && git clone https://github.com/samirhvbr/cicd.git /srv/cicd
#
# What it installs, by what changed since the last deploy (all of it on the first one):
#   dashboard/   bash dashboard/instalar.sh, then one snapshot, checked
#   cleanup/     the scripts, units and timers (docs/cleanup.md, "The layers")
#   watcher/     NEVER by itself: the machine runs a newer vigia.py than this repository until shvia-web
#                #607 lands here (.continue/README.md), and installing this one would downgrade it. It
#                also restarts the watcher, which kills the builds running. --watcher does it, and
#                refuses while a build runs.
#   host/        never: Docker's daemon.json and the sudoers drop-in are applied by hand (docs/install.md)
#
# Before installing anything, the repository's rulers run (tests/*.test.mjs). A red ruler installs
# nothing. The Release is not made here: it belongs to the CI (version.md, docs/versioning.md).
set -euo pipefail
# The whole script is one block, read to its end before it runs: it checks out another version of this
# very file, and bash reads a script as it goes, so without the block it would carry on in the new text.
{

DIR="$(cd "$(dirname "$0")" && pwd)"
LOCK=/run/cicd-deploy.lock
STATE_DIR=/var/lib/cicd-deploy
STATE="$STATE_DIR/deployed"        # the commit last deployed: what "changed" is measured against
BUILDS=/var/lib/cicd-painel/www/vigia/builds.json

BRANCH=master
FORCE=0
WATCHER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --branch) BRANCH="${2:?--branch needs a name}"; shift ;;
    --force) FORCE=1 ;;
    --watcher) WATCHER=1 ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

log() { printf '[%(%H:%M:%S)T] %s\n' -1 "$*"; }
die() { log "❌ $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || { printf 'run as root: sudo bash %s\n' "$0" >&2; exit 1; }
exec 9>"$LOCK"
flock -n 9 || die "another deploy is running (lock: $LOCK)"

OWNER="$(stat -c %U "$DIR")"
asowner() { if [ "$(id -un)" = "$OWNER" ]; then "$@"; else sudo -u "$OWNER" "$@"; fi; }
cd "$DIR"
[ -f dashboard/instalar.sh ] || die "$DIR is not a clone of samirhvbr/cicd"

# A deploy clone holds no work: a local change would be deployed without being in any commit.
asowner git diff --quiet && asowner git diff --cached --quiet || die "the clone at $DIR has local changes; it must be clean"

log "==> fetching origin/$BRANCH"
asowner git fetch -q origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" || die "git fetch failed"
NEW="$(asowner git rev-parse "origin/$BRANCH")"
OLD="$(cat "$STATE" 2>/dev/null || true)"
if [ -n "$OLD" ] && ! asowner git cat-file -e "$OLD^{commit}" 2>/dev/null; then
  log "⚠️  the last deployed commit ${OLD:0:8} is not in this clone: everything is reinstalled"
  OLD=""
fi
if [ "$OLD" = "$NEW" ] && [ "$FORCE" = 0 ]; then
  log "✓ $(asowner git log -1 --format='%h %s' "$NEW") is already deployed. (--force reinstalls it)"
  exit 0
fi

PREV="$(asowner git rev-parse HEAD)"
asowner git checkout -q --detach "$NEW"
log "==> $(asowner git log -1 --format='%h %s')"

# ── The rulers, before anything is installed ─────────────────────────────────────────────────────
for t in tests/*.test.mjs; do
  if ! asowner node "$t" >/dev/null 2>&1; then
    asowner git checkout -q --detach "$PREV"
    die "ruler $t is red: nothing was installed (run it: node $t)"
  fi
done
log "  ✓ rulers green: $(ls tests/*.test.mjs | xargs -n1 basename | tr '\n' ' ')"

# ── What changed ─────────────────────────────────────────────────────────────────────────────────
if [ -n "$OLD" ] && [ "$FORCE" = 0 ]; then
  changed() { ! asowner git diff --quiet "$OLD" "$NEW" -- "$@"; }
else
  changed() { true; }
fi

install_dashboard() {
  bash dashboard/instalar.sh >/dev/null
  # instalar.sh takes one snapshot; a collector that fails shows here, not 30 s later in the journal.
  systemctl is-active --quiet cicd-painel-web.service || return 1
  systemctl start cicd-painel-coletor.service || return 1
  curl -fsS -m 10 -o /dev/null http://127.0.0.1:8080/estado.json || return 1
}
install_cleanup() {
  install -m 755 cleanup/cicd-container-prune.sh cleanup/cicd-disk-guard.sh /usr/local/sbin/
  install -m 644 cleanup/*.service cleanup/*.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now cicd-volume-prune.timer cicd-container-prune.timer cicd-cache-prune.timer cicd-disk-guard.timer >/dev/null 2>&1
}
install_watcher() { bash watcher/instalar.sh; }

INSTALLED=()
run_all() {
  for c in "${TODO[@]}"; do
    log "==> installing $c"
    "install_$c" || return 1
    INSTALLED+=("$c")
  done
}

TODO=()
changed dashboard && TODO+=(dashboard)
changed cleanup && TODO+=(cleanup)
if changed watcher; then
  if [ "$WATCHER" = 1 ]; then
    if [ -r "$BUILDS" ] && grep -q '"estado": "rodando"' "$BUILDS"; then
      asowner git checkout -q --detach "$PREV"
      die "--watcher: a build is running, and restarting the watcher would kill it; try again when /vigia/ shows none"
    fi
    TODO+=(watcher)
  else
    log "⚠️  watcher/ changed and was NOT installed (the machine's vigia.py is newer; see the header). --watcher installs it"
  fi
fi
changed host && log "⚠️  host/ changed: it is applied by hand (docs/install.md)"

if [ ${#TODO[@]} -eq 0 ]; then
  log "✓ nothing installable changed"
elif ! run_all; then
  # Put back what was there: the same installers, from the commit deployed before. A first deploy
  # has none, and says so.
  log "❌ installing ${TODO[${#INSTALLED[@]}]} failed"
  if [ -n "$OLD" ]; then
    asowner git checkout -q --detach "$OLD"
    TODO=("${INSTALLED[@]}" "${TODO[${#INSTALLED[@]}]}")
    INSTALLED=()
    run_all && log "  ✓ ${OLD:0:8} reinstalled" || log "  ❌ reinstalling ${OLD:0:8} failed too: fix it by hand"
  else
    log "  no earlier deploy to go back to: fix it by hand"
  fi
  exit 1
fi

install -d -m 755 "$STATE_DIR"
printf '%s\n' "$NEW" > "$STATE"
log "✅ deployed $(asowner git log -1 --format='%h %s')${TODO[*]:+ — ${TODO[*]}}"
exit 0
}
