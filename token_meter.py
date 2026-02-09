#!/usr/bin/env python3
"""Token Meter — Mac menu bar app showing Claude API rate limits."""

import json
import logging
import os
import threading
from datetime import datetime, timezone

import requests
import rumps

CONFIG_PATH = os.path.expanduser("~/.config/token-meter/config.json")
LOG_PATH = os.path.expanduser("~/.config/token-meter/debug.log")
MESSAGES_URL = "https://api.anthropic.com/v1/messages"

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

INTERVALS = [
    ("30 seconds", 30),
    ("1 minute", 60),
    ("5 minutes", 300),
    ("15 minutes", 900),
]


def fmt(n):
    """Format large numbers: 1500000 -> '1.5M', 42000 -> '42.0K'."""
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def parse_rate_limits(headers):
    """Extract anthropic-ratelimit-* values from response headers."""
    prefix = "anthropic-ratelimit-"
    return {
        k.lower()[len(prefix):]: v
        for k, v in headers.items()
        if k.lower().startswith(prefix)
    }


def bar(pct, width=20):
    """Render a text progress bar: [████████░░░░░░░░░░░░]."""
    filled = round(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


class TokenMeterApp(rumps.App):
    def __init__(self):
        super().__init__("Token Meter", title="◉ —", quit_button=None)

        self.api_key = None
        self.refresh_seconds = 60
        self.limits = {}
        self.last_checked = None
        self._fetching = False

        self._load_config()
        self._build_menu()

        self.timer = rumps.Timer(self._on_timer, self.refresh_seconds)
        self.timer.start()

        if self.api_key:
            self._refresh()
        else:
            self.title = "◉ No Key"

    # ── Config ────────────────────────────────────────────────────────

    def _load_config(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key and os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    cfg = json.load(f)
                self.api_key = cfg.get("api_key")
                self.refresh_seconds = cfg.get("refresh_seconds", 60)
            except Exception:
                pass

    def _save_config(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(
                {"api_key": self.api_key, "refresh_seconds": self.refresh_seconds},
                f,
                indent=2,
            )

    # ── Menu ──────────────────────────────────────────────────────────

    def _build_menu(self):
        self.input_item = rumps.MenuItem("Input Tokens:   —")
        self.output_item = rumps.MenuItem("Output Tokens:  —")
        self.requests_item = rumps.MenuItem("Requests:       —")
        self.tokens_item = rumps.MenuItem("Total Tokens:   —")
        self.input_bar = rumps.MenuItem("")
        self.output_bar = rumps.MenuItem("")
        self.requests_bar = rumps.MenuItem("")
        self.tokens_bar = rumps.MenuItem("")
        self.reset_item = rumps.MenuItem("Resets: —")
        self.checked_item = rumps.MenuItem("Last checked: never")
        self.status_item = rumps.MenuItem("")

        # Interval sub-menu
        self.interval_menu = rumps.MenuItem("Auto-refresh")
        self._interval_items = {}
        for label, secs in INTERVALS:
            item = rumps.MenuItem(label, callback=self._make_interval_cb(secs))
            item.state = 1 if secs == self.refresh_seconds else 0
            self._interval_items[secs] = item
            self.interval_menu.add(item)

        self.menu = [
            self.status_item,
            None,
            self.input_item,
            self.input_bar,
            self.output_item,
            self.output_bar,
            self.requests_item,
            self.requests_bar,
            self.tokens_item,
            self.tokens_bar,
            None,
            self.reset_item,
            self.checked_item,
            None,
            rumps.MenuItem("Refresh Now", callback=self._on_refresh),
            self.interval_menu,
            rumps.MenuItem("Set API Key…", callback=self._on_set_key),
            None,
            rumps.MenuItem("Quit Token Meter", callback=self._on_quit),
        ]

    def _make_interval_cb(self, seconds):
        def cb(sender):
            self.refresh_seconds = seconds
            self.timer.stop()
            self.timer.interval = seconds
            self.timer.start()
            self._save_config()
            for secs, item in self._interval_items.items():
                item.state = 1 if secs == seconds else 0

        return cb

    # ── Callbacks ─────────────────────────────────────────────────────

    def _on_timer(self, _):
        if self.api_key:
            self._refresh()

    def _on_refresh(self, _):
        if not self.api_key:
            self._on_set_key(None)
            return
        self._refresh()

    def _on_set_key(self, _):
        win = rumps.Window(
            message="Enter your Anthropic API key:",
            title="Token Meter",
            default_text=self.api_key or "",
            ok="Save",
            cancel="Cancel",
            dimensions=(360, 24),
        )
        resp = win.run()
        if resp.clicked:
            key = resp.text.strip()
            if key:
                self.api_key = key
                self._save_config()
                self._refresh()

    @staticmethod
    def _on_quit(_):
        rumps.quit_application()

    # ── Data fetching ─────────────────────────────────────────────────

    def _refresh(self):
        if self._fetching or not self.api_key:
            return
        self._fetching = True
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            logging.info("Fetching rate limits...")
            resp = requests.post(
                MESSAGES_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "h"}],
                },
                timeout=15,
            )

            logging.info(f"Response status: {resp.status_code}")

            if resp.status_code == 401:
                self.title = "◉ Bad Key"
                self.status_item.title = "⚠ Invalid API key"
                logging.warning("API key is invalid (401)")
                return
            if resp.status_code == 429:
                self.title = "○ 0%"
                self.status_item.title = "⚠ Rate limited"
                logging.warning("Rate limited (429)")
                return
            if resp.status_code != 200:
                # Try to extract a readable error message from the API
                try:
                    err_msg = resp.json()["error"]["message"]
                except Exception:
                    err_msg = f"HTTP {resp.status_code}"
                self.title = "◉ ⚠"
                self.status_item.title = f"⚠ {err_msg[:80]}"
                logging.error(f"Unexpected status {resp.status_code}: {resp.text[:200]}")
                return

            self.limits = parse_rate_limits(resp.headers)
            logging.info(f"Parsed rate limits: {self.limits}")
            self.last_checked = datetime.now()
            self._update_display()

        except requests.ConnectionError as e:
            self.title = "◉ offline"
            self.status_item.title = "⚠ No connection"
            logging.error(f"Connection error: {e}")
        except Exception as e:
            self.title = "◉ ⚠"
            self.status_item.title = f"⚠ {str(e)[:60]}"
            logging.error(f"Unexpected error: {e}", exc_info=True)
        finally:
            self._fetching = False

    # ── Display ───────────────────────────────────────────────────────

    def _update_display(self):
        rl = self.limits
        if not rl:
            return

        percentages = []

        # Helper to update a metric row
        def update_metric(label, key_prefix, text_item, bar_item):
            lim_key = f"{key_prefix}-limit"
            rem_key = f"{key_prefix}-remaining"
            if lim_key in rl and rem_key in rl:
                lim = int(rl[lim_key])
                rem = int(rl[rem_key])
                pct = (rem / lim * 100) if lim else 0
                used = lim - rem
                text_item.title = (
                    f"{label}: {fmt(used)} used / {fmt(lim)}  ({pct:.0f}% left)"
                )
                bar_item.title = f"  {bar(pct)}  {fmt(rem)} remaining"
                percentages.append(pct)
            else:
                text_item.title = f"{label}: —"
                bar_item.title = ""

        update_metric("Input Tokens ", "input-tokens", self.input_item, self.input_bar)
        update_metric("Output Tokens", "output-tokens", self.output_item, self.output_bar)
        update_metric("Requests     ", "requests", self.requests_item, self.requests_bar)
        update_metric("Total Tokens ", "tokens", self.tokens_item, self.tokens_bar)

        # Reset time
        reset_key = next(
            (k for k in ("input-tokens-reset", "tokens-reset", "requests-reset") if k in rl),
            None,
        )
        if reset_key:
            try:
                raw = rl[reset_key]
                reset_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                diff = (reset_dt - datetime.now(timezone.utc)).total_seconds()
                if diff > 0:
                    m, s = divmod(int(diff), 60)
                    self.reset_item.title = f"Resets in {m}m {s}s"
                else:
                    self.reset_item.title = "Limit window just reset"
            except Exception:
                self.reset_item.title = f"Reset: {rl[reset_key]}"

        # Last checked
        if self.last_checked:
            self.checked_item.title = (
                f"Last checked: {self.last_checked.strftime('%-I:%M:%S %p')}"
            )

        # Menu bar title — show lowest remaining percentage
        if percentages:
            min_pct = min(percentages)
            if min_pct > 50:
                icon = "●"
            elif min_pct > 20:
                icon = "◐"
            else:
                icon = "○"
            self.title = f"{icon} {min_pct:.0f}%"
            self.status_item.title = f"Token Meter — {min_pct:.0f}% capacity left"
        else:
            self.title = "◉ —"
            self.status_item.title = "Token Meter — no data"


if __name__ == "__main__":
    TokenMeterApp().run()
