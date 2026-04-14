# Desktop widget

A small **always-on-top** Windows desktop panel built with **PyQt6**. It shows the time, local and regional weather, quick notes, system resource usage, and a lightweight process list—with optional **end process** (with confirmation). Sections can be turned on or off and settings persist between sessions.

**Repository:** [github.com/leopardguru/desktop-widget](https://github.com/leopardguru/desktop-widget)

---

## Features


| Area              | Description                                                                                                                                                                                                          |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Clock**         | Live time (HH:MM:SS) and full calendar date.                                                                                                                                                                         |
| **Local weather** | Today’s conditions plus a **3-day** outlook. Location is estimated from your **public IP** (city-level, approximate). Uses [Open-Meteo](https://open-meteo.com/) (no API key). Refreshes about every **15 minutes**. |
| **Asia weather**  | Second forecast for a **fixed city** chosen from: Hong Kong, Tokyo, Bangkok, Shanghai, Taiwan (coordinates use the **Taipei** area for Taiwan). Same forecast layout and refresh interval as local weather.          |
| **Notes**         | Plain-text scratch pad; **auto-saved** as you type.                                                                                                                                                                  |
| **System**        | Overall **CPU %** and **RAM %** (used/total GiB).                                                                                                                                                                    |
| **Processes**     | Table of top processes by **CPU** or **RAM** (sort via dropdown). **End process…** sends `terminate`, waits, then `kill` if needed—only after you confirm in a dialog. The widget’s own PID cannot be ended.         |
| **Window**        | **Always on top** toggle, **opacity** slider, **drag** by the title bar (“Desk widget” / ⚙ / ✕ row).                                                                                                                 |


### Feature toggles

Click **⚙** to open **Features**. Each major block can be enabled or disabled; choices are saved automatically.

---

## Requirements

- **Windows** (developed and tested on Windows 10/11).
- **Python 3.10+** recommended (uses modern typing syntax).
- Network access for weather and (for local weather) IP-based geolocation.

### Python dependencies

See `[requirements.txt](requirements.txt)`:

- `PyQt6` — UI.
- `psutil` — CPU/RAM and process metrics.
- `requests` — HTTPS for weather and geolocation (more reliable TLS on Windows than stdlib alone; urllib is used as fallback).

---

## Installation

1. **Clone the repository**
  ```powershell
   git clone https://github.com/leopardguru/desktop-widget.git
   cd desktop-widget
  ```
   Active development branch in this repo: `cursor/desktop-widget` (check with `git branch -a`).
2. **Create a virtual environment** (recommended)
  ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
  ```

---

## Running

From the project folder:

```powershell
.\run.bat
```

`run.bat` expects `.venv` and dependencies to exist; if not, it prints the `venv` / `pip install` hint.

**Manual run:**

```powershell
.\.venv\Scripts\python.exe main.py
```

### Start with Windows (optional)

Create a shortcut to `run.bat` in the Startup folder:

1. Press **Win+R**, enter `shell:startup`, Enter.
2. Paste a shortcut to `run.bat` (or `pythonw` + `main.py` if you prefer no console).

---

## Data and config (on disk)

All app data lives under:

`%LOCALAPPDATA%\desktop-widget\`


| File                    | Purpose                                                                                                             |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `settings.json`         | Boolean feature flags (which sections are visible).                                                                 |
| `notes.json`            | Saved notes text.                                                                                                   |
| `weather_location.json` | Cached **latitude / longitude / city label** for local weather (refreshed when the cache expires—see code for TTL). |
| `world_weather.json`    | Last selected **Asia weather** city name.                                                                           |


Deleting these files resets the corresponding settings (the directory is recreated as needed).

---

## Weather details

- **Local weather**  
  - Coarse location from **ipapi.co** (HTTPS), then **ip-api.com** (HTTP) if needed, then a **London** fallback for coordinates only if both fail.  
  - Forecast data: **Open-Meteo** `v1/forecast` endpoint.  
  - VPNs and corporate networks can change the apparent location.
- **Asia weather**  
  - Fixed coordinates per city in code; not GPS.
- **Privacy**  
  - IP-based geolocation and Open-Meteo requests mean **your public IP** is visible to those services while fetching weather.

If you see **“Weather unavailable (check network)”**, check firewall/VPN, ensure `requests` is installed, and that `https://api.open-meteo.com` is reachable.

---

## Process list and “End process”

- Refresh runs on a timer; work is done in a **background thread**; UI updates are marshalled safely to the Qt main thread.
- Ending a process may require **Administrator** rights for protected processes; if access is denied, use Task Manager or run the widget elevated (not generally recommended unless you understand the risk).

---

## Project layout

```
desktop-widget/
├── main.py           # Application entry point and UI
├── requirements.txt
├── run.bat           # Windows launcher (uses .venv)
├── README.md
└── .gitignore
```

---

## Troubleshooting


| Issue                   | Things to try                                                                                                              |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Weather never loads     | Install/update deps: `pip install -r requirements.txt`. Check internet and TLS/proxy.                                      |
| Empty process table     | Usually resolves after a few seconds; if not, check antivirus blocking `psutil`.                                           |
| Cannot end a process    | Expected for system processes; try “Run as administrator” only if you accept the risk.                                     |
| Window stuck off-screen | Reset position by toggling features or editing window state is not implemented—restart app or use Alt+Space if applicable. |


---

## Contributing / license

There is no license file in this repository yet. If you open-source the project, add a `LICENSE` and clarify terms for contributors.

Suggestions and pull requests can go through [GitHub Issues / PRs](https://github.com/leopardguru/desktop-widget) on the main repository.

---

## Acknowledgements

- [Open-Meteo](https://open-meteo.com/) — weather API (free, no key required for non-commercial use per their terms).
- [psutil](https://github.com/giampaolo/psutil) — cross-platform system and process utilities.
- [Qt / PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — GUI framework.

