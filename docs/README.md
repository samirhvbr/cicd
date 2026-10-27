# Documentation — cicd

> **Status:** `ACTIVE`

Index of the project's **stable** documentation. Work in progress lives in
[`../.continue/`](../.continue/) and migrates here when the work it describes
exists.

This index is curated, not exhaustive. Keep it that way: a table of contents
that lists everything stops being read.

## Pages

| Document | What it answers |
|---|---|
| [install.md](install.md) | **How to build a new cicd machine from an empty VM**, step by step, and what the machine in service looks like (measured 27/10/2026). |
| [runners.md](runners.md) | The GitHub Actions self-hosted runners: the `CI_RUNNER` switch, which repositories may use them, adding and removing one, the locale and dpkg traps. |
| [watcher.md](watcher.md) | `cicd-vigia`: the CI triggered from this machine with `act` when GitHub Actions hands out no jobs — modes, configuration, what act does differently, switching a repository on. |
| [dashboard.md](dashboard.md) | `cicd-painel`: what the page shows, how it is built, its token, what it costs in API requests. |
| [cleanup.md](cleanup.md) | The prune timers and the disk guard, each with the incident that added it. |
| [operations.md](operations.md) | **Symptom → cause → check**, routine checks, updating what is installed, and what the machine does not do. |
| [versioning.md](versioning.md) | How a version is set and a commit is written. `version.md` is the sole authority and the version is the **first semver in it**; the `X`/`Y`/`Z` criteria **for this project**; `X.Y.Z - description in English` — and the host's convention instead, in a repository we do not own; **[tags and Releases](versioning.md#tags-and-releases)**; what the two git hooks check. |
| [decisions.md](decisions.md) | **ADRs** — the chronological record of what was decided here and why, so it is not re-litigated. |
| [security.md](security.md) | The normative security document. In a conflict with any other document, it wins. |
| [runbook.md](runbook.md) | Where installation and operation are documented (the pages above), and the repository's own maintenance and release checks. |
| [repodocs.md](repodocs.md) | **What in this repository came from the fleet standard, and where each piece lives.** The map of the relationship: what travels out of repodocs by copy, what by stamp, and what is only ever linked; the manifest of files and what is lost when one is missing; how to bring an existing repository in; how a fleet rule reaches this one. |


## The norm

The documentation convention this repository follows — queue vs. record vs.
history, filenames that carry state, the status vocabulary, the language rule —
lives once, in the fleet standard:
[samirhvbr/repodocs `docs/conventions.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md).
It is deliberately **not** copied here.

[repodocs.md](repodocs.md) is the map of that relationship from this side: which
files here came from the standard, which of them are mirrors that get
regenerated, and which questions are answered upstream rather than here.

## Where a new document goes

| It describes… | It goes to |
|---|---|
| something that already exists — a measurement, a contract, a runbook, an ADR | `docs/` |
| something still to be done — **at any length**, in whatever shape | `.continue/` |
| something that happened, with its date and its why | `CHANGELOG.md` |

**A document leaves `.continue/` when, and only when, the thing it describes
exists.** Length is not an exit condition, and neither is language, age or
untidiness. A 1,300-line brief about something unbuilt is in the only place it
can be — it *is* the specification, and until the thing exists it is the only
place the thing exists. To *produce* a queue item is to make the thing exist,
not to edit, translate or promote the document. **Never empty that folder as
tidying.**

If a queue item needs half a page **to describe something that already exists**,
that is a record that ended up in the queue: write it here and leave one line
and a pointer. That is the whole reach of the rule.
