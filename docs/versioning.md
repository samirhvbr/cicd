# Versioning and commits — cicd

> **Status:** `ACTIVE` · **Single source** for how a version is set and how a
> commit is written in this repository.
>
> The fleet-wide rule this implements is
> [samirhvbr/repodocs `docs/conventions.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md).
> What is per-project here is the **bump triggers** — §"Bump criteria".

## `version.md` is the authority

The version lives in **`version.md` at the repository root**. The rule that
matters is not the file's shape but how it is read:

> **The version is the FIRST semver (`X.Y.Z`) in the file.**

A bare string is the simplest thing satisfying it, and is what a new repository
should use:

```
0.1.0
```

A markdown document whose first number is the version satisfies it equally — that
is the shape several repositories in this fleet already use, and the reason the
rule is written as "first semver" rather than "the whole file".

It is git-tracked so the bump **travels inside the commit** and the deploy
propagates it automatically. That is the whole reason it is a file and not an
environment variable: `.env` is excluded from the deploy rsync in every repo
here, so a version kept there has to be edited by hand on each server, and it
silently drifts.

**Where the app exposes the version** (a footer, a `/version` route, a health
page), it reads `version.md`. An environment variable may exist as a *fallback*
for the case where the file is absent. It is never the authority, and **no
document may claim otherwise** — a sibling repository's `README.md` claimed
`version.md` had been "removed in favour of `APP_VERSION`" while the file was
still there and its own `CLAUDE.md` called it the source of truth. Two documents
disagreeing about one number is how a wrong deploy gets signed off.

## Bump criteria

Bump `version.md` **in the same commit as the change it describes.** Never in a
commit of its own.

<!-- The three slots and the discipline are the fleet convention. WHAT COUNTS AS
     A Z IS PER-PROJECT — replace the examples with this project's real
     triggers, concretely enough that two people would classify the same change
     the same way. -->

| Part | When it moves | Who moves it |
|---|---|---|
| **Z** | _e.g. a new screen, a new database table, a layout change, a renamed button, a wording fix_ | Every change. The normal case. |
| **Y** | _e.g. a new main service, an API redesign, a compatibility break, a completed phase_ | When it lands |
| **X** | Reserved — a stable release | Manual, owner's call |

## Who commits, and when

**The agent commits.** Not "leave the tree ready and something downstream
packages it" — the agent runs `git commit`, and `git push`, as the last step of
the work it was asked to do. There is no commit automation in this fleet; if the
agent does not commit, nobody does.

- **A delivery is not delivered until it is committed.** Do not report a task as
  finished before the commit exists. "Done" means the work is in `git log`, not
  that it is sitting uncommitted where only the current session can see it.
- **One subject per commit.** The subject has to describe the whole commit
  honestly — the moment it needs an "and" to be true, it is two commits.
- **A large delivery is split into blocks**, grouped by subject, each small
  enough to be described in one line and read on its own. They may share a
  version: bump `version.md` in the first and repeat the number in the rest.
  Splitting is the default for anything non-trivial, because the history is the
  documentation of *how* the work was done.

The test to run before committing: could someone reading `git log` alone, a year
from now, say what happened, when, why, and at which version?

Full text and the reasoning:
[samirhvbr/repodocs `docs/versioning.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/versioning.md#who-commits-and-when).

## Commit message

**Mandatory format:**

```
version - short description in English
```

For example: `0.1.0 - initial documentation structure`.

- **English (US)**, like everything else in the repository. In a repository we
  do **not** own, the host's commit convention governs instead — their subject
  line, in their language
  ([conventions.md §8](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md#when-the-repository-is-not-ours-the-upstreams-conventions-win)).
- Descriptive enough to be found later with `git log --grep`. Explain the
  **why**, not only the what.
- **Forbidden:** Conventional Commits prefixes — `feat:`, `fix:`, `chore:`,
  `docs:`, `refactor:` — and vague messages: "ajuste", "update", "fix", "wip".
  The version, not a type prefix, is what makes this history searchable.

**Several commits may share one version.** A single delivery can be split into
commits by subject that carry the **same** version — group files by theme, bump
`version.md` in **one** of them (the first), and let the others repeat the same
number in the subject. Two commits with the same version in `git log` are
expected, not a mistake.

## The CHANGELOG heading *is* the commit message

`CHANGELOG.md` is newest-first, and each entry's H2 is literally the subject
that lands in git:

```markdown
## 0.1.0 - initial documentation structure

<narrative body: what changed, why, and what it measured>
```

Writing the entry first means the agent uses the same sentence for the
changelog heading and the commit subject. The agent commits the work; there is
no separate commit automation or handoff to another committer.

Bodies are narrative, not bullet lists: the fleet's changelogs read as
engineering post-mortems ("how it is proven", "where it came from", "measured",
"what is left"), which is why a two-year-old entry is still worth reading.

## Tags and Releases

**Every version gets a git tag named after it, and a published GitHub Release
on top of that tag.**

GitHub never infers a version from a commit subject: without a tag, a repository
full of `X.Y.Z - …` commits still shows *"No releases published"*, and
`git diff <old>..<new>` fails because neither name exists as a ref. The tag is
what pins a version number to the exact code it named — and what a bad deploy
rolls back to.

> **The `version.md` on GitHub equals the Releases on GitHub.** The local
> checkout does not enter the calculation — `tools/release.sh` reads the version
> from the remote default branch and tags that commit. A PR publishes nothing;
> the moment it merges, the workflow fires and the Release becomes that version.

**The bump and the Release are one act.** A commit that bumps `version.md` is
not finished until that version has a Release **and the `Latest` badge is on
it** — same push, not "later". The badge belongs to the version `version.md`
names, never to "the newest by date". `./tools/release.sh` is idempotent and
repairs a drifted badge on every run.

| Thing | Value |
|---|---|
| Tag | The version **exactly as `version.md` holds it — no `v` prefix** |
| Release title | The same string |
| Release notes | The `CHANGELOG.md` section for that version, falling back to the commit subjects that carried it, then to GitHub's generated notes |

### Who creates it

Two owners, both guarding on *"does this tag already exist?"*, so whichever runs
first wins and the other is a no-op:

- **`.github/workflows/release.yml`** — every push that touches `version.md`,
  whoever made it.
- **`tools/release.sh`** — run by hand, to close it now instead of waiting for
  Actions, or to backfill.

Neither ever *decides* a version: both copy the number the agent already wrote
into `version.md`.

### `tools/release.sh`

The one implementation both owners call — the workflow runs this script rather
than reimplementing the rules.

```bash
./tools/release.sh --dry-run              # print the table, create nothing
./tools/release.sh                        # tag + Release for the current version
./tools/release.sh --backfill --dry-run   # the whole history, as a table
./tools/release.sh --backfill             # the whole history, for real
```

Idempotent and resumable — anything already published is skipped. In
`--backfill`, each version's tag points at the **last** commit that carried it:
the finished state of that version, not its first commit.

---

## The hooks

Two hooks live in [`../tools/git-hooks/`](../tools/git-hooks/). They are **not
active on clone** — enable them once, per clone:

```bash
git config core.hooksPath tools/git-hooks
```

| Hook | What it checks | Why there |
|---|---|---|
| `commit-msg` | The subject matches `X.Y.Z - <comment>`, **and that `X.Y.Z` is the version the commit carries in `version.md`**; rejects Conventional Commits prefixes, vague and too-short comments; exempts a merge commit | It is the only moment the message exists and the commit does not |
| `pre-push` | The `version.md` **of the commit being pushed** (not the working tree's) against the remote default branch: rejects a duplicate, rejects a decrease — and **only when the push actually updates that branch**, so a deletion, a tag and a topic branch pass through | It is the only hook that sees the **remote** — and `commit-msg` provably does not run during a rebase, which is how duplicate versions get born |

Two deliberate design choices, both load-bearing:

- **`pre-push` runs no test suite.** A push that waits four minutes becomes
  `--no-verify` the following week, and then the control is dead. It asks two
  questions about one line of one file.
- **With no reachable remote it degrades with a warning, never a refusal.** A
  guard that blocks work when it cannot measure is a guard that gets switched
  off. `commit-msg` answers a missing or semver-less `version.md` the same way:
  a warning, and the subject's version goes unverified.

### The subject's version is checked against the file, not only its shape

A well-formed subject can still be wrong, and the shape test cannot see it: a
number typed from memory, a sibling repository's version, or a bump that never
entered the commit. Both failures were live in the fleet the day this check was
written — one repository four commits deep on a version its `version.md` had
never reached, with the bump sitting uncommitted in the working tree, and one
whose subject carried the number of the repository next to it.

`commit-msg` reads `version.md` **from the index**, because the index is what
the commit will contain. That is what makes the check compatible with the rules
above rather than a second opinion on them:

| Case | Result |
|---|---|
| The bump is staged in this commit (the normal case, and the first commit of a block) | Passes |
| A later commit of the same block repeats the version | Passes — the file already holds that number and the index still shows it |
| The subject carries a version the file does not | **Refused**, naming both numbers |
| The bump is in the working tree but not staged | **Refused** — the commit does not carry it, which is the whole point |
| No `version.md`, or no semver in it | Warning, not a refusal |

**A subject git wrote is exempt** — `Merge …`, `Revert …`, `fixup! …`,
`squash! …`, `amend! …`, and a merge detected by `MERGE_HEAD`. None of them
carries a version of its own: a merge's versions are in the commits being
merged, a revert's is in the commit it undoes, and a fixup line is consumed by
the rebase that lands it. Refusing them would only teach `--no-verify`, which
switches off every guard at once. **This list is EOP's**, which has been running
it in its own `commit-msg` since 04/09/2026 — including the same check against
`version.md`, reached independently. Two implementations of one rule is how a
rule ends up with two versions, so this one takes the tested list rather than
inventing a shorter one.

**A repository that stamps its version some other way does not install
`commit-msg`.** If this repository fills the version in at merge, or from a
build, its subjects do not carry an `X.Y.Z` when the hook runs, and this hook
refuses that shape by design. That is allowed — the norm lets a repository
override the bump clause **in writing**, in its own documentation, with the
reason. What it does not allow is an override nobody wrote down. `pre-push`
stays useful either way.

Escape hatch, declared in both: rename `HOOK_ESCAPE_VAR` at the top of each hook
from `PROJECT_NO_HOOK` to **`CICD_NO_HOOK`**.

An escape hatch is not a loophole — it is what keeps the hooks installed. A
guard with no declared bypass gets bypassed with `--no-verify`, which bypasses
*every* guard at once.
