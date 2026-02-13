#!/usr/bin/env python3
"""Token Meter — Mac menu bar app showing Claude plan usage limits."""

import json
import logging
import os
import subprocess
import threading
from datetime import datetime, timezone

import requests
import rumps

CONFIG_PATH = os.path.expanduser("~/.config/token-meter/config.json")
LOG_PATH = os.path.expanduser("~/.config/token-meter/debug.log")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

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


def bar(pct, width=20):
    """Render a text progress bar: [████████░░░░░░░░░░░░]."""
    filled = round(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def format_reset_time(resets_at):
    """Format a reset timestamp into a human-readable string."""
    if not resets_at:
        return None
    try:
        reset_dt = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        diff = (reset_dt - datetime.now(timezone.utc)).total_seconds()
        if diff <= 0:
            return "just reset"
        if diff < 3600:
            m, s = divmod(int(diff), 60)
            return f"in {m}m {s}s"
        h, remainder = divmod(int(diff), 3600)
        m = remainder // 60
        return f"in {h} hr {m} min"
    except Exception:
        return resets_at


def get_claude_oauth_token():
    """Retrieve Claude Code OAuth token from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            logging.info("No Claude Code credentials found in Keychain")
            return None
        creds = json.loads(result.stdout.strip())
        # Token may be at top level or nested under claudeAiOauth
        oauth = creds.get("claudeAiOauth", creds)
        return oauth.get("accessToken")
    except (json.JSONDecodeError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logging.warning(f"Failed to get OAuth token: {e}")
        return None


class TokenMeterApp(rumps.App):
    def __init__(self):
        super().__init__("Token Meter", title="◉ —", quit_button=None)

        self.refresh_seconds = 60
        self.plan_usage = {}
        self.last_checked = None
        self._fetching = False
        self._oauth_token = None

        self._load_config()
        self._build_menu()

        self.timer = rumps.Timer(self._on_timer, self.refresh_seconds)
        self.timer.start()

        self._refresh()

    # ── Config ────────────────────────────────────────────────────────

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    cfg = json.load(f)
                self.refresh_seconds = cfg.get("refresh_seconds", 60)
            except Exception:
                pass

    def _save_config(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"refresh_seconds": self.refresh_seconds}, f, indent=2)

    # ── Menu ──────────────────────────────────────────────────────────

    def _build_menu(self):
        self.status_item = rumps.MenuItem("")

        # Plan usage section
        self.plan_header = rumps.MenuItem("Plan Usage Limits")
        self.session_item = rumps.MenuItem("Session:  —")
        self.session_bar = rumps.MenuItem("")
        self.session_reset = rumps.MenuItem("")
        self.weekly_item = rumps.MenuItem("Weekly:   —")
        self.weekly_bar = rumps.MenuItem("")
        self.weekly_reset = rumps.MenuItem("")
        self.plan_status = rumps.MenuItem("")

        self.checked_item = rumps.MenuItem("Last checked: never")

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
            self.plan_header,
            self.session_item,
            self.session_bar,
            self.session_reset,
            self.weekly_item,
            self.weekly_bar,
            self.weekly_reset,
            self.plan_status,
            None,
            self.checked_item,
            None,
            rumps.MenuItem("Refresh Now", callback=self._on_refresh),
            self.interval_menu,
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
        self._refresh()

    def _on_refresh(self, _):
        self._refresh()

    @staticmethod
    def _on_quit(_):
        rumps.quit_application()

    # ── Data fetching ─────────────────────────────────────────────────

    def _refresh(self):
        if self._fetching:
            return
        self._fetching = True
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            self._fetch_plan_usage()
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

    def _fetch_plan_usage(self):
        """Fetch Claude plan usage limits via OAuth endpoint."""
        if not self._oauth_token:
            self._oauth_token = get_claude_oauth_token()
        if not self._oauth_token:
            self.plan_usage = {}
            self.plan_status.title = "⚠ No Claude Code credentials"
            return

        try:
            resp = requests.get(
                USAGE_URL,
                headers={
                    "Authorization": f"Bearer {self._oauth_token}",
                    "Content-Type": "application/json",
                    "anthropic-beta": "oauth-2025-04-20",
                },
                timeout=15,
            )
            logging.info(f"Plan usage response: {resp.status_code}")

            if resp.status_code == 401:
                # Token expired, try refreshing
                self._oauth_token = get_claude_oauth_token()
                if self._oauth_token:
                    resp = requests.get(
                        USAGE_URL,
                        headers={
                            "Authorization": f"Bearer {self._oauth_token}",
                            "Content-Type": "application/json",
                            "anthropic-beta": "oauth-2025-04-20",
                        },
                        timeout=15,
                    )
                if not self._oauth_token or resp.status_code != 200:
                    self.plan_usage = {}
                    self.plan_status.title = "⚠ OAuth token expired"
                    logging.warning("OAuth token expired or invalid")
                    return

            if resp.status_code != 200:
                self.plan_usage = {}
                self.plan_status.title = f"⚠ Usage API: HTTP {resp.status_code}"
                logging.error(f"Usage API error: {resp.status_code} {resp.text[:200]}")
                return

            self.plan_usage = resp.json()
            self.plan_status.title = ""
            logging.info(f"Plan usage: {self.plan_usage}")

        except Exception as e:
            self.plan_usage = {}
            self.plan_status.title = f"⚠ {str(e)[:50]}"
            logging.error(f"Plan usage fetch error: {e}", exc_info=True)

    # ── Display ───────────────────────────────────────────────────────

    def _update_display(self):
        all_percentages = []

        self._update_plan_display(all_percentages)

        # Last checked
        if self.last_checked:
            self.checked_item.title = (
                f"Last checked: {self.last_checked.strftime('%-I:%M:%S %p')}"
            )

        # Menu bar title — show highest used percentage (most critical)
        if all_percentages:
            max_used = max(all_percentages)
            if max_used < 50:
                icon = "●"
            elif max_used < 80:
                icon = "◐"
            else:
                icon = "○"
            self.title = f"{icon} {max_used:.0f}%"
            self.status_item.title = f"Token Meter — {max_used:.0f}% used"
        else:
            self.title = "◉ —"
            self.status_item.title = "Token Meter — no data"

    def _update_plan_display(self, all_percentages):
        """Update plan usage menu items."""
        pu = self.plan_usage
        if not pu:
            self.session_item.title = "Session:  —"
            self.session_bar.title = ""
            self.session_reset.title = ""
            self.weekly_item.title = "Weekly:   —"
            self.weekly_bar.title = ""
            self.weekly_reset.title = ""
            return

        # Session (five_hour)
        five = pu.get("five_hour", {})
        util = five.get("utilization")
        if util is not None:
            pct_used = round(util * 100)
            self.session_item.title = f"Session:  {pct_used}% used"
            self.session_bar.title = f"  {bar(100 - pct_used)}"
            reset_str = format_reset_time(five.get("resets_at"))
            self.session_reset.title = f"  Resets {reset_str}" if reset_str else ""
            all_percentages.append(pct_used)
        else:
            self.session_item.title = "Session:  —"
            self.session_bar.title = ""
            self.session_reset.title = ""

        # Weekly (seven_day)
        seven = pu.get("seven_day", {})
        util = seven.get("utilization")
        if util is not None:
            pct_used = round(util * 100)
            self.weekly_item.title = f"Weekly:   {pct_used}% used"
            self.weekly_bar.title = f"  {bar(100 - pct_used)}"
            reset_str = format_reset_time(seven.get("resets_at"))
            self.weekly_reset.title = f"  Resets {reset_str}" if reset_str else ""
            all_percentages.append(pct_used)
        else:
            self.weekly_item.title = "Weekly:   —"
            self.weekly_bar.title = ""
            self.weekly_reset.title = ""


if __name__ == "__main__":
    TokenMeterApp().run()
