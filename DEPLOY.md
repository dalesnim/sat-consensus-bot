# Deploying the bot to a server

The bot is a **worker**, not a web app. It makes outbound connections to Telegram and OpenRouter and listens on **no port**. Any host that requires your app to bind `$PORT` (Render's free tier, most "web service" templates) will kill it. Pick a host that runs plain containers or gives you a Linux box.

Two paths below. **Option A (Fly.io)** is fastest. **Option B (any VPS)** is what you want long term.

---

## Before you start, either way

**Only one instance may poll a Telegram token.** If two run at once they fight with `409 Conflict` and neither works reliably. Stop the local one first:

```bash
./bot.sh stop
```

Have these five values ready:

| Variable | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `OPENROUTER_API_KEY` | from openrouter.ai/settings/keys |
| `OWNER_ID` | your numeric Telegram ID |
| `DAILY_SPEND_CAP_USD` | e.g. `3` |
| `ALLOWED_USER_IDS` | comma-separated student IDs |

> **Set `ALLOWED_USER_IDS`.** On hosts with an ephemeral filesystem the database resets on redeploy. This variable re-seeds your allowlist at every boot, so students never lose access. Question history and the cache are rebuilt over time; the allowlist must not be.

---

## Option A — Fly.io (fastest, ~10 minutes)

### 1. Install the CLI and sign in

```bash
brew install flyctl          # macOS
fly auth signup              # or: fly auth login
```

### 2. Create the app — do NOT let it deploy yet

From the project root:

```bash
fly launch --no-deploy
```

Answer:
- **App name:** anything, e.g. `sat-consensus-bot`
- **Region:** pick one near your students
- **Postgres / Redis / Upstash:** **No** to all — the bot uses local SQLite
- **Deploy now:** **No**

### 3. Make it a worker, not a web service

`fly launch` writes a `fly.toml` that usually assumes a web app. Open it and **delete the entire `[http_service]` block** (and any `[[services]]` block). The bot listens on no port, and leaving those in makes Fly health-check a port that never opens — the deploy then fails or restarts forever.

Keep it minimal:

```toml
app = "sat-consensus-bot"
primary_region = "fra"

[build]

[[vm]]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1
```

### 4. Add a volume so the database survives restarts

```bash
fly volumes create sat_data --size 1 --region fra
```

Then add to `fly.toml`:

```toml
[mounts]
  source = "sat_data"
  destination = "/app/data"
```

### 5. Set your secrets

```bash
fly secrets set \
  TELEGRAM_BOT_TOKEN="..." \
  OPENROUTER_API_KEY="..." \
  OWNER_ID="..." \
  DAILY_SPEND_CAP_USD="3" \
  ALLOWED_USER_IDS="...,..."
```

### 6. Deploy and watch

```bash
fly deploy
fly logs
```

**Success looks like:**

```
roster ok: 7 models, 5 labs
Run polling for bot @yourbot id=...
```

---

## Option B — Any Ubuntu VPS (Vultr, DigitalOcean, RackNerd)

Create the cheapest **Ubuntu 24.04** instance offered (1 vCPU / 1 GB is plenty), then SSH in:

```bash
ssh root@YOUR_SERVER_IP
```

### One-shot setup

Paste this whole block. It installs Docker, clones the repo, and prepares the config:

```bash
set -e
apt-get update && apt-get install -y docker.io docker-compose-plugin git
systemctl enable --now docker

git clone https://github.com/dalesnim/sat-consensus-bot.git /opt/satbot
cd /opt/satbot
cp .env.example .env
echo "Now edit /opt/satbot/.env  ->  nano .env"
```

> **Private repo?** Either make it public temporarily, or create a GitHub personal access token and clone with
> `git clone https://<TOKEN>@github.com/dalesnim/sat-consensus-bot.git /opt/satbot`

### Fill in the config

```bash
nano /opt/satbot/.env
```

Set the five variables from the table above. Save with `Ctrl+O`, `Enter`, then `Ctrl+X`.

### Start it

```bash
cd /opt/satbot
docker compose up -d --build
docker compose logs -f bot
```

**Success looks like:**

```
roster ok: 7 models, 5 labs
Run polling for bot @yourbot id=...
```

Press `Ctrl+C` to stop following the logs — the bot keeps running.

`docker-compose.yml` already sets `restart: unless-stopped`, so the bot survives crashes **and server reboots**. Nothing else to configure.

### Updating later

```bash
cd /opt/satbot && git pull && docker compose up -d --build
```

---

## Verifying it actually works

"Running" and "connected to Telegram" are different things. A container can be up while the bot is dead.

**Read the logs — that is the honest signal:**

```bash
docker compose logs --tail 20 bot
```

`Run polling for bot @yourbot id=...` means it is connected. A dashboard showing
"running" or "online" only means the container started, which is not the same thing.

> **Do not use the `getUpdates` trick against a live bot.** It is tempting to call
> `https://api.telegram.org/bot<TOKEN>/getUpdates` and treat a `409 Conflict` as proof
> something else is polling. It does work as a one-off check when you believe nothing
> is running — but Telegram gives the *newest* caller priority, so against a healthy bot
> your request **terminates the server's poll** instead of being refused by it. The bot
> recovers on its own, but you will have caused a brief outage and a confusing
> `Conflict: terminated by other getUpdates request` in the logs. Read the logs instead.

Finally, send the bot a real question from Telegram and confirm a reply comes back.

---

## Troubleshooting

| Symptom in logs | Cause | Fix |
|---|---|---|
| `unable to open database file` | Image predates the `/app/data` ownership fix | `git pull` and rebuild; needs commit `0629041` or newer |
| `ValidationError` / `Field required` | A variable is missing or misspelled | Recheck all five names exactly |
| `BootValidationError` | OpenRouter key is wrong, or the account has no credit | Verify the key and top up |
| `Conflict: terminated by other getUpdates` | Two instances polling | Stop one — `./bot.sh stop` locally, or scale the old host to zero |
| Health check fails / restart loop on Fly | An `[http_service]` block is still in `fly.toml` | Delete it — the bot binds no port |
| Everything times out at once | Server has no outbound internet, or DNS is broken | `curl https://openrouter.ai/api/v1/models` from the box |

**Free health check, costs nothing:**

```bash
docker compose exec bot python -m bot --validate-only
```

Prints `roster ok: 7 models, 5 labs` if configuration and connectivity are sound. It makes no inference calls, so it is safe to run any time.
