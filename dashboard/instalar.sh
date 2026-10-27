#!/bin/bash
# Installs (or updates) the cicd dashboard on the cicd machine. Idempotent. Run on the machine,
# from this folder, as a user with sudo:  bash instalar.sh
# The GitHub token is NOT handled here: see docs/dashboard.md.
set -euo pipefail
cd "$(dirname "$0")"
id painel >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin --comment "cicd dashboard" painel
sudo install -d -m 755 /opt/cicd-painel
sudo install -m 644 coletor.py /opt/cicd-painel/coletor.py
# /var/lib/cicd-painel holds the history database and the ETag cache; only www/ is served.
sudo install -d -m 755 -o painel -g painel /var/lib/cicd-painel /var/lib/cicd-painel/www
sudo install -m 644 -o painel -g painel index.html /var/lib/cicd-painel/www/index.html
# Before the history (28/09/2026) the page and its snapshot sat in /var/lib/cicd-painel itself,
# and the web server served that whole folder. It now holds the database, so the old files go.
sudo rm -f /var/lib/cicd-painel/index.html /var/lib/cicd-painel/estado.json /var/lib/cicd-painel/jobs-terminados.json
# The token's folder: readable by the dashboard's user only. The jobs run as `runner`, which
# must never read it.
sudo install -d -m 750 -o root -g painel /etc/cicd-painel
for u in cicd-painel-coletor.service cicd-painel-coletor.timer cicd-painel-web.service; do
  sudo install -m 644 "$u" /etc/systemd/system/"$u"
done
sudo systemctl daemon-reload
sudo systemctl enable --now cicd-painel-web.service cicd-painel-coletor.timer
# `enable --now` leaves a running server alone; a changed unit (the served folder moved) needs this.
sudo systemctl restart cicd-painel-web.service
sudo systemctl start cicd-painel-coletor.service
echo "dashboard: http://$(hostname -I | awk '{print $1}'):8080/"
# sudo: the folder is 750 root:painel, so the installing user cannot see into it, and a plain
# test said "no token yet" on 28/09/2026 with the token in place.
sudo test -s /etc/cicd-painel/token || echo "no token yet: the page shows the machine only (see docs/dashboard.md, "The token")"
