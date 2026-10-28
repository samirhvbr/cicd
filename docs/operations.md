# Operations — when something looks wrong

> **Status:** `ACTIVE` · Each row is a case measured on the machine in service between 25/09 and
> 27/10/2026. Read the symptom, run the check, and only then look at the code.

## Symptom → cause

| Symptom | Most likely cause | Check |
|---|---|---|
| Every job fails in 2–5 s with **zero steps** | GitHub's side, not the code: the Actions budget (25/09) or a locked account (26/10) | `gh run view <id>` and read the annotations. *"Actions budget is preventing further use"* = budget; *"account is locked due to a billing issue"* = lock. A self-hosted runner does not help with either: [watcher.md](watcher.md) |
| shvia-web run shows `startup_failure`, "(Unknown event)", "workflow file issue", no jobs | the same lock, worded differently — **not** the YAML | look at a job of another repository of the same owner: its annotation names the cause |
| Jobs queue and never start, runners show online | the same lock; or `CI_RUNNER` names a label no runner has | `gh variable list -R <owner>/<repo>`; [runners.md](runners.md#checking) |
| A job fails at *Initialize containers*; MariaDB `error 28`; *"No more room in record file"* | the disk | `df -h /var/lib/docker /srv/runners`, `sudo docker system df`; [cleanup.md](cleanup.md) |
| *"Could not get lock /var/lib/dpkg/lock-frontend"* | two jobs in `apt` at once | the step needs `-o DPkg::Lock::Timeout=600`; [runners.md](runners.md#dpkg-is-shared) |
| Numbers formatted with a comma (`10,00`), percentages missing | the runner's locale | the runner's `.env` must pin `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`; [runners.md](runners.md#-the-locale) |
| Two test jobs of one repository collide on a database port | fixed host ports in the workflow | `ports: - 3306`, read the port from `job.services`; [runners.md](runners.md#several-runners-for-one-repository) |
| The dashboard shows the machine but no runs | the token is missing, empty, or does not reach the repository | `sudo test -s /etc/cicd-painel/token`; the page's warnings show `HTTP 404` per repository; [dashboard.md](dashboard.md#the-token) |
| The dashboard says *"Nada rodando"* while `/vigia/` lists a build `rodando` | the dashboard installed is older than 0.1.1 and reads GitHub Actions only; or `builds.json` is unreadable to `painel` | `curl -s :8080/estado.json` must list `cicd-vigia` in `runners`; `bash dashboard/instalar.sh`; [dashboard.md](dashboard.md#how-it-is-built) |
| A watcher status says to rebase | the pull request conflicts with its base; its merge ref is stale | rebase the branch; [watcher.md](watcher.md#what-act-does-differently-from-githubs-runner) |
| `sudo` prints *"unable to resolve host"* | the hostname is not in `/etc/hosts` | [install.md §1](install.md#1-the-base-system) |
| Docker images land on `/var` | Docker 29 keeps them in containerd's store | `/var/lib/containerd` must be its own volume; [install.md §2](install.md#2--the-data-volumes--before-docker) |
| `pgrep -f Runner.Worker` always finds something | `pgrep -f` matches its own command line | `pgrep -x Runner.Worker` |

## Routine checks

```bash
ssh samir@100.64.100.240 '
  df -h /var/lib/containerd /var/lib/docker /srv/runners
  systemctl --failed --no-legend
  systemctl list-timers "cicd-*" --no-legend
  systemctl is-active cicd-painel-web cicd-vigia
  systemctl list-units "actions.runner.*" --no-legend | grep -vc "active running"'
```

The last line counts runner services that are **not** running; it should print `0`.

## Updating what is installed

From a clone of this repository, at the version you want, on the machine:

| What | Command |
|---|---|
| Dashboard | `bash dashboard/instalar.sh` |
| Watcher | `bash watcher/instalar.sh` (rebuilds the job image; keeps `/etc/cicd-vigia/repos.json`) |
| Cleanup | the `install` lines of [cleanup.md](cleanup.md#the-layers), then `sudo systemctl daemon-reload` |
| Runners | nothing: they update themselves |

## What this machine does not do

- **No deploy.** Deploying on a green master would need an SSH key into production. The shape
  considered: a dedicated key limited in `authorized_keys` to
  `command="<the deploy script>",no-pty,no-port-forwarding,no-agent-forwarding`, a job that needs
  the test job, and a manual approval. Until then, the deploy stays the owner's command.
- **No network isolation from inside the VM.** Keeping this machine away from production and the
  office LAN is the network's job (Proxmox, firewall). Jobs only need outbound access to GitHub,
  Docker Hub, npm, Packagist, crates.io and the Debian/Sury mirrors.
- **No macOS, Windows or nested virtualisation** ([install.md §0](install.md#0-what-you-need)).
- **No backup.** Everything on it is rebuildable from this repository and from GitHub, except the
  dashboard's history database (`/var/lib/cicd-painel/historico.db`) and the tokens, which the owner
  re-creates. The owner keeps a Proxmox snapshot from before the first setup (28/09/2026).
