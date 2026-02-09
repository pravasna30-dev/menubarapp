# Token Meter

A macOS menu bar app that monitors your Claude API rate limits in real time.

Token Meter sits in your menu bar and periodically queries the Anthropic API, displaying remaining capacity for input tokens, output tokens, requests, and total tokens as visual progress bars.

## Menu Bar Icons

| Icon | Meaning |
|------|---------|
| `●`  | >50% capacity remaining |
| `◐`  | 20–50% capacity remaining |
| `○`  | <20% capacity remaining |

## Setup

### Run directly

```bash
./run.sh
```

This creates a virtual environment, installs dependencies, and launches the app.

### Build as a macOS .app bundle

```bash
./build.sh
```

Then install:

```bash
cp -r "dist/Token Meter.app" /Applications/
```

## Configuration

On first launch, Token Meter will prompt you to enter your Anthropic API key. You can also set it via:

- **Environment variable:** `ANTHROPIC_API_KEY`
- **Config file:** `~/.config/token-meter/config.json`

```json
{
  "api_key": "sk-ant-...",
  "refresh_seconds": 60
}
```

## Auto-Refresh Intervals

Configurable from the menu:

- 30 seconds
- 1 minute (default)
- 5 minutes
- 15 minutes

## Requirements

- macOS
- Python 3.10+

## Debug Log

Logs are written to `~/.config/token-meter/debug.log`.
