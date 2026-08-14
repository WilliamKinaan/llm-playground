# Context: Deployment on Oracle Cloud

Deployed on the same Oracle Cloud instance as `rag-prototype`
(`~/Documents/ai/rag-prototype`, live at `http://134.98.154.12:8000/`), on a separate
port — same VM, independent app, independent systemd service.

- **Live at:** `http://134.98.154.12:8001/`
- **Instance:** Oracle Linux 9.8, SELinux Enforcing, user `opc`, same VM as
  rag-prototype. See `rag-prototype/CONTEXT-deploy-oracle.md` for instance-shape
  history and the two Oracle-Linux-specific gotchas (SQLite version, SELinux) —
  the SELinux one applies here too (see below).
- **Python:** `python3.12` (the box's default `python3` is 3.9, too old for this
  codebase's `X | None` type hints) — venv built explicitly with `python3.12 -m venv`.
- **Repo on the box:** `~/llm-playground` (public GitHub repo, plain `git clone`,
  no auth needed)
- **Secrets:** `~/llm-playground/.env` (gitignored, hand-created on the server,
  `chmod 600`), holding `MISTRAL_API_KEY`. Read both by the app's own
  `pydantic-settings` config (`backend/app/config.py`) and by systemd's
  `EnvironmentFile=` (belt and suspenders, same pattern as rag-prototype).

## SELinux (same fix rag-prototype needed)

`systemd` runs services in the `init_t` domain, which can't exec anything labeled
`user_home_t` — the default label for everything under `/home`. Needed once after
creating the venv (and again if the venv is ever recreated at this path):
```bash
sudo semanage fcontext -a -t bin_t '/home/opc/llm-playground/.venv/bin(/.*)?'
sudo restorecon -Rv /home/opc/llm-playground/.venv/bin
```

## Running as a service

`systemd` unit at `/etc/systemd/system/llm-playground.service` (server-only file,
not in the repo — recreate from this if the instance is ever rebuilt):
```ini
[Unit]
Description=LLM Playground FastAPI webapp
After=network.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/llm-playground
Environment="PATH=/home/opc/llm-playground/.venv/bin:/usr/bin:/bin"
EnvironmentFile=-/home/opc/llm-playground/.env
ExecStart=/home/opc/llm-playground/.venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8001
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Common commands:
```bash
sudo systemctl status llm-playground     # health check
sudo systemctl restart llm-playground    # restart, e.g. after a git pull
sudo journalctl -u llm-playground -f     # live logs
```

## Networking

Two independent layers, both needed:
- **OS firewall** (`firewalld`): `sudo firewall-cmd --permanent --add-port=8001/tcp && sudo firewall-cmd --reload`
- **Cloud network** (Oracle Security List on the instance's VCN, console-only): an
  ingress rule — source `0.0.0.0/0`, TCP, destination port `8001`. Same list that
  already has the rule for rag-prototype's port 8000.

No TLS/domain — plain HTTP on the raw public IP, same as rag-prototype.

## Redeploying after a code change

Same rule as rag-prototype: **committing/pushing to GitHub is always fine without
asking; actually SSHing in to restart the live service is a separate,
explicitly-confirmed step every time**, even when a change is already pushed.

```bash
# locally: commit + push as normal
git add -A && git commit -m "..." && git push origin main

# on the server, once confirmed:
ssh -i ~/.ssh/oracle_rag_prototype opc@134.98.154.12
~/llm-playground/deploy-oracle.sh
```

## Deploy-from-scratch steps (for rebuilding on a fresh instance, or first-time setup)

```bash
git clone https://github.com/WilliamKinaan/llm-playground.git ~/llm-playground
cd ~/llm-playground
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

echo "MISTRAL_API_KEY=..." > ~/llm-playground/.env
chmod 600 ~/llm-playground/.env

sudo semanage fcontext -a -t bin_t '/home/opc/llm-playground/.venv/bin(/.*)?'
sudo restorecon -Rv /home/opc/llm-playground/.venv/bin

# create /etc/systemd/system/llm-playground.service (see above), then:
sudo systemctl daemon-reload
sudo systemctl enable --now llm-playground

sudo firewall-cmd --permanent --add-port=8001/tcp && sudo firewall-cmd --reload
# + add the Security List ingress rule in the Oracle console (see above)
```

## Known caveats

- **No auth / no rate limiting** on `/api/moderation/check` or
  `/api/llm-quirks/.../run` — anyone who finds the URL can spend the Mistral quota
  on the key in `.env`. Acceptable for a portfolio demo; revisit if that changes.
- **No TLS/domain** — plain HTTP on the public IP only, same as rag-prototype.
- Uses a Mistral key rotated specifically for this deployment, not the one that was
  originally exposed in plaintext in `openai/moderation.py`.
