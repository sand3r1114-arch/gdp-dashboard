"""Verbruiksgeschiedenis bewaren in een SQLite-bestand en per uur/dag samenvatten."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, time as dtime
from pathlib import Path

import pandas as pd
from dateutil import tz

from home_store import DATA_DIR

DB_FILE = DATA_DIR / "verbruik.sqlite"
COUNTERS = ("gas_m3", "import_kwh", "export_kwh")
# Sprongen groter dan dit per meting tellen we niet mee (bv. nieuwe meter).
MAX_STEP = {"gas_m3": 10.0, "import_kwh": 50.0, "export_kwh": 50.0}


def connect(path: Path = DB_FILE) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.execute("""CREATE TABLE IF NOT EXISTS p1 (
        ts REAL PRIMARY KEY, power_w REAL, import_kwh REAL, export_kwh REAL, gas_m3 REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS heating (
        ts REAL PRIMARY KEY, outside_c REAL, room_c REAL, target_c REAL, supply_c REAL, dhw_c REAL)""")
    return con


def add_p1(reading, path: Path = DB_FILE) -> None:
    with connect(path) as con:
        con.execute("INSERT OR REPLACE INTO p1 VALUES (?,?,?,?,?)",
                    (reading.ts, reading.power_w, reading.import_kwh, reading.export_kwh, reading.gas_m3))


def add_heating(ts: float, values: dict, path: Path = DB_FILE) -> None:
    def v(label):
        val = values.get(label, (None,))[0]
        return val if isinstance(val, (int, float)) and not isinstance(val, bool) else None
    with connect(path) as con:
        con.execute("INSERT OR REPLACE INTO heating VALUES (?,?,?,?,?,?)", (
            ts, v("Buitentemperatuur"), v("Kamertemperatuur"), v("Gewenste temperatuur"),
            v("Aanvoertemperatuur"), v("Warm water (boiler)")))


def _load(table: str, since_ts: float, path: Path) -> pd.DataFrame:
    with connect(path) as con:
        df = pd.read_sql_query(f"SELECT * FROM {table} WHERE ts >= ? ORDER BY ts", con, params=(since_ts,))
    # Tijd van deze computer, net als midnight_ts(), zodat "vandaag" overal hetzelfde is.
    df["time"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert(tz.tzlocal()).dt.tz_localize(None)
    return df


def load_p1(since_ts: float, path: Path = DB_FILE) -> pd.DataFrame:
    return _load("p1", since_ts, path)


def load_heating(since_ts: float, path: Path = DB_FILE) -> pd.DataFrame:
    return _load("heating", since_ts, path)


def step_usage(df: pd.DataFrame) -> pd.DataFrame:
    """Verbruik tussen opeenvolgende metingen (verschil van de meterstanden)."""
    out = pd.DataFrame({"time": df["time"]})
    for col in COUNTERS:
        d = df[col].diff()
        out[col] = d.where((d >= 0) & (d <= MAX_STEP[col]), 0.0).fillna(0.0)
    return out


def usage_per(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Verbruik per periode: freq 'h' (uur) of 'D' (dag)."""
    if len(df) < 2:
        return pd.DataFrame(columns=["time", *COUNTERS])
    steps = step_usage(df)
    # Een stap telt bij de periode waarin hij eindigt; een stap die precies om 00:00
    # eindigt hoort dus nog bij gisteren (zelfde afspraak als usage_today).
    return steps.set_index("time").resample(freq, closed="right", label="left").sum().reset_index()


def midnight_ts(now: float | None = None) -> float:
    return datetime.combine(datetime.fromtimestamp(now or time.time()).date(), dtime.min).timestamp()


def usage_today(path: Path = DB_FILE, latest=None) -> tuple[dict, float | None]:
    """Verbruik sinds middernacht. Geeft ({teller: verbruik}, starttijd van de meting).

    Als het dashboard pas na middernacht begon met meten, is de starttijd later.
    """
    start = midnight_ts()
    with connect(path) as con:
        before = con.execute("SELECT * FROM p1 WHERE ts <= ? ORDER BY ts DESC LIMIT 1", (start,)).fetchone()
        first = before or con.execute("SELECT * FROM p1 WHERE ts > ? ORDER BY ts LIMIT 1", (start,)).fetchone()
        last = con.execute("SELECT * FROM p1 ORDER BY ts DESC LIMIT 1").fetchone()
    if not first:
        return {}, None
    end = {"gas_m3": last[4], "import_kwh": last[2], "export_kwh": last[3]} if last else {}
    if latest is not None:
        end = {"gas_m3": latest.gas_m3, "import_kwh": latest.import_kwh, "export_kwh": latest.export_kwh}
    begin = {"gas_m3": first[4], "import_kwh": first[2], "export_kwh": first[3]}
    used = {k: max(0.0, end[k] - begin[k]) for k in COUNTERS if end.get(k) is not None and begin.get(k) is not None}
    return used, (start if before else first[0])
