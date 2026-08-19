# Context: Deployment on Oracle Cloud

Deployed on the same Oracle Cloud instance as `rag-prototype`
(`~/Documents/ai/rag-prototype`, live at `http://134.98.154.12:8000/`), on a separate
port — same VM, independent app, independent systemd service.

- **Live at:** `http://134.98.154.12:8001/` (raw IP) and
  `https://llm.williamkinaan.com/` (custom domain — see "Custom domain" below).
  Same origin, same systemd service — not two deployments.
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

No TLS on the raw IP:port — plain HTTP on `134.98.154.12:8001`, same as
rag-prototype. TLS/domain access goes through nginx instead (see below).

## Custom domain (`llm.williamkinaan.com`)

DNS is Cloudflare-proxied (orange-cloud) — `dig llm.williamkinaan.com` resolves to
Cloudflare's edge IPs, not the Oracle box directly. Cloudflare terminates the
public HTTPS connection, then proxies to the box over HTTPS ("Full (strict)" SSL
mode), where **nginx** (already installed on the box for other subdomains, not
part of this repo) terminates that connection using a Cloudflare Origin CA cert
and reverse-proxies to the same `llm-playground` service the raw IP hits:

```
# /etc/nginx/conf.d/subdomains.conf (server-only file, not in this repo — shared
# with sibling domains rag.williamkinaan.com -> :8000 and
# harness.williamkinaan.com -> :8003, each its own server{} block)
server {
    listen 443 ssl;
    server_name llm.williamkinaan.com;
    ssl_certificate     /etc/nginx/ssl/cf-origin.pem;
    ssl_certificate_key /etc/nginx/ssl/cf-origin.key;
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
(plus a `listen 80` block for the same `server_name` that 301-redirects to
`https://`).

**Practically: there is nothing extra to deploy for the domain.** It's the same
`llm-playground` systemd service on port 8001 that `deploy-oracle.sh` already
restarts — one redeploy updates both URLs at once. Confirmed by diffing the two
responses byte-for-byte after a deploy. If the domain ever serves something
*different* from the raw IP, the systemd service is fine and the problem is in
nginx or Cloudflare (e.g. Cloudflare edge cache — check `cf-cache-status` in the
response headers — or nginx not reloaded), not in this app.

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

- **No auth**, and only a simple in-memory rate limit (see
  `backend/app/rate_limiter.py` — one global fixed-window request counter, no
  Redis, resets on restart, blind to traffic on other apps sharing this same
  Mistral key). Anyone who finds the URL can still spend the Mistral quota, just
  bounded per short window instead of unbounded. Tune `RATE_LIMIT_MAX_REQUESTS` /
  `RATE_LIMIT_WINDOW_SECONDS` in `.env` against the real limit at
  console.mistral.ai → Admin Panel → API → Limits (sized as this app's *share*,
  since rag-prototype and other live apps draw on the same workspace key).
  Acceptable for a portfolio demo; revisit if that changes.
- **No TLS on the raw IP:port** — `134.98.154.12:8001` is plain HTTP, same as
  rag-prototype. TLS is only available via the `llm.williamkinaan.com` domain
  (Cloudflare + nginx, see "Custom domain" above).
- Uses a Mistral key rotated specifically for this deployment, not the one that was
  originally exposed in plaintext in `openai/moderation.py`.
