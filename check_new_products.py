#!/usr/bin/env python3
"""Sender push-varsel til mobilen (via ntfy.sh) når nye plagg dukker opp på ludwig.gg.

Hvordan det fungerer:
  1. Henter forsiden og plukker ut alle lenker som inneholder /product/
  2. Sammenligner med seen_products.json (produkter vi har sett før)
  3. Sender ett push-varsel per nytt produkt og oppdaterer seen_products.json

Kun standardbiblioteket i Python brukes, så ingenting må installeres.
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

SHOP_URL = os.environ.get("SHOP_URL", "https://ludwig.gg/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
DRY_RUN = os.environ.get("DRY_RUN") == "1"  # skriver varsler til skjermen i stedet for å sende
STATE_FILE = Path(__file__).with_name("seen_products.json")

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_products(html: str) -> dict:
    """Returnerer {slug: full_url} for alle produktlenker på siden."""
    products = {}
    for href in re.findall(r"""href=["']([^"']*?/product/[^"'#?\s]+)""", html):
        url = urljoin(SHOP_URL, href).rstrip("/")
        slug = url.rsplit("/", 1)[-1]
        products[slug] = url
    return products


def pretty_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def notify(title: str, message: str, click_url: str = "", priority: int = 3) -> None:
    if DRY_RUN:
        print(f"[VARSEL] {title} | {message} | {click_url}")
        return
    if not NTFY_TOPIC:
        raise RuntimeError("NTFY_TOPIC er ikke satt (se oppsettet i GitHub-hemmeligheter).")
    payload = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": message,
        "priority": priority,
        "tags": ["shopping_bags"],
    }
    if click_url:
        payload["click"] = click_url
    req = urllib.request.Request(
        "https://ntfy.sh",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def load_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    current = extract_products(fetch_html(SHOP_URL))

    if not current:
        print("Fant ingen produktlenker på siden. Kan være at siden har endret oppbygning, "
              "eller at produktene lastes inn med JavaScript.", file=sys.stderr)
        return 1

    seen = load_state()

    if seen is None:
        # Første kjøring: lagre det som finnes nå uten å sende varsel per produkt.
        notify(
            "Overvåkning av ludwig.gg er i gang",
            f"Følger {len(current)} produkter: " + ", ".join(pretty_name(s) for s in sorted(current)),
            SHOP_URL,
            priority=2,
        )
        save_state(current)
        print(f"Første kjøring: lagret {len(current)} produkter.")
        return 0

    new = {slug: url for slug, url in current.items() if slug not in seen}

    for slug, url in sorted(new.items()):
        notify("Nytt plagg hos Ludwig!", pretty_name(slug), url, priority=4)
        print(f"Varslet om: {slug}")

    if new:
        # Slå sammen, slik at et produkt som forsvinner og kommer tilbake ikke varsles om som nytt.
        save_state({**seen, **current})
    else:
        print(f"Ingen nye produkter ({len(current)} på siden).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
