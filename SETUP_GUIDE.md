# Complete Setup Guide

This guide assumes **nothing is installed yet**. If you already have Python, Node,
and Docker set up, skip to [`RUN_AND_DEPLOY.md`](RUN_AND_DEPLOY.md) instead — that
one assumes tools exist and focuses purely on running the app.

---

## Part 1 — Installing prerequisites

You need: **Python 3.10+**, **Node.js 20+**, **Git**, and optionally **Docker**.

### macOS

```bash
# Install Homebrew first if you don't have it: https://brew.sh
brew install python@3.11 node git
brew install --cask docker   # optional, for Option B later
```

### Windows

1. Install **Python**: download from python.org/downloads — during install, check
   **"Add python.exe to PATH"**.
2. Install **Node.js**: download the LTS installer from nodejs.org.
3. Install **Git**: download from git-scm.com/download/win.
4. Optional — install **Docker Desktop** from docker.com.
5. Use **PowerShell** or **Git Bash** for all commands below (Git Bash is closer
   to the Linux/macOS commands shown throughout this project's docs).

### Linux (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm git
# Docker (optional): follow the official Docker Engine install guide for Ubuntu
```

### Verify everything installed correctly

```bash
python3 --version    # should print 3.10 or higher
node --version        # should print v20 or higher
npm --version
git --version
docker --version      # only if you installed it
```

If any command says "not found," the install didn't complete or your terminal
needs restarting to pick up the updated PATH — close and reopen your terminal
and try again before continuing.

---

## Part 2 — Getting the code

If you received this as a `.zip` file, extract it and `cd` into the `autorecon`
folder. If you're setting it up from GitHub instead:

```bash
git clone <your-repo-url>
cd autorecon
```

---

## Part 3 — Get an Anthropic API key

The AI reasoning layer (explaining discrepancies, natural-language Q&A) needs a
Claude API key. Everything else — matching, dashboard, audit trail, forecasting,
CSV export — works without one.

1. Go to console.anthropic.com and sign up/log in.
2. Create an API key.
3. Keep it somewhere safe — you'll paste it into `.env` in the next part.

---

## Part 4 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` in any text editor. At minimum, set:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Everything else in `.env.example` has a working default for local development —
you don't need to touch `DATABASE_URL`, `AUTORECON_API_KEY`, or any of the other
values unless you know you want to change them. Each one is commented explaining
what it does.

---

## Part 5 — Run it

You now have two paths. **Path A is faster to a first working result.**

### Path A — Run directly on your machine

```bash
python3 -m venv venv
source venv/bin/activate          # Windows (Git Bash): source venv/Scripts/activate
                                   # Windows (PowerShell): venv\Scripts\Activate.ps1
pip install -r requirements.txt
./deploy.sh                        # or: make deploy
```

`deploy.sh` runs the test suite, starts the backend, waits for it to actually be
ready (polling, not guessing), then seeds demo data and reconciles it — telling
you clearly if any step fails instead of leaving you to guess why.

Then, in a **second terminal window**:
```bash
cd autorecon/frontend
npm install
npm run dev
```

Open **http://localhost:3000** in your browser. That's it — you should see the
AutoRecon dashboard with demo data already loaded.

### Path B — Run everything via Docker

```bash
docker compose up --build
```

This builds and starts Postgres, the backend, and the frontend together, waiting
for each to actually be ready before starting the next (see `docker-compose.yml`'s
healthchecks). Takes longer the first time (building images), faster on repeat runs.

Open **http://localhost:3000**. You'll need to seed demo data manually the first
time since `deploy.sh` isn't part of the Docker flow:
```bash
curl -X POST http://localhost:8000/demo/seed
curl -X POST http://localhost:8000/reconcile/run
```

---

## Part 6 — Confirm it actually works

Walk through every page — this is the real test, not just "the server started":

1. **Dashboard** (`/`) — you should see summary cards with numbers, a 7-day
   forecast table, and a list of reconciliation results. Click "Run AI analysis"
   and confirm some results move to "needs review" or "auto-resolved."
2. **Review Queue** (`/review`) — enter a name, approve or reject an item.
3. **Audit Trail** (`/audit`) — confirm you see a chronological log of everything
   that just happened.
4. **Ask AutoRecon** (`/ask`) — ask about a specific order (check the Dashboard
   table for a real `order_id` first) and confirm you get a grounded answer.
5. **Export** — click "Export CSV" on the dashboard and confirm a file downloads
   and opens correctly in Excel/Google Sheets/Numbers.
6. **404 handling** — visit a nonexistent page like `http://localhost:3000/nothing-here`
   and confirm you see a clean custom 404 page (not a raw error or blank screen).
7. **Mobile** — open browser DevTools, toggle device toolbar, pick a phone preset,
   and click through all four pages again.

If every one of those works, the application is genuinely functioning end to end
on your machine — not just "the server didn't crash."

---

## Troubleshooting

See the **Troubleshooting** section in `RUN_AND_DEPLOY.md` — it covers the
specific error messages you're most likely to hit and exactly what they mean.

## What's next

Once this runs locally, `RUN_AND_DEPLOY.md` covers deploying it live (Railway +
Vercel), and `NEXT_STEPS.md` has a prioritized checklist for getting from "runs
on my machine" to "submitted."
