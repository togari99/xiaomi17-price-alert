"""
Xiaomi 17 — Amazon India Price Alert
Single-shot script: checks price once, sends alert if below threshold, exits.

Local usage:
    python monitor.py

GitHub Actions: triggered by cron every 5 minutes (see .github/workflows/price-check.yml).
State (last alerted price) is read/written to STATE_FILE so duplicate alerts are suppressed.

Configure via environment variables (GitHub Actions Secrets) or the CONFIG block below.
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG — values here are used when env vars are not set (local runs)
# ─────────────────────────────────────────────────────────────────────────────

AMAZON_URL        = os.getenv("AMAZON_URL",        "https://www.amazon.in/dp/B0GMQDDRX8")
PRICE_THRESHOLD   = int(os.getenv("PRICE_THRESHOLD", "70000"))
NTFY_SERVER       = os.getenv("NTFY_SERVER",       "https://ntfy.sh")
NTFY_TOPIC        = os.getenv("NTFY_TOPIC",        "xiaomi17-price-ranjith42")   # ← set as GitHub Secret
PUSHBULLET_KEY    = os.getenv("PUSHBULLET_API_KEY", "")

# File that stores the last price we sent an alert for (persisted via GH Actions cache)
STATE_FILE        = Path(os.getenv("STATE_FILE", "price_state.json"))

# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ── State helpers ─────────────────────────────────────────────────────────────

def load_last_alerted() -> float | None:
    try:
        data = json.loads(STATE_FILE.read_text())
        return float(data.get("last_alerted_price", 0)) or None
    except Exception:
        return None


def save_last_alerted(price: float) -> None:
    try:
        STATE_FILE.write_text(json.dumps({"last_alerted_price": price}))
    except Exception as exc:
        log.warning("Could not save state: %s", exc)


# ── Browser ───────────────────────────────────────────────────────────────────

def _make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=en-IN")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    return driver


# ── Price fetcher ─────────────────────────────────────────────────────────────

def fetch_price() -> float | None:
    driver = None
    try:
        driver = _make_driver()
        driver.get(AMAZON_URL)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".a-price-whole"))
            )
        except Exception:
            pass

        page = driver.page_source

        # Strategy 1 — .a-price-whole (standard product page)
        try:
            el = driver.find_element(By.CSS_SELECTOR, ".a-price-whole")
            raw = el.text.strip().replace(",", "").replace(".", "")
            if raw.isdigit():
                return float(raw)
        except Exception:
            pass

        # Strategy 2 — alternative price block selectors
        for sel in (
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#corePrice_feature_div .a-price .a-offscreen",
            ".apexPriceToPay .a-offscreen",
        ):
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                raw = re.sub(r"[^\d]", "", el.get_attribute("innerHTML") or el.text)
                if raw.isdigit() and 30_000 <= int(raw) <= 200_000:
                    return float(raw)
            except Exception:
                continue

        # Strategy 3 — regex on full page source
        matches = re.findall(r"\u20b9\s*([\d,]+)", page)
        candidates = []
        for m in matches:
            try:
                v = float(m.replace(",", ""))
                if 30_000 <= v <= 200_000:
                    candidates.append(v)
            except ValueError:
                pass
        if candidates:
            return max(set(candidates), key=candidates.count)

        if "captcha" in page.lower() or "robot" in page.lower():
            log.warning("Amazon returned a CAPTCHA page — will retry next run.")
        else:
            log.warning("Could not parse price — product may not be listed yet.")
        return None

    except Exception as exc:
        log.warning("Browser error: %s", exc)
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


# ── Notifications ─────────────────────────────────────────────────────────────

def _send_ntfy(price: float) -> None:
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    headers = {
        "Title": quote("Xiaomi 17 Price Alert! Now Rs. {:,.0f}".format(price)),
        "Priority": "urgent",
        "Tags": "rotating_light,moneybag",
        "Content-Type": "text/plain; charset=utf-8",
        "Click": AMAZON_URL,
    }
    body = (
        f"Xiaomi 17 is now Rs.{price:,.0f} on Amazon India!\n"
        f"Threshold: Rs.{PRICE_THRESHOLD:,}\n"
        f"Buy now: {AMAZON_URL}"
    )
    try:
        r = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=10)
        r.raise_for_status()
        log.info("Ntfy notification sent (HTTP %s)", r.status_code)
    except Exception as exc:
        log.error("Ntfy send failed: %s", exc)


def _send_pushbullet(price: float) -> None:
    if not PUSHBULLET_KEY:
        return
    try:
        r = requests.post(
            "https://api.pushbullet.com/v2/pushes",
            json={
                "type": "note",
                "title": "Xiaomi 17 Price Alert!",
                "body": (
                    f"Xiaomi 17 is now Rs.{price:,.0f} on Amazon India!\n"
                    f"Threshold was Rs.{PRICE_THRESHOLD:,}.\n"
                    f"Buy now: {AMAZON_URL}"
                ),
            },
            headers={"Access-Token": PUSHBULLET_KEY},
            timeout=10,
        )
        r.raise_for_status()
        log.info("Pushbullet notification sent.")
    except Exception as exc:
        log.error("Pushbullet send failed: %s", exc)


def send_alert(price: float) -> None:
    _send_ntfy(price)
    _send_pushbullet(price)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    log.info("Checking price for Xiaomi 17 on Amazon India")
    log.info("URL        : %s", AMAZON_URL)
    log.info("Threshold  : Rs.%s", f"{PRICE_THRESHOLD:,}")
    log.info("Ntfy topic : %s/%s", NTFY_SERVER, NTFY_TOPIC)

    price = fetch_price()

    if price is None:
        log.warning("Price unavailable this run — will retry on next scheduled run.")
        sys.exit(0)

    log.info("Current price: Rs.%s", f"{price:,.0f}")

    if price < PRICE_THRESHOLD:
        last_alerted = load_last_alerted()
        if last_alerted == price:
            log.info("Already alerted at Rs.%s — skipping duplicate.", f"{price:,.0f}")
        else:
            log.info("PRICE BELOW THRESHOLD — sending alert!")
            send_alert(price)
            save_last_alerted(price)
    else:
        log.info("Price is above threshold — no alert needed.")
        # Reset state so we alert again if price drops in the future
        if STATE_FILE.exists():
            STATE_FILE.write_text(json.dumps({"last_alerted_price": 0}))


if __name__ == "__main__":
    main()
