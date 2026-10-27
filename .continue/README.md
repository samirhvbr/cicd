# `.continue/` — the queue

> **Status:** `ACTIVE` · Last reviewed 27/10/2026, repository at 0.1.0

Work in progress: drafts, plans under discussion, notes on things still being
built, briefings for picking the work back up later.

**The norm this folder obeys lives once, in the fleet standard:**
[samirhvbr/repodocs `docs/conventions.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md)
— §1 (queue vs. record) and §2 (this README is mandatory). Read it there; a copy
here would be a second source of truth.

## How it works

- **Git-tracked on purpose — deliberately NOT in `.gitignore`.** Opening the
  project on another machine brings the context along, which is the whole point:
  you can *continue* from where you stopped.
- **Nothing here is source of truth.** The moment a document describes something
  that already exists, it moves to [`../docs/`](../docs/) and the permanent
  record of *when* is [`../CHANGELOG.md`](../CHANGELOG.md).
- **A finished item leaves — and *finished* means the thing exists.** It is
  deleted here, not ticked off; the permanent record of completion is the
  changelog. A queue holding an already-done item costs more than an incomplete
  queue: it makes the next session redo work.
- **Nothing leaves for any other reason.** Not length, not language, not a
  session ending, not an agent who would have written it differently. **To
  produce an item is to make the thing exist**, and deleting the document is the
  last step of the commit that carries the work — never a step of its own.
- **If an item needs half a page to describe something that already exists**, it
  is in the wrong place. Write it in
  `../docs/` and leave one line and a pointer here.
- **In a contradiction between this folder and a document in `../docs/`, the
  document wins.**
- The **Continue** IDE also uses this folder for its own configuration.

## 1. What is left here

<!-- One line per item. Delete a row when the item is done — do not tick it. -->

| Item | State | Who unblocks it |
|---|---|---|
| **Replay [docs/install.md](../docs/install.md) on a scratch VM**, from an empty disk to §10 | Written from the machine in service, never replayed as one sequence | anyone with a scratch VM on the Proxmox |
| **shvia-web: replace `deploy/servidor-cicd.md` and `deploy/cicd-*` with a pointer here** ([ADR-001](../docs/decisions.md)) | Two copies until then; they can drift | a shvia-web pull request |
| **shvia-web #607 (the watcher)**: land it in this repository instead, or copy its final version here when it lands | `watcher/` is #607 at `44a323b3`, still under review on 27/10/2026; the machine also has a `shvia/act-ubuntu:26.04` image that is not in that commit | the session working on #607 |
| **repodocs: point `docs/ci.md` and the `CICD-RULE` echo block at this repository** | They point at shvia-web's runbook | a repodocs pull request, then `fleet.sh echo` |
| **`cicd-eop` runs as the owner's user with `LANG=pt_BR.UTF-8`** — re-register it as `runner`, with the locale pin ([runners.md](../docs/runners.md#adding-a-repository)) | Measured 27/10/2026; every other runner is `runner` + `C.UTF-8` | the owner (registering is the owner's act) |
| Watcher: macOS jobs on the owner's Mac over SSH; Windows MSVC as a manual pre-release step ([ADR-004](../docs/decisions.md)) | Decided, not built | the owner's Mac access |
| CI for this repository (the two rulers on `ubuntu-latest`) | `.github/workflows/tests.yml` exists; no run yet — the account is locked for billing since 26/10/2026 | the account's billing |

## 2. Where things went

<!-- When a document leaves for ../docs/, give it a row with a relative link.
     This is what keeps "it misleads whoever opens it" from becoming "nobody
     can find it". -->

| It was here | It is now at |
|---|---|
| shvia-web `deploy/servidor-cicd.md` | [docs/](../docs/README.md) — split into install, runners, watcher, dashboard, cleanup, operations |
| shvia-web `deploy/cicd-painel/` | [dashboard/](../dashboard/) |
| shvia-web `deploy/cicd-limpeza/` | [cleanup/](../cleanup/) |
| shvia-web `deploy/cicd-vigia/` (#607) | [watcher/](../watcher/) |
| shvia-web `scripts/prova-guarda-de-disco-do-cicd.mjs`, `prova-limpeza-de-conteineres-do-cicd.mjs` | [tests/](../tests/) |
| only on the machine: `/etc/docker/daemon.json`, `/etc/sudoers.d/90-runner`, `/etc/cron.weekly/cicd-limpeza` | [host/](../host/) |

## 3. Pending decisions

| Decision | Whose | Note |
|---|---|---|
| Automatic deploy of shvia-web from this machine on a green master | the owner | needs a restricted SSH key into production and a manual approval ([operations.md](../docs/operations.md#what-this-machine-does-not-do)) |
| Whether the site-specific values in the code (`shvia-ci`, the `assunto` rule, the `shvia.*` label) become configuration | the owner | only worth it when a second site needs other values ([ADR-001](../docs/decisions.md)) |
