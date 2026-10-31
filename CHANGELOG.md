# Changelog

Entries in the commit-message format (`version - short description in English`,
see [docs/versioning.md](docs/versioning.md)), newest first. **Each `##` heading
is literally the commit subject** — the entry is written *before* the commit, so
the sentence that lands in `git log` is one that was weighed rather than
improvised at `git commit` time.

Bodies are narrative: what changed, why, and what was measured. This file is
never rewritten.

## 0.1.4 - Show a job act skips as skipped, not as running

On 31/10/2026 shvia-desktop's master build #90 showed `Platforms/macOS` and `Platforms/Windows MSVC`
as running, with no step. They would have stayed that way until the build ended. act does not run a
macOS or Windows job on this machine. For each one it writes a single line, `🚧  Skipping unsupported
platform`, and never the `🏁` the collector waited for. That line now ends the job as `skipped`,
which the page shows grey, like a GitHub job whose `if:` was false. The ruler has a twelfth mutant
for it, and it is caught.

## 0.1.3 - Show each watcher job's step and expected length on the dashboard

Once 0.1.1 was installed, the owner noticed what was missing: a GitHub job used to show its step,
a progress bar and a time estimate, and a watcher build showed one line, "act", with the time since
it was queued. The watcher writes act's output as it runs, one line per event, each prefixed with
its job. That output already has everything the old view showed. A step starts with `⭐ Run`, ends
with its duration, and the job ends with `🏁`.

The collector now reads the live log of every running build. Each job of a build becomes its own
line again, with its step and its state; a finished job gets its result, and shvia-web's
`assunto` turns grey as it did. The total steps and the typical length of each job come from the
repository's last five finished logs where that job succeeded. Each of those logs is read once and
cached in `meta`. Measured on the machine's logs of 28/10: shvia-web's `CI/test` reads "passo
16/20: Testes (php artisan test)", typical ~50 min over 4 green runs.

Reading the log also fixed a wrong state. Build #29 had been "rodando" for 45 minutes with no log:
it was waiting for #28 to release the lock on the `CI/test` job name. A build in that state is now
shown queued. The ruler covers all of this with four more mutants, 11 in all, and all of them are
caught. The page was rendered in headless Chrome against the machine's real logs, not only parsed.

## 0.1.2 - Update the machine from its own clone with deploy.sh

Installing 0.1.1 showed why this was missing. The owner ran the documented `tar | ssh … instalar.sh`
from the workstation's checkout, which was on master at 0.1.0. That reinstalled the old dashboard,
and nothing said so: the page looked exactly as before. The fleet's other projects have a
`deploy.sh` that runs on the server, from a clone, and says what it deployed. This repository now
has one too.

`sudo bash /srv/cicd/deploy.sh [--branch <name>]` fetches the branch and runs the rulers before
installing anything; a red ruler installs nothing. It then runs the installers of the components
that changed since the last deploy, recorded in `/var/lib/cicd-deploy/deployed`, and checks the
dashboard by taking a snapshot. If an installer fails, it puts the previous deploy back. `--branch`
lets a pull request be seen on the machine before its merge. It also leaves two things alone. The
watcher stays as it is: the machine's `vigia.py` (sha256 `63169e60…`) is newer than this
repository's (`04e3e376…`), because shvia-web #607 moved on after the copy, so installing ours would
downgrade it. Restarting the watcher would also kill the builds running, so `--watcher` refuses
while one runs. `host/` stays applied by hand. Measured before writing it: every other installed
unit and script matches this repository, except two comments that still name shvia-web's old paths.
The script is one block, so bash reads all of it before it checks out a new version of the file
it is running.

## 0.1.1 - Show the watcher's builds on the dashboard

On 28/10/2026 the dashboard said "Nada rodando, fila vazia" while the watcher was building three
shvia-web pull requests, and the owner only knew the CI was alive from the watcher's plain list at
`/vigia/`. The page was not stuck: its collector ran every 30 s without an error. It read one source,
GitHub Actions, and since the account was locked for billing on 26/10 every Actions run has zero jobs,
so there was nothing to show and the 13 runners read "livre" for good. The watcher has written
`www/vigia/builds.json` "for the dashboard" since it was installed on 27/10; nothing read it.

The collector now reads it on every snapshot, with no token needed. A running or queued build is a
live run of the workflow `cicd-vigia`, linked to its log; a finished one is recorded once in the
history, with its jobs from the build's `detalhe` and shvia-web's expected `assunto` red applied; the
watcher is listed with the runners and counted in the load samples. Its runs take negative ids, so they
cannot collide with GitHub's run ids, and the page links them to `/vigia/<log>`. `runs` gains a `log`
column, added to an existing database on the first snapshot. `vigia.py` is unchanged: it is still the
copy of shvia-web #607.

Measured against the machine's real `builds.json` of 15:05Z (29 builds): three live runs, 23 recorded
(29 minus the three running, two `ignorado` and one `conflito`). `tests/dashboard-watcher.test.mjs` is
new: it runs the collector twice against every state the watcher writes and an old-schema database,
and catches seven mutants (recording what ran nothing, positive ids, dropping the queue, losing the
expected red, recording twice, no migration, no log in the export). The three rulers pass. The page's
script was parsed but not rendered in a browser here; the installed page is the check, and installing
it is the owner's act (`bash dashboard/instalar.sh`).

## 0.1.0 - Document the cicd machine from an empty VM to a working one

The fleet's CI machine gets its own public repository. Until today its runbook and its code lived
in shvia-web (`deploy/servidor-cicd.md`, `deploy/cicd-painel/`, `deploy/cicd-limpeza/`, and the
watcher in pull request #607), because the machine was first built for that repository's CI. It
runs 13 runners for seven repositories now, so it moved here (ADR-001), split into one page per
component: install, runners, watcher, dashboard, cleanup and operations.

The code came over unchanged except for its references: the dashboard (`dashboard/`), the cleanup
timers and the disk guard (`cleanup/`), and the watcher (`watcher/`, from #607 at `44a323b3`, still
under review there). Three files that existed only on the machine are versioned for the first time
in `host/`: Docker's `daemon.json`, the runner's sudoers drop-in and the weekly cleanup cron, read
from the machine on 27/10/2026. The two rulers of the cleanup scripts came along as
`tests/disk-guard.test.mjs` and `tests/container-prune.test.mjs`; both pass here (the script
correct, every mutant caught), as they did in shvia-web before the copy.

`docs/install.md` is new: the sequence from an empty VM to a working machine, written from the
machine in service and measured read-only the same day. It has not been replayed on a clean VM,
and says so. The measurement also corrected the old runbook in three places — the Docker volume is
50 GB, not 30; there are 13 runners, not 8; Java is installed — and found one runner, `cicd-eop`,
running as the owner's login user with a Portuguese locale, which `docs/security.md §0` and the
queue record for the owner to fix.

