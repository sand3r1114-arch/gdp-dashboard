"""Lokale opslag voor het thuisdashboard: apparaatnamen, kamers en scangeschiedenis.

Alles staat in de map `thuis_data/` naast deze file (staat in .gitignore,
zodat de gegevens van je eigen netwerk niet per ongeluk op GitHub komen).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "thuis_data"
DEVICES_FILE = DATA_DIR / "apparaten.json"
SETTINGS_FILE = DATA_DIR / "instellingen.json"
LAST_SCAN_FILE = DATA_DIR / "laatste_scan.json"
OUI_FILE = DATA_DIR / "oui.json"

DEFAULT_ROOMS = [
    "Woonkamer", "Keuken", "Slaapkamer", "Kinderkamer", "Werkkamer",
    "Badkamer", "Hal", "Zolder", "Garage", "Tuin", "Overal / mobiel",
]
UNASSIGNED = "Nog niet ingedeeld"


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_devices() -> dict[str, dict]:
    return _read_json(DEVICES_FILE, {})


def save_devices(devices: dict[str, dict]) -> None:
    _write_json(DEVICES_FILE, devices)


def load_settings() -> dict:
    settings = _read_json(SETTINGS_FILE, {})
    settings.setdefault("rooms", list(DEFAULT_ROOMS))
    return settings


def save_settings(settings: dict) -> None:
    _write_json(SETTINGS_FILE, settings)


def load_last_scan() -> dict | None:
    return _read_json(LAST_SCAN_FILE, None)


def save_last_scan(scan: dict) -> None:
    _write_json(LAST_SCAN_FILE, scan)


def merge_scan(store: dict[str, dict], scan: dict, now: float | None = None) -> list[str]:
    """Verwerk een scan in de opslag. Geeft de sleutels van nooit eerder geziene apparaten."""
    now = now or scan.get("started_at") or time.time()
    new_keys = []
    for dev in scan["devices"]:
        key = dev["key"]
        entry = store.get(key)
        if entry is None:
            new_keys.append(key)
            entry = store[key] = {
                "name": "",
                "room": UNASSIGNED,
                "trusted": bool(dev.get("is_self") or dev.get("is_gateway")),
                "first_seen": now,
            }
        entry.update({
            "last_seen": now,
            "ip": dev["ip"],
            "mac": dev.get("mac"),
            "hostname": dev.get("hostname") or entry.get("hostname"),
            "vendor": dev.get("vendor") or entry.get("vendor"),
            "device_type": dev.get("device_type", "Onbekend"),
            "icon": dev.get("icon", "❔"),
            "open_ports": dev.get("open_ports", []),
            "randomized_mac": dev.get("randomized_mac", False),
        })
    return new_keys


def display_name(entry: dict) -> str:
    return entry.get("name") or entry.get("hostname") or entry.get("vendor") or entry.get("device_type") or entry.get("ip", "?")


def build_rows(store: dict[str, dict], scan: dict | None) -> list[dict]:
    """Eén rij per apparaat dat ooit gezien is, met online-status van de laatste scan."""
    online = {d["key"] for d in (scan or {}).get("devices", [])}
    rows = []
    for key, e in store.items():
        rows.append({
            "key": key,
            "online": key in online,
            "icon": e.get("icon", "❔"),
            "name": e.get("name", ""),
            "display": display_name(e),
            "room": e.get("room", UNASSIGNED),
            "type": e.get("device_type", "Onbekend"),
            "ip": e.get("ip", ""),
            "mac": e.get("mac") or "",
            "vendor": e.get("vendor") or ("(privé-MAC)" if e.get("randomized_mac") else ""),
            "hostname": e.get("hostname") or "",
            "ports": ", ".join(str(p) for p in e.get("open_ports", [])),
            "trusted": bool(e.get("trusted")),
            "first_seen": e.get("first_seen"),
            "last_seen": e.get("last_seen"),
        })
    rows.sort(key=lambda r: (not r["online"], tuple(int(x) for x in r["ip"].split(".")) if r["ip"] else ()))
    return rows


# --------------------------------------------------------------------------- #
# Voorbeeldgegevens, zodat je het dashboard kunt bekijken zonder te scannen.

_DEMO = [
    # ip-eind, mac, hostname, vendor, type, icoon, poorten, kamer, naam, vertrouwd
    (1, "3c:a6:2f:11:22:33", "fritz.box", "AVM GmbH", "Router", "📶", [53, 80, 443], "Hal", "Router", True),
    (2, "3c:a6:2f:44:55:66", "fritz-repeater", "AVM GmbH", "Netwerk (router/repeater)", "📶", [80], "Zolder", "Repeater zolder", True),
    (10, "f0:18:98:aa:bb:01", "macbook-pro", "Apple, Inc.", "Computer", "💻", [22, 445], "Werkkamer", "MacBook", True),
    (11, "ba:7e:21:0c:9d:12", "iphone", None, "iPhone / iPad", "📱", [62078], "Overal / mobiel", "iPhone", True),
    (12, "5e:2a:91:77:01:3c", None, None, "Telefoon / tablet / laptop (privé-MAC)", "📱", [], "Overal / mobiel", "", False),
    (20, "54:60:09:12:34:56", "chromecast", "Google, Inc.", "Google / Chromecast", "📺", [8008, 8009], "Woonkamer", "Chromecast", True),
    (21, "48:a6:b8:aa:00:01", "sonos-woonkamer", "Sonos, Inc.", "Speaker", "🔊", [1400], "Woonkamer", "Sonos", True),
    (22, "ec:b5:fa:01:02:03", "philips-hue", "Philips Lighting BV", "Philips Hue bridge", "💡", [80, 443], "Woonkamer", "Hue bridge", True),
    (30, "a4:cf:12:ab:cd:01", "shelly-wasmachine", "Espressif Inc.", "Smart home (IoT)", "🔌", [80], "Badkamer", "Stekker wasmachine", True),
    (31, "a4:cf:12:ab:cd:02", None, "Espressif Inc.", "Smart home (IoT)", "🔌", [], UNASSIGNED, "", False),
    (40, "30:05:5c:aa:bb:cc", "brother-printer", "Brother Industries", "Printer", "🖨️", [80, 631, 9100], "Werkkamer", "Printer", True),
    (50, "00:11:32:aa:bb:cc", "diskstation", "Synology Incorporated", "NAS", "🗄️", [80, 445, 5000], "Zolder", "NAS", True),
    (60, "dc:a6:32:12:34:56", "homeassistant", "Raspberry Pi Trading Ltd", "Home Assistant", "🏠", [22, 8123], "Werkkamer", "Home Assistant", True),
    (70, "70:9e:29:aa:bb:cc", "ps5", "Sony Interactive Entertainment", "Spelcomputer", "🎮", [], "Woonkamer", "PlayStation", True),
]


def demo_data(now: float | None = None) -> tuple[dict, dict]:
    """Geeft (scan, opslag) met nep-apparaten. Duidelijk geen echte gegevens."""
    now = now or time.time()
    devices, store = [], {}
    for i, (end, mac, host, vendor, kind, icon, ports, room, name, trusted) in enumerate(_DEMO):
        ip = f"192.168.178.{end}"
        dev = {
            "key": mac, "ip": ip, "mac": mac, "hostname": host, "vendor": vendor,
            "open_ports": ports, "randomized_mac": vendor is None and int(mac[:2], 16) & 2 == 2,
            "is_gateway": end == 1, "is_self": end == 10, "device_type": kind, "icon": icon,
        }
        store[mac] = {
            "name": name, "room": room, "trusted": trusted,
            "first_seen": now - (40 - i) * 86400 if trusted else now - 3600,
        }
        if end != 70:  # de PlayStation staat uit
            devices.append(dev)
        else:
            store[mac].update({"last_seen": now - 3 * 86400, "ip": ip, "mac": mac, "hostname": host,
                               "vendor": vendor, "device_type": kind, "icon": icon, "open_ports": ports})
    scan = {"network": "192.168.178.0/24", "local_ip": "192.168.178.10", "gateway": "192.168.178.1",
            "started_at": now, "duration_s": 12.3, "devices": devices, "demo": True}
    merge_scan(store, scan, now)
    return scan, store
