# cicd

> **Status:** `ACTIVE`

The CI machine of the samirhvbr fleet, as code and documentation: what it is, what runs on it,
and everything needed to build a new one from zero.

It is one Debian VM, inside the office network, that runs the fleet's CI so that a repository's
tests do not depend on the account's GitHub-hosted minutes. Four things run on it:

| Component | What it does | Folder | Page |
|---|---|---|---|
| **Runners** | GitHub Actions self-hosted runners, one per repository, label `shvia-ci`. A repository opts in with the variable `CI_RUNNER` | — (installed from GitHub's release) | [docs/runners.md](docs/runners.md) |
| **Watcher** (`cicd-vigia`) | Runs the same `.github/workflows/` with [`act`](https://github.com/nektos/act), triggered from this machine, and posts each job's result to GitHub as a commit status. For when GitHub Actions does not hand out jobs at all | [`watcher/`](watcher/) | [docs/watcher.md](docs/watcher.md) |
| **Dashboard** (`cicd-painel`) | A read-only page on port 8080: what is running now, the queue, the numbers of the period, the machine's load and disks | [`dashboard/`](dashboard/) | [docs/dashboard.md](docs/dashboard.md) |
| **Cleanup** | Timers that keep Docker and the runners' work folders from filling the disks, and a disk guard that frees space in a safe order | [`cleanup/`](cleanup/) | [docs/cleanup.md](docs/cleanup.md) |

```
                 GitHub (code, pull requests, Releases, commit statuses)
                   ▲    │ jobs (when Actions works)        ▲
      statuses/API │    ▼                                  │ API, read-only
 ┌─────────────────┴──────────────────────────────────────┴───────────────┐
 │ cicd (Debian 13 VM)                                                     │
 │                                                                         │
 │  actions.runner.<owner>-<repo>.cicd-<name>.service   (user runner)      │
 │  cicd-vigia.service ── act ── Docker ── job containers (user runner)    │
 │  cicd-painel-coletor.timer ──► /var/lib/cicd-painel ◄── cicd-painel-web │
 │  cicd-{volume,container,cache}-prune.timer · cicd-disk-guard.timer      │
 │                                                                         │
 │  /var/lib/containerd · /var/lib/docker · /srv/runners   (data volumes)  │
 └─────────────────────────────────────────────────────────────────────────┘
                   ▲ http://<host>:8080/   (office network, no login)
```

## Build a new machine

**[docs/install.md](docs/install.md)** — from an empty VM to a machine running all four
components, step by step, with the source each step was taken from.

## This installation

| | |
|---|---|
| Machine | `cicd` — a Debian 13 VM on the office Proxmox, 8 vCPU, 16 GB RAM, a 60 GB system disk and a 320 GB data disk |
| Address | `100.64.100.240` — office network only. RFC 6598 shared space: not routable from the internet |
| Access | `ssh samir@100.64.100.240` — the owner's user, with `sudo` |
| Dashboard | `http://100.64.100.240:8080/` — read-only, no login. Watcher logs at `/vigia/` |
| In service since | 28/09/2026 (runners) · 27/10/2026 (watcher) |

Publishing the address and the SSH user is the owner's decision of 07/10/2026
([repodocs ADR-030](https://github.com/samirhvbr/repodocs/blob/master/docs/decisions.md)): the
address is internal, so what is published is topology, not a route. The SSH key, the GitHub
tokens and the runners' registration tokens are never written down — see
[docs/security.md](docs/security.md#0-this-machine).

What the machine looks like, measured read-only on 27/10/2026, is in
[docs/install.md](docs/install.md#what-the-running-machine-looks-like).

## 🔴 Before anything else

- **A job on this machine is root on a machine inside the office network.** The runners and the
  watcher run as `runner`, which has passwordless `sudo` and the `docker` group. That is
  acceptable only because the VM does nothing else. Never put a service, a credential or a
  checkout that matters on it.
- **A self-hosted runner does not survive a locked GitHub account.** GitHub is what hands a job to
  a runner; on 26/10/2026 the account was locked for billing and the idle runners here received
  nothing. The watcher exists for that case ([docs/watcher.md](docs/watcher.md)).
- **The dashboard has no login.** Port 8080 is for the office network only.

## Repository layout

| Path | What it is |
|---|---|
| [docs/](docs/README.md) | **The record** — install, runners, dashboard, cleanup, watcher, operations, decisions, security |
| [dashboard/](dashboard/) | The dashboard: `coletor.py` (collector), `index.html` (the page), its systemd units and `instalar.sh` |
| [cleanup/](cleanup/) | The prune timers and the disk guard (`cicd-disk-guard.sh`) |
| [watcher/](watcher/) | The watcher: `vigia.py`, its unit, the example `repos.json`, `image/Dockerfile` and `instalar.sh` |
| [host/](host/) | Host configuration that is not a service: Docker's `daemon.json`, the runner's sudoers drop-in, the weekly cleanup cron |
| [tests/](tests/) | Rulers for the cleanup scripts and the dashboard's collector: each runs the real code against fakes and shows that its mutants are caught |
| [deploy.sh](deploy.sh) | Updates the machine from its clone at `/srv/cicd`: the rulers first, then the installers of what changed ([operations.md](docs/operations.md#updating-what-is-installed)) |
| [.continue/](.continue/README.md) | **The queue** — what is still open, and whose call it is |
| [CHANGELOG.md](CHANGELOG.md) | **The history** — newest first; each heading is a commit subject |
| [version.md](version.md) | **The single authority on the version.** Every bump becomes a tag and a published Release |

The installed names stay Portuguese where the machine already uses them — `/opt/cicd-painel`,
`cicd-vigia.service`, `coletor.py`, `instalar.sh` — so that a reinstall from this repository
replaces files in place instead of leaving a second copy beside the first.

## Tests

```bash
node tests/disk-guard.test.mjs
node tests/container-prune.test.mjs
```

Each prints a JSON verdict and exits 0 only when the script under test is correct **and** every
mutant of it is caught. They need `bash`, `git`, `python3` and Node 20+, and touch nothing
outside a temporary folder.

## Where this came from

Until 27/10/2026 all of this lived in `samirhvbr/shvia-web`, under `deploy/servidor-cicd.md` and
`deploy/cicd-*`, because the machine was first built for that repository's CI. It serves the
whole fleet now, so it moved here ([ADR-001](docs/decisions.md)). The watcher was copied from
shvia-web pull request #607 at `44a323b3`, still under review there on the day of the move.

## Contributing

```bash
git pull
git config core.hooksPath tools/git-hooks   # once per clone
```

Write the `CHANGELOG.md` entry, bump `version.md` in the same commit, and commit with the entry's
heading as the subject — `0.1.1 - short description`. Rules:
[docs/versioning.md](docs/versioning.md).

## Standard

The documentation structure of this repository comes from the fleet standard at
[samirhvbr/repodocs](https://github.com/samirhvbr/repodocs). The norm itself lives there and is
deliberately **not** copied here, so there is one place to change it.

## Language

English (US) for everything in the repository — documents, commit messages, pull requests,
issues, code comments. **End-user-facing strings** may stay Portuguese for the Brazilian
audience: the dashboard's page is in Portuguese. **`.continue/` drafts** use the author's working
language. See
[conventions.md §8](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md#8-language).

## License

MIT — see [LICENSE](LICENSE).
