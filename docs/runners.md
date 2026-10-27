# Runners — GitHub Actions on this machine

> **Status:** `ACTIVE` · From the shvia-web runbook (28/09–15/10/2026) and the machine measured
> read-only on 27/10/2026.

A self-hosted runner does not consume the account's GitHub-hosted minutes. That is why this
machine exists: on 25/09/2026 the Actions budget ran out and every job of a private repository
failed in 2–5 s with zero steps (*"The job was not started because an Actions budget is preventing
further use"*).

**As of 28/09/2026 GitHub charges nothing for a self-hosted runner.** A $0.002/min platform fee
for self-hosted runners in private repositories was announced for 01/03/2026 and then
**postponed, not cancelled**
([GitHub](https://github.com/resources/insights/2026-pricing-changes-for-github-actions)). If it
comes back, these minutes count against the same budget.

🔴 **And a runner does not survive a locked account.** GitHub is what hands a job to a runner. On
26/10/2026 the account was locked for billing: the four `cicd-web` runners were online and idle,
and a push to shvia-web's master created a run with zero jobs (`startup_failure`, measured on
27/10 at 12:15Z). Dependabot and the release workflows stop for the same reason. That case is
the [watcher](watcher.md)'s.

## The switch — a repository variable, not an edit

Every job reads:

```yaml
runs-on: ${{ vars.CI_RUNNER || 'ubuntu-latest' }}
```

```bash
gh variable set CI_RUNNER --body shvia-ci -R <owner>/<repo>    # jobs go to this machine
gh variable delete CI_RUNNER -R <owner>/<repo>                 # jobs go back to GitHub
```

The runners carry the labels `self-hosted, Linux, X64, shvia-ci`. `shvia-ci` is ours so that it
never collides with a GitHub-hosted label. **Never set the variable at organisation scope**: it
retargets every repository at once, public ones that run free on hosted minutes included.

## Which repositories may use it

**Every repository of the fleet, public ones included** — the owner's decision of 07/10/2026
([repodocs ADR-030](https://github.com/samirhvbr/repodocs/blob/master/docs/decisions.md)). Until
then a public repository was forbidden, and the reason has not gone away: **a pull request from
any fork runs its author's code on this machine**, as a user with passwordless `sudo` and
`docker`. What stands where the prohibition stood is one setting, per public repository:
*Settings → Actions → Fork pull request workflows → **Require approval for all external
contributors***. On a public repository that uses this machine, it is not optional.

**Joining is pre-authorised; registering is the owner's act.** It needs admin on the repository
and a one-hour registration token, and the jobs run with `sudo` inside the office network. An
agent says what is needed and asks; it never registers a runner on its own initiative.

A repository of **another account** is not covered: registering needs admin there, the minutes
are billed to that account anyway, and the dashboard's token cannot reach it. Decided case by
case (28/09/2026: a collaborator's private repository, left on GitHub-hosted runners).

Jobs that cannot run here at all: macOS, Windows, and anything that needs `/dev/kvm` (an Android
emulator). shvia-code's `build-windows.yml` stays on `windows-latest` for that reason.

## Layout

| | |
|---|---|
| User | `runner`, home `/srv/runners/home`, groups `runner` and `docker`, passwordless `sudo` |
| One folder per runner | `/srv/runners/<short>` — e.g. `web`, `web-2`, `code`, `workspace` |
| The package | `/srv/runners/_pkg/actions-runner-linux-x64-<version>.tar.gz`, checked against the release notes' SHA-256 |
| Service | `actions.runner.<owner>-<repo>.cicd-<short>.service`, created by the runner's `svc.sh` |
| Updates | the runners update themselves (2.337.0 installed on 28/09; 2.338.0 arrived on 24/10) |

**One runner per repository.** A personal account cannot share a runner between its
repositories. An organisation can register one for all of them; the dashboard lists such a
runner with a warning, because it does not read organisation runs yet.

## Several runners for one repository

shvia-web has four (`cicd-web`, `-2`, `-3`, `-4`). Its suite takes ~25 min here and every landing
runs it again on master, so one runner queued a day's worth of pull requests. Four test jobs run at
once because:

- **the service containers publish random host ports.** The workflow declares `ports: - 3306`
  (not `3306:3306`), reads the port in its first step from `job.services.<name>.ports` and writes
  it to `$GITHUB_ENV` as `DB_PORT`/`PGSQL_PORT`. With a fixed host port, two jobs collided;
- **they install the same PHP** with `setup-php`, which installs system-wide, so they do not fight
  over the version. Only shvia-web uses `setup-php` on this machine.

### dpkg is shared

The one collision random ports do not cover. Run 36598888287 (29/09/2026) died in 1 s on
*"Could not get lock /var/lib/dpkg/lock-frontend … held by process (apt-fast)"* — another job's
`setup-php`. A step that installs a system package on this machine must skip when the tool is
already there and otherwise wait for the lock:

```bash
command -v pdftotext >/dev/null || sudo apt-get -o DPkg::Lock::Timeout=600 install -y poppler-utils
```

## 🔴 The locale

**Each runner's `.env` pins `LANG=C.UTF-8` and `LC_ALL=C.UTF-8`.** `config.sh` copies the host's
`LANG` into `.env`; the VM was installed in Portuguese, and the first shvia-web run failed five
tests on the decimal comma (`'10,00 MB'` where the test expects `10.00 MB`, a missing `50.0%`).
PHP's `%f` follows `LC_NUMERIC`. GitHub-hosted runners run in `C.UTF-8`, and so must these.

## Adding a repository

From your workstation, with `gh` logged in as the repository's owner. The registration token
lasts one hour and goes through stdin, never into a file:

```bash
OWNER=samirhvbr; REPO=<repo>; SHORT=<short>            # SHORT names the folder and the runner
HOST=samir@100.64.100.240; V=2.337.0                     # V = the tarball in /srv/runners/_pkg
gh api -X POST "repos/$OWNER/$REPO/actions/runners/registration-token" -q .token \
| ssh "$HOST" "sudo -u runner bash -c 'set -e; D=/srv/runners/$SHORT; mkdir -p \$D; cd \$D; \
    tar -xzf /srv/runners/_pkg/actions-runner-linux-x64-$V.tar.gz; \
    ./config.sh --unattended --url https://github.com/$OWNER/$REPO --token \"\$(cat)\" \
      --name cicd-$SHORT --labels shvia-ci --work _work; \
    sed -i /^LANG=/d .env; printf \"runner=self-hosted\nLANG=C.UTF-8\nLC_ALL=C.UTF-8\n\" >> .env' \
  && cd /srv/runners/$SHORT && sudo ./svc.sh install runner && sudo ./svc.sh start"
gh variable set CI_RUNNER --body shvia-ci -R "$OWNER/$REPO"
```

- `sudo -u runner` and `svc.sh install runner`: the runner's files and its jobs belong to
  `runner`, never to the login user (see the exception in
  [install.md](install.md#what-the-running-machine-looks-like)).
- A second runner for the same repository: the same command with `SHORT=<short>-2`.
- **The dashboard picks the runner up by itself** (it reads every runner's `.runner`), but it can
  read the repository's runs only once **the owner adds the repository to the dashboard's
  token** ([dashboard.md](dashboard.md#the-token)). Until then its warnings show `HTTP 404`.
- For a public repository: set fork pull request approval first (above).

## Removing a runner

```bash
gh api -X POST "repos/$OWNER/$REPO/actions/runners/remove-token" -q .token \
| ssh "$HOST" "cd /srv/runners/$SHORT && sudo ./svc.sh stop && sudo ./svc.sh uninstall \
  && sudo -u runner ./config.sh remove --token \"\$(cat)\""
gh variable delete CI_RUNNER -R "$OWNER/$REPO"          # if it was the repository's last runner here
```

Delete the folder afterwards (`sudo rm -rf /srv/runners/$SHORT`) — after `config.sh remove`, so
GitHub forgets the runner too.

## Checking

```bash
for r in shvia-web shvia-code shvia-workspace shvia-site shvia-ollama; do
  gh api "repos/samirhvbr/$r/actions/runners" -q '.runners[] | "\(.name) \(.status) busy=\(.busy)"'
done
```

On the machine: `systemctl list-units 'actions.runner.*'`. To see whether a runner is running a
job, look for its `Runner.Worker` with `pgrep -x Runner.Worker` — `pgrep -f` matches its own
command line.

**A job that fails in 2 s with zero steps** is not the code: read the run's annotations
(`gh run view <id>`) before anything else. *"Actions budget"* is the budget, *"account is locked
due to a billing issue"* is the lock, and on shvia-web a run with `startup_failure`,
"(Unknown event)" and "workflow file issue" was the same lock, not the YAML.
