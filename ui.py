"""Gedeelde hulpjes voor de pagina's van het thuisdashboard."""

from __future__ import annotations

import time
from datetime import datetime

import streamlit as st

import home_store as hs
from integrations import camera, homewizard, weather, wiz

STROOM = "#2a78d6"  # blauw
GAS = "#c2410c"     # oranjerood


def ago(ts: float | None) -> str:
    if not ts:
        return "-"
    s = max(0, time.time() - ts)
    if s < 90:
        return "zojuist"
    if s < 3600:
        return f"{int(s // 60)} min geleden"
    if s < 86400:
        return f"{int(s // 3600)} uur geleden"
    days = int(s // 86400)
    return "gisteren" if days == 1 else f"{days} dagen geleden"


def fmt_time(ts: float | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%d-%m-%Y %H:%M") if ts else "-"


def nl(value: float | None, decimals: int = 1) -> str:
    """Getal in Nederlandse notatie: 1234.5 -> '1.234,5'."""
    if value is None:
        return "-"
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def euro(value: float | None) -> str:
    return "-" if value is None else f"€ {nl(value, 2)}"


def not_configured(text: str) -> None:
    st.info(text, icon="⚙️")
    st.page_link("app_pages/instellingen.py", label="Naar Instellingen", icon="⚙️")


@st.cache_data(ttl=5, show_spinner=False)
def live_p1(host: str):
    """(meting, foutmelding). Wordt hooguit elke 5 seconden echt opgehaald."""
    try:
        return homewizard.read_p1(host), None
    except Exception as exc:  # noqa: BLE001
        return None, f"Geen verbinding met de P1-meter op {host}: {exc}"


@st.cache_data(ttl=900, show_spinner=False)
def weather_now(lat: float, lon: float):
    try:
        return weather.forecast(lat, lon), None
    except Exception as exc:  # noqa: BLE001
        return None, f"Weer ophalen lukt niet: {exc}"


@st.cache_data(ttl=8, show_spinner=False)
def camera_snapshot(url: str):
    try:
        return camera.snapshot(url), None
    except camera.CameraError as exc:
        return None, str(exc)


@st.cache_data(ttl=20, show_spinner=False)
def find_lamps(extra_hosts: tuple[str, ...]) -> dict[str, dict]:
    import network_scanner as ns

    targets = wiz.broadcast_addresses(ns.get_local_ip()) + list(extra_hosts)
    return wiz.discover(targets)


def lamp_targets() -> tuple[str, ...]:
    """Bekende lamp-adressen plus alles uit de laatste netwerkscan (voor als broadcast geblokkeerd is)."""
    settings = hs.load_settings()
    ips = {lamp.get("ip") for lamp in settings.get("lamps", {}).values() if lamp.get("ip")}
    scan = hs.load_last_scan() or {}
    ips |= {d["ip"] for d in scan.get("devices", []) if not d.get("is_self")}
    return tuple(sorted(ips))


def known_lamps() -> list[dict]:
    """Alle lampen: gevonden op het netwerk, aangevuld met namen/kamers uit de instellingen."""
    settings = hs.load_settings()
    saved: dict[str, dict] = settings.setdefault("lamps", {})
    found = find_lamps(lamp_targets())
    changed = False
    lamps = []
    for ip, state in found.items():
        mac = state.get("mac") or ip
        entry = saved.setdefault(mac, {"name": "", "room": hs.UNASSIGNED})
        if entry.get("ip") != ip:
            entry["ip"] = ip
            changed = True
        lamps.append({"mac": mac, "ip": ip, "online": True, **entry, "state": state})
    for mac, entry in saved.items():
        if not any(lamp["mac"] == mac for lamp in lamps):
            lamps.append({"mac": mac, "online": False, "state": {}, **entry})
    if changed:
        hs.save_settings(settings)
    for lamp in lamps:
        lamp["label"] = lamp.get("name") or f"Lamp {lamp.get('ip') or lamp['mac']}"
    return sorted(lamps, key=lambda x: (x["room"], x["label"]))


def toggle_lamp(ip: str, key: str) -> None:
    try:
        wiz.set_on(ip, st.session_state[key])
    except Exception as exc:  # noqa: BLE001
        st.toast(f"Lamp reageert niet: {exc}", icon="💡")
    find_lamps.clear()


def dim_lamp(ip: str, key: str) -> None:
    try:
        wiz.set_brightness(ip, st.session_state[key])
    except Exception as exc:  # noqa: BLE001
        st.toast(f"Lamp reageert niet: {exc}", icon="💡")
    find_lamps.clear()
