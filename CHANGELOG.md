# Changelog

Entries in the commit-message format (`version - short description in English`,
see [docs/versioning.md](docs/versioning.md)), newest first. **Each `##` heading
is literally the commit subject** — the entry is written *before* the commit, so
the sentence that lands in `git log` is one that was weighed rather than
improvised at `git commit` time.

Bodies are narrative: what changed, why, and what was measured. This file is
never rewritten.

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

