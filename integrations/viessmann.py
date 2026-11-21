"""Viessmann-ketel uitlezen via de officiële ViCare-API (met PyViCare).

Je hebt nodig: je ViCare-e-mail en -wachtwoord, en een gratis 'client ID' van
https://app.developer.viessmann.com/ (zie de uitleg op de pagina Verwarming).
"""

from __future__ import annotations

import time
from pathlib import Path

# (label, eenheid, methode) - ketel / apparaat
DEVICE_FIELDS = [
    ("Buitentemperatuur", "°C", "getOutsideTemperature"),
    ("Keteltemperatuur", "°C", "getBoilerTemperature"),
    ("Warm water (boiler)", "°C", "getDomesticHotWaterStorageTemperature"),
    ("Warm water ingesteld", "°C", "getDomesticHotWaterConfiguredTemperature"),
]
# per verwarmingscircuit
CIRCUIT_FIELDS = [
    ("Kamertemperatuur", "°C", "getRoomTemperature"),
    ("Gewenste temperatuur", "°C", "getCurrentDesiredTemperature"),
    ("Aanvoertemperatuur", "°C", "getSupplyTemperature"),
    ("Programma", "", "getActiveProgram"),
    ("Modus", "", "getActiveMode"),
]

PROGRAMS = {
    "normal": "Normaal", "reduced": "Verlaagd", "comfort": "Comfort", "eco": "Eco",
    "standby": "Stand-by", "holiday": "Vakantie", "fixed": "Vast", "summerEco": "Zomer eco",
    "heating": "Verwarmen", "dhw": "Alleen warm water", "dhwAndHeating": "Warm water + verwarmen",
}


def _safe(obj, method: str):
    try:
        value = getattr(obj, method)()
    except Exception:  # noqa: BLE001 - functie niet ondersteund door dit model
        return None
    return PROGRAMS.get(value, value) if isinstance(value, str) else value


def collect(device) -> dict:
    """Lees alle bekende waarden van een (PyViCare-)apparaat. Onbekende velden worden overgeslagen."""
    values: dict[str, tuple] = {}
    for label, unit, method in DEVICE_FIELDS:
        v = _safe(device, method)
        if v is not None:
            values[label] = (v, unit)
    try:
        circuits = list(device.circuits)
    except Exception:  # noqa: BLE001
        circuits = []
    for c in circuits[:1]:  # de meeste huizen hebben één circuit
        for label, unit, method in CIRCUIT_FIELDS:
            v = _safe(c, method)
            if v is not None:
                values[label] = (v, unit)
    try:
        burners = list(device.burners)
    except Exception:  # noqa: BLE001
        burners = []
    if burners:
        active = _safe(burners[0], "getActive")
        if active is not None:
            values["Brander"] = ("aan 🔥" if active else "uit", "")
    return values


def read_status(email: str, password: str, client_id: str, token_file: Path) -> dict:
    """Geeft {'model': ..., 'values': {label: (waarde, eenheid)}, 'ts': ...}."""
    from PyViCare.PyViCare import PyViCare

    token_file.parent.mkdir(parents=True, exist_ok=True)
    vicare = PyViCare()
    vicare.initWithCredentials(email, password, client_id, str(token_file))
    configs = [d for d in vicare.devices if not _safe(d, "isGateway")]
    if not configs:
        raise RuntimeError("Geen verwarmingstoestel gevonden in je ViCare-account.")
    for cfg in configs:
        values = collect(cfg.asAutoDetectDevice())
        if values:
            return {"model": _safe(cfg, "getModel") or "Viessmann", "values": values, "ts": time.time()}
    raise RuntimeError("Toestel gevonden, maar het gaf geen temperaturen terug.")
