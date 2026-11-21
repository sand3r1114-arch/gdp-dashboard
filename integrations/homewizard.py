"""HomeWizard P1-meter uitlezen via de lokale API (v1).

Zet de lokale API eerst aan in de HomeWizard Energy-app:
Instellingen → Meters → (je P1-meter) → Lokale API.
"""

from __future__ import annotations

import concurrent.futures as cf
import time
from dataclasses import dataclass

from integrations.http import get_json


@dataclass
class P1Reading:
    ts: float
    power_w: float | None          # huidig vermogen; negatief = teruglevering
    import_kwh: float | None       # meterstand stroom afgenomen (totaal)
    export_kwh: float | None       # meterstand stroom teruggeleverd (totaal)
    gas_m3: float | None           # meterstand gas (totaal)
    wifi_strength: int | None = None
    meter_model: str | None = None


def _url(host: str, path: str) -> str:
    host = host.strip().removeprefix("http://").rstrip("/")
    return f"http://{host}{path}"


def parse_p1(data: dict, ts: float | None = None) -> P1Reading:
    return P1Reading(
        ts=ts or time.time(),
        power_w=data.get("active_power_w"),
        import_kwh=data.get("total_power_import_kwh"),
        export_kwh=data.get("total_power_export_kwh"),
        gas_m3=data.get("total_gas_m3"),
        wifi_strength=data.get("wifi_strength"),
        meter_model=data.get("meter_model"),
    )


def read_p1(host: str, timeout: float = 3.0) -> P1Reading:
    return parse_p1(get_json(_url(host, "/api/v1/data"), timeout=timeout))


def identify(host: str, timeout: float = 1.5) -> dict | None:
    """Geeft apparaatinfo als `host` een HomeWizard-apparaat met lokale API is."""
    try:
        info = get_json(_url(host, "/api"), timeout=timeout)
    except Exception:  # noqa: BLE001 - geen HomeWizard
        return None
    if isinstance(info, dict) and str(info.get("product_type", "")).startswith("HWE-"):
        return {"host": host, **info}
    return None


def find_devices(hosts: list[str]) -> list[dict]:
    """Zoek tussen de gegeven adressen naar HomeWizard-apparaten (P1-meter eerst)."""
    with cf.ThreadPoolExecutor(max_workers=32) as pool:
        found = [r for r in pool.map(identify, hosts) if r]
    return sorted(found, key=lambda d: d.get("product_type") != "HWE-P1")
