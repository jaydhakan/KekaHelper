# KekaHelper
Get Keka daily checkout windows, extra-hours summary, and token refresh from one CLI.

## Project Structure
```text
KekaHelper/
├── keka_helper/          # Python package
│   ├── main.py           # CLI commands
│   ├── util.py           # token + request helpers
│   ├── daily_hours.py
│   ├── extra_hours.py
│   ├── common_helpers.py
│   └── config.py
├── scripts/              # launcher scripts for keyboard shortcuts
├── .env
├── .env.example
└── requirements.txt
```

## Setup
1. `python3 -m venv venv`
2. `./venv/bin/pip install -r requirements.txt`
3. `./venv/bin/playwright install chromium`
4. Create `.env` (copy from `.env.example` and update values as needed)
5. If token refresh keeps failing, set `KEKA_BROWSER_HEADLESS=0` in `.env` and run refresh once to complete Keka login in the browser window.

## Usage
1. `./venv/bin/python -m keka_helper daily`
2. `./venv/bin/python -m keka_helper extra`
3. `./venv/bin/python -m keka_helper refresh-token`

## Shortcut Scripts
1. Daily hours: `./scripts/run_daily_hours.sh`
2. Extra hours: `./scripts/run_extra_hours.sh`
