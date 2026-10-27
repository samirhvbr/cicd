# Cleanup — keeping the disks from filling

> **Status:** `ACTIVE` · Each layer below was added after the disk filled for a reason the
> previous layers did not cover (30/09, 13/10 and 15/10/2026). Source: [`cleanup/`](../cleanup/)
> and [`host/cicd-limpeza`](../host/cicd-limpeza).

**When a job fails at *Initialize containers*, or a database says *"No space left"* / *"error
28"* / *"No more room in record file"*, look at the disk before the code:**

```bash
df -h /var/lib/docker /srv/runners /var/lib/containerd
sudo docker system df
```

## The layers

| Unit | When | What it removes | Added after |
|---|---|---|---|
| `/etc/cron.weekly/cicd-limpeza` | weekly | images, **stopped** containers and build cache older than 7 days | the setup (28/09) |
| `cicd-volume-prune.timer` | hourly | Docker volumes no container references (anonymous only) | 30/09 — 257 orphaned volumes |
| `cicd-container-prune.timer` | daily 03:30 | **running** containers with a `shvia.*` label, created more than 24 h ago | 13/10 — 47 leaked test containers |
| `cicd-cache-prune.timer` | daily 03:40 | build cache unused for 48 h | 13/10 — 12.9 GB of build cache |
| `cicd-disk-guard.timer` | every 15 min | above 75%: Docker leftovers, then Rust incremental caches, then (from 85%) ignored build output of idle runners | 15/10 — another project's `target/` |

Install all of them ([install.md §7](install.md#7-cleanup)):

```bash
sudo install -m 755 host/cicd-limpeza /etc/cron.weekly/cicd-limpeza
sudo install -m 755 cleanup/cicd-container-prune.sh cleanup/cicd-disk-guard.sh /usr/local/sbin/
sudo install -m 644 cleanup/*.service cleanup/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cicd-volume-prune.timer cicd-container-prune.timer cicd-cache-prune.timer cicd-disk-guard.timer
```

## Orphaned volumes — the hourly prune

**Measured on 30/09/2026:** every pull request went red at *Initialize containers*, with MariaDB
saying `preallocating ... failed with error 28` — no space left. `/var/lib/docker` (29 GB then)
was 100% full with **257 volumes, 29.4 GB, none in use**. Each CI job starts MariaDB and pgvector
as service containers whose images declare a `VOLUME`; the runner removes the containers at the
end of the job but **not their anonymous volumes**, so every run left two behind — about 15 GB a
day, two days to fill the volume, and it looked like a broken pull request.

`cicd-volume-prune.timer` runs `docker volume prune -f` every hour. It removes only volumes no
container references, and by default (Docker 23+) only anonymous ones, so a running job's database
is never touched.

## Test containers that outlive their job — the daily prune

**Measured on 13/10/2026:** 47 containers of `node:22.23.2-slim` were alive, the oldest 13 days. 45
carried the label `shvia.workspace=ws1`: a shvia-workspace test sent a **valid** provisioning
request for `ws1` on every run, and `ws1` lacked the `test-` prefix the suite's own sweeper requires
(fixed in shvia-workspace 0.33.8); a job cancelled before its `afterAll` left the rest. They were
RUNNING, so the weekly `docker system prune`, which removes only stopped containers, never touched
them.

`cicd-container-prune.sh` (daily at 03:30) removes the containers that carry a `shvia.*` label
**and** were created more than 24 hours ago, nothing else: other projects' containers have no such
label, and a job running now started its containers minutes ago. `--dry-run` lists what it would
remove.

⚠️ **For a CI machine only:** on a host that serves real workspaces these labels name the users'
own containers.

Ruler: [`tests/container-prune.test.mjs`](../tests/container-prune.test.mjs) runs the script
against a fake `docker` and shows that two mutants of it are caught.

## The disk that filled and emptied between two prunes

shvia-web's master CI of 13/10/2026 failed with `No more room in record file` in the middle of the
suite, and two hours later `/var/lib/docker` was at 51%: it filled and emptied between two hourly
volume prunes. The peak was **not captured** — the dashboard records load and queue, not disk — so
this is what could be measured afterwards, not a proven cause:

| Item | Size | Note |
|---|---|---|
| Docker build cache | 12.9 GB | all reclaimable; the weekly prune kept up to 7 days of it |
| Images | about 12 GB | six of them 1.2 GB layers of one build |
| Volumes | 14.6 GB | two `tura-ci-*` runner volumes of 5.7 GB each and a 3 GB scanner cache; a web job adds two more while it runs |

`cicd-cache-prune.timer` removes build cache unused for 48 hours, daily at 03:40
(`docker builder prune -f --filter until=48h`; a missing cache entry costs rebuild time, never
correctness). The other lever is the volume itself: `sudo lvextend -r -L +20G /dev/vg_cicd/docker`
grows `/var/lib/docker` online, which is how it went from 30 to 50 GB.

## The disk guard

**Measured on 15/10/2026:** `/var/lib/docker` reached **100%** (7.7 MB free) with 58 containers
running. The cause was not the SHVIA suites (their service volumes are 65–185 MB each) and not the
prunes missing: of the 29 GB of volumes, about **24 GB were two runner volumes of another
project** (`tura-ci-1` 12 GB, `tura-ci-2` 13 GB), nearly all `_work/<repo>/<repo>/target/debug`. A
self-hosted runner keeps its work folder between jobs, so a Rust `target/` only grows: two days
earlier the same volumes were 5.7 GB each. Nothing above touches a runner's work folder, and
nothing keeps a Node, Gradle or Tauri build from doing the same, so the guard names no project.

`cicd-disk-guard.sh` runs **every 15 minutes**. It looks at `/var/lib/docker` and `/srv/runners`,
does nothing in a place below **75%**, and above it frees space in this order, stopping as soon as
the place is below 75% again:

1. *(Docker only)* `docker volume prune`, `docker image prune` (dangling only), `docker builder
   prune` (older than 24 h);
2. `target/debug/incremental` of each **idle** runner's checkout — a Rust build's cache: a missing
   one costs rebuild time, never correctness;
3. **only from 85%:** `git clean -fdX` of each idle runner's checkout, biggest first. It removes
   exactly what the project's own `.gitignore` names (`target`, `node_modules`, `build`, caches):
   never a tracked file, never an untracked file the project did not ignore. The next job of that
   checkout builds from zero.

A runner is *idle* when no `Runner.Worker` process is running for it — that process exists for
exactly as long as a job does (`docker top <container> -eo pid,comm` for a runner in a Docker
volume, `ps` for an installed one). A runner whose state cannot be read counts as busy. A path is
touched only when it is its own canonical form, so a `target/debug` that is a link elsewhere is left
alone. If a place is still at 85% or more after all of this, the script **exits 1 and prints the
five biggest folders of the place**, and the service shows in `systemctl --failed`. The dashboard
warns at 80%.

```bash
sudo /usr/local/sbin/cicd-disk-guard.sh --dry-run     # what it would do now; removes nothing
journalctl -u cicd-disk-guard --since today
```

⚠️ **For a CI machine only.** The guard deletes build output inside runners' work folders. Where a
checkout holds something its `.gitignore` names and nobody can rebuild, `git clean -fdX` is the
wrong tool.

Ruler: [`tests/disk-guard.test.mjs`](../tests/disk-guard.test.mjs) runs the script against fakes and
eight mutants; one of them is the `docker top` form the real command refuses, found by running it on
the machine.
