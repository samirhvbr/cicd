# Watcher — `cicd-vigia`: the CI runs here without GitHub Actions

> **Status:** `ACTIVE` · Installed on the machine on 27/10/2026. Source: [`watcher/`](../watcher/),
> copied from shvia-web pull request #607 at `44a323b3`, which was **still under review** on the
> day of the copy. If #607 changes before it lands, this folder is updated from it — there must be
> one source.

> 🔴 **Why: a self-hosted runner does not survive a locked account.** On 26/10/2026 the
> `samirhvbr` account was locked for billing. Measured on 27/10 at 12:15Z: the four `cicd-web`
> runners online and idle, and the push to master of shvia-web created a run with **zero jobs**
> (`startup_failure`). GitHub is what hands a job to a runner, so the runners here waited for work
> that never came. The owner's decision the same day: the CI runs on this machine, **triggered from
> this machine**, and GitHub keeps the code, the pull requests and the Releases.

## What it does

`vigia.py` (Python standard library only, like the dashboard's collector) runs as
`cicd-vigia.service`, user `runner`, and every 60 s:

- reads the open pull requests of each repository switched on in `/etc/cicd-vigia/repos.json`
  (one request, with an ETag) and `git ls-remote` of the default branch;
- builds **only pull requests whose branch lives in the repository itself**. A fork's pull request
  never runs here: its code would run on this machine with the token in reach;
- runs a pull request on GitHub's merge ref (`refs/pull/N/merge`), the tree Actions would have
  tested, and a push to the default branch on that branch;
- executes the repository's existing `.github/workflows/` with
  [`act`](https://github.com/nektos/act) (`/usr/local/bin/act`, 0.2.89). Nothing is rewritten;
- posts each job's result to GitHub as a **commit status** named like the job, linked to its log at
  `http://<host>:8080/vigia/`. `gh pr checks` and `statusCheckRollup` read a commit status like the
  check it replaces, so shvia-web's `aterrissar.sh` keeps working. Measured on 27/10 on shvia-web
  #606: the status API works while Actions is locked.

**The first sight of a repository records its default-branch head without building it**, so
switching a repository on does not run its past (and its Release job) at once. `--backfill`
overrides that.

## Two modes per repository

| `modo` | For | How a job runs |
|---|---|---|
| `vm` | repositories that used the runners (`vars.CI_RUNNER`) | on this machine, as `runner`, like the self-hosted runner did: `-P shvia-ci=-self-hosted --var CI_RUNNER=shvia-ci` |
| `conteiner` | repositories on `ubuntu-latest` | in `shvia/act-ubuntu:24.04`, built here by `instalar.sh` from [`image/Dockerfile`](../watcher/image/Dockerfile): `catthehacker/ubuntu:act-24.04` plus what a workflow needs from GitHub's image |

A job for macOS or Windows maps to no platform and act skips it; `fora` in the config keeps it from
getting a status. **The desktop's macOS job is meant to run on the owner's Mac over SSH, and Windows
MSVC becomes a manual step before a release** (owner's decision, 27/10/2026): that part is not
built yet (the `mac` block in the example config is its placeholder).

## The configuration

[`watcher/repos.json`](../watcher/repos.json) is the example `instalar.sh` installs when
`/etc/cicd-vigia/repos.json` does not exist yet. **The installed file is never overwritten**: which
repositories are on is decided on the machine, one at a time.

| Key | Meaning |
|---|---|
| `dono` | the account the repositories belong to |
| `paralelo` | how many jobs run at once |
| `url_logs` | the base URL of the logs, as linked from each status |
| `repos.<name>.modo` | `vm` or `conteiner` |
| `repos.<name>.ativo` | `false` keeps the repository off. **A repository without the key is on** (`vigia.py` reads `ativo` with a default of `true`); in the example only shvia-desktop is on |
| `repos.<name>.fora` | jobs that get no status (they cannot run here) |
| `repos.<name>.mac` | the planned Mac host for macOS jobs — not built yet |

## What act does differently from GitHub's runner

Each of these was found by a real run on 27/10/2026, and each is handled in `vigia.py` or in the
image:

- 🔴 **`--use-new-action-cache` is required.** `dtolnay/rust-toolchain` regenerates its branches, so
  a pin to one of its commits is no longer the tip of any branch. GitHub serves it by SHA; act's
  default clone does not find it (*"Unable to resolve 4360b52…: reference not found"*).
- **PowerShell.** GitHub's `ubuntu-latest` ships `pwsh`; act's image does not, and shvia-desktop's
  `prova:instaladores-ps1` fails on purpose in CI without it. The image adds it.
- **Database clients.** shvia-web's `test` job waits for MariaDB with `mysqladmin ping` and for
  pgvector with `pg_isready` (*"mysqladmin: command not found"*). The image adds both clients.
- **No init in act's container.** PID 1 is act's placeholder process, which never reaps, so a
  process a test kills becomes a zombie and still "exists". Three PTY tests failed on that.
  `conteiner` jobs run with `--container-options --init`.
- **act names a job's container after the workflow and job names only.** Two pull requests running
  `CI/Provas` at once removed each other's container (*"No such container"*). Same-named jobs, from
  any repository, take turns behind a lock; different jobs still run in parallel.
- **Without `--rm`**, a job that fails leaves its container and its service containers running.
- **`job.services` is empty under act**, so a workflow that reads a service's port from it gets
  nothing; shvia-web reads the port from Docker (`--filter expose=`) instead.
- **A pull request that started to conflict keeps its OLD merge ref.** The watcher asks GitHub for
  `mergeable` first: `false` gets a `cicd-vigia` failure that says to rebase, `null` (still
  computing) waits for the next poll.
- **A job's container must receive a `.git` that git recognises.** A worktree's `.git` is a file
  pointing at a path that does not exist in the container, and a local clone keeps every ref in
  `packed-refs` while act copies files, not empty directories. The watcher builds from a local
  clone (hard-linked objects) with one loose ref, `refs/heads/cicd-vigia`.

## Installing and switching a repository on

1. **`act`**, pinned and checked: [install.md §9](install.md#9-act-and-the-watcher).
2. **The token is the owner's.** A fine-grained token for the repositories the watcher builds,
   with *Contents* read and write (cloning the private ones, tags and Releases), *Commit statuses*
   read and write, *Pull requests* read and *Metadata* read. Typed on the machine, never echoed,
   never in a repository:

   ```bash
   ssh -t samir@100.64.100.240 'read -rsp "token: " T; echo; printf "%s" "$T" | sudo install -m 640 -o root -g runner /dev/stdin /etc/cicd-vigia/token && echo ok'
   ```

3. `bash watcher/instalar.sh` from a clone, on the machine. It starts the service only when the
   token is in place.
4. **A rehearsal first, one repository at a time** — it prints every status instead of posting it:

   ```bash
   sudo -u runner python3 /opt/cicd-vigia/vigia.py --ensaio --uma-vez --config <a copy with one repository on>
   ```

5. Set `"ativo": true` for the repository, `sudo systemctl restart cicd-vigia`, and watch the next
   pull request's checks. Only then switch GitHub Actions off for it
   (`gh api -X PUT repos/<owner>/<repo>/actions/permissions -F enabled=false`) and remove its runner
   service here ([runners.md](runners.md#removing-a-runner)).

Logs: `journalctl -u cicd-vigia -f`, and each job's log at `http://<host>:8080/vigia/`.

## Limits

- **macOS and Windows jobs do not run here** (above).
- **A fork's pull request never runs.** A public repository's outside contributions get no status
  from the watcher.
- **It reports, it does not deploy.** See [operations.md](operations.md#what-this-machine-does-not-do).
