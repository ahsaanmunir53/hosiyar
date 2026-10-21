# Setup guide (all free, no credit card)

Every service below has a free plan that does not need a card. If any sign-up page asks for one, stop and use the alternative listed.

Never paste API keys or passwords into chat, issues or commits. They go only in `backend/.env` (local) or in the hosting dashboard's environment settings.

**Upgrading from ScamShield?** Pull the new code and redeploy. Your Render service and URL can keep their names. New tables are created automatically on start-up and existing data stays. Then add the new environment variables from section 8 (at least `AUTH_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `CRON_SECRET`). `SIMILARITY_THRESHOLD_GEMINI` now defaults to the calibrated `0.90`, so you can remove it.

**Groq model retired?** Groq shut down `llama-3.3-70b-versatile` for free keys on 16 August 2026. If your `.env` or Render settings still say `GROQ_MODEL=llama-3.3-70b-versatile`, change it to `openai/gpt-oss-120b` or delete the line. The app also notices a retired model at start-up, switches to a current one and logs `Model check: ...`.

## 1. Run it with no keys

Follow "Run it locally" in the README. The app works in rules-only mode. Check `http://localhost:8000/api/health`.

## 2. Groq (chat model and voice notes)

1. Sign up at https://console.groq.com
2. Go to **API Keys** → **Create API Key**.
3. In `backend/.env`: `GROQ_API_KEY=gsk_...`
4. Restart the backend. `/api/health` should show `"llm": "groq"` and `"voice_notes": true`.

Models: `GROQ_MODEL=openai/gpt-oss-120b` reads messages and writes explanations; `GROQ_FAST_MODEL=openai/gpt-oss-20b` runs the tool-calling agents. They have separate free quotas (about 30 requests and 8,000 tokens per minute each; your exact limits are in the console under **Limits**). `GROQ_REASONING_EFFORT=low` keeps each answer short.

Each check makes about 4 to 6 model calls, spread over the chain (Groq main → Gemini → Groq fast). When a model hits its limit, the app skips it until the provider says it can be used again; identical messages are read once and cached for 7 days. With every model resting, the rules answer alone, which is quick and still safe because the rules decide the verdict anyway.

Open `/api/health/ai` to test every model in the chain. A model that fails shows a `kind` (`retired`, `bad_key`, `rate_limited`) and a hint. `/api/health` lists which models are resting right now.

## 3. Google AI Studio (screenshots, embeddings, backup model)

1. Go to https://aistudio.google.com/apikey and create a key in a new project. Do not enable billing.
2. In `backend/.env`: `GOOGLE_API_KEY=...`
3. Restart. `/api/health` should show `"screenshots": true` and `"embeddings": "gemini768"`.

If a model name stops working, check https://ai.google.dev/gemini-api/docs/models and update `GEMINI_MODEL`, `GEMINI_VISION_MODEL` or `GEMINI_EMBEDDING_MODEL`.

The memory similarity threshold for Gemini embeddings defaults to `0.90`, the value `python -m eval.calibrate_memory` picked (no legitimate message matched). Re-run the script if you change the embedding model.

## 4. Neon (Postgres + pgvector)

1. Sign up at https://neon.com and create a project.
2. Copy the connection string. Use the **direct** connection (host without `-pooler`), for example
   `postgresql://user:pass@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`
3. In `backend/.env`: `DATABASE_URL=...`
4. Restart. On first start the app creates its tables, the pgvector extension, the LangGraph checkpoint and store tables, and loads the scam pattern library. `/api/health` shows `"storage": "postgres"`.

Neon's free compute sleeps after 5 minutes of inactivity and wakes on the next query.

## 5. Telegram bot, family alerts and the weekly warning (optional)

1. In Telegram, message **@BotFather**, send `/newbot`, choose a name and username.
2. Put the token in `.env`: `TELEGRAM_BOT_TOKEN=...` and set `TELEGRAM_WEBHOOK_SECRET` to any long random string.
3. Locally: start the backend, then run `python scripts/telegram_polling.py` and message your bot.
4. After deploying: `python scripts/set_telegram_webhook.py https://your-api.onrender.com`

Family alerts then work on their own: someone sends `/family` to the bot (or uses **Tools → Family alerts** on the website) and gets a code; a relative sends `/guard CODE` to the bot.

For the weekly warning, create a Telegram channel, add your bot as an administrator, and set `TELEGRAM_ALERT_CHAT_ID` to the channel's `@username`. The message is sent by the scheduled job in section 10.

## 6. Google Safe Browsing (optional)

Google says all use of the Safe Browsing APIs is free of charge; the Lookup API is meant for non-commercial use, which fits a portfolio project.

1. Open https://console.cloud.google.com and create a project (top bar → project picker → **New Project**).
2. **APIs & Services** → **Library** → search "Safe Browsing API" → **Enable**.
3. **APIs & Services** → **Credentials** → **Create credentials** → **API key**. Optionally restrict the key to the Safe Browsing API.
4. In `backend/.env`: `SAFE_BROWSING_API_KEY=...` and restart. `/api/health` shows `"safe_browsing": true`.

If any screen asks for billing or a card, skip this step; the other link checks still work.

## 7. Review panel (analyst accounts)

1. In `.env` set `AUTH_SECRET` to a long random string of 16+ characters (it signs login tokens). In production, or whenever `DATABASE_URL` is set, login and all review-panel requests stay off until it is set.
2. Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` (10+ characters). The first admin is created at start-up when there are no users yet. After that you can remove `ADMIN_PASSWORD`; changing it later does not change the existing account.
3. Open the website's **Review panel** link (bottom of every page, or `/admin`) and log in.
4. Under **Users**, create analyst accounts for anyone who reviews reports.

A long random string can be made with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 8. Deploy the API on Render

Push the repository to GitHub first (`.env` is in `.gitignore`, so keys stay local).

**Option A, manual (works on every account):** Render dashboard → **New** → **Web Service** → select the repo, then:

| Setting | Value |
|---|---|
| Language | Python 3 |
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | Free |
| Health Check Path (Advanced) | `/api/health` |

Environment variables (the **Add from .env** button lets you paste your `.env`):

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.8` (Render's default is newer; pin the version the project is tested on) |
| `APP_ENV` | `production` |
| `GROQ_API_KEY`, `GOOGLE_API_KEY`, `DATABASE_URL` | your values |
| `FINGERPRINT_SECRET` | a long random string; keep it fixed, changing it breaks matching of earlier fingerprints |
| `AUTH_SECRET` | a different long random string |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | the first review-panel account |
| `CRON_SECRET` | a long random string, also saved in GitHub (section 10) |
| `ALLOWED_ORIGINS` | `http://localhost:5173` for now; set to the Vercel URL after section 9 |
| `PUBLIC_APP_URL` | the Vercel URL (used in Telegram messages) |
| `SEED_DEMO_DATA` | `true` (clearly labelled sample rows for the trends page) |
| `TRUSTED_PROXY_HOPS` | `3` (the default). Rate limits use Cloudflare's `CF-Connecting-IP` header, which Render's traffic carries; without it, the visitor is the third entry from the end of `X-Forwarded-For` (visitor, Cloudflare edge, Render hop). If everyone suddenly gets "Too many requests" at once, set it to `0` as a fallback. |
| Optional | `SAFE_BROWSING_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALERT_CHAT_ID`, `TURNSTILE_SECRET`, `INTEGRATION_KEY` |

**Option B, Blueprint (API and website together):** **New** → **Blueprint** → select the repo. It reads `render.yaml`, creates the API (`hoshiyar-api`, free web service) and the website (`hoshiyar-web`, free static site, which does not sleep), and asks once for every secret. Enter `https://hoshiyar-web.onrender.com` for `ALLOWED_ORIGINS` and `PUBLIC_APP_URL`, and `https://hoshiyar-api.onrender.com` for `VITE_API_URL`. If Render adds a suffix to a name, put the real URLs in afterwards and redeploy both. `TELEGRAM_WEBHOOK_SECRET` must be the same value as in your local `.env` and use only letters, digits, `_` and `-` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`). Copy the generated `CRON_SECRET` into GitHub (section 10). Section 9 is then not needed.

When the deploy finishes, the logs show `Hoshiyar ready: model=... storage=postgres`. Open `https://<your-service>.onrender.com/api/health` to confirm.

Free web services sleep after 15 minutes without traffic and take about a minute to wake. Do not use Render's free Postgres for this project; it expires after 30 days. Use Neon.

## 9. Deploy the frontend on Vercel

1. Vercel → **Add New** → **Project** → import the repo.
2. Root directory: `frontend`. Framework: Vite.
3. Environment variable: `VITE_API_URL=https://<your-service>.onrender.com`
4. Deploy, then copy the Vercel URL into Render's `ALLOWED_ORIGINS` and redeploy the API.

The site is an installable app (PWA): on Android, Chrome offers **Install app** (or use **Tools → Install**); after that, Hoshiyar appears in the share menu, so a WhatsApp message can be shared straight to it. On iPhone, use Safari → Share → **Add to Home Screen**.

## 10. Scheduled jobs on GitHub Actions (free)

In GitHub: **Settings** → **Secrets and variables** → **Actions**.

- **Variables** → add `BACKEND_URL` with your Render URL.
- **Secrets** → add `CRON_SECRET` with the same value as on Render.

Then:

- `.github/workflows/scheduled-jobs.yml` sends the weekly warning on Mondays at 09:00 Pakistan time and runs the data-retention purge every night. Run it by hand from the **Actions** tab (**Run workflow**, job `weekly` or `purge`) to test.
- `.github/workflows/keep-warm.yml` pings the API every 10 minutes on weekdays during Singapore office hours (about 220 hours a month). Render gives each workspace 750 free hours a month shared by all its services, so do not ping around the clock.
- `.github/workflows/ci.yml` runs the tests, the evaluation, the red-team set and the quality gate on every push.

## 11. Captcha with Cloudflare Turnstile (optional)

Only needed if bots start using up your free AI quota.

1. Create a free Cloudflare account, open **Turnstile** → **Add widget**, add your Vercel domain (and `localhost` for testing), mode **Managed**.
2. Put the **Secret Key** on Render as `TURNSTILE_SECRET`, and the **Site Key** on Vercel as `VITE_TURNSTILE_SITE_KEY`. Redeploy both.
3. Set `INTEGRATION_KEY` on Render to a long random string and enter the same value in the browser extension's settings, so the extension and the MCP server can still call the API.

## 12. Browser extension

1. Open `chrome://extensions` (or `edge://extensions`), turn on **Developer mode**, click **Load unpacked** and choose the `extension` folder.
2. Open the extension's **Settings**, enter your Render API address and, if you use a captcha, the integration key.
3. Select text on any page → right-click → **Check with Hoshiyar**. Visit a look-alike site and a warning bar appears (the check runs in the browser).

## 13. MCP server for AI assistants (optional)

The MCP server runs on your computer and calls your Hoshiyar API. In Claude Desktop, open **Settings → Developer → Edit config** and add (with your own paths):

```json
{
  "mcpServers": {
    "hoshiyar": {
      "command": "C:\\path\\to\\backend\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\backend\\app\\mcp_server.py"],
      "env": { "HOSHIYAR_API_URL": "https://your-api.onrender.com" }
    }
  }
}
```

Restart Claude Desktop. It can then use `check_message`, `lookup`, `recent_campaigns` and `reporting_channels`. If your server uses a captcha, add `"HOSHIYAR_KEY": "<INTEGRATION_KEY>"` to `env`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend says it cannot reach the checker | Check `VITE_API_URL`, and that the Vercel URL is in `ALLOWED_ORIGINS`. The first request after sleep can take a minute. |
| `"llm": false` in `/api/health` | The key is missing or `LLM_PROVIDER=none`. |
| Results say "The AI step failed" | Open `/api/health/ai` on your backend. It calls each model once and shows the exact error: `401`/`AuthenticationError` means a wrong key (check for spaces or quotes in the Render value), `429` means a free-tier rate limit (wait a minute). The rules still produce a result. With both `GROQ_API_KEY` and `GOOGLE_API_KEY` set, Gemini takes over automatically when Groq fails. |
| Review panel login says "Set AUTH_SECRET" | Add `AUTH_SECRET` on Render and redeploy. |
| No admin account | `ADMIN_EMAIL`/`ADMIN_PASSWORD` were not set when the app first started with an empty users table, or the password was shorter than 10 characters. Set them and restart. |
| Weekly job fails with 401 or 404 | `CRON_SECRET` differs between GitHub and Render (401), or is not set on Render (404). |
| Family alerts say the bot is not set up | Set `TELEGRAM_BOT_TOKEN` and register the webhook (section 5). |
| Postgres errors about prepared statements | You used Neon's pooled (`-pooler`) host. Use the direct one (the app now also switches to it by itself and logs a warning). |
| `invalid channel_binding value: "require` and `PoolTimeout` at start-up | The pasted `DATABASE_URL` ends with a newline. Edit it on Render and remove the line break (the app now strips it too). |
| Screenshot or payment-screenshot check returns 503 | `GOOGLE_API_KEY` is not set. |
| Windows: "Psycopg cannot use the 'ProactorEventLoop'" | Start with `python run.py` or `uvicorn app.main:app --reload`. Scripts in `eval/` already handle this. |
| `429 RESOURCE_EXHAUSTED` from Gemini | Free-tier per-minute limit. Wait a minute. The app keeps working: a failed memory search is skipped. |
