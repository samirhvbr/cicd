# Building a new cicd machine

> **Status:** `ACTIVE` · Written 27/10/2026 from the machine in service (measured read-only that
> day) and from the original runbook in shvia-web (28/09–27/10/2026).
>
> ⚠️ **This sequence has not yet been replayed end to end on a clean VM.** Each step was done on
> the machine in service, but over a month and partly by hand; the commands below are that work
> written as one sequence. Every step names its source, and every step ends with a check, so a
> deviation shows up at the step that caused it. Replaying it on a scratch VM is the first item
> of the [queue](../.continue/README.md).

The order matters in three places, and each is marked 🔴: the data volumes go in **before**
Docker, the locale of the runners is pinned **before** the first job, and the tokens are put on
the machine **by the owner**, never by a script.

## 0. What you need

| | |
|---|---|
| A VM | Debian 13 "trixie", amd64. In service: 8 vCPU, 16 GB RAM. More vCPUs mean more jobs at once; RAM is what a suite with MariaDB and Postgres service containers uses up first |
| Disks | A system disk (60 GB in service) and a separate data disk (320 GB in service) for images, containers and the runners' work folders |
| Network | Outbound HTTPS to GitHub, Docker Hub, npm, Packagist, crates.io and the Debian mirrors. No inbound access from the internet. Port 8080 open to the office network for the dashboard |
| GitHub | Admin on every repository that gets a runner (registering one needs it), and the owner to create two fine-grained tokens (§8, §9) |
| Your workstation | `ssh` to the VM, `gh` logged in as the repositories' owner, and a clone of this repository |

Nested virtualisation is **not** needed and was not available in service (measured 06/10/2026:
`QEMU Virtual CPU`, no `vmx`/`svm`, no `/dev/kvm`). So no Android emulator, and no Windows or macOS
inside this VM: those jobs stay on GitHub-hosted runners or on a machine of that OS.

## 1. The base system

Install Debian 13 with LVM on the system disk. The layout in service, as the installer left it:

| Volume (`vg0`) | Size | Mount |
|---|---|---|
| `root` | 7.6 GB, xfs | `/` |
| `var` | 7.6 GB, btrfs | `/var` |
| `log` | 11.4 GB, btrfs | `/var/log` |
| `tmp` | 3.8 GB, btrfs | `/tmp` |
| `swap` | 3.8 GB | swap |

`/var` is small on purpose: nothing heavy may land there, and §2 is what keeps it so.

The hostname must resolve, or every `sudo` prints *"unable to resolve host"*. In service the
machine is called `cicd` and `/etc/hostname` says `cicd-web`; both are aliases in `/etc/hosts`:

```bash
grep 127.0.1.1 /etc/hosts      # in service: 127.0.1.1  <fqdn>  cicd-web cicd
```

Packages (measured on the machine in service, 27/10/2026):

```bash
sudo apt-get update
sudo apt-get install -y git jq zip unzip xz-utils rsync build-essential pkg-config libssl-dev \
  python3 mariadb-client postgresql-client poppler-utils unattended-upgrades curl ca-certificates
sudo systemctl enable --now unattended-upgrades
```

- **Clients only** of MariaDB and PostgreSQL. The servers come as service containers in each job.
  A MariaDB or Postgres installed on the host takes their ports and breaks the jobs.
- `poppler-utils` (`pdftotext`) is there because shvia-web's CI installs it with `apt`, and with
  it already present the step skips (see [runners.md](runners.md#dpkg-is-shared)).
- PHP, Node and Rust are **not** installed on the host: `setup-php`, `setup-node` and
  `dtolnay/rust-toolchain` install them per job.
- Java (`openjdk-21-jdk-headless`) is installed in service for the Java projects' jobs. Install
  it only if a repository needs it.

The VM in service was installed in Portuguese (`LANG=pt_BR.UTF-8` in `/etc/default/locale`). That
is harmless for the host and **wrong for a job** — §6 pins the runners to `C.UTF-8`.

## 2. 🔴 The data volumes — before Docker

Docker 29 keeps images in **containerd's** store (`/var/lib/containerd`), not in
`/var/lib/docker`. On the first run in service, 1.1 GB of images landed on the 7.6 GB `/var`
(measured 28/09/2026), and the volumes were moved the same day. Create them first and Docker
never writes to the system disk.

| Volume (`vg_cicd`) | Size in service | Mount | What lands there |
|---|---|---|---|
| `containerd` | 110 GB | `/var/lib/containerd` | images and container layers |
| `docker` | 50 GB (created at 120, cut to 30, grown to 50) | `/var/lib/docker` | volumes (the jobs' databases), container config, logs, build cache |
| `runners` | 140 GB | `/srv/runners` | each runner, its `_work`, and the `runner` user's home with the cargo, npm and composer caches |
| free | 20 GB | — | `lvextend -r` grows any of them online |

```bash
lsblk                                   # find the data disk; it is /dev/sda in service — check yours
DISK=/dev/sdX
sudo pvcreate "$DISK"
sudo vgcreate vg_cicd "$DISK"
sudo lvcreate -n containerd -L 110G vg_cicd
sudo lvcreate -n docker     -L 50G  vg_cicd
sudo lvcreate -n runners    -L 140G vg_cicd
for lv in containerd docker runners; do sudo mkfs.ext4 -q "/dev/vg_cicd/$lv"; done
sudo mkdir -p /var/lib/containerd /var/lib/docker /srv/runners
for pair in containerd:/var/lib/containerd docker:/var/lib/docker runners:/srv/runners; do
  lv=${pair%%:*}; mnt=${pair#*:}
  echo "UUID=$(sudo blkid -s UUID -o value /dev/vg_cicd/$lv)  $mnt  ext4  defaults,noatime  0  2" | sudo tee -a /etc/fstab
done
sudo systemctl daemon-reload && sudo mount -a
df -h /var/lib/containerd /var/lib/docker /srv/runners     # check: three ext4 mounts on vg_cicd
```

Growing one later, online: `sudo lvextend -r -L +20G /dev/vg_cicd/docker`.

## 3. Docker Engine

From Docker's own Debian repository (`download.docker.com`), with `buildx` and `compose`. Follow
[docs.docker.com/engine/install/debian](https://docs.docker.com/engine/install/debian/) — the
commands in service were that page's:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Log rotation, 10 MB × 3 per container ([`host/daemon.json`](../host/daemon.json)):

```bash
sudo install -m 644 host/daemon.json /etc/docker/daemon.json
sudo systemctl restart docker
docker info --format '{{.LoggingDriver}} {{.DockerRootDir}}'   # check: json-file /var/lib/docker
```

In service on 27/10/2026: Docker 29.9.2, Compose v5.6.1, buildx v0.38.1.

## 4. GitHub CLI

Self-hosted runners do not come with `gh`, and release workflows call it. From
[cli.github.com](https://github.com/cli/cli/blob/trunk/docs/install_linux.md):

```bash
sudo curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg
sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
  | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt-get update && sudo apt-get install -y gh
gh --version
```

## 5. The `runner` user

```bash
sudo useradd --create-home --home-dir /srv/runners/home --shell /bin/bash --comment "GitHub Actions runner" runner
sudo usermod -aG docker runner
sudo chown runner:runner /srv/runners
sudo install -m 440 host/90-runner /etc/sudoers.d/90-runner
sudo visudo -cf /etc/sudoers.d/90-runner                    # check: parsed OK
```

[`host/90-runner`](../host/90-runner) is `runner ALL=(ALL) NOPASSWD:ALL`. `setup-php` and some
workflows install packages with `apt`, so the jobs need it. **It is acceptable only because the VM
does nothing else** — see [security.md](security.md#0-this-machine).

The home lives on the runners' volume so that the per-user caches (`~/.cargo`, `~/.npm`,
composer) do not fill the system disk.

## 6. 🔴 The runners

Download the runner once, check it, keep it in `/srv/runners/_pkg`:

```bash
V=2.337.0            # the version in service; any recent one works — runners update themselves
sudo -u runner mkdir -p /srv/runners/_pkg
cd /srv/runners/_pkg
sudo -u runner curl -fsSLO "https://github.com/actions/runner/releases/download/v$V/actions-runner-linux-x64-$V.tar.gz"
sha256sum "actions-runner-linux-x64-$V.tar.gz"   # compare with the SHA-256 in that release's notes
```

Then one runner per repository, as [runners.md](runners.md#adding-a-repository) describes. The
step that must not be skipped is the `.env` of each runner:

```
runner=self-hosted
LANG=C.UTF-8
LC_ALL=C.UTF-8
```

`config.sh` copies the host's `LANG` into the runner's `.env`. In service that was `pt_BR.UTF-8`,
and the first shvia-web run failed five tests on the decimal comma (`'10,00 MB'` where the test
expects `10.00 MB`), because PHP's `%f` follows `LC_NUMERIC`. GitHub's runners run in `C.UTF-8`,
and so must these. `runner=self-hosted` is what `setup-php` asks for on a self-hosted runner.

## 7. Cleanup

Install all of it before the first job — the disk filled within two days the first time
([cleanup.md](cleanup.md) has each case):

```bash
sudo install -m 755 host/cicd-limpeza /etc/cron.weekly/cicd-limpeza
sudo install -m 755 cleanup/cicd-container-prune.sh cleanup/cicd-disk-guard.sh /usr/local/sbin/
sudo install -m 644 cleanup/*.service cleanup/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cicd-volume-prune.timer cicd-container-prune.timer cicd-cache-prune.timer cicd-disk-guard.timer
systemctl list-timers 'cicd-*'                               # check: four timers with a next run
sudo /usr/local/sbin/cicd-disk-guard.sh --dry-run           # prints what it would do; removes nothing
```

## 8. The dashboard

```bash
bash dashboard/instalar.sh          # on the machine, from a clone of this repository
```

It creates the system user `painel`, installs the collector in `/opt/cicd-painel`, the page in
`/var/lib/cicd-painel/www`, and starts `cicd-painel-web.service` (port 8080) and
`cicd-painel-coletor.timer` (every 30 s). Without a token the page shows the machine only. The
token, its scopes and how the owner puts it on the machine: [dashboard.md](dashboard.md#the-token).

Check: `http://<host>:8080/` loads, and the machine panel shows the three data volumes.

## 9. act and the watcher

`act`, pinned and checked against the release's checksums:

```bash
A=0.2.89             # the version in service
cd "$(mktemp -d)"
curl -fsSLO "https://github.com/nektos/act/releases/download/v$A/act_Linux_x86_64.tar.gz"
curl -fsSLO "https://github.com/nektos/act/releases/download/v$A/checksums.txt"
grep ' act_Linux_x86_64.tar.gz$' checksums.txt | sha256sum -c -      # check: OK
tar -xzf act_Linux_x86_64.tar.gz act
sudo install -m 755 act /usr/local/bin/act
act --version
```

Then the watcher, from a clone of this repository on the machine:

```bash
bash watcher/instalar.sh
```

It builds the job image (`shvia/act-ubuntu:24.04`, from [`watcher/image/`](../watcher/image/)),
installs `vigia.py` in `/opt/cicd-vigia`, installs `/etc/cicd-vigia/repos.json` **only if it does
not exist**, and starts `cicd-vigia.service` only when the token is in place. Edit
`/etc/cicd-vigia/repos.json` for this machine — owner, log URL, which repositories are on — and
follow [watcher.md](watcher.md#installing-and-switching-a-repository-on) for the token and the
rehearsal.

## 10. Done — what a working machine shows

```bash
df -h /var/lib/containerd /var/lib/docker /srv/runners          # three volumes, none above 75%
systemctl --failed                                               # nothing
systemctl list-units 'actions.runner.*' --no-legend              # one per runner, active running
systemctl list-timers 'cicd-*' --no-legend                       # five timers
systemctl is-active cicd-painel-web cicd-vigia                   # active active
```

And from your workstation, for each repository:

```bash
gh api repos/<owner>/<repo>/actions/runners -q '.runners[] | "\(.name) \(.status) busy=\(.busy)"'
```

## What the running machine looks like

Measured read-only on 27/10/2026, so that a new machine can be compared with the one in service.

| | |
|---|---|
| OS | Debian GNU/Linux 13 (trixie), Python 3.13.5 |
| CPU / RAM | 8 vCPU, 15 GiB |
| Data volumes | `containerd` 110 GB, `docker` 50 GB, `runners` 140 GB; `vg_cicd` 20 GB free |
| Docker | 29.9.2 · Compose v5.6.1 · buildx v0.38.1 |
| gh / act | 2.103.0 / 0.2.89 |
| Runners (13) | `cicd-web`, `-2`, `-3`, `-4` (shvia-web); `cicd-code`, `cicd-workspace`, `cicd-site`, `cicd-ollama` (shvia-*); `cicd-eop`; `cicd-blue3-intranet`; `cicd-sshvterm-api`, `-desktop`, `-web` |
| Runner `.env` | 12 of the 13: `runner=self-hosted`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`, folder owned by `runner` |
| 🔴 The exception | `cicd-eop` (registered 30/09/2026) runs as **`samir`**, the owner's login user, not `runner`; its folder is `samir`'s, and its `.env` has no locale pin, so its jobs run with `LANG=pt_BR.UTF-8` (measured in the process environment). Both are the two things §5 and §6 exist to prevent. Not changed here: re-registering a runner is the owner's act — it is in the [queue](../.continue/README.md) |
| Services | 13 `actions.runner.*`, `cicd-painel-web`, `cicd-vigia` — all active |
| Timers | `cicd-painel-coletor`, `cicd-disk-guard`, `cicd-volume-prune`, `cicd-container-prune`, `cicd-cache-prune` |
| Job images | `shvia/act-ubuntu:24.04` (2.66 GB) and a `26.04` being tried, over `catthehacker/ubuntu:act-24.04` |
| Users | `runner` (1001, groups `runner`, `docker`), `painel` (system, no login) |
| Permissions | `/etc/cicd-painel` `750 root:painel` · `/etc/cicd-vigia` `750 root:runner` · `/etc/sudoers.d/90-runner` `440 root:root` |

Other projects also run on the machine in Docker volumes of their own (`tura-ci-1`, `tura-ci-2`),
which the cleanup takes into account ([cleanup.md](cleanup.md#the-disk-guard)).
