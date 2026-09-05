# Deploying EvidenceGraph

Three free services, one blueprint file, no code changes. Read this once,
then follow **Part A** end to end.

| Piece | Where it runs | Cost |
|---|---|---|
| Frontend (React SPA) | Vercel | Free |
| Backend (FastAPI) | Render | Free (spins down after 15 min idle — see note below) |
| Redis (webhook queue) | Upstash | Free |
| Database (PostgreSQL) | Supabase | Already hosted — nothing to do |

Nothing in the app's code changes for this. The frontend still makes the
exact same relative `fetch('/api/v1/...')` calls it always has — Vercel is
configured to transparently forward those to the Render backend, the same
job nginx does locally. You will not touch a single `.tsx` file.

The only thing you do twice is **paste values into two dashboards** and
**tell me one URL** partway through, so I can wire the two services together.

---

## Part A — the deploy, in order

### Step 1 — Redis (Upstash), ~2 minutes

1. Go to **upstash.com** → sign up (GitHub login is fastest) → **Create Database**.
2. Name it anything (e.g. `evidencegraph`), pick the region closest to you, leave everything else default. Free tier is enough.
3. Once created, open it → **Details** tab → find **`ioredis` / "Redis Connect"** and copy the URL that starts with `rediss://` (note the double **s** — that's the TLS one, use that one, not the plain `redis://` one).
4. Paste it somewhere safe for a minute — you'll need it in Step 2.

### Step 2 — Backend (Render), ~5 minutes

1. Go to **render.com** → sign up with GitHub → authorize Render to see your `EvidenceGraph` repo.
2. Dashboard → **New +** → **Blueprint**.
3. Pick the `EvidenceGraph` repo. Render finds `render.yaml` at the repo root automatically and shows you every service it's about to create (one: `evidencegraph-backend`) plus a form asking for the secret values marked `sync: false`.
4. Fill in exactly these (copy from your local `.env` file, or paste fresh values):

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | your Supabase connection string (same one in your local `.env`) |
   | `REDIS_URL` | the `rediss://...` URL from Step 1 |
   | `CORS_ORIGINS` | leave as `http://localhost:5173` for now — you'll update this in Step 4 |
   | `RAZORPAY_KEY_ID` | from your local `.env` |
   | `RAZORPAY_KEY_SECRET` | from your local `.env` |
   | `RAZORPAY_WEBHOOK_SECRET` | from your local `.env` |
   | `ADMIN_API_KEY` | from your local `.env` |
   | `MISTRAL_API_KEY` | from your local `.env` |

5. Click **Apply** / **Create**. Render builds `backend/Dockerfile` and deploys it — first build takes 3-5 minutes (watch the log).
6. When it's live, Render shows a URL at the top like:
   ```
   https://evidencegraph-backend-xxxx.onrender.com
   ```
   **Copy that exact URL.** You'll need it for Step 3.
7. Sanity check — open `https://<that-url>/api/v1/health/ready` in a browser. You should see:
   ```json
   {"status":"ready","database":"connected","redis":"connected"}
   ```
   If `redis` says `unavailable`, double check you copied the `rediss://` (TLS) URL, not `redis://`.

### Step 3 — tell me the Render URL

Paste the URL from Step 2.6 back to me in chat. I'll update `frontend/vercel.json` with it and push — that's the one edit only I can make, since the URL doesn't exist until Render assigns it.

*(If you'd rather not wait on me: open `frontend/vercel.json` yourself and replace every `REPLACE-WITH-YOUR-RENDER-URL.onrender.com` with your real Render hostname — five lines, all identical — then commit and push. Either way works.)*

### Step 4 — Frontend (Vercel), ~3 minutes

1. Go to **vercel.com** → sign up with GitHub → **Add New** → **Project**.
2. Import the `EvidenceGraph` repo.
3. **This step is the one that's easy to miss:** under "Root Directory," click **Edit** and set it to `frontend`. Vercel auto-detects the framework (Vite) and the build command once you do.
4. Click **Deploy**. Takes about a minute.
5. When it's live, Vercel gives you a URL like:
   ```
   https://evidence-graph-xxxx.vercel.app
   ```
   This is the link you hand to evaluators.

### Step 5 — close the loop: update CORS on Render

1. Back in Render → your `evidencegraph-backend` service → **Environment** tab.
2. Edit `CORS_ORIGINS` → set it to your real Vercel URL from Step 4.5 (e.g. `https://evidence-graph-xxxx.vercel.app`).
3. Save — Render redeploys automatically (~1 minute).

### Step 6 — verify

Open your Vercel URL in a browser. You should land on **Start Here** exactly like local. Walk the checklist:

- Step 1 (Operations) should show all services healthy.
- Step 2 (GOLDEN_007 in AI Verify) should return `CONTRADICTED` with claims populated.
- Step 4 (Defense Eval) should show real accuracy numbers.

If a panel says "failed to load" on first click: Render's free tier spins the container down after 15 minutes idle, and the first request after that wakes it back up — this can take 20-50 seconds. That's normal free-tier behavior, not a bug. Refresh after a moment. See the cold-start note below if you want to avoid this for the actual evaluation window.

---

## Part B — day-to-day after that

- **Every `git push` to `main` auto-redeploys both sides** — Render rebuilds the backend, Vercel rebuilds the frontend. You don't need to repeat any of Part A again.
- **The golden dataset seeds itself** on the backend's first boot (`SEED_GOLDEN_CASES=true`, `SEED_FREEZE_DATASET=true` are already in `render.yaml`) — no manual step.
- **`AI_ENABLED` is `false`** on the deployed backend by default, same reasoning as your local setup: keeps every demo case fast and immune to Mistral's rate limit. To run the real three-way comparison for evaluators or your own recording: Render → Environment → set `AI_ENABLED` to `true` → save (redeploys) → run it → set it back to `false` afterward so casual clicking by an evaluator doesn't burn your Mistral quota.

## Cold starts, and whether to pay to remove them

Render's free web service tier sleeps after 15 minutes with no traffic and takes 20-50 seconds to wake on the next request. For a hackathon link an evaluator opens once, this is a normal, expected free-tier trait — plenty of real submissions work this way. Two ways to remove it if you'd rather not risk it during judging:

- Upgrade the Render service to the **Starter** plan (~$7/month) — never sleeps.
- Or just visit your own Vercel URL a minute or two before an evaluator is expected to look, which wakes the backend up ahead of time. Free, manual, works fine for a scheduled review window.

## Rotating the database password

Unrelated to this deploy but worth doing once either way: the Supabase DB
password is still the one flagged in `docs/security-notes.md`. Rotating it
means updating `DATABASE_URL` in exactly one place now instead of two —
Render's environment tab — since your local `.env` and the deployed backend
both just read the same variable.
