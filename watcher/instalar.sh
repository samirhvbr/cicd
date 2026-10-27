#!/usr/bin/env bash
# Installs or updates the cicd watcher on this machine (docs/watcher.md).
# Run from a checkout of this repository, on the cicd machine, as a user with sudo.
set -euo pipefail
cd "$(dirname "$0")"
command -v act >/dev/null || { echo "act is not installed (see docs/install.md, "act")" >&2; exit 1; }
# The image `conteiner` jobs run in. Rebuilt on every install, so a new base image or a new tool
# in the Dockerfile arrives with the next install.
sudo docker build -q --pull -t shvia/act-ubuntu:24.04 image/
sudo install -d -m 755 /opt/cicd-vigia
sudo install -m 644 vigia.py /opt/cicd-vigia/vigia.py
sudo install -d -m 750 -o root -g runner /etc/cicd-vigia
# The config is replaced only when it does not exist yet: which repositories are switched on is
# decided on the machine, one at a time, and a reinstall must not switch them back.
sudo test -e /etc/cicd-vigia/repos.json || sudo install -m 640 -o root -g runner repos.json /etc/cicd-vigia/repos.json
sudo install -d -m 755 -o runner -g runner /srv/runners/_vigia
sudo install -d -m 755 -o runner -g runner /var/lib/cicd-painel/www/vigia
sudo install -m 644 cicd-vigia.service /etc/systemd/system/cicd-vigia.service
sudo systemctl daemon-reload
if sudo test -s /etc/cicd-vigia/token; then
  sudo systemctl enable --now cicd-vigia.service
  sudo systemctl restart cicd-vigia.service
  echo "watcher running: journalctl -u cicd-vigia -f · http://$(hostname -I | awk '{print $1}'):8080/vigia/"
else
  echo "no token at /etc/cicd-vigia/token yet: the watcher is installed but not started (see docs/watcher.md)"
fi
