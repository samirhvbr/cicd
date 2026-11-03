# cicd — Instructions for coding agents

<!--
  The content below the H1 is duplicated between CLAUDE.md (read by Claude
  Code) and AGENTS.md (read by other tooling, agents.md standard) — keep the
  two byte-identical below the H1. If you edit one, edit the other.
-->

> **Read in this order:** [.continue/README.md](.continue/README.md) (the queue —
> where we stopped, **always first**) · [docs/versioning.md](docs/versioning.md)
> (how a version and a commit are written) ·
> [docs/decisions.md](docs/decisions.md) (ADRs — do not re-litigate a decided
> direction, link the ADR) · [docs/security.md](docs/security.md) (normative;
> wins any conflict).
>
> **The fleet documentation norm is not in this repository.** It lives once, at
> [samirhvbr/repodocs `docs/conventions.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md).
> Read it there; do not copy it here.
>
> **[docs/repodocs.md](docs/repodocs.md) is the map of what came from that
> standard** — which files here arrived from the skeleton, which blocks below
> are mirrors that get regenerated rather than edited, and which questions are
> answered upstream. Read it before adding, moving or deleting a documentation
> file.

---

## 🔄 Before you start: `git pull`

**ALWAYS** check for remote updates before writing or changing anything in this
repository:

```bash
git pull
```

Working on a stale base creates conflicts. Pull first, always. To inspect
without merging: `git fetch && git status`.

**Fresh clone — enable the hooks ONCE:**

```bash
git config core.hooksPath tools/git-hooks
```

Two hooks then run, and each exists because the other cannot reach its moment:

| Hook | What it checks | Why there |
|---|---|---|
| `commit-msg` | The subject is `X.Y.Z - description in English`; no Conventional Commits prefix, no vague comment | It is the only moment the message exists and the commit does not |
| `pre-push` | The `version.md` **of the commit being pushed** against the remote default branch — duplicate and monotonicity, and only for a push that updates that branch | It is the only hook that sees the **remote**, and `commit-msg` provably does not run during a rebase, which is how duplicate versions get born |

⚠️ **`pre-push` runs no suite, and that is a choice:** a push that waits four
minutes becomes `--no-verify` the following week, and then the control is dead.
**With no reachable remote it degrades with a warning, never a refusal.** Escape
hatch declared in both, named by `HOOK_ESCAPE_VAR` at the top of each hook —
rename it to `CICD_NO_HOOK`.

---

## What this project is

**cicd** — The CI machine of the samirhvbr fleet, as code and documentation: self-hosted GitHub Actions runners, a watcher that runs the same workflows with act when Actions is unavailable, a dashboard and the disk cleanup, with everything needed to build a new one from zero.

- **Stack:** Debian 13, Docker Engine, GitHub Actions self-hosted runners, `act`; the
  dashboard and the watcher are Python 3 standard library only, the page is one static
  `index.html`, the cleanup is bash with systemd timers. No build step.
- **Runs:** on the cicd machine only, installed by each component's `instalar.sh` or the
  `install` lines in its page ([docs/install.md](docs/install.md)). Nothing here runs as a
  service on a workstation.
- **Tests run with:** `node tests/disk-guard.test.mjs && node tests/container-prune.test.mjs && node tests/dashboard-watcher.test.mjs`
  (each exits 0 only when the script is correct and every mutant is caught). The permission to
  run them is not in `.claude/settings.json` yet — granting it is the owner's act.
- **Never touch:** the machine itself without the owner's go-ahead — registering a runner,
  installing a token, or changing a service there is the owner's act. Never commit a token, a
  registration token, the SSH key, or a runner's `.credentials`/`.runner`
  ([docs/security.md §0](docs/security.md#0-this-machine)).
- **Where things are:** [README.md](README.md) maps the components; the machine as it runs is in
  [docs/install.md](docs/install.md#what-the-running-machine-looks-like); symptom → cause in
  [docs/operations.md](docs/operations.md).

---

## Golden rules

1. **`.continue/` is the queue · `docs/` is the record · `CHANGELOG.md` is the
   history.** A document leaves the queue when — and **only** when — the thing
   it describes **exists**. Length, language and untidiness are not exit
   conditions. To *produce* a queue item is to make the thing exist, not to
   edit, translate or promote the document; removing it is the last step of the
   commit that carries the work. **Never empty this folder as tidying.**
2. **If a queue item needs half a page to describe something that already
   exists, it is in the wrong place.** Write it in `docs/` and leave one line
   and a pointer. This says nothing about the length of a specification of work
   not yet done: a 1,300-line brief about something unbuilt is in the only place
   it can be.
3. **In a contradiction between the queue and a document, the document wins.**
4. **Every prescriptive document declares its status** on the first lines:
   `ACTIVE` · `HISTORICAL` · `PROPOSED` · `DEPRECATED` · `NOT ADOPTED`. One
   with no declaration is read as `ACTIVE`, which is exactly the failure mode.
5. **A document made stale by a change is fixed in the same pass.** A document
   that ages in silence is worse than a missing one, because it has the
   authority of being written down.
6. **`CLAUDE.md` and `AGENTS.md` are byte-identical below the H1.** Edit one,
   edit the other.
7. **Everything is versioned; the only exception is a secret.** `.claude/` and
   `.continue/` are tracked on purpose. A new `.gitignore` exception beyond
   secrets requires an ADR, never a silent line.
8. **Granting the agent a permission is the owner's act** — written into
   `.claude/settings.json` with its reason and how to revert it, never applied
   silently and never left as a promise in prose.
9. **A new decision becomes an ADR** in `docs/decisions.md`, in the same pass.
10. **You commit, and nothing is finished until you have.** The commit is the
    last step of the task, not a follow-up — never report work as done while it
    sits uncommitted. One subject per commit; a large delivery is split into
    blocks.

---

<!-- RELEASES-RULE:repodocs -->

## Releases — the `version.md` on GitHub is what the Releases show

> Marked echo. The single source is **[samirhvbr/repodocs](https://github.com/samirhvbr/repodocs/blob/master/docs/versioning.md)**
> — change it there, not here. This block is regenerated.

**The `version.md` of the default branch, on GitHub, is what the GitHub Releases
must show.** The local checkout does not enter the calculation: it can be behind,
ahead or mid-work, and none of that is published — GitHub cannot tag a commit it
does not have.

**The bump and the Release are one act.** A commit that bumps `version.md` is not
finished until that version has a tag, a published Release, and the **`Latest`
badge on it** — the same push, not "later". A badge sitting on an older release
tells whoever looks that the project is at a version it is not.

- `.github/workflows/release.yml` does it on any push that touches `version.md`.
- `./tools/release.sh` does it by hand. It is **idempotent and self-healing**:
  it publishes whatever is missing and moves a drifted badge back. Running it is
  always safe, so it is both the check and the fix.

A PR publishes nothing while it is a PR. The moment it merges, the push moves
`version.md` on the default branch and the Release becomes that version.

Tag and Release title are the **bare version — no `v` prefix**.

<!-- /RELEASES-RULE -->

<!-- CICD-RULE:repodocs -->

## CI — the fleet's self-hosted runner is open to every repository

> Marked echo. The single source is **[samirhvbr/repodocs](https://github.com/samirhvbr/repodocs/blob/master/docs/ci.md)**
> — change it there, not here. This block is regenerated.

**The fleet has one CI machine, `cicd`: a self-hosted GitHub Actions runner that
does not spend the account's hosted minutes.** It exists because that budget ran
out on 25/09/2026 and every job in a private repository failed within seconds,
with zero steps.

| | |
|---|---|
| Address | `100.64.100.240` — the office network only. RFC 6598 shared space: not routable from the internet |
| Access | `ssh samir@100.64.100.240` |
| Dashboard | `http://100.64.100.240:8080/` — read-only, no login, office network only. It shows the jobs; it is **not** how a repository joins |

**Every repository may use it, public ones included** — the owner's decision of
07/10/2026. Until that date a public repository was forbidden, and the reason has
not gone away: **a pull request from any fork runs its author's code on this
machine**, where the jobs have passwordless `sudo` and `docker`, which is
effectively root on a machine inside the office network. What stands where the
prohibition stood is one setting, per repository: *Settings → Actions → Fork pull
request workflows → **Require approval for all external contributors***. On a
public repository on `cicd`, that setting is not optional.

**Permission is not destination.** A job reads
`runs-on: ${{ vars.CI_RUNNER || 'ubuntu-latest' }}`, so nothing moves until
somebody sets the variable:
`gh variable set CI_RUNNER --body shvia-ci -R <owner>/<repo>` sends the jobs to
`cicd`, `gh variable delete CI_RUNNER -R <owner>/<repo>` hands them back to
GitHub. **Never set it at organisation scope** — that retargets every repository
at once, public ones that run free on hosted minutes included.

**Joining is pre-authorised; registering is still the owner's act.** One runner
per repository, registered over SSH with a one-hour token. The jobs run with
`sudo` on a machine inside the office network, so an agent **never registers a
runner on its own initiative**: it says what is needed and asks. A repository
belonging to somebody else's account is not covered by the decision above — that
one is still decided case by case.

<!-- /CICD-RULE -->

<!-- QUEUE-RULE:repodocs -->

## The queue empties by production, and by nothing else

> Marked echo. The single source is **[samirhvbr/repodocs](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md#1-continue-is-the-queue--docs-is-what-has-been-produced)**
> — change it there, not here. This block is regenerated.

**`.continue/` holds work that does not exist yet.** A document leaves it when —
and **only** when — the thing it describes **exists**. Length is not an exit
condition. Neither is age, language, untidiness, the end of a session, or an
agent who would have written it differently.

> `tela.md` says *"a black screen with a yellow ball in the middle"*. It leaves
> the queue when there is a black screen with a yellow ball. Until then it stays,
> at any length, in whatever shape it is in — because until then it is the only
> place that thing exists.

**"Produce", applied to a queue item, means making the thing exist.** Not editing
the document, not translating it, not promoting it to `docs/`. The document is
the specification; the deliverable is the thing. Removing the document is the
**last step of the commit that carries the work** — never a step of its own.

**Never empty this folder as tidying.** A queue item deleted without the work
being done destroys the only artefact a project has before it has code — and
what usually replaces it is worse than the loss: a `docs/` page describing a
screen nobody built, indistinguishable from a page describing one that exists.
If a plan has to be visible in `docs/` before it is built, it is `PROPOSED`,
never `ACTIVE`.

**The half-a-page rule is about a record that ended up in the queue**, and about
nothing else. It has no opinion on the length of a specification of unbuilt
work: a 1,300-line brief about something that does not exist is in the only
place it can be. A long queue item is a project with a lot still to build.

**The queue is written in the language its author thinks in**, and becomes
English (US) on the way out, when the work is produced and the document moves to
`docs/`. A Portuguese draft in `.continue/` is not a violation to be fixed.

<!-- /QUEUE-RULE -->

<!-- LANGUAGE-RULE:repodocs -->

## Language — English (US) at home, the upstream's when we are guests

> Marked echo. The single source is **[samirhvbr/repodocs](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md#8-language)**
> — change it there, not here. This block is regenerated.

**Everything that lives in this repository, or in GitHub's interface around it,
is written in English (US)**: documents, **commit messages**, pull request titles
and bodies, issues, code comments, changelog entries, release notes.

Commit format: `X.Y.Z - short description in English`. The version comes from
`version.md` and is bumped in the same commit. Conventional Commits prefixes
(`feat:`, `fix:`, `chore:`) and vague one-word messages are forbidden.

**Three carve-outs, and only three.** The first is end-user-facing strings — UI
text, transactional email, product copy: product i18n for a Brazilian audience,
not repository content. The second is the **Blue3 internal repositories**
(`BLUE3-ISP/*`, `samirhvbr/blue3-intranet`, `samirhvbr/blue3-ai-login`), which
are Portuguese throughout — if you are reading this block inside one of them,
this is the wrong block: they carry `LANGUAGE-RULE-PT`. A repository joins that
set by a written decision, never by argument.

**The third is `.continue/`.** The queue is written in the language its author
thinks in, and becomes English (US) when the work is **produced** and the
document moves to `docs/`. A Portuguese draft in the queue is not a violation to
be fixed: it is unfinished work in the language it is being thought in, and
translating it or moving it out before the thing exists destroys the only place
that thing exists.

History is not rewritten: Portuguese messages already in the log stay as they
are.

**In a repository that is not ours, the upstream's conventions win — the
language and the commit shape both.** Opening a pull request or an issue on a
repository we do not own makes us guests, and a guest writes in the host's
language. Our `X.Y.Z - description` is meaningless there anyway: they have no
`version.md` of ours, and no version for us to bump.

**Check before you write, and the first signal that answers wins:** a written
instruction (`CONTRIBUTING.md`, a pull request or issue template, a contribution
section in the README), then the last ~20 merged pull requests, then the issues,
then the commit log. A written instruction beats observed practice — if they ask
for English and their log is Portuguese, write English. Below that line the
**clear majority** decides, and clear means clear.

**When you cannot tell, write English (US).** A private repository, an empty
history, no network, a refused `gh` call and a genuinely mixed log all land in
the same place — the house rule. Unverifiable is not a licence to guess.

**This is a scope boundary, not a second carve-out.** Nothing in *our*
repositories changes because a foreign one is Portuguese, and code identifiers
are English wherever you are.

<!-- /LANGUAGE-RULE -->

---

## Branch

**`master`, never `main`.** The default branch of every repository in this fleet
is `master` — a house convention so that every script, hook and runbook can say
`origin/master` and be right. A repo created as `main` gets renamed with GitHub's
rename (it keeps open PRs and redirects old links); every existing clone then
needs `git branch -m main master`, `git fetch origin`,
`git branch -u origin/master master` and — the step people skip —
`git remote set-head origin -a`.

A different branch is fine **only as a written decision**, recorded in
`docs/decisions.md`.

Norm: [samirhvbr/repodocs `docs/conventions.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md).

---

<!-- COMMIT-RULE:repodocs -->

## Commits — you commit, and nothing is delivered until you have

> Marked echo. The single source is **[samirhvbr/repodocs](https://github.com/samirhvbr/repodocs/blob/master/docs/versioning.md#who-commits-and-when)**
> — change it there, not here. This block is regenerated.

**Committing is your job.** Not "leave the tree ready and something downstream
packages it" — you run `git commit`, and `git push`, as the last step of the work
you were asked to do. The COMMITTER skill that used to commit on an agent's
behalf is `enabled: false` in every repository of this fleet since 03/09/2026;
what is left of it is a kill-switch, not a scheduler. **If you do not commit,
nobody does.**

**Do not report a task as finished before the commit exists.** "Done",
"delivered", "concluded" mean the work is in `git log` — never that it is sitting
uncommitted where only this session can see it. The commit is the last step *of
the task*, not a follow-up for someone else. If you are about to write
"finished", commit first, then write it.

**Push is part of the delivery, and a refused push is the one place a human enters.**
Commit *and* push, every delivery — a clean push needs nobody's permission and is never
held back for review. When the push is **refused** (conflict, non-fast-forward, protected
branch), stop there and say so: never force, never rewrite history to get past it, never
invent a merge resolution you have not verified. The gate is the refused push, not the
commit.

**Every commit obeys the versioning rules**, with no exception:

- Subject `X.Y.Z - short description in English (US)`, the version taken from
  `version.md` and **bumped in the same commit**.
- The `CHANGELOG.md` entry is written first — its `## X.Y.Z - description`
  heading *is* the subject.
- No Conventional Commits prefix (`feat:`, `fix:`, `chore:`) and no vague
  subject ("update", "ajuste", "wip", "changes", "several improvements").

**The bump is the one clause a repository may override — in writing.** If this
repository's own documentation says the version is stamped some other way, and says
why, follow that. Otherwise the line above applies to you. An override nobody wrote
down is not an exception. Nothing else in this block bends: the changelog entry, the
subject, the language, one subject per commit, and committing before you report done
all hold regardless.

**An override moves *when* the version is decided, never *whether* every commit
carries it.** A delivery split into blocks — the default — must come out with the
version on **every** subject, not on the last one. A placeholder left in a subject
that reaches the default branch is a defect and is permanent, because the default
branch is not rewritten. Measured: 26 of them in the one repository that stamps at
merge, before its mechanism was fixed.

**All of this governs the repositories we own.** In a repository that is not
ours, the host's commit convention governs instead — their subject line, in
their language. `X.Y.Z` is meaningless where there is no `version.md` of ours,
and there is no version there for us to bump. Our versioning rules govern our
remotes, not every remote we can push to.

**One subject per commit.** The subject has to describe the whole commit
honestly. The moment your description needs an "and" to be true, it is two
commits.

**Split a large delivery into blocks.** A complex task is committed as a series
of commits grouped by subject, each small enough to be described in one line and
read on its own. They may share a version — bump `version.md` in the first and
repeat the number in the rest; two commits carrying one version is expected, not
a mistake. **Splitting is the default** for anything non-trivial, because the
history is the documentation of *how* the work was done, and one commit touching
six unrelated subjects documents none of them.

**The standard you are keeping:** someone reading `git log` alone — a year from
now, without the conversation that produced the work — can say what happened,
when, why, and at which version. If your commit would fail that test, it is too
big or its subject is too vague, and both are fixed the same way.

<!-- /COMMIT-RULE -->

---

## Version and commits (mandatory)

Format: `version - short description in English`. The version comes from
[version.md](version.md), **bumped in the same commit**:

- **Z** — a fix or a change inside one component (a cleanup rule, a dashboard panel, a watcher
  difference handled), a new documented procedure, a correction of the docs against the machine.
- **Y** — a new component on the machine, a change that requires reinstalling or reconfiguring
  the machine (a path, a service name, a token scope, a new data volume), or one that changes how
  a repository joins.
- **X** — reserved; a stable release, by hand.

Forbidden: `feat:` / `fix:` / `chore:` prefixes and vague messages ("ajuste",
"update", "wip"). Several commits may share one version — group by subject, bump
in the first, repeat the number in the rest.

**Write the `CHANGELOG.md` entry first: its `## X.Y.Z - description` heading
*is* the commit subject.** Bodies are narrative — what changed, why, and what it
measured — not bullet lists.

**The version is the FIRST semver in `version.md`** — a bare string and a
markdown document both satisfy that.

**Every version gets a tag named exactly after it — no `v` prefix — and a
published GitHub Release.** `.github/workflows/release.yml` does it on every push
that touches `version.md`, calling `tools/release.sh`; run that script by hand
for a backfill. Both skip what already exists.

**The `version.md` on GitHub equals the Releases on GitHub.** Your local checkout
does not enter the calculation. A PR publishes nothing; the moment it merges, the
Release becomes that version.

**The bump and the Release are one act.** A commit that bumps `version.md` is not
finished until that version has a Release and the `Latest` badge is on it — same
push, not "later". `./tools/release.sh` is idempotent and also repairs a drifted
badge.

Full rules: [docs/versioning.md](docs/versioning.md).

---

## Before closing a version

- [ ] What changed is in `CHANGELOG.md`, with the **why**, not just the what.
- [ ] A new or changed document is in `docs/` — not in the queue, not in the
      commit body.
- [ ] A finished item **left** `.continue/` — *finished* meaning the thing it
      described now exists, not that the document reads well.
- [ ] A document made stale by this change was corrected in the same pass.
- [ ] A change in behavior carries the test that fails when it breaks, and the
      pertinent tests **ran** — or the changelog entry says why not and what was
      checked instead ([conventions.md §9](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md#9-a-change-in-behavior-ships-with-the-test-that-fails-when-the-behavior-breaks)).
- [ ] `version.md` bumped, in this commit.
- [ ] **The work is committed** — and split into one commit per subject if it
      covered more than one. Nothing is reported as finished while it is
      uncommitted.
- [ ] The **tag and the GitHub Release** exist for this version. Normally the
      workflow does it on push; `./tools/release.sh` if you need it now.
- [ ] The twins still match: `diff <(tail -n +2 CLAUDE.md) <(tail -n +2 AGENTS.md)`.
