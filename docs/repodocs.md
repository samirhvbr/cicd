# repodocs — the standard this repository follows

> **Status:** `ACTIVE` · What in this repository came from the fleet standard,
> where each piece lives, how to bring an existing repository in, and how to
> consult the standard without ever copying it.

**[samirhvbr/repodocs](https://github.com/samirhvbr/repodocs) is a source of
consultation, not a dependency.** It is never a submodule, never a package,
never vendored. Nothing here installs it and nothing here breaks when it moves.
What it does instead is narrower and more durable: it hands a new repository a
starting structure once, keeps a small set of rules stamped into the files an
agent actually reads, and holds the norm itself in exactly one place so that the
fleet has one version of it rather than sixteen.

This page is the map of that relationship, from the side of the repository that
follows it. The mechanical steps of a bootstrap are **not** repeated here — they
live in
[repodocs `docs/runbook.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/runbook.md),
and a second copy of them would be the exact failure this standard exists to
prevent.

## The map

```
repodocs = SOURCE OF CONSULTATION (never a dependency)
│
├── 0. WHAT TRAVELS, AND WHAT NEVER DOES
│   ├── travels by copy ....... templates/skeleton/      → once, at bootstrap
│   ├── travels by stamp ...... templates/echo-blocks/   → 5 blocks, regenerated in place
│   └── never travels ......... docs/conventions.md      → linked only (ADR-001)
│                               a rule copied into 16 repositories is a rule
│                               with 16 versions, 15 of them stale
│
├── 1. WHICH FILES THIS REPOSITORY GOT, AND WHERE THEY LIVE
│   ├── root/        README.md · CLAUDE.md + AGENTS.md (twins) · version.md
│   │                CHANGELOG.md · LICENSE · NOTICE · SECURITY.md · .gitignore
│   ├── docs/        README.md · versioning.md · decisions.md · security.md
│   │                runbook.md · repodocs.md (this page)
│   │                ⛔ no conventions.md — docs/README.md links it upstream
│   ├── .continue/   README.md      (the queue; git-tracked on purpose)
│   ├── .claude/     settings.json · README.md   (the permission posture)
│   ├── .github/     CODEOWNERS · dependabot.yml · workflows/release.yml
│   └── tools/       git-hooks/{commit-msg,pre-push} · release.sh
│
├── 2. HOW THE FILES GET HERE   (two routes, one command)
│   ├── A) a local clone exists .. cp -r /path/to/repodocs/templates/skeleton/. .
│   │                              the trailing /. is what brings the dotfiles
│   └── B) no clone .............. gh repo clone samirhvbr/repodocs /tmp/repodocs
│                                  then the same copy
│
├── 3. WHAT CHANGES AFTER THE COPY   (points, never repeats)
│   ├── placeholders ......... runbook §2 owns the table + the sweep
│   ├── per-repo decisions ... runbook §3: settings.json grants · bump triggers
│   │                          · security.md §2 and §4
│   ├── echo blocks .......... 5 blocks, verbatim, in CLAUDE.md AND AGENTS.md
│   │                          COMMIT-RULE · RELEASES-RULE · LANGUAGE-RULE
│   │                          · QUEUE-RULE · CICD-RULE
│   └── hooks ................ git config core.hooksPath tools/git-hooks  (1× per clone)
│
├── 4. CONSULTING IT AFTERWARDS   ← the permanent part, the reason this page stays
│   ├── "what is the norm?" ....... conventions.md   (read there, never copy)
│   ├── "how do I version?" ....... versioning.md
│   ├── "was this decided?" ....... decisions.md     (do not re-litigate; link the ADR)
│   ├── "is this safe?" ........... security.md      (normative; wins any conflict)
│   └── "the rule changed there" .. the echo block is regenerated here,
│                                   between its markers
│
├── 5. A REPOSITORY THAT ALREADY EXISTS ≠ AN EMPTY ONE
│   ├── never overwrite an existing README/LICENSE — merge, and write the divergence down
│   └── order: .claude/ → CLAUDE.md+AGENTS.md → version.md+CHANGELOG → docs/ → tools/
│
└── 6. VERIFY BEFORE CLOSING
    ├── diff <(tail -n +2 CLAUDE.md) <(tail -n +2 AGENTS.md)   → empty
    ├── grep -rn '<[A-Z_]\+>' . --exclude-dir=.git             → empty
    ├── python3 -m json.tool .claude/settings.json             → ok
    ├── invoke commit-msg directly with rejected and accepted subjects (runbook §5)
    └── ./tools/release.sh --backfill --dry-run
```

## 1. What travels out of repodocs, and what never does

Three things leave that repository, and each leaves by a different mechanism.
Knowing which is which is most of knowing how to work with the standard.

| What | Mechanism | When it moves | What that means here |
|---|---|---|---|
| [`templates/skeleton/`](https://github.com/samirhvbr/repodocs/tree/master/templates/skeleton) | **Copied**, once | At bootstrap only | Everything in §2 below. After the copy it is *this repository's* file — edit it freely, it is not a mirror |
| [`templates/echo-blocks/`](https://github.com/samirhvbr/repodocs/tree/master/templates/echo-blocks) | **Stamped**, and regenerated in place | Whenever the rule changes upstream | The delimited blocks inside `CLAUDE.md` and `AGENTS.md`. These *are* mirrors — see §5 |
| [`docs/conventions.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md) | **Never copied.** Linked | — | The norm has one home. A copy here is a second source of truth, which is a stale source of truth by the following month |

The asymmetry is deliberate. The skeleton is a *starting point*, so it stops
being repodocs' business the moment it lands. The echo blocks are *rules*, so
they stay repodocs' business forever and are replaced rather than edited. The
norm is neither — it is the thing every repository has to agree on, so it is
read where it is written.

## 2. The manifest — what this repository has because of repodocs

Everything below arrived from the skeleton. The third column is the one worth
reading: it says what is actually lost when a file is missing, which is the only
argument that survives contact with someone in a hurry.

### Root

| File | What it is | Missing it costs |
|---|---|---|
| `CLAUDE.md` + `AGENTS.md` | The agent's instructions. **Twins — byte-identical below the H1** | The agent works without the house rules, and the echo blocks have nowhere to land |
| `version.md` | The sole authority on the version. A bare semver, or a document whose **first** semver is the version | Nothing can be committed to convention, tagged, or released — the hooks and the release workflow both read it |
| `CHANGELOG.md` | The history. Each `##` heading *is* a commit subject | The *why* of a change survives only in the head of whoever made it |
| `README.md` | What the project is, for a human arriving cold | — |
| `LICENSE` · `NOTICE` | Plain English MIT, and a `NOTICE` that agrees with it | GitHub shows no license badge; a public repository with no license is legally closed |
| `SECURITY.md` | A monitored reporting address | A vulnerability report finds no door and becomes a public issue |
| `.gitignore` | Everything is versioned; the only exception is a secret | — |

### Directories

| Path | What it is | Missing it costs |
|---|---|---|
| `docs/` | The record — `README.md`, `versioning.md`, `decisions.md`, `security.md`, `runbook.md`, and this page | Decisions get re-litigated, because nothing wrote down that they were decided |
| `.continue/README.md` | The queue. **Git-tracked on purpose** | The next session starts from zero, or redoes finished work |
| `.claude/` | `settings.json` (the permission posture) and `README.md` (why each grant exists) | The repository is born without a deny-list. This is the single file most often lost by a `cp -r` without the trailing `/.` |
| `.github/` | `CODEOWNERS`, `dependabot.yml`, `workflows/release.yml` | No automatic Release on a version bump; the `Latest` badge drifts to an old version |
| `tools/git-hooks/` | `commit-msg` and `pre-push` | The commit format becomes advisory, and duplicate versions get born during rebases |
| `tools/release.sh` | Tag + GitHub Release for `version.md`. Idempotent and self-healing | No way to repair a missed Release or a drifted badge by hand |

**`docs/conventions.md` is deliberately absent**, and its absence is the point.
[`docs/README.md`](README.md) links it upstream instead.

## 3. Starting a brand-new repository

The whole bootstrap is one copy plus a substitution:

```bash
# from inside the new, empty repository
cp -r /path/to/repodocs/templates/skeleton/. .
```

**The trailing `/.` matters.** It is what brings `.claude/`, `.continue/`,
`.github/` and `.gitignore` along. Without it you get the visible files only —
a repository that looks conforming and has no permission posture.

With no local clone to copy from:

```bash
gh repo clone samirhvbr/repodocs /tmp/repodocs
cp -r /tmp/repodocs/templates/skeleton/. .
```

Then substitute the placeholders, make the three per-repo decisions, enable the
hooks, and make the first commit — each of those steps, with the table of
placeholders and the reason each per-repo decision is left open, is
[repodocs `docs/runbook.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/runbook.md).
It is the single source for that procedure; this page does not restate it.

The one check to run before believing the substitution worked:

```bash
grep -rn '<[A-Z_]\+>' . --exclude-dir=.git   # must come back empty
```

## 4. Bringing an existing repository in

A repository with history is not an empty one, and `cp -r` into it is
destructive: it overwrites a `README.md` somebody wrote and a `LICENSE` that may
already be correct. Adopt file by file, in this order — each step leaves the
repository more conforming than it was, and none of them depends on a later one.

| # | What | Why here |
|---|---|---|
| 1 | `.claude/settings.json` + `.claude/README.md` | The posture comes first, before an agent starts working on the rest of the adoption |
| 2 | `CLAUDE.md` + `AGENTS.md`, with the five echo blocks | The agent cannot follow rules it has not been given |
| 3 | `version.md` + `CHANGELOG.md` | Nothing after this point can be committed to convention without them |
| 4 | `tools/git-hooks/` + `git config core.hooksPath tools/git-hooks` | Enforcement only makes sense once the format it enforces exists |
| 5 | `docs/` — `README.md`, `versioning.md`, `decisions.md`, `security.md`, this page | The record. An existing document that already covers one of these is kept and linked, not replaced |
| 6 | `.continue/README.md` | Even empty, it needs the README saying where the documents went |
| 7 | `.github/workflows/release.yml` + `tools/release.sh` | Last, because it publishes: run `./tools/release.sh --backfill --dry-run` before the first real run |

**Three merge rules, and they are not negotiable:**

- **Never overwrite a file the repository already had** because the skeleton has
  one with the same name. Merge, and if the result diverges from the skeleton on
  purpose, write down *where* and *why* — an undocumented divergence reads as a
  mistake to the next person and gets "fixed" back.
- **An existing document that already answers what a skeleton document answers
  is kept.** Point to it from `docs/README.md`. Two documents answering one
  question is the failure mode; the fix is not a third.
- **The version does not restart.** A repository already at `2.4.0` stays there.
  The skeleton's `0.1.0` is for a repository that has shipped nothing.

## 5. When a fleet rule changes upstream

The rules that every repository must follow live inside `CLAUDE.md` and
`AGENTS.md` as delimited blocks:

```
<!-- COMMIT-RULE:repodocs -->   …   <!-- /COMMIT-RULE -->
<!-- RELEASES-RULE:repodocs -->  …  <!-- /RELEASES-RULE -->
<!-- LANGUAGE-RULE:repodocs -->  …  <!-- /LANGUAGE-RULE -->
<!-- QUEUE-RULE:repodocs -->     …  <!-- /QUEUE-RULE -->
<!-- CICD-RULE:repodocs -->      …  <!-- /CICD-RULE -->
```

Each carries a link back to its source in repodocs' `docs/`. **They are
regenerated, not edited:** replace everything between the markers with the
current block from
[`templates/echo-blocks/`](https://github.com/samirhvbr/repodocs/tree/master/templates/echo-blocks),
in both twins, and commit it like any other change — changelog entry first,
version bumped in the same commit.

Editing the text of a block *here* is the one thing that breaks the mechanism:
the next regeneration overwrites it silently, and in the meantime this
repository is following a rule no other repository has. If a block is wrong,
it is wrong for the fleet — fix it at the source, in repodocs.

## 6. Verifying this repository still conforms

The checks live in [`runbook.md` §7](runbook.md), which is where they belong —
they are operations, not a description of the standard. Run them when a twin was
edited, after an echo-block regeneration, and before making the repository
public.

## 7. Where each question is answered

| Question | Where |
|---|---|
| What is the documentation norm? | [repodocs `docs/conventions.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md) — the single source for the whole fleet |
| How is a version set and a commit written? | [`versioning.md`](versioning.md) here, and [repodocs `docs/versioning.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/versioning.md) for the fleet's reasoning |
| Was this already decided? | [`decisions.md`](decisions.md) here first, then [repodocs `docs/decisions.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/decisions.md). Do not re-litigate a decided direction — link the ADR |
| Does this change need a test, and did it run? | [repodocs `docs/conventions.md` §9](https://github.com/samirhvbr/repodocs/blob/master/docs/conventions.md#9-a-change-in-behavior-ships-with-the-test-that-fails-when-the-behavior-breaks) — the *Tests run with* line of `CLAUDE.md` says how |
| Is this safe to do? | [`security.md`](security.md). Normative: in a conflict with any other document, it wins |
| How do I bootstrap another repository? | [repodocs `docs/runbook.md`](https://github.com/samirhvbr/repodocs/blob/master/docs/runbook.md) |
| What is still open here? | [`../.continue/README.md`](../.continue/README.md) — the queue, always read first |
