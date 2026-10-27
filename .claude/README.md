# Claude Code profile — cicd

> **Status:** `ACTIVE`

`.claude/` in this repository follows the standard of the samirhvbr/Blue3 fleet:
a **permission posture**, versioned. **Nothing here chooses the model**: no
`model`, no `fallbackModel`, no `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_*_MODEL` or
`CLAUDE_CODE_SUBAGENT_MODEL` in `env`. The model is the user's choice, made with
`/model`, and a subagent inherits it (repodocs ADR-027). A custom agent in
`agents/` says `model: inherit`, or nothing.

Conduct rules for the agent are in [CLAUDE.md](../CLAUDE.md).

## Files

| File | Role |
|------|------|
| `settings.json` | The **active** profile, versioned. |
| `settings.local.json` | Machine-local override, **gitignored** — it may hold paths and tokens that belong to one machine. Never commit it. |

## The deny-list beats the allow-list — always

No allow-list entry can re-open a denied rule — that mechanism is unchanged.
What is denied changed on 24/09/2026, by the owner's decision
(repodocs ADR-028):

- **Denied:** key reads by path — `*.pem`, `*.key`, `*.p8`, `*.p12`, `*.pfx`.
- **Ask for confirmation:** `sudo`, `rm -rf`, `curl`/`wget` piped into a shell,
  `gh repo edit`, `gh repo delete`.
- **In no list:** `git push --force` / `-f`, `git reset --hard`, `git clean -fd`
  and reading `.env`. A force-push and a `.env` read match `Bash(git push:*)` and
  `Read` in the allow-list and run without a prompt; `reset --hard` and
  `clean -fd` fall to the default prompt. Not rewriting published history is a
  rule of conduct here, not a block.

## Granting a new permission is the owner's act

The skeleton grants **reading, writing and git, and nothing else**. Nothing for
your stack is granted yet — no build, no test, no package manager, no database
client. That is deliberate.

When a permission needs to exist, it is **written into `settings.json` together
with its reason and how to revert it** — never applied silently, and never left
as a promise in prose.

That last clause is not style. In a sibling repository the agent guide claimed
`git pull` was "pre-authorised (allow)" while no such rule existed in any
settings file; the norm and the artefact disagreed for weeks. A norm that does
not match the artefact is a defect.

<!-- Record each grant here as you make it: what, when, why, how to revert. -->

| Granted | When | Why | Revert by |
|---|---|---|---|
| _(nothing yet)_ | | | |
