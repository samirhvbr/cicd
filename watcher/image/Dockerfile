# The image `conteiner` jobs run in (docs/watcher.md): act's Ubuntu 24.04
# image plus what GitHub's ubuntu-latest ships and a workflow here relies on. Each addition says
# which job needs it, so a tool nobody uses any more can be taken out.
FROM catthehacker/ubuntu:act-24.04

# PowerShell: shvia-desktop's `prova:instaladores-ps1` runs the Windows runner installers under
# pwsh, and in CI it fails on purpose when pwsh is missing (measured on 27/10/2026).
RUN apt-get update \
 && apt-get install -y --no-install-recommends wget ca-certificates \
 && wget -q https://packages.microsoft.com/config/ubuntu/24.04/packages-microsoft-prod.deb \
 && dpkg -i packages-microsoft-prod.deb && rm packages-microsoft-prod.deb \
 && apt-get update && apt-get install -y --no-install-recommends powershell \
 && rm -rf /var/lib/apt/lists/* \
 && pwsh -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'

# Database clients: shvia-web's `test` job waits for its MariaDB service with `mysqladmin ping` and
# for pgvector with `pg_isready`/`psql` (measured on 27/10/2026: "mysqladmin: command not found").
RUN apt-get update \
 && apt-get install -y --no-install-recommends mariadb-client postgresql-client \
 && rm -rf /var/lib/apt/lists/* \
 && mysqladmin --version && pg_isready --version
