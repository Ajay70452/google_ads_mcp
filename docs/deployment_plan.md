# Deployment Plan — Google Ads MCP

End-to-end plan for taking this project from local dev to a 24/7 production deployment serving the MethodPro team.

---

## 1. What's Being Deployed

### Components

| Component | Runs Where | Purpose |
|---|---|---|
| **FastAPI backend** | Cloud server | Serves all 11 MCP tools via HTTP. Hits Google Ads API, manages cache. |
| **Scheduler** | Cloud server | Runs the 3 agents on cron schedule (daily/weekly). |
| **PostgreSQL 16** | Cloud server | Account registry, change log, ad copy history. |
| **Redis 7** | Cloud server | Query cache (3 hr TTL) + API call counter. |
| **MCP server** | Each user's laptop | stdio bridge from Claude Desktop → cloud backend. **Stays local.** |

### Deployment topology

```
┌─────────────────────────────────────────────┐
│  User's laptop (Claude Desktop)             │
│    └─ mcp_server.server (stdio subprocess)  │──── HTTPS ────┐
└─────────────────────────────────────────────┘               │
                                                              ▼
                        ┌──────────────────────────────────────────┐
                        │  Cloud server  (EC2 t3.small or similar) │
                        │  ┌────────────────────────────────────┐  │
                        │  │  docker-compose:                   │  │
                        │  │    backend  (FastAPI, port 8001)   │──┼─→ Google Ads API
                        │  │    scheduler  (APScheduler loop)   │──┼─→ OpenAI API
                        │  │    postgres                        │──┼─→ Zoho Cliq
                        │  │    redis                           │  │
                        │  │    caddy   (HTTPS reverse proxy)   │  │
                        │  └────────────────────────────────────┘  │
                        └──────────────────────────────────────────┘
```

---

## 2. Pre-Deployment Checklist

Before touching infrastructure, finish these items locally:

### 2.1 Google OAuth — move to Production

**Critical.** Currently the OAuth app is in "Testing" mode → refresh tokens expire after 7 days. Once-deployed agents will start failing 7 days after each token refresh.

1. Open https://console.cloud.google.com/apis/credentials/consent
2. Select the app (the one tied to `CLIENT_ID=53212855766-...`)
3. Publishing status → **Publish App**
4. Verification: not required for internal use within the workspace, but Google may flag for review if scopes are sensitive. For Google Ads API scope, expect "Verification not required" since `adwords` is non-sensitive when used with a developer token.
5. After publishing, regenerate `REFRESH_TOKEN` once more so the new token is issued under the production-mode app. Update `.env`.

### 2.2 Generate a long-lived service refresh token

Recommended: generate the refresh token from a dedicated Google account (e.g. `automation@methodpro.com`) that has manager access to MCC `7701109307`. Avoid tying production to a personal account that might lose access.

### 2.3 Lock down secrets

Audit `.env` and confirm none of these have leaked into git:
- `DEVELOPER_TOKEN`
- `CLIENT_SECRET`
- `REFRESH_TOKEN`
- `OPENAI_API_KEY`
- `CLIQ_ZAPIKEY`

Run `git log --all -p -- .env` to check. If any were ever committed, **rotate them now** (regenerate at the source) before deploying.

### 2.4 Domain — skipped (demo deployment)

This is a demo, so no DNS or HTTPS is required. The backend will be reachable directly at `http://<server-ip>:8001`. When ready to promote to production:

1. Buy / pick a subdomain (e.g. `ads-api.methodpro.com`)
2. Point an A record at the server's elastic IP
3. Add a `caddy` service to `docker-compose.prod.yml` with auto Let's Encrypt — Caddy needs only the domain in its `Caddyfile` and it handles certs automatically

### 2.5 Containerize

Done. The repo includes:
- `Dockerfile` — multi-purpose image used for both the backend and the scheduler
- `docker-compose.prod.yml` — orchestrates backend, scheduler, postgres, redis
- `.dockerignore` — keeps the build context lean
- `.env.prod.example` — template for the production env file

Local dev still uses the original `docker-compose.yml` (Postgres + Redis only).

---

## 3. Infrastructure

### 3.1 Recommended path: single EC2 with docker-compose

For 20 client accounts and ~3 daily agent runs, this is the right scale. ~$20/month total. Promote to managed services (RDS, ElastiCache, Fargate) only when load demands it.

**Provision:**
- AWS EC2 `t3.small` (2 vCPU, 2 GB RAM) — Ubuntu 22.04 LTS
- 30 GB gp3 EBS volume
- Security group: inbound 22 (SSH from your IP only), 8001 (anywhere — demo mode). When adding a domain later, swap 8001 for 80+443.
- Elastic IP attached so the IP doesn't change on reboot
- Region: pick the one closest to MethodPro's office (e.g. `us-west-2` or `ap-south-1`)

**Why not Fargate?**
- The scheduler is a long-running process; Fargate works but costs ~3× more for a constant workload
- docker-compose with `restart: always` covers the same auto-restart needs
- One instance is plenty for this scale

### 3.2 Production Dockerfile

Create `Dockerfile` at repo root:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies for asyncpg, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster installs
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend ./backend
COPY agents ./agents
COPY mcp_server ./mcp_server
COPY alembic ./alembic
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Healthcheck for the backend service (overridden for scheduler)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 3.3 Production docker-compose

`docker-compose.prod.yml` is at the repo root. Four services: `backend`, `scheduler`, `postgres`, `redis`. Backend exposes port 8001 publicly (demo mode — no reverse proxy yet).

When promoting to production with a domain, add a fifth `caddy` service to handle HTTPS.

### 3.4 Reverse proxy — deferred (no domain)

For now, the backend is reached directly at `http://<server-ip>:8001`. When you're ready to add a domain:

1. Add this service to `docker-compose.prod.yml`:
   ```yaml
   caddy:
     image: caddy:2-alpine
     restart: always
     ports: ["80:80", "443:443"]
     volumes:
       - ./Caddyfile:/etc/caddy/Caddyfile:ro
       - caddydata:/data
       - caddyconfig:/config
     depends_on: [backend]
   ```
2. Create `Caddyfile`:
   ```
   ads-api.methodpro.com {
       reverse_proxy backend:8001
   }
   ```
3. Change the backend service's ports to `"127.0.0.1:8001:8001"` so it's not directly internet-facing.
4. Add `caddydata` and `caddyconfig` volumes.

### 3.5 Production env file

Create `.env.prod` on the server (not in git):

```bash
# Google Ads
DEVELOPER_TOKEN=...
CLIENT_ID=...
CLIENT_SECRET=...
REFRESH_TOKEN=...                 # the production-mode token from step 2.1
MCC_CUSTOMER_ID=7701109307

# Database (internal Docker DNS)
DATABASE_URL=postgresql+asyncpg://ga_user:CHANGEME@postgres:5432/ga_auto
POSTGRES_PASSWORD=CHANGEME

# Redis
REDIS_URL=redis://redis:6379/0

# Backend (used internally by scheduler container to hit backend)
BACKEND_URL=http://backend:8001

# OpenAI
OPENAI_API_KEY=sk-proj-...

# Zoho Cliq
CLIQ_ZAPIKEY=1001....
CLIQ_COMPANY_ID=746931876
```

Set `chmod 600 .env.prod` so only the deploy user can read it.

---

## 4. Step-by-Step First Deploy

### 4.1 Server prep (one-time, ~15 minutes)

```bash
# SSH in
ssh -i methodpro.pem ubuntu@<elastic-ip>

# Install docker
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker ubuntu
exit  # log back in for group change to take effect

# Clone repo
ssh -i methodpro.pem ubuntu@<elastic-ip>
git clone https://github.com/Ajay70452/google_ads_mcp.git
cd google_ads_mcp

# Create .env.prod (paste contents from your password manager)
nano .env.prod
chmod 600 .env.prod

# Create Caddyfile
nano Caddyfile  # paste from section 3.4
```

### 4.2 DNS — skipped (demo)

No DNS step. Use the elastic IP directly. (Skip to 4.3.)

### 4.3 First boot

```bash
# Build images and start everything
docker compose -f docker-compose.prod.yml up -d --build

# Watch logs until healthy
docker compose -f docker-compose.prod.yml logs -f
```

Expected boot sequence:
1. postgres → ready (~10 s)
2. redis → ready (~2 s)
3. backend → "Database connection OK" then "Redis connection OK"
4. scheduler → "Scheduler starting — 3 agents registered"

### 4.4 Run database migrations

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_accounts.py
```

### 4.5 Smoke test

From your laptop:

```bash
curl http://<elastic-ip>:8001/health
# {"status":"ok"}

curl http://<elastic-ip>:8001/accounts
# [{"customer_id":"...","name":"All Smiles..."}, ...]
```

### 4.6 Update each user's MCP config

In each user's `claude_desktop_config.json`, change `BACKEND_URL`:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "BACKEND_URL": "http://<elastic-ip>:8001"
      }
    }
  }
}
```

Restart Claude Desktop. Tools should now hit the demo backend.

> **Demo caveat:** the API is HTTP, no auth, and exposed on the internet. Anyone with the IP can hit it. For demo purposes that's fine; before letting real customers near it, add the Caddy + domain step (3.4) and put the backend behind HTTPS. Consider also adding a static API key in middleware.

---

## 5. CI/CD — Auto-deploy on push to main

GitHub Actions workflow `.github/workflows/deploy.yml`:

```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ubuntu
          key: ${{ secrets.DEPLOY_KEY }}
          script: |
            cd ~/google_ads_mcp
            git pull
            docker compose -f docker-compose.prod.yml up -d --build
            docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head
            sleep 5
            curl -fs http://localhost:8001/health
```

Required GitHub repo secrets:
- `DEPLOY_HOST` — the elastic IP
- `DEPLOY_KEY` — SSH private key (the matching `.pem` content)

---

## 6. Operations

### 6.1 Monitoring the agents actually ran

The agents log to stdout (captured by docker). To verify a run:

```bash
docker compose -f docker-compose.prod.yml logs scheduler --since 24h | grep "Completed successfully"
```

For real monitoring, add a heartbeat: each agent's `BaseAgent.execute()` should POST to a healthcheck URL on success. Use **healthchecks.io** (free tier, dead simple):

1. Create 3 checks: `pacing-monitor`, `anomaly-detector`, `search-terms-agent`
2. Set the cron schedule on each (matching `scheduler.py`)
3. In `agents/base.py`, after a successful `run()`, add:
   ```python
   import httpx, os
   url = os.environ.get(f"HC_URL_{self.__class__.__name__.upper()}")
   if url:
       try: httpx.get(url, timeout=10)
       except Exception: pass
   ```
4. Add the 3 ping URLs to `.env.prod`

You'll get an email/Slack alert if any agent skips a run.

### 6.2 Database backups

Daily `pg_dump` to S3:

```bash
# Create cron on the server
crontab -e

# Add:
0 3 * * * cd ~/google_ads_mcp && docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U ga_user ga_auto | gzip | aws s3 cp - s3://methodpro-ga-backups/$(date +\%Y-\%m-\%d).sql.gz
```

Keep 30 days of backups (S3 lifecycle rule). Cost: pennies.

### 6.3 Logs

Application logs live in docker. Rotate them:

```yaml
# Add to each service in docker-compose.prod.yml:
logging:
  driver: json-file
  options:
    max-size: "20m"
    max-file: "5"
```

For long-term searchable logs, ship to CloudWatch with the `awslogs` driver — optional, only if you need historical search.

### 6.4 Updating Google Ads OAuth refresh token

Even with the app published, refresh tokens *can* be revoked by the user, by Google, or by a password change. If `invalid_grant` shows up:

1. Re-run the OAuth flow (same script you've been using locally)
2. Update `REFRESH_TOKEN` in `.env.prod`
3. `docker compose -f docker-compose.prod.yml restart backend scheduler`

The `@lru_cache` on `get_google_ads_client()` means a restart is required to pick up the new token.

### 6.5 Updating client_accounts

When MethodPro onboards a new clinic:

```bash
# Edit the seed script with the new clinic's customer_id + name
# Then:
docker compose -f docker-compose.prod.yml exec backend python scripts/seed_accounts.py
```

The script should be idempotent (use `INSERT ... ON CONFLICT DO UPDATE`).

---

## 7. Cost Estimate

| Item | Monthly |
|---|---|
| EC2 t3.small (Reserved 1yr) | ~$12 |
| EBS 30 GB gp3 | ~$3 |
| Elastic IP (attached) | $0 |
| Data transfer out (~5 GB/mo) | ~$0.45 |
| S3 backups (~1 GB) | ~$0.05 |
| **AWS subtotal** | **~$15** |
| OpenAI API (gpt-4o-mini, weekly classification of ~20 accounts) | ~$2 |
| Healthchecks.io (free tier) | $0 |
| Domain (existing) | $0 |
| **Total** | **~$17/month** |

If usage grows (>50 client accounts, write tools used heavily), promote to:
- RDS db.t4g.micro (~$15/mo) — managed Postgres with automated backups
- ElastiCache cache.t4g.micro (~$13/mo) — managed Redis
- Same EC2 for backend+scheduler

---

## 8. Security

- **Inbound (demo)**: ports 22 (SSH from your IP), 8001 (FastAPI, anywhere). When promoting to prod, close 8001 and open 80+443 with Caddy.
- **HTTPS**: not enabled in demo mode. Tokens and live Google Ads data travel over plain HTTP. Acceptable for an internal demo on a non-public IP; **not acceptable for any customer-facing release**.
- **Backend internet-facing in demo**: backend container publishes on `0.0.0.0:8001`. Once Caddy is added, switch the port binding to `127.0.0.1:8001:8001`.
- **Secrets**: `.env.prod` is `chmod 600`, never in git. For higher-security needs, switch to AWS Parameter Store and inject at container start.
- **No auth on the API** currently. The MCP server is the only client and traffic is HTTPS to a private subdomain. If you ever expose the API to additional clients, add a static API key check via FastAPI middleware.
- **Database**: not exposed outside the docker network.
- **Audit log**: all write tools insert into `change_log` (ensure this is wired up in `backend/main.py` — currently a TODO per the existing `/changes` endpoint stub).

---

## 9. Rollback

### 9.1 Bad deploy

```bash
ssh ubuntu@<elastic-ip>
cd ~/google_ads_mcp
git log --oneline -5      # find the last good commit
git checkout <good-sha>
docker compose -f docker-compose.prod.yml up -d --build
```

### 9.2 Bad migration

Alembic supports downgrade:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic downgrade -1
```

If a migration corrupted data, restore from S3 backup:

```bash
aws s3 cp s3://methodpro-ga-backups/<date>.sql.gz - | gunzip | \
  docker compose -f docker-compose.prod.yml exec -T postgres psql -U ga_user ga_auto
```

### 9.3 Server down entirely

Elastic IP keeps the address. Spin up a fresh EC2 from the same AMI, attach the EBS volume from the dead one (Postgres + Redis data persist), reattach the Elastic IP, and `docker compose up`. ~15 minute recovery.

For zero-downtime guarantees, switch to RDS (point-in-time recovery) and run two backend containers behind an ALB. Not needed at current scale.

---

## 10. Post-Deployment Validation

Run this checklist after first deploy and after any major change:

- [ ] `curl http://<elastic-ip>:8001/health` → `{"status":"ok"}`
- [ ] `curl http://<elastic-ip>:8001/accounts` returns the full client list
- [ ] `curl "http://<elastic-ip>:8001/accounts/summary?customer_id=8785895348&date_range=LAST_7_DAYS"` returns live Google Ads data
- [ ] From Claude Desktop with updated config: `list_accounts` tool works
- [ ] Manually trigger each agent and confirm the Cliq message arrived:
  ```bash
  docker compose -f docker-compose.prod.yml exec scheduler python -c "from agents.budget_pacing_monitor import BudgetPacingMonitor; BudgetPacingMonitor().execute()"
  docker compose -f docker-compose.prod.yml exec scheduler python -c "from agents.anomaly_detector import AnomalyDetector; AnomalyDetector().execute()"
  docker compose -f docker-compose.prod.yml exec scheduler python -c "from agents.search_terms_agent import SearchTermsAgent; SearchTermsAgent().execute()"
  ```
- [ ] Healthchecks.io shows green for all 3 checks after the next scheduled run
- [ ] First daily backup appeared in the S3 bucket the morning after deploy
- [ ] One full week passes with no `invalid_grant` errors in `docker compose logs backend`

---

## 11. Phased Rollout

Don't flip everyone over at once.

**Day 1:** Deploy infrastructure. Manually trigger all agents in dry-run mode (skip Cliq) to verify Google Ads access. Switch your own MCP config to production.

**Day 2–3:** Let one user other than the developer test the MCP tools through Claude Desktop. Watch logs.

**Day 4:** Enable the scheduler. Confirm the next 8 AM run posts to Cliq.

**Day 5–7:** Monitor. Then roll out the new MCP config to the rest of the team.

**Day 8–14:** Watch for the OAuth 7-day cliff. If the app was published correctly in step 2.1, no token failure should occur. If it does, the OAuth app is still in testing mode — fix step 2.1.

---

## 12. Open Questions / Future Work

These aren't blockers for first deploy but should be on the next sprint:

- **Change log persistence** — `backend/main.py` line 502 returns a hardcoded empty change log. Wire up the `change_log` table inserts in each write tool.
- **Rollback for `create_campaign`** — currently if keyword creation fails, the campaign is left orphaned. Add cleanup logic that removes the campaign if any subsequent step fails.
- **Per-user attribution on writes** — when the team has multiple Claude Desktop users, log who triggered each write op (requires adding an X-User-Id header from the MCP server).
- **Move to AWS Secrets Manager** — once more than 2 people deploy, `.env.prod` on disk becomes a coordination problem.
- **Dashboard** — a small read-only web UI showing recent agent runs, change log, rate-limit status. The FastAPI backend already has all the data.
