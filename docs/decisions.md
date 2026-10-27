# Decisions (ADR log)

> **Status:** `ACTIVE` · The single, chronological record of decisions taken in
> this repository. Format: Architecture Decision Record.

An ADR records a decision **and the reason it was taken**, so that the next
session does not re-litigate it. A how-to does not argue direction — it links
the ADR.

Numbering is sequential and never reused. A superseded ADR is not deleted: its
status changes to `SUPERSEDED` and it names the ADR that replaced it.

ADR-002 to ADR-004 were taken before this repository existed, in shvia-web and in repodocs; they
are recorded here because this is now where the machine is documented, and each names where it was
first written.

---

## ADR-001 — This repository is the source for the cicd machine

**Status:** `ACCEPTED` · 27/10/2026

**Context.** The machine was built on 28/09/2026 for shvia-web's CI, so its runbook
(`deploy/servidor-cicd.md`) and its code (`deploy/cicd-painel/`, `deploy/cicd-limpeza/`, and the
watcher in pull request #607) lived in shvia-web. By 27/10 it ran 13 runners for seven
repositories of three projects, and repodocs' `docs/ci.md` pointed the whole fleet at a page
inside one application's repository. The runbook had also fallen behind the machine: it said the
Docker volume was 30 GB (it is 50), listed 8 runners (there are 13), and did not mention Java.
The owner asked for a public repository that documents the machine well enough to build a new
one from zero.

**Decision.** `samirhvbr/cicd` is the single source for the machine: its documentation, the
dashboard, the cleanup, the watcher, and the host configuration that was only on the machine
(`daemon.json`, the runner's sudoers drop-in, the weekly cleanup cron). The copies in shvia-web
become a pointer here, and repodocs' `docs/ci.md` and `CICD-RULE` link here.

**Consequences.** One place to change the machine, and a public one. Until shvia-web replaces its
copies with a pointer, **there are two copies and they can drift** — that replacement is the first
follow-up in the [queue](../.continue/README.md). Code that names a shvia repository (the
`assunto` rule in the dashboard, the `shvia-ci` label, the `shvia.*` container label) is now
visibly site-specific in a fleet-wide repository; it stays as it is until a second site needs a
different value. The installed paths keep their Portuguese names (`/opt/cicd-painel`,
`cicd-vigia`) so that installing from here replaces files in place.

---

## ADR-002 — One self-hosted runner per repository, selected by a repository variable

**Status:** `ACCEPTED` · 28/09/2026 (shvia-web `deploy/servidor-cicd.md`)

**Context.** On 25/09/2026 the account's Actions budget ran out; every job of a private repository
failed in seconds with zero steps. A self-hosted runner does not consume hosted minutes. A personal
account cannot share one runner between repositories.

**Decision.** One runner (or more) per repository, user `runner`, label `shvia-ci`. Workflows read
`runs-on: ${{ vars.CI_RUNNER || 'ubuntu-latest' }}`; setting the repository variable moves the jobs
here, deleting it moves them back. Never at organisation scope.

**Consequences.** Moving a repository in or out is one command and no edit of the workflow. Each
repository needs its own registration (admin, a one-hour token). The jobs run with passwordless
`sudo` on a machine in the office network, which is acceptable only because the VM does nothing
else ([security.md](security.md#0-this-machine)).

---

## ADR-003 — Public repositories may use the machine, behind fork approval

**Status:** `ACCEPTED` · 07/10/2026 ([repodocs ADR-030](https://github.com/samirhvbr/repodocs/blob/master/docs/decisions.md))

**Context.** Until 07/10/2026 a public repository was forbidden here: a pull request from any fork
runs its author's code on the runner.

**Decision.** Every repository of the fleet may use the machine. A public one must set *Require
approval for all external contributors* for fork pull request workflows. The address and the SSH
user of the machine may appear in public repositories (RFC 6598, not routable from the internet).

**Consequences.** The fork-approval setting carries what the prohibition used to. Registering a
runner stays the owner's act.

---

## ADR-004 — When GitHub does not hand out jobs, the machine triggers its own CI

**Status:** `ACCEPTED` · 27/10/2026 (owner's decision; shvia-web pull request #607)

**Context.** On 26/10/2026 the account was locked for billing. The runners here were online and
idle while every run had zero jobs: a self-hosted runner depends on GitHub to receive work.
Dependabot and the release workflows stopped too.

**Decision.** A watcher on this machine (`cicd-vigia`) polls the repositories, runs their existing
workflows with `act`, and reports each job as a commit status. GitHub keeps the code, the pull
requests and the Releases. Forks never run. macOS jobs are meant for the owner's Mac over SSH;
Windows MSVC becomes a manual step before a release.

**Consequences.** CI keeps working while Actions is unavailable, with the same workflow files.
`act` is not GitHub's runner, and each difference found so far needed a flag, an image change or
code in the watcher ([watcher.md](watcher.md#what-act-does-differently-from-githubs-runner)). The
Mac and Windows parts are not built.
