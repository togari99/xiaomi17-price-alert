# Xiaomi 17 — Amazon India Price Alert

Monitors the Xiaomi 17 listing on Amazon India and sends a **high-priority push notification** to your phone the moment the price drops below ₹70,000.

Runs **24/7 on GitHub Actions** — no server, no laptop needed.

---

## How it works

```
GitHub Actions cron (every 5 min)
        │
        ▼
  monitor.py (single-shot)
        │
        ├─ headless Chrome → amazon.in/dp/B0GMQDDRX8
        │         extracts current price
        │
        ├─ price < Rs.70,000?
        │       └─ yes → send Ntfy push → your phone
        │
        └─ save state (last alerted price) → cache
```

State is persisted via `actions/cache` so you don't get spammed with repeat alerts when the price stays low.

---

## Phone setup (Ntfy — free, 2 minutes)

1. Install **Ntfy** on your Android phone:  
   [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy) · [F-Droid](https://f-droid.org/en/packages/io.heckel.ntfy/)
2. Open the app → tap **+** → subscribe to a topic name you invent, e.g. `xiaomi17-ranjith42`  
   *(treat it like a password — anyone who knows it can post to it)*
3. In Ntfy app settings → **Notifications** → enable **Full-screen notifications** and turn off battery optimisation for Ntfy so alerts fire even when the screen is off.

---

## Deploy to GitHub Actions (one-time setup)

### Step 1 — Create a GitHub repository

```bash
# From inside the xiaomi17-price-alert folder:
git init
git add .
git commit -m "initial"
gh repo create xiaomi17-price-alert --private --source=. --push
```

Or create a repo at [github.com/new](https://github.com/new), then push this folder to it.

> **Important:** The `.github/workflows/` folder **must be at the repo root**, not inside a subfolder.  
> Either push the entire `xiaomi17-price-alert/` folder contents as the repo root, or see the note below.

### Step 2 — Add your Ntfy topic as a GitHub Secret

1. On GitHub → your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
2. Name: `NTFY_TOPIC`  
   Value: your topic name (e.g. `xiaomi17-ranjith42`)
3. Click **Add secret**

*(Optional) If you use Pushbullet instead, add a second secret `PUSHBULLET_API_KEY` with your key from [pushbullet.com](https://www.pushbullet.com/#settings)*

### Step 3 — Enable Actions

- Go to your repo → **Actions** tab → click **"I understand my workflows, go ahead and enable them"**
- The cron will start automatically. To test immediately: **Actions → Xiaomi 17 Price Check → Run workflow**

### Step 4 — Watch it run

Each run appears under **Actions** with logs like:

```
Checking price for Xiaomi 17 on Amazon India
URL        : https://www.amazon.in/dp/B0GMQDDRX8
Threshold  : Rs.70,000
Current price: Rs.89,999
Price is above threshold — no alert needed.
```

When the price drops below ₹70,000 you'll get a **high-priority notification** on your phone with a direct link to buy.

---

## Repository structure

```
.
├── monitor.py                        ← price checker (single-shot)
├── requirements.txt
├── README.md
└── .github/
    └── workflows/
        └── price-check.yml           ← GitHub Actions cron (every 5 min)
```

---

## Running locally (laptop)

Still works exactly as before — just runs once and exits:

```powershell
# Install deps (first time only)
pip install -r requirements.txt

# Run a single check
python monitor.py
```

To simulate the old loop behaviour locally:

```powershell
while ($true) { python monitor.py; Start-Sleep 300 }
```

---

## Configuration

All settings are controlled via environment variables (set as GitHub Secrets for remote, or in your shell for local):

| Variable | Default | Description |
|---|---|---|
| `NTFY_TOPIC` | `xiaomi17-price-ranjith42` | **Set this as a GitHub Secret** |
| `PRICE_THRESHOLD` | `70000` | Alert when price drops below this (INR) |
| `AMAZON_URL` | Xiaomi 17 ASIN link | Change if ASIN changes |
| `NTFY_SERVER` | `https://ntfy.sh` | Self-hosted Ntfy URL if applicable |
| `PUSHBULLET_API_KEY` | *(empty)* | Optional: Pushbullet API key |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Workflow doesn't trigger | GitHub disables scheduled workflows after 60 days of repo inactivity — push a dummy commit or re-enable manually |
| `CAPTCHA page` in logs | GitHub's IPs are sometimes blocked by Amazon — the next run usually succeeds |
| No notification received | Check that `NTFY_TOPIC` secret matches exactly what you subscribed to in the app |
| Duplicate alerts | Restart the cache by renaming the cache key in `price-check.yml` from `price-state-v1` to `price-state-v2` |
