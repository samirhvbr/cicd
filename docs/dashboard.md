# Dashboard — `cicd-painel`

> **Status:** `ACTIVE` · Built 28/09/2026 (shvia-web #388), in service since. Source:
> [`dashboard/`](../dashboard/).

Follow the CI without opening GitHub. The owner asked for it on 28/09/2026, twice: first what is
running, then the numbers, *"to follow the CIs as I centralize them here"*.

## What the page shows

- **The period's numbers** (24 h, 7, 30 or 90 days, each compared with the period before): runs,
  success rate, runner hours, queue wait, run duration, peak of simultaneous jobs.
- **Now:** the runs in progress, each job with its step and a progress bar against the job's
  typical duration (amber past the 90th percentile), and the queue. Every runner, with the job it
  is running.
- **Where the load comes from:** runs per day (by repository or by result), each repository's
  share, a ranking, each runner's occupation, who and what triggers the runs, the hours of the
  week jobs start, the jobs that fail most, the slowest workflows.
- **The machine:** load, memory, the free space of each volume — with a warning at **80%** — and
  the last 24 h of load and running jobs.
- **The recent runs,** with each job's result.

A click on a repository filters the page. Period and filter live in the URL's hash, so a view can
be linked: `#p=30d&repo=samirhvbr/shvia-web`. The page's text is Portuguese (it is read by the
owner); the code and its comments are English.

## How it is built

| Piece | Installed at | Source |
|---|---|---|
| Collector: the GitHub API, `/proc`, and the runners' `.runner` files. Python standard library only | `/opt/cicd-painel/coletor.py`, run by `cicd-painel-coletor.timer` every 30 s | [`coletor.py`](../dashboard/coletor.py), [`cicd-painel-coletor.service`](../dashboard/cicd-painel-coletor.service), [`.timer`](../dashboard/cicd-painel-coletor.timer) |
| History (SQLite) and the ETag cache | `/var/lib/cicd-painel/{historico.db,etags.json}` — **not served** | — |
| The page, the live snapshot, the history export | `/var/lib/cicd-painel/www/{index.html,estado.json,historico.json}` | [`index.html`](../dashboard/index.html) |
| Web server: `python3 -m http.server 8080`, serving `www/` only | `cicd-painel-web.service` | [`cicd-painel-web.service`](../dashboard/cicd-painel-web.service) |
| The token | `/etc/cicd-painel/token`, folder `750 root:painel` | never in a repository |

Both services run as the system user `painel`, with `ProtectSystem=strict`, and write only to
`/var/lib/cicd-painel`. **The jobs run as `runner`, which cannot read the token.** The watcher
writes its logs to `/var/lib/cicd-painel/www/vigia/`, which is why the page serves them at
`/vigia/`.

**Which repositories:** the ones the machine has a runner for, read from each runner's `.runner`
file (`gitHubUrl`). A new runner appears by itself; its runs appear once the token reaches its
repository.

**The watcher is the second source.** Since 26/10/2026 GitHub Actions hands no job to the runners
(the account is locked for billing) and the CI runs in the [watcher](watcher.md). Until 0.1.1 the
page did not know: on 28/10 it said *"Nada rodando, fila vazia"* while the watcher was building three
pull requests, and the 13 runners read "livre" for good. The collector now reads the watcher's
`www/vigia/builds.json` on every snapshot, with no token needed:

- a build `rodando` or `na fila` is a live run of the workflow `cicd-vigia`, with one job `act`
  linked to its log. Its progress bar measures against the repository's typical green build;
- a finished build is recorded once: `passou` → success, `falhou`/`erro` → failure,
  `interrompido` → cancelled. `ignorado` and `conflito` ran nothing and are not recorded. Its jobs
  come from the build's `detalhe` (`provas=success, windows=failure`), and the expected-red rule
  below applies to them;
- the watcher is listed with the runners as `cicd-vigia`, busy while it builds, and its running
  builds count in the load samples.

Its runs share the tables with GitHub's under **negative ids** (`-<build id>`). A GitHub run id is
positive, so the two cannot collide, and the page links a negative id to `/vigia/<log>` instead of
github.com. The `log` column of `runs` exists for these runs only; an older database gets it on the
first snapshot.

**What the watcher's numbers cannot say:** it keeps no time per job, so each job of a build carries
the whole build's start and end. Runner hours and job durations of a watcher build are therefore
approximations (act runs a build's independent jobs in parallel, so the error is small but
present), and there is no queue wait: the build's start is when it was queued.

**The history.** GitHub keeps no cheap history to ask again, so the collector records every
finished run once, with its jobs: runner, result, and when each was queued, started and finished.
It starts on 28/09/2026, the day the first runner went live. Once an hour a paginated pass records
what the 30-run lists missed (the machine was off, the token was missing, a burst of runs). The
page reads `historico.json` — the runs of the last 90 days with a job that ran here — and
aggregates it in the browser; the database keeps everything.

**What it costs in API requests.** The lists go with ETags, and an unchanged list comes back 304,
which does not count against the token's 5,000 requests an hour. Measured on 28/09/2026 with no
run going on: 10 requests per snapshot, all 304. A run in progress costs one request per snapshot
(its jobs, for the step); a finished run costs one request, once. The footer shows what the token
has left.

## Install or update

Idempotent. From a clone of this repository on the machine:

```bash
bash dashboard/instalar.sh
```

Or from your workstation:

```bash
tar -C dashboard -cf - . | ssh samir@100.64.100.240 'd=$(mktemp -d) && tar -xf - -C "$d" && bash "$d/instalar.sh"; rm -rf "$d"'
```

(`scp *` of the folder stopped on a `__pycache__` directory once; `tar` does not.)

## The token

A **fine-grained personal access token** of the repositories' owner, limited to the repositories
with a runner here, with:

- **Actions: read-only** — runs and jobs;
- **Administration: read-only** — GitHub lists self-hosted runners only under Administration.

A fine-grained token only reaches repositories of its owner, so a repository of another account
stays out. **The owner puts it on the machine, typed and never echoed:**

```bash
ssh -t samir@100.64.100.240 'read -rsp "token: " T; echo; printf "%s" "$T" | sudo install -m 640 -o root -g painel /dev/stdin /etc/cicd-painel/token && echo ok'
```

To check it is there, use `sudo test -s /etc/cicd-painel/token`: the folder is `750 root:painel`,
so a plain `test` as the login user says "missing" with the token in place (measured on
28/09/2026). Without a token the page shows the machine and says the GitHub part is missing.

## What the page takes as expected

On shvia-web, a red `assunto` job in a **pull-request** run is shown grey ("sem carimbo") and left
out of the run's verdict and of the success rate: shvia-web stamps the version at landing, and
`assunto` refuses the unstamped subject of an open pull request by design. On a push to master the
same red stays red. The rule lives in `coletor.py` (`esperado`), so the live view and the numbers
agree. It names that repository and that job; a rule for another repository goes next to it.

## Limits

- **No login.** Port 8080 is for the office network. Opening it wider needs authentication first.
- **No disk history.** The database records load and the queue, not disk usage; the peak of the
  13/10/2026 disk incident was not captured ([cleanup.md](cleanup.md#the-disk-that-filled-and-emptied-between-two-prunes)).
- **No organisation runs** yet: a runner registered for an organisation is listed with a warning.
