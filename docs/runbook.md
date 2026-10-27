# Runbook — cicd

> **Status:** `ACTIVE` · §§1–4 point at the pages that hold the machine's procedures; §§5–7 are
> the repository's own maintenance and release checks, inherited from the fleet standard.

## 1. Requirements

A Debian 13 VM with a separate data disk, Docker Engine, `gh`, `act`, and admin on the
repositories that get a runner: [install.md §0](install.md#0-what-you-need).

## 2. Installation

[install.md](install.md), from an empty VM to a working machine. To work on this repository
itself:

```bash
git clone git@github.com:samirhvbr/cicd.git
cd cicd
git config core.hooksPath tools/git-hooks   # once per clone — see §5
node tests/disk-guard.test.mjs && node tests/container-prune.test.mjs
```

## 3. Configuration

| What | Where | Secret |
|---|---|---|
| Docker logging | `/etc/docker/daemon.json` ([`host/daemon.json`](../host/daemon.json)) | no |
| Each runner's environment | `/srv/runners/<short>/.env` — `runner=self-hosted`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8` | no |
| Which repositories the watcher builds | `/etc/cicd-vigia/repos.json` (example: [`watcher/repos.json`](../watcher/repos.json)); never overwritten by a reinstall | no |
| The dashboard's token | `/etc/cicd-painel/token` | **yes** — the owner's, [dashboard.md](dashboard.md#the-token) |
| The watcher's token | `/etc/cicd-vigia/token` | **yes** — the owner's, [watcher.md](watcher.md#installing-and-switching-a-repository-on) |
| A runner's registration | `/srv/runners/<short>/.credentials`, `.runner` | **yes** — written by `config.sh` |

## 4. Deploy

There is no automatic deploy of this repository to the machine. A change reaches it when someone
runs the component's installer from a clone at the new version:
[operations.md, "Updating what is installed"](operations.md#updating-what-is-installed). Each
installer is idempotent.

## 5. The git hooks

Once per clone — yours, and every collaborator's:

```bash
git config core.hooksPath tools/git-hooks
```

Check the hook directly, without creating commits. Run from the repository
root, outside a merge, with the hook's escape variable unset. `version.md` must
already be in the index; stage it during initial bootstrap. The accepted subject
uses that indexed version, including when a different version is unstaged.

```bash
(
  set -euo pipefail
  hook_version="$(git show :version.md | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | sed -n '1p')"
  test -n "$hook_version"
  hook_other_version=0.0.0
  if [ "$hook_version" = "$hook_other_version" ]; then hook_other_version=0.0.1; fi
  hook_message="$(mktemp)"
  trap 'rm -f "$hook_message"' EXIT

  printf '%s\n' 'feat: a hook validation subject' > "$hook_message"
  if bash tools/git-hooks/commit-msg "$hook_message"; then
    echo 'ERROR: the hook accepted a Conventional Commits prefix' >&2
    exit 1
  fi
  printf '%s - a hook validation subject\n' "$hook_other_version" > "$hook_message"
  if bash tools/git-hooks/commit-msg "$hook_message"; then
    echo 'ERROR: the hook accepted a version absent from the index' >&2
    exit 1
  fi
  printf '%s - a hook validation subject\n' "$hook_version" > "$hook_message"
  bash tools/git-hooks/commit-msg "$hook_message"
  echo 'commit-msg: expected rejection and acceptance checks passed; no commit created'
)
```

Rename `HOOK_ESCAPE_VAR` at the top of each hook to `CICD_NO_HOOK`.
Rules: [versioning.md](versioning.md).

## 6. Pre-flight before making a repository public

A private repository accumulates content that assumed privacy. Before flipping
visibility:

- [ ] `git log -p | grep -iE 'password|secret|token|api[_-]?key'` — scan the
      **history**, not just the working tree. A secret removed from HEAD is
      still in every clone.
- [ ] Any secret ever committed has been **rotated**, not merely deleted.
- [ ] No internal hostname, private IP range or infrastructure path that should
      not be public.
- [ ] `LICENSE` is present and `NOTICE` agrees with it about the license and the
      copyright holder.
- [ ] `SECURITY.md` names a reporting address that is actually monitored.
- [ ] Every prescriptive document declares its status; nothing reads as current
      while describing something abandoned.
- [ ] `.continue/` holds no finished item or detailed record of work that already
      exists. Specifications of unbuilt work stay there, at any length.
- [ ] `README.md` is in English and describes what the project **is**, not what
      it was going to be.
- [ ] No placeholder left over from the skeleton:
      `grep -rn '<[A-Z_]\+>' . --exclude-dir=.git`

## 7. Verifying the repository still conforms

```bash
# the twins are identical below the H1
diff <(tail -n +2 CLAUDE.md) <(tail -n +2 AGENTS.md)

# version.md is a bare X.Y.Z
grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' version.md && echo ok

# settings.json parses
python3 -m json.tool .claude/settings.json > /dev/null && echo ok

# every version in history has a tag and a Release (prints what is missing)
./tools/release.sh --backfill --dry-run
```

If the `diff` on the twins reports anything other than the mirroring comment,
an edit was applied to one file and not the other.
