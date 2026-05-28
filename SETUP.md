# Utility Tracker — Setup Guide

## Prerequisites

- Python 3.11+ (tested with 3.14)
- Node.js 20+
- Docker with Compose V2 (`docker compose`, not `docker-compose`)
- A Google Cloud project with the **Gmail API** and **Cloud Pub/Sub API** enabled
- An [Anthropic API key](https://console.anthropic.com/)
- A [LangSmith API key](https://smith.langchain.com/)
- A free [ngrok account](https://dashboard.ngrok.com/) for local Pub/Sub webhook delivery

---

## 1. Environment variables

Create a `.env` file at the project root with the values below.

```env
# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── Google OAuth 2.0 ──────────────────────────────────────────────────────────
# Create at https://console.cloud.google.com/apis/credentials
#   Application type : Web application
#   Authorised redirect URI : http://localhost:8000/auth/callback
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# ── Google Cloud Pub/Sub ──────────────────────────────────────────────────────
# Topic format: projects/<project-id>/topics/<topic-name>
GOOGLE_PUBSUB_TOPIC=
# A secret token you choose — embedded in the push subscription endpoint URL
PUBSUB_WEBHOOK_TOKEN=

# ── Anthropic / Claude ────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-opus-4-5

# ── LangSmith observability ───────────────────────────────────────────────────
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=utility-tracker
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

# ── JWT session tokens ────────────────────────────────────────────────────────
# Generate with: openssl rand -hex 32
JWT_SECRET=

# ── VAPID keys (Web Push / browser notifications) ────────────────────────────
# See step 2c for generation instructions.
VAPID_PRIVATE_KEY=
VAPID_PUBLIC_KEY=
VAPID_EMAIL=mailto:you@example.com

# ── Application ───────────────────────────────────────────────────────────────
APP_URL=http://localhost:8000
DEFAULT_TIMEZONE=America/New_York

# ── Admin ─────────────────────────────────────────────────────────────────────
# Comma-separated Gmail addresses that receive the admin role on login.
# The role is re-evaluated on every login, so changes take effect at next sign-in.
ADMIN_EMAILS=you@gmail.com
```

---

## 2. Google Cloud setup

### 2a. OAuth 2.0 credentials

1. Go to [APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. **Create credentials → OAuth client ID**
   - Application type: **Web application**
   - Authorised redirect URI: `http://localhost:8000/auth/callback`
3. Copy **Client ID** and **Client Secret** into `.env`.

### 2b. OAuth consent screen — add yourself as a test user

The app uses sensitive Gmail scopes. While the app is in **Testing** mode, only explicitly approved addresses can sign in.

1. Go to [APIs & Services → OAuth consent screen](https://console.cloud.google.com/apis/auth/oauth2/v2/brand)
2. Under **Test users**, click **Add users**
3. Add every Gmail address that will sign in during development
4. Click **Save**

> Skip this step only if you publish the app (requires Google verification).

### 2c. VAPID keys for Web Push

```bash
# Keys are generated once and stored in the project root.
# If private_key.pem / public_key.pem do not exist yet:
pip install pywebpush
python -c "
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
v.save_key('private_key.pem')
v.save_public_key('public_key.pem')
print('Keys written to private_key.pem and public_key.pem')
"

# Extract values for .env:
#   VAPID_PRIVATE_KEY = full contents of private_key.pem
#   VAPID_PUBLIC_KEY  = output of the command below (base64url application server key)
python -c "
from py_vapid import Vapid
v = Vapid()
v.from_file('private_key.pem')
print(v.public_key)
"
```

### 2d. Pub/Sub topic and permissions

1. Go to [Pub/Sub → Topics](https://console.cloud.google.com/cloudpubsub/topic/list) → **Create topic**
2. Name it (e.g. `gmail-push`) and note the full topic name:
   `projects/<project-id>/topics/<topic-name>`
3. Paste it into `.env` as `GOOGLE_PUBSUB_TOPIC`.
4. Grant Gmail permission to publish to the topic:
   - On the topic page, open the **Permissions** panel
   - **Add principal**: `gmail-api-push@system.gserviceaccount.com`
   - **Role**: Pub/Sub Publisher (or Editor — both work)
   - **Save**
5. **Create a push subscription** on the topic (see step 6 after ngrok is running).

---

## 3. Start Redis

```bash
docker compose up redis -d
```

Verify it is healthy:

```bash
docker exec utility-tracker-redis redis-cli ping
# → PONG
```

---

## 4. Install Python dependencies

```bash
pip install -e .
```

---

## 5. Set up ngrok

Google's Pub/Sub must reach your local server. ngrok creates a public HTTPS tunnel to `localhost:8000`.

```bash
# One-time: authenticate (free account required)
ngrok config add-authtoken <your-authtoken>   # from dashboard.ngrok.com

# Start the tunnel (run this every development session)
ngrok http 8000
```

Note the HTTPS URL (e.g. `https://xxxx-xx-xx.ngrok-free.dev`). You need it in the next step.

> **Important:** The free ngrok URL changes every time you restart ngrok. Whenever it changes you must update the Pub/Sub push subscription endpoint (step 6). Always access the app at `http://localhost:8000` — never through the ngrok URL, which would break session cookies.

### Create the Pub/Sub push subscription

1. Go to [Pub/Sub → Subscriptions](https://console.cloud.google.com/cloudpubsub/subscription/list) → **Create subscription**
2. Select your topic
3. Delivery type: **Push**
4. Endpoint URL:
   ```
   https://<your-ngrok-id>.ngrok-free.dev/webhook/gmail?token=<PUBSUB_WEBHOOK_TOKEN>
   ```
5. **Create**

> When the server starts it logs the exact webhook path (including your token) so you always have it handy.

---

## 6. Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

Rebuild whenever you change frontend source files.

---

## 7. Start the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

At startup the server prints a block like this — use the path shown to set your Pub/Sub subscription endpoint:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Pub/Sub subscription endpoint — set this in Google Cloud Console:
  https://<your-ngrok-id>.ngrok-free.dev/webhook/gmail?token=<token>
  Gmail watch status:  GET  http://localhost:8000/auth/watch-status
  Re-register watch:   POST http://localhost:8000/auth/rewatch
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Open **http://localhost:8000** and sign in with Google.

---

## 8. Register the Gmail watch

After signing in, the server attempts to register a Gmail push watch automatically. Verify it succeeded:

```
http://localhost:8000/auth/watch-status
```

Expected response:
```json
{"registered": true, "history_id": "...", "expires_in_hours": 167.9, "expired": false}
```

If `registered` is `false`, register it manually — run this in your browser's DevTools console while on the dashboard:

```javascript
fetch('/auth/rewatch', {method:'POST', credentials:'include'})
  .then(r => r.json()).then(console.log)
```

A successful response looks like:
```json
{"status": "ok", "uid": "...", "history_id": "...", "watch_expiry_epoch_ms": ...}
```

If you receive a `502` error, check the server log for the Google API error message. The most common cause is missing Pub/Sub publisher permission (step 2d).

> Gmail watches expire after ~7 days. The scheduler automatically renews them daily; you never need to re-register manually in normal operation.

---

## 9. Configure notification rules

Open **http://localhost:8000/settings** and add at least one rule. Each rule specifies:

- **Days before due date** to fire
- **Time of day** (hour / minute) in your local timezone
- **Channels**: `email`, `browser_push`, `ui_popup`, `macos` (any combination)

Without at least one rule, no scheduled reminders are sent.

---

## 10. Install the macOS notifier daemon

The daemon subscribes to Redis and fires native Notification Centre alerts. It runs as a LaunchAgent and starts automatically on login.

```bash
# Install (uses the Python interpreter from your active virtual environment)
REDIS_URL=redis://localhost:6379/0 python notifier/install.py
```

### Verify it is working

```bash
# Check daemon status and tail the logs
python notifier/install.py status

# Send a test notification immediately (replace with your uid from /auth/me)
REDIS_URL=redis://localhost:6379/0 python notifier/install.py test <your-uid>
```

You should see a Notification Centre alert within one second. If the test shows **1 receiver** but no alert appears, grant notification permission:

1. **System Settings → Notifications**
2. Find **Script Editor** (or **Terminal**)
3. Enable **Allow Notifications**

### Uninstall

```bash
python notifier/install.py unload
```

Logs are at `~/Library/Logs/UtilityTracker/notifier.log`.

> The daemon receives two types of macOS alerts:
> - **Immediate** — fires the moment a new utility bill is detected in your inbox
> - **Scheduled reminders** — fire at the times you configured in Settings (step 9)

---

## 11. Development — hot reload

Run the Vite dev server alongside FastAPI for instant frontend changes without rebuilding:

```bash
# Terminal 1 — backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

The Vite dev server runs on port 5173. Open `http://localhost:5173` during development. The `vite.config.js` proxy forwards all `/api`, `/auth`, `/webhook`, and `/ws` calls to FastAPI automatically.

> **Note:** When uvicorn reloads after a Python file change, any open WebSocket connections are dropped. The browser automatically reconnects within 1–2 seconds (reconnect logic is built into the frontend).

---

## Troubleshooting

### "Not authenticated" on API calls
Your session cookie may have expired (24-hour TTL). Sign out and sign back in.

### Pub/Sub shows no activity after receiving a payment email
Work through this checklist in order:
1. Confirm the Gmail watch is registered: `GET /auth/watch-status` → `registered: true`
2. If not registered, run `POST /auth/rewatch` (see step 8)
3. Confirm the Pub/Sub push subscription endpoint matches your current ngrok URL
4. Confirm `gmail-api-push@system.gserviceaccount.com` has Publisher permission on the topic
5. Check the server log for `Pipeline enqueued uid=...` — if it appears, the webhook is working

### `502 Bad Gateway` from `/auth/rewatch`
The Google API returned an error. Common causes:
- `gmail-api-push@system.gserviceaccount.com` does not have Pub/Sub Publisher permission
- `GOOGLE_PUBSUB_TOPIC` is wrong or the topic does not exist
- The Gmail API is not enabled in your GCP project

### OAuth "Access blocked" (403 access_denied)
Your Gmail address has not been added as a test user. See step 2b.

### OAuth state mismatch at `/auth/callback`
You accessed the app through the ngrok URL instead of `http://localhost:8000`. Always use localhost in your browser.

### `launchctl` error when installing the notifier
If `launchctl load` fails, unload first and retry:
```bash
python notifier/install.py unload
REDIS_URL=redis://localhost:6379/0 python notifier/install.py
```

### macOS notifications not appearing (daemon shows 1 receiver)
Grant notification permission to **Script Editor** in **System Settings → Notifications**.

### Dashboard does not update in real time after a payment is detected
Open DevTools → Console. You should see `[WS] Connected ✓` after page load. If you see `[WS] Closed` without a subsequent `[WS] Connected`, the WebSocket failed to connect — check the server log for errors. The browser will automatically retry with exponential backoff (1 s → 2 s → 4 s … up to 30 s).
