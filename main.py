"""
Desktop widget: clock, date, weather, notes, system summary, process peek.
Drag the header to move. End process uses terminate → wait → kill with confirm.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
from typing import Any, cast
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psutil
from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DragHeader(QWidget):
    """Drag the window by grabbing the title bar area."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__()
        self._window = window
        self._drag_pos: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "desktop-widget"
NOTES_FILE = DATA_DIR / "notes.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, bool] = {
    "feature_clock": True,
    "feature_weather": True,
    "feature_world_weather": True,
    "feature_notes": True,
    "feature_system": True,
    "feature_processes": True,
}

GEO_CACHE_FILE = DATA_DIR / "weather_location.json"
WORLD_WEATHER_FILE = DATA_DIR / "world_weather.json"

# Fixed cities (lat, lon) for the “Asia weather” picker (Taiwan → Taipei area).
WORLD_WEATHER_COORDS: dict[str, tuple[float, float]] = {
    "Hong Kong": (22.3193, 114.1694),
    "Tokyo": (35.6762, 139.6503),
    "Bangkok": (13.7563, 100.5018),
    "Shanghai": (31.2304, 121.4737),
    "Taiwan": (25.0330, 121.5654),
}
WORLD_CITY_ORDER: tuple[str, ...] = ("Hong Kong", "Tokyo", "Bangkok", "Shanghai", "Taiwan")

_HTTP_HEADERS = {"User-Agent": "DeskWidget/1.0 (local weather; +https://open-meteo.com)"}


def _http_get_json(url: str, timeout: float = 25.0) -> dict[str, Any] | None:
    """Fetch JSON. Prefer requests (reliable TLS on Windows); fall back to urllib."""
    try:
        import requests

        r = requests.get(url, timeout=timeout, headers=_HTTP_HEADERS)
        if r.status_code != 200:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    try:
        req = Request(url, headers=_HTTP_HEADERS)
        ctx = None if url.startswith("http://") else ssl.create_default_context()
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, dict) else None
    except (URLError, OSError, json.JSONDecodeError, TypeError, ValueError):
        pass

    if url.startswith("https://"):
        try:
            req = Request(url, headers=_HTTP_HEADERS)
            unverified = ssl._create_unverified_context()
            with urlopen(req, timeout=timeout, context=unverified) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data if isinstance(data, dict) else None
        except (URLError, OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    return None


def _weather_emoji(code: int) -> str:
    if code == 0:
        return "☀"
    if code in (1, 2):
        return "🌤"
    if code == 3:
        return "☁"
    if code in (45, 48):
        return "🌫"
    if code in (51, 53, 55):
        return "🌦"
    if code in (61, 63, 65, 80, 81, 82):
        return "🌧"
    if code in (71, 73, 75, 77, 85, 86):
        return "🌨"
    if code in (95, 96, 99):
        return "⛈"
    return "🌡"


def _wmo_label(code: int) -> str:
    labels: dict[int, str] = {
        0: "Clear",
        1: "Mostly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Fog",
        51: "Drizzle",
        53: "Drizzle",
        55: "Drizzle",
        56: "Freezing drizzle",
        57: "Freezing drizzle",
        61: "Rain",
        63: "Rain",
        65: "Rain",
        66: "Freezing rain",
        67: "Freezing rain",
        71: "Snow",
        73: "Snow",
        75: "Snow",
        77: "Snow grains",
        80: "Showers",
        81: "Showers",
        82: "Heavy rain",
        85: "Snow showers",
        86: "Snow showers",
        95: "Thunderstorm",
        96: "Thunderstorm",
        99: "Thunderstorm",
    }
    return labels.get(code, "Mixed")


def _read_geo_cache() -> tuple[float, float, str] | None:
    if not GEO_CACHE_FILE.is_file():
        return None
    try:
        raw = json.loads(GEO_CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        ts_s = raw.get("cached_at")
        if isinstance(ts_s, str):
            ts = datetime.fromisoformat(ts_s)
            if (datetime.now() - ts).days > 7:
                return None
        lat = float(raw["lat"])
        lon = float(raw["lon"])
        city = str(raw.get("city") or "").strip() or "Local"
        return lat, lon, city
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_geo_cache(lat: float, lon: float, city: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        GEO_CACHE_FILE.write_text(
            json.dumps(
                {
                    "lat": lat,
                    "lon": lon,
                    "city": city,
                    "cached_at": datetime.now().isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _fetch_location_from_ip() -> tuple[float, float, str] | None:
    j = _http_get_json("https://ipapi.co/json/")
    if j and j.get("error") is None and j.get("latitude") is not None:
        lat = float(j["latitude"])
        lon = float(j["longitude"])
        parts = [p for p in (j.get("city"), j.get("region"), j.get("country_name")) if p]
        city = ", ".join(str(p) for p in parts) if parts else "Local"
        return lat, lon, city

    j = _http_get_json("http://ip-api.com/json/?fields=status,lat,lon,city,country")
    if j and j.get("status") == "success" and j.get("lat") is not None:
        lat = float(j["lat"])
        lon = float(j["lon"])
        city = f'{j.get("city", "")}, {j.get("country", "")}'.strip().strip(",")
        return lat, lon, city or "Local"

    return None


def resolve_lat_lon_city() -> tuple[float, float, str]:
    cached = _read_geo_cache()
    if cached:
        return cached
    loc = _fetch_location_from_ip()
    if loc:
        lat, lon, city = loc
        _write_geo_cache(lat, lon, city)
        return lat, lon, city
    return 51.5074, -0.1278, "London (fallback)"


def load_world_city_choice() -> str:
    default = WORLD_CITY_ORDER[0]
    if not WORLD_WEATHER_FILE.is_file():
        return default
    try:
        raw = json.loads(WORLD_WEATHER_FILE.read_text(encoding="utf-8"))
        c = raw.get("city") if isinstance(raw, dict) else None
        if isinstance(c, str) and c in WORLD_WEATHER_COORDS:
            return c
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return default


def save_world_city_choice(city: str) -> None:
    if city not in WORLD_WEATHER_COORDS:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        WORLD_WEATHER_FILE.write_text(
            json.dumps({"city": city}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _open_meteo_forecast(lat: float, lon: float) -> dict[str, Any] | None:
    """Query Open-Meteo; retries alternate timezone if needed."""
    base = {
        "latitude": f"{lat:.5f}",
        "longitude": f"{lon:.5f}",
        "current": "temperature_2m,apparent_temperature,weather_code",
        # Do not request "time" in daily — Open-Meteo returns it automatically; including it causes HTTP 400.
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "forecast_days": "4",
    }
    for tz in ("auto", "GMT"):
        q = urlencode({**base, "timezone": tz})
        data = _http_get_json(f"https://api.open-meteo.com/v1/forecast?{q}")
        if not data:
            continue
        if data.get("error") is True:
            continue
        if "current" in data:
            return data
    return None


def parse_open_meteo_to_payload(data: dict[str, Any] | None, city_label: str) -> dict[str, Any] | None:
    """Turn an Open-Meteo JSON response into the widget’s weather dict."""
    if data is None or "current" not in data:
        return None

    cur = data["current"]
    daily = data.get("daily") or {}
    times: list[str] = list(daily.get("time") or [])
    wcodes: list[int] = [int(x) for x in (daily.get("weather_code") or [])]
    tmax: list[float] = [float(x) for x in (daily.get("temperature_2m_max") or [])]
    tmin: list[float] = [float(x) for x in (daily.get("temperature_2m_min") or [])]

    ctemp = float(cur.get("temperature_2m", 0))
    cfeel = float(cur.get("apparent_temperature", ctemp))
    ccode = int(cur.get("weather_code", 0))
    emoji = _weather_emoji(ccode)
    cond = _wmo_label(ccode)

    today_hi = tmax[0] if tmax else ctemp
    today_lo = tmin[0] if tmin else ctemp
    today_line = (
        f"{emoji} {ctemp:.0f}°C  ·  feels {cfeel:.0f}°  ·  {cond}\n"
        f"Today  ·  high {today_hi:.0f}°  ·  low {today_lo:.0f}°"
    )

    forecast_rows: list[str] = []
    for i in range(1, min(4, len(times))):
        try:
            d = datetime.fromisoformat(times[i])
            day_lbl = d.strftime("%a %d %b")
        except ValueError:
            day_lbl = times[i]
        wc = wcodes[i] if i < len(wcodes) else 0
        hi = tmax[i] if i < len(tmax) else 0.0
        lo = tmin[i] if i < len(tmin) else 0.0
        forecast_rows.append(
            f"{_weather_emoji(wc)} {day_lbl}  ·  {hi:.0f}° / {lo:.0f}°  ·  {_wmo_label(wc)}"
        )

    return {
        "city": city_label,
        "today": today_line,
        "forecast": forecast_rows,
    }


def fetch_weather_payload() -> dict[str, Any] | None:
    """Build UI payload from Open-Meteo + geolocation; None on total failure."""
    lat, lon, city = resolve_lat_lon_city()
    data = _open_meteo_forecast(lat, lon)
    if data is None:
        data = _open_meteo_forecast(51.5074, -0.1278)
        if data is not None:
            city = "London (backup forecast — primary location unreachable)"

    return parse_open_meteo_to_payload(data, city)


def fetch_world_weather(city_name: str) -> dict[str, Any] | None:
    """Forecast for a fixed city from WORLD_WEATHER_COORDS."""
    coords = WORLD_WEATHER_COORDS.get(city_name)
    if coords is None:
        return None
    lat, lon = coords
    data = _open_meteo_forecast(lat, lon)
    return parse_open_meteo_to_payload(data, city_name)


def load_settings() -> dict[str, bool]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    merged = dict(DEFAULT_SETTINGS)
    if not SETTINGS_FILE.is_file():
        return merged
    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in merged and isinstance(v, bool):
                    merged[k] = v
    except (json.JSONDecodeError, OSError):
        pass
    return merged


def save_settings(settings: dict[str, bool]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {k: bool(settings.get(k, DEFAULT_SETTINGS[k])) for k in DEFAULT_SETTINGS}
    try:
        SETTINGS_FILE.write_text(json.dumps(payload, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass


def load_notes() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not NOTES_FILE.is_file():
        return ""
    try:
        data = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        return data.get("text", "") if isinstance(data, dict) else ""
    except (json.JSONDecodeError, OSError):
        return ""


def save_notes(text: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        NOTES_FILE.write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _fetch_top_by_memory_only(limit: int) -> list[tuple[int, str, float, float]]:
    """Single-pass top processes by RAM (no CPU interval); used as fallback."""
    rows: list[tuple[int, str, float, float]] = []
    for p in psutil.process_iter(["pid", "name", "memory_percent"]):
        try:
            info = p.info
            pid = info["pid"]
            name = (info.get("name") or "?").strip() or "?"
            mem = info.get("memory_percent")
            if mem is None:
                mem = p.memory_percent()
            cpu = p.cpu_percent(interval=None)
            rows.append((pid, name, cpu, mem))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    rows.sort(key=lambda r: r[3], reverse=True)
    return rows[:limit]


def fetch_top_processes(limit: int = 8, sort_by: str = "cpu") -> list[tuple[int, str, float, float]]:
    """Return up to `limit` rows: (pid, name, cpu_percent, memory_percent)."""
    procs: list[psutil.Process] = []
    for p in psutil.process_iter():
        try:
            p.cpu_percent(None)
            procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    time.sleep(0.1)

    rows: list[tuple[int, str, float, float]] = []
    for p in procs:
        try:
            cpu = p.cpu_percent(None)
            mem = p.memory_percent()
            name = p.name()
            rows.append((p.pid, name, cpu, mem))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    if not rows:
        rows = _fetch_top_by_memory_only(limit * 2)

    key_cpu = 2
    key_mem = 3
    rows.sort(key=lambda r: r[key_mem if sort_by == "ram" else key_cpu], reverse=True)
    return rows[:limit]


class DesktopWidget(QMainWindow):
    """Cross-thread: worker emits this signal; Qt delivers the slot on the GUI thread."""

    _proc_rows_ready = pyqtSignal(object)
    _weather_ready = pyqtSignal(object)
    _world_weather_ready = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()

        self.setWindowTitle("Desktop widget")
        self.setFixedWidth(320)
        self.setMinimumHeight(260)
        self.resize(320, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        header = DragHeader(self)
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Desk widget")
        title.setObjectName("title")
        hl.addWidget(title)
        hl.addStretch()
        settings_btn = QLabel(" ⚙ ")
        settings_btn.setObjectName("gearBtn")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setToolTip("Features & settings")
        settings_btn.mousePressEvent = lambda _e: self._open_feature_settings()  # type: ignore[method-assign]
        hl.addWidget(settings_btn)
        close_btn = QLabel(" ✕ ")
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.mousePressEvent = lambda _e: self.close()  # type: ignore[method-assign]
        hl.addWidget(close_btn)
        root.addWidget(header)

        self.time_lbl = QLabel()
        self.time_lbl.setObjectName("time")
        tfont = QFont()
        tfont.setPointSize(28)
        tfont.setBold(True)
        self.time_lbl.setFont(tfont)
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.date_lbl = QLabel()
        self.date_lbl.setObjectName("date")
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.section_clock = QWidget()
        sc_l = QVBoxLayout(self.section_clock)
        sc_l.setContentsMargins(0, 0, 0, 0)
        sc_l.setSpacing(4)
        sc_l.addWidget(self.time_lbl)
        sc_l.addWidget(self.date_lbl)
        root.addWidget(self.section_clock)

        weather_title = QLabel("Weather")
        weather_title.setObjectName("section")
        weather_title.setToolTip(
            "Location is estimated from your IP (about city level). "
            "Forecast data from Open-Meteo. Refreshes every 15 minutes."
        )
        self.weather_city_lbl = QLabel()
        self.weather_city_lbl.setObjectName("weatherCity")
        self.weather_city_lbl.setWordWrap(True)
        self.weather_now_lbl = QLabel("Loading weather…")
        self.weather_now_lbl.setObjectName("weatherNow")
        self.weather_now_lbl.setWordWrap(True)
        self.weather_fc_lbl = QLabel()
        self.weather_fc_lbl.setObjectName("weatherFc")
        self.weather_fc_lbl.setWordWrap(True)

        self.section_weather = QWidget()
        sw_l = QVBoxLayout(self.section_weather)
        sw_l.setContentsMargins(0, 0, 0, 0)
        sw_l.setSpacing(6)
        sw_l.addWidget(weather_title)
        sw_l.addWidget(self.weather_city_lbl)
        sw_l.addWidget(self.weather_now_lbl)
        sw_l.addWidget(self.weather_fc_lbl)
        root.addWidget(self.section_weather)

        ww_title = QLabel("Asia weather")
        ww_title.setObjectName("section")
        ww_title.setToolTip(
            "Forecast for a fixed city (coordinates). Same 15-minute refresh as local weather. "
            "“Taiwan” uses Taipei-area coordinates."
        )
        world_pick = QHBoxLayout()
        wc_lbl = QLabel("City")
        wc_lbl.setObjectName("muted")
        self.world_city_combo = QComboBox()
        self.world_city_combo.setObjectName("worldCityCombo")
        for n in WORLD_CITY_ORDER:
            self.world_city_combo.addItem(n)
        self.world_city_combo.blockSignals(True)
        self.world_city_combo.setCurrentText(load_world_city_choice())
        self.world_city_combo.blockSignals(False)
        self.world_city_combo.currentTextChanged.connect(self._on_world_city_changed)
        world_pick.addWidget(wc_lbl)
        world_pick.addWidget(self.world_city_combo, stretch=1)

        self.world_now_lbl = QLabel("Loading weather…")
        self.world_now_lbl.setObjectName("worldNow")
        self.world_now_lbl.setWordWrap(True)
        self.world_fc_lbl = QLabel()
        self.world_fc_lbl.setObjectName("worldFc")
        self.world_fc_lbl.setWordWrap(True)

        self.section_world_weather = QWidget()
        sww_l = QVBoxLayout(self.section_world_weather)
        sww_l.setContentsMargins(0, 0, 0, 0)
        sww_l.setSpacing(6)
        sww_l.addWidget(ww_title)
        sww_l.addLayout(world_pick)
        sww_l.addWidget(self.world_now_lbl)
        sww_l.addWidget(self.world_fc_lbl)
        root.addWidget(self.section_world_weather)

        self.notes_title = QLabel("Notes")
        self.notes_title.setObjectName("section")
        self.notes = QPlainTextEdit()
        self.notes.setObjectName("notes")
        self.notes.setPlaceholderText("Quick notes…")
        self.notes.setPlainText(load_notes())
        self.notes.textChanged.connect(self._on_notes_changed)

        self.section_notes = QWidget()
        sn_l = QVBoxLayout(self.section_notes)
        sn_l.setContentsMargins(0, 0, 0, 0)
        sn_l.setSpacing(6)
        sn_l.addWidget(self.notes_title)
        sn_l.addWidget(self.notes, stretch=1)
        root.addWidget(self.section_notes, stretch=1)

        sys_title = QLabel("System")
        sys_title.setObjectName("section")
        self.sys_lbl = QLabel()
        self.sys_lbl.setObjectName("sys")
        self.sys_lbl.setWordWrap(True)

        self.section_system = QWidget()
        ss_l = QVBoxLayout(self.section_system)
        ss_l.setContentsMargins(0, 0, 0, 0)
        ss_l.setSpacing(6)
        ss_l.addWidget(sys_title)
        ss_l.addWidget(self.sys_lbl)
        root.addWidget(self.section_system)

        proc_row = QHBoxLayout()
        proc_lbl = QLabel("Processes")
        proc_lbl.setObjectName("section")
        proc_row.addWidget(proc_lbl)
        proc_row.addStretch()
        self.proc_sort = QComboBox()
        self.proc_sort.addItems(["Top by CPU", "Top by RAM"])
        self.proc_sort.setObjectName("procSort")
        self.proc_sort.currentIndexChanged.connect(lambda _i: self._schedule_proc_refresh())
        proc_row.addWidget(self.proc_sort)

        self.proc_table = QTableWidget(0, 3)
        self.proc_table.setObjectName("procTable")
        self.proc_table.setHorizontalHeaderLabels(["Name", "CPU%", "RAM%"])
        self.proc_table.verticalHeader().setVisible(False)
        self.proc_table.setShowGrid(False)
        self.proc_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.proc_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.proc_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.proc_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hh = self.proc_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.proc_table.setColumnWidth(1, 48)
        self.proc_table.setColumnWidth(2, 48)
        self.proc_table.setMaximumHeight(200)
        self.proc_table.setMinimumHeight(120)
        self.proc_table.itemSelectionChanged.connect(self._update_kill_enabled)

        kill_row = QHBoxLayout()
        self.kill_btn = QPushButton("End process…")
        self.kill_btn.setObjectName("killBtn")
        self.kill_btn.clicked.connect(self._confirm_kill_process)
        kill_row.addWidget(self.kill_btn)
        kill_row.addStretch()

        self.section_process = QWidget()
        sp_l = QVBoxLayout(self.section_process)
        sp_l.setContentsMargins(0, 0, 0, 0)
        sp_l.setSpacing(6)
        sp_l.addLayout(proc_row)
        sp_l.addWidget(self.proc_table)
        sp_l.addLayout(kill_row)
        root.addWidget(self.section_process)

        self._our_pid = os.getpid()
        self._proc_refresh_pending = False
        self._weather_refresh_pending = False
        self._world_weather_refresh_pending = False
        self._proc_rows_ready.connect(self._apply_proc_rows)
        self._weather_ready.connect(self._apply_weather_payload)
        self._world_weather_ready.connect(self._apply_world_weather_payload)

        controls = QHBoxLayout()
        self.pin = QCheckBox("Always on top")
        self.pin.setChecked(True)
        self.pin.toggled.connect(self._apply_topmost)
        controls.addWidget(self.pin)

        op_label = QLabel("Opacity")
        op_label.setObjectName("muted")
        controls.addWidget(op_label)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(40, 100)
        self.opacity_slider.setValue(96)
        self.opacity_slider.valueChanged.connect(self._set_opacity)
        controls.addWidget(self.opacity_slider, stretch=1)
        root.addLayout(controls)

        self.setStyleSheet(
            """
            QWidget#central {
                background-color: #1a1b26;
                border-radius: 12px;
                border: 1px solid #3b4261;
            }
            QWidget#header { background: transparent; }
            QLabel#title { color: #c0caf5; font-weight: 600; font-size: 13px; }
            QLabel#closeBtn {
                color: #565f89;
                font-size: 14px;
                padding: 2px 6px;
                border-radius: 4px;
            }
            QLabel#closeBtn:hover { color: #f7768e; background: #292e42; }
            QLabel#gearBtn {
                color: #565f89;
                font-size: 14px;
                padding: 2px 6px;
                border-radius: 4px;
            }
            QLabel#gearBtn:hover { color: #7dcfff; background: #292e42; }
            QLabel#time { color: #7aa2f7; }
            QLabel#date { color: #a9b1d6; font-size: 12px; }
            QLabel#section { color: #bb9af7; font-size: 11px; font-weight: 600; }
            QLabel#weatherCity { color: #7dcfff; font-size: 11px; }
            QLabel#weatherNow { color: #c0caf5; font-size: 12px; }
            QLabel#weatherFc { color: #a9b1d6; font-size: 11px; }
            QLabel#worldNow { color: #c0caf5; font-size: 12px; }
            QLabel#worldFc { color: #a9b1d6; font-size: 11px; }
            QLabel#sys { color: #9ece6a; font-size: 12px; }
            QLabel#muted { color: #565f89; font-size: 11px; }
            QPlainTextEdit#notes {
                background-color: #16161e;
                color: #c0caf5;
                border: 1px solid #3b4261;
                border-radius: 8px;
                padding: 8px;
                font-size: 12px;
            }
            QCheckBox { color: #a9b1d6; font-size: 11px; }
            QCheckBox::indicator { width: 14px; height: 14px; }
            QSlider::groove:horizontal {
                height: 4px;
                background: #3b4261;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                margin: -5px 0;
                background: #7aa2f7;
                border-radius: 7px;
            }
            QComboBox#procSort {
                background-color: #16161e;
                color: #a9b1d6;
                border: 1px solid #3b4261;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
                min-width: 7em;
            }
            QComboBox#procSort::drop-down { border: none; }
            QComboBox#worldCityCombo {
                background-color: #16161e;
                color: #a9b1d6;
                border: 1px solid #3b4261;
                border-radius: 6px;
                padding: 2px 8px;
                font-size: 11px;
                min-width: 9em;
            }
            QComboBox#worldCityCombo::drop-down { border: none; }
            QTableWidget#procTable {
                background-color: #16161e;
                color: #c0caf5;
                gridline-color: #3b4261;
                border: 1px solid #3b4261;
                border-radius: 8px;
                font-size: 11px;
            }
            QTableWidget#procTable::item:selected {
                background-color: #3b4261;
                color: #c0caf5;
            }
            QHeaderView::section {
                background-color: #24283b;
                color: #a9b1d6;
                border: none;
                border-bottom: 1px solid #3b4261;
                font-size: 10px;
                padding: 4px;
            }
            QPushButton#killBtn {
                background-color: #292e42;
                color: #f7768e;
                border: 1px solid #3b4261;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton#killBtn:hover { background-color: #3b4261; }
            QPushButton#killBtn:disabled { color: #565f89; }
            """
        )

        self._apply_topmost(True)
        self._set_opacity(self.opacity_slider.value())

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._tick_clock)
        self.sys_timer = QTimer(self)
        self.sys_timer.timeout.connect(self._tick_sys)
        self.proc_timer = QTimer(self)
        self.proc_timer.timeout.connect(self._schedule_proc_refresh)
        self.weather_timer = QTimer(self)
        self.weather_timer.timeout.connect(self._schedule_weather_refresh)
        self.world_weather_timer = QTimer(self)
        self.world_weather_timer.timeout.connect(self._schedule_world_weather_refresh)

        self._apply_feature_settings()

    def _set_feature(self, key: str, enabled: bool) -> None:
        if key not in DEFAULT_SETTINGS:
            return
        self._settings[key] = enabled
        save_settings(self._settings)
        self._apply_feature_settings()

    def _apply_feature_settings(self) -> None:
        self.section_clock.setVisible(self._settings.get("feature_clock", True))
        self.section_weather.setVisible(self._settings.get("feature_weather", True))
        self.section_world_weather.setVisible(self._settings.get("feature_world_weather", True))
        self.section_notes.setVisible(self._settings.get("feature_notes", True))
        self.section_system.setVisible(self._settings.get("feature_system", True))
        self.section_process.setVisible(self._settings.get("feature_processes", True))

        if self._settings.get("feature_clock", True):
            if not self.clock_timer.isActive():
                self.clock_timer.start(1000)
        else:
            self.clock_timer.stop()

        if self._settings.get("feature_system", True):
            if not self.sys_timer.isActive():
                self.sys_timer.start(2000)
        else:
            self.sys_timer.stop()

        if self._settings.get("feature_processes", True):
            if not self.proc_timer.isActive():
                self.proc_timer.start(3500)
        else:
            self.proc_timer.stop()
            self._proc_refresh_pending = False
            self.proc_table.setRowCount(0)

        if self._settings.get("feature_weather", True):
            if not self.weather_timer.isActive():
                self.weather_timer.start(900_000)
        else:
            self.weather_timer.stop()
            self._weather_refresh_pending = False

        if self._settings.get("feature_world_weather", True):
            if not self.world_weather_timer.isActive():
                self.world_weather_timer.start(900_000)
        else:
            self.world_weather_timer.stop()
            self._world_weather_refresh_pending = False

        if self._settings.get("feature_clock", True):
            self._tick_clock()
        if self._settings.get("feature_system", True):
            psutil.cpu_percent(interval=0.15)
            self._tick_sys()
        if self._settings.get("feature_processes", True):
            self._schedule_proc_refresh()
        if self._settings.get("feature_weather", True):
            self.weather_city_lbl.setText("")
            self.weather_now_lbl.setText("Loading weather…")
            self.weather_fc_lbl.setText("")
            self._schedule_weather_refresh()
        if self._settings.get("feature_world_weather", True):
            self.world_now_lbl.setText("Loading weather…")
            self.world_fc_lbl.setText("")
            self._schedule_world_weather_refresh()

        self.adjustSize()

    def _open_feature_settings(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Features")
        dlg.setModal(True)
        dlg.setMinimumWidth(300)
        lay = QVBoxLayout(dlg)
        intro = QLabel("Turn sections on or off. Settings are saved automatically.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        lay.addWidget(intro)

        feature_defs: list[tuple[str, str]] = [
            ("feature_clock", "Clock & date"),
            ("feature_weather", "Weather (today + 3-day forecast)"),
            ("feature_world_weather", "Asia weather (city picker)"),
            ("feature_notes", "Notes"),
            ("feature_system", "System summary (CPU & RAM)"),
            ("feature_processes", "Process list & end process"),
        ]
        for key, label in feature_defs:
            cb = QCheckBox(label)
            cb.blockSignals(True)
            cb.setChecked(self._settings.get(key, DEFAULT_SETTINGS[key]))
            cb.blockSignals(False)
            cb.toggled.connect(lambda on, k=key: self._set_feature(k, on))
            lay.addWidget(cb)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dlg.accept)
        lay.addWidget(buttons)

        dlg.setStyleSheet(
            """
            QDialog { background-color: #1a1b26; color: #c0caf5; }
            QLabel { color: #a9b1d6; font-size: 12px; }
            QLabel#muted { color: #565f89; font-size: 11px; }
            QCheckBox { color: #c0caf5; font-size: 12px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QPushButton { background-color: #292e42; color: #c0caf5; border: 1px solid #3b4261;
                border-radius: 6px; padding: 6px 14px; font-size: 12px; }
            QPushButton:hover { background-color: #3b4261; }
            """
        )
        dlg.exec()

    def _base_flags(self) -> Qt.WindowType:
        return Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool

    def _apply_topmost(self, on: bool) -> None:
        f = self._base_flags()
        if on:
            f |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(f)
        self.show()

    def _set_opacity(self, value: int) -> None:
        self.setWindowOpacity(value / 100.0)

    def _tick_clock(self) -> None:
        now = datetime.now()
        self.time_lbl.setText(now.strftime("%H:%M:%S"))
        self.date_lbl.setText(now.strftime("%A, %d %B %Y"))

    def _tick_sys(self) -> None:
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        self.sys_lbl.setText(
            f"CPU: {cpu:.0f}%   ·   RAM: {vm.percent:.0f}% "
            f"({vm.used // (1024**3)} / {vm.total // (1024**3)} GiB)"
        )

    def _schedule_weather_refresh(self) -> None:
        if not self._settings.get("feature_weather", True):
            return
        if self._weather_refresh_pending:
            return
        self._weather_refresh_pending = True

        def work() -> None:
            payload: dict[str, Any] | None = None
            try:
                payload = fetch_weather_payload()
            except Exception:
                payload = None
            self._weather_ready.emit(payload)

        threading.Thread(target=work, daemon=True).start()

    def _apply_weather_payload(self, payload: object) -> None:
        self._weather_refresh_pending = False
        if not self._settings.get("feature_weather", True):
            return
        if payload is None or not isinstance(payload, dict):
            self.weather_city_lbl.setText("")
            self.weather_now_lbl.setText("Weather unavailable (check network).")
            self.weather_fc_lbl.setText("")
            return
        city = str(payload.get("city") or "").strip()
        self.weather_city_lbl.setText(city)
        self.weather_now_lbl.setText(str(payload.get("today") or ""))
        fc = payload.get("forecast")
        if isinstance(fc, list):
            self.weather_fc_lbl.setText("\n".join(str(x) for x in fc))
        else:
            self.weather_fc_lbl.setText("")

    def _on_world_city_changed(self, city_name: str) -> None:
        if city_name not in WORLD_WEATHER_COORDS:
            return
        save_world_city_choice(city_name)
        self.world_now_lbl.setText("Loading weather…")
        self.world_fc_lbl.setText("")
        self._schedule_world_weather_refresh()

    def _schedule_world_weather_refresh(self) -> None:
        if not self._settings.get("feature_world_weather", True):
            return
        if self._world_weather_refresh_pending:
            return
        self._world_weather_refresh_pending = True
        city_name = self.world_city_combo.currentText()

        def work() -> None:
            payload: dict[str, Any] | None = None
            try:
                payload = fetch_world_weather(city_name)
            except Exception:
                payload = None
            self._world_weather_ready.emit(payload)

        threading.Thread(target=work, daemon=True).start()

    def _apply_world_weather_payload(self, payload: object) -> None:
        self._world_weather_refresh_pending = False
        if not self._settings.get("feature_world_weather", True):
            return
        if payload is None or not isinstance(payload, dict):
            self.world_now_lbl.setText("Weather unavailable (check network).")
            self.world_fc_lbl.setText("")
            return
        self.world_now_lbl.setText(str(payload.get("today") or ""))
        fc = payload.get("forecast")
        if isinstance(fc, list):
            self.world_fc_lbl.setText("\n".join(str(x) for x in fc))
        else:
            self.world_fc_lbl.setText("")

    def _proc_sort_key(self) -> str:
        return "ram" if self.proc_sort.currentIndex() == 1 else "cpu"

    def _schedule_proc_refresh(self) -> None:
        if not self._settings.get("feature_processes", True):
            return
        if self._proc_refresh_pending:
            return
        self._proc_refresh_pending = True

        sort_key = self._proc_sort_key()

        def work() -> None:
            rows: list[tuple[int, str, float, float]] = []
            try:
                rows = fetch_top_processes(8, sort_key)
            except Exception:
                rows = []
            self._proc_rows_ready.emit(rows)

        threading.Thread(target=work, daemon=True).start()

    def _apply_proc_rows(self, rows: object) -> None:
        self._proc_refresh_pending = False
        if not self._settings.get("feature_processes", True):
            return
        raw = rows if isinstance(rows, list) else []
        row_list = cast(list[tuple[int, str, float, float]], raw)
        self.proc_table.setRowCount(len(row_list))
        for i, (pid, name, cpu, mem) in enumerate(row_list):
            name_item = QTableWidgetItem(name[:28] + ("…" if len(name) > 28 else ""))
            name_item.setData(Qt.ItemDataRole.UserRole, pid)
            name_item.setToolTip(f"{name} (PID {pid})")
            self.proc_table.setItem(i, 0, name_item)
            c = QTableWidgetItem(f"{cpu:.0f}")
            c.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.proc_table.setItem(i, 1, c)
            m = QTableWidgetItem(f"{mem:.0f}")
            m.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.proc_table.setItem(i, 2, m)

        self.proc_table.clearSelection()
        self._update_kill_enabled()

    def _selected_pid(self) -> int | None:
        row = self.proc_table.currentRow()
        if row < 0:
            return None
        it = self.proc_table.item(row, 0)
        if it is None:
            return None
        pid = it.data(Qt.ItemDataRole.UserRole)
        return int(pid) if pid is not None else None

    def _update_kill_enabled(self) -> None:
        pid = self._selected_pid()
        if pid is None:
            self.kill_btn.setEnabled(False)
            return
        if pid == self._our_pid:
            self.kill_btn.setEnabled(False)
            return
        self.kill_btn.setEnabled(True)

    def _confirm_kill_process(self) -> None:
        pid = self._selected_pid()
        if pid is None or pid == self._our_pid:
            return
        row = self.proc_table.currentRow()
        name_cell = self.proc_table.item(row, 0) if row >= 0 else None
        if name_cell is not None and name_cell.toolTip():
            name = name_cell.toolTip().split(" (PID")[0]
        else:
            name = str(pid)

        r = QMessageBox.question(
            self,
            "End process",
            f'End “{name}” (PID {pid})?\n\nUnsaved work in that application may be lost.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return

        try:
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=3.0)
            except psutil.TimeoutExpired:
                p.kill()
        except psutil.NoSuchProcess:
            QMessageBox.information(self, "End process", "That process is no longer running.")
        except (psutil.AccessDenied, PermissionError):
            QMessageBox.warning(
                self,
                "End process",
                "Access denied. Try running the widget as Administrator or use Task Manager.",
            )
        except Exception as e:
            QMessageBox.critical(self, "End process", str(e))

        self._schedule_proc_refresh()

    def _on_notes_changed(self) -> None:
        save_notes(self.notes.toPlainText())


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    w = DesktopWidget()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
