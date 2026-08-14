#!/usr/bin/env bash
# Redeploys llm-playground on the Oracle instance. Run this ON THE SERVER
# (not locally) after a first-time setup — see CONTEXT-deploy-oracle.md for
# provisioning steps (venv, systemd unit, firewall) that only happen once.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Pulling latest code..."
git pull

echo "==> Installing/updating dependencies..."
source .venv/bin/activate
pip install -q -r backend/requirements.txt

echo "==> Clearing stale bytecode cache..."
find . -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

echo "==> Restarting service..."
sudo systemctl restart llm-playground

echo "==> Waiting for it to come back up..."
for i in $(seq 1 15); do
  if curl -sf --max-time 3 localhost:8001/api/llm-quirks/cases >/dev/null 2>&1; then
    echo "==> READY after $((i * 2))s"
    exit 0
  fi
  sleep 2
done

echo "==> TIMED OUT"
sudo journalctl -u llm-playground -n 40 --no-pager
exit 1
