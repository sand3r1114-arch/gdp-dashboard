"""Achtergrondtaak: zolang het dashboard draait, wordt elke minuut de P1-meter
gelezen en elk kwartier de Viessmann-ketel. Alles komt in thuis_data/verbruik.sqlite."""

from __future__ import annotations

import threading
import time

import streamlit as st

import energy_log
import home_store as hs
from integrations import homewizard, viessmann

P1_INTERVAL = 60
HEATING_INTERVAL = 15 * 60  # de ViCare-API heeft een daglimiet; elk kwartier is ruim veilig
TOKEN_FILE = hs.DATA_DIR / "vicare_token.save"


class Collector(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="thuis-collector")
        self.latest_p1 = None
        self.heating: dict | None = None
        self.errors: dict[str, str] = {}
        self._next_heating = 0.0
        self._wake = threading.Event()

    def refresh_heating_now(self) -> None:
        self._next_heating = 0.0
        self._wake.set()

    def _p1(self, settings: dict) -> None:
        host = settings.get("homewizard", {}).get("host")
        if not host:
            return
        try:
            reading = homewizard.read_p1(host)
            energy_log.add_p1(reading)
            self.latest_p1 = reading
            self.errors.pop("p1", None)
        except Exception as exc:  # noqa: BLE001
            self.errors["p1"] = f"{type(exc).__name__}: {exc}"

    def _heating(self, settings: dict) -> None:
        cfg = settings.get("viessmann", {})
        if not (cfg.get("email") and cfg.get("password") and cfg.get("client_id")):
            return
        if time.time() < self._next_heating:
            return
        self._next_heating = time.time() + HEATING_INTERVAL
        try:
            status = viessmann.read_status(cfg["email"], cfg["password"], cfg["client_id"], TOKEN_FILE)
            energy_log.add_heating(status["ts"], status["values"])
            self.heating = status
            self.errors.pop("heating", None)
        except Exception as exc:  # noqa: BLE001
            self.errors["heating"] = f"{type(exc).__name__}: {exc}"

    def run(self) -> None:
        while True:
            settings = hs.load_settings()
            self._p1(settings)
            self._heating(settings)
            self._wake.wait(P1_INTERVAL)
            self._wake.clear()


@st.cache_resource
def get_collector() -> Collector:
    c = Collector()
    c.start()
    return c
