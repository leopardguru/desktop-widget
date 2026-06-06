# Desktop widget

A small **always-on-top** Windows desktop panel built with **PyQt6**. It shows the time, local and city weather, quick notes, system resource usage, and a lightweight process list—with optional **end process** (with confirmation). Sections can be turned on or off and settings persist between sessions.

**Repository:** [github.com/leopardguru/desktop-widget](https://github.com/leopardguru/desktop-widget)

---

## Features


| Area              | Description                                                                                                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Clock**         | Live time (HH:MM:SS) and full calendar date.                                                                                                                                                       |
| **Local weather** | Today’s conditions plus a **3-day** outlook. Location from your **public IP** (city-level, approximate). [Open-Meteo](https://open-meteo.com/) (no API key). Refreshes about every **15 minutes**. |
| **City weather**  | Second forecast for a **fixed city** you pick from the dropdown. Same layout and refresh interval as local weather.                                                                                |
| **Notes**         | Plain-text scratch pad; **auto-saved** as you type.                                                                                                                                                |
| **System**        | Overall **CPU %** and **RAM %** (used/total GiB).                                                                                                                                                  |
| **Processes**     | Top processes by **CPU** or **RAM** (sort via dropdown). **End process…** uses `terminate` → wait → `kill`, only after confirmation. This widget’s PID cannot be ended.                            |
| **Window**        | **Always on top** toggle, **opacity** slider, **drag** by the title bar (“Desk widget” / ⚙ / ✕).                                                                                                   |


### City weather choices

Hong Kong · Tokyo · Bangkok · Shanghai · **Taipei** · Seoul · **Busan 釜山** · **Sapporo 札幌 (Hokkaido 北海道)**

Your last selection is saved in `world_weather.json`.

### Feature toggles (⚙)

Each block can be enabled or disabled; choices are saved to `settings.json`:


| Setting key             | Section                    |
| ----------------------- | -------------------------- |
| `feature_clock`         | Clock & date               |
| `feature_weather`       | Local weather              |
| `feature_world_weather` | City weather (dropdown)    |
| `feature_notes`         | Notes                      |
| `feature_system`        | System summary             |
| `feature_processes`     | Process list & end process |


---

## Recent improvements

- **Local weather location** — Looks up your IP **on every refresh** (about every 15 minutes). Uses cached coordinates only when live lookup fails; cache expires after **7 days**.
- **City weather** — Added **Seoul** and **Busan**; section renamed from “Asia weather” to **City weather**.
- **Weather API** — Fixed Open-Meteo requests (removed invalid `time` from the `daily` parameter, which caused HTTP 400).
- **HTTPS on Windows** — Uses `requests` first for weather/geolocation, with urllib fallbacks.
- **Process & weather UI** — Background fetches use worker threads; results are delivered to the UI via Qt signals (avoids empty or frozen panels).
- **Dropdown readability** — City and process sort combos use an explicit light palette on Windows so selected text is visible on the dark theme.

---

## Requirements

- **Windows** (developed and tested on Windows 10/11).
- **Python 3.10+** recommended.
- Network access for weather and IP geolocation.

### Python dependencies

See [requirements.txt](requirements.txt):

- `PyQt6` — UI.
- `psutil` — CPU/RAM and process metrics.
- `requests` — HTTPS for weather and geolocation (urllib used as fallback).

---

## Installation

1. **Clone the repository**
  ```powershell
   git clone https://github.com/leopardguru/desktop-widget.git
   cd desktop-widget
   git checkout cursor/desktop-widget
  ```
2. **Create a virtual environment**
  ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
  ```

---

## Running

```powershell
.\run.bat
```

**Manual run:**

```powershell
.\.venv\Scripts\python.exe main.py
```

### Start with Windows (optional)

1. Press **Win+R**, enter `shell:startup`, Enter.
2. Add a shortcut to `run.bat`.

---

## Data and config (on disk)

All app data lives under `%LOCALAPPDATA%\desktop-widget\`:


| File                    | Purpose                                                                                      |
| ----------------------- | -------------------------------------------------------------------------------------------- |
| `settings.json`         | Feature on/off flags.                                                                        |
| `notes.json`            | Saved notes text.                                                                            |
| `weather_location.json` | Fallback cache of lat/lon/city for local weather (used when IP lookup fails; **7-day** TTL). |
| `world_weather.json`    | Last selected city for **City weather**.                                                     |


Delete a file to reset that setting (the folder is recreated as needed).

---

## Weather details

### Local weather

1. Try **ipapi.co** (HTTPS), then **ip-api.com** (HTTP).
2. On success, update cache and fetch forecast from **Open-Meteo** `v1/forecast`.
3. If IP lookup fails, use **cached** coordinates (if any, and not expired).
4. If still no location, use **London** coordinates as a last-resort grid only.

VPNs and corporate networks can change the apparent location.

### City weather

Fixed coordinates per city in code (not GPS). Changing the dropdown refetches immediately and saves your choice.

### Privacy

IP geolocation and Open-Meteo requests expose your **public IP** to those services while fetching weather.

---

## Process list and “End process”

- Process sampling runs in a **background thread**; the table updates on the Qt main thread.
- Protected processes may return **Access denied**; use Task Manager or run elevated only if you accept the risk.

---

## Project layout

```
desktop-widget/
├── main.py
├── requirements.txt
├── run.bat
├── README.md
└── .gitignore
```

---

## Troubleshooting


| Issue                               | Things to try                                                                                                        |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Weather unavailable**             | Run `pip install -r requirements.txt`. Check firewall/VPN and that `https://api.open-meteo.com` is reachable.        |
| **Wrong local city**                | VPN/proxy affects IP geolocation. Wait for the next refresh (~15 min) or delete `weather_location.json` and restart. |
| **Empty process table**             | Wait a few seconds; check antivirus blocking `psutil`.                                                               |
| **Dark / unreadable dropdown text** | Fixed in recent builds (palette + stylesheet). Restart after updating.                                               |
| **Cannot end a process**            | Expected for system processes; administrator rights may be required.                                                 |


---

## Contributing / license

No `LICENSE` file yet. Add one before wider distribution.

Issues and PRs: [github.com/leopardguru/desktop-widget](https://github.com/leopardguru/desktop-widget)

---

## Acknowledgements

- [Open-Meteo](https://open-meteo.com/) — weather API.
- [psutil](https://github.com/giampaolo/psutil) — system/process utilities.
- [Qt / PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — GUI framework.

