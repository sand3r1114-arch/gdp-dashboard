import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

import energy_log
from integrations import camera, homewizard, viessmann, weather, wiz

P1_DATA = {
    "wifi_strength": 80, "meter_model": "ISKRA 2M550T-1012", "active_power_w": 512.0,
    "total_power_import_kwh": 1234.567, "total_power_export_kwh": 12.5, "total_gas_m3": 4321.123,
}


# --------------------------------------------------------------------------- HomeWizard
@pytest.fixture
def fake_p1():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = {"/api": {"product_type": "HWE-P1", "product_name": "P1 meter", "serial": "abc"},
                    "/api/v1/data": P1_DATA}.get(self.path)
            self.send_response(200 if body else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body or {}).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{server.server_port}"
    server.shutdown()


def test_homewizard_read_and_identify(fake_p1):
    r = homewizard.read_p1(fake_p1)
    assert (r.power_w, r.gas_m3, r.import_kwh, r.export_kwh) == (512.0, 4321.123, 1234.567, 12.5)
    found = homewizard.find_devices(["127.0.0.1:9", fake_p1])  # poort 9: niets
    assert [d["host"] for d in found] == [fake_p1]
    assert found[0]["product_type"] == "HWE-P1"


# --------------------------------------------------------------------------- WiZ
@pytest.fixture
def fake_bulb():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    state = {"mac": "a8bb50aabbcc", "state": False, "dimming": 50, "temp": 2700, "rssi": -55}
    stop = threading.Event()

    def serve():
        s.settimeout(0.1)
        while not stop.is_set():
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            msg = json.loads(data)
            if msg["method"] == "setPilot":
                state.update(msg["params"])
                reply = {"method": "setPilot", "result": {"success": True}}
            else:
                reply = {"method": "getPilot", "env": "pro", "result": dict(state)}
            s.sendto(json.dumps(reply).encode(), addr)

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    yield s.getsockname()[1], state
    stop.set()
    t.join()
    s.close()


def test_wiz_control_and_discover(fake_bulb):
    port, state = fake_bulb
    assert wiz.get_state("127.0.0.1", port=port)["mac"] == "a8bb50aabbcc"
    wiz.set_on("127.0.0.1", True, port=port)
    assert state["state"] is True
    wiz.set_brightness("127.0.0.1", 5, port=port)  # minimaal 10%
    assert state["dimming"] == 10
    found = wiz.discover(["127.0.0.1"], timeout=0.8, port=port)
    assert found["127.0.0.1"]["state"] is True


def test_wiz_timeout_when_nobody_answers():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))  # poort bestaat, maar antwoordt nooit
        with pytest.raises(TimeoutError):
            wiz.get_state("127.0.0.1", port=s.getsockname()[1])


def test_wiz_broadcast_addresses():
    assert wiz.broadcast_addresses("192.168.1.23") == ["255.255.255.255", "192.168.1.255"]


# --------------------------------------------------------------------------- Energie-opslag
def test_energy_log_usage(tmp_path):
    db = tmp_path / "v.sqlite"
    start = energy_log.midnight_ts() - 1800  # half uur voor middernacht
    gas, kwh = 100.0, 500.0
    for i in range(8):  # elke 15 minuten
        gas += 0.25 if i else 0
        kwh += 0.5 if i else 0
        energy_log.add_p1(SimpleNamespace(ts=start + i * 900, power_w=400, import_kwh=kwh,
                                          export_kwh=0.0, gas_m3=gas), db)
    df = energy_log.load_p1(0, db)
    assert len(df) == 8
    per_hour = energy_log.usage_per(df, "h")
    assert per_hour["gas_m3"].sum() == pytest.approx(7 * 0.25)
    used, since = energy_log.usage_today(db)
    # vanaf de laatste meting voor middernacht (i=2) tot de laatste (i=7): 5 stappen
    assert used["gas_m3"] == pytest.approx(5 * 0.25)
    assert used["import_kwh"] == pytest.approx(5 * 0.5)
    assert since == energy_log.midnight_ts()
    # de grafiek ("per uur sinds middernacht") moet hetzelfde totaal geven als de tegel
    import pandas as pd
    hours = per_hour[per_hour["time"] >= pd.Timestamp.fromtimestamp(energy_log.midnight_ts())]
    assert hours["gas_m3"].sum() == pytest.approx(used["gas_m3"])


def test_energy_log_ignores_meter_reset(tmp_path):
    db = tmp_path / "v.sqlite"
    for i, g in enumerate([10.0, 10.5, 0.2, 0.7]):  # nieuwe meter tussendoor
        energy_log.add_p1(SimpleNamespace(ts=1000 + i * 60, power_w=1, import_kwh=1, export_kwh=0, gas_m3=g), db)
    steps = energy_log.step_usage(energy_log.load_p1(0, db))
    assert steps["gas_m3"].sum() == pytest.approx(1.0)


# --------------------------------------------------------------------------- Weer
def test_weather_describe_and_geocode(monkeypatch):
    assert weather.describe(61) == ("Lichte regen", "🌦️")
    assert weather.describe(None)[0] == "Onbekend"
    calls = []

    def fake_get_json(url, params=None, timeout=5.0):
        calls.append(params)
        return {"results": [{"name": "Utrecht", "latitude": 52.09, "longitude": 5.12, "admin1": "Utrecht"}]}

    monkeypatch.setattr(weather, "get_json", fake_get_json)
    assert weather.geocode("utrecht") == {"name": "Utrecht", "lat": 52.09, "lon": 5.12, "region": "Utrecht"}
    assert calls[0]["countryCode"] == "NL"


# --------------------------------------------------------------------------- Camera
def test_camera_snapshot_from_video(tmp_path):
    import cv2
    import numpy as np

    path = str(tmp_path / "test.avi")
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 5, (64, 48))
    for i in range(10):
        out.write(np.full((48, 64, 3), i * 20, dtype=np.uint8))
    out.release()
    jpg = camera.snapshot(path)
    assert jpg[:2] == b"\xff\xd8"  # JPEG


def test_camera_errors_and_mask():
    with pytest.raises(camera.CameraError):
        camera.snapshot("rtsp://127.0.0.1:9/live0", timeout_s=2)
    assert camera.mask_url("rtsp://admin:geheim123@192.168.1.5/live0") == "rtsp://admin:•••@192.168.1.5/live0"


# --------------------------------------------------------------------------- Viessmann
def test_viessmann_collect_skips_unsupported():
    def unsupported():
        raise RuntimeError("niet ondersteund")

    circuit = SimpleNamespace(getRoomTemperature=lambda: 20.5, getActiveProgram=lambda: "reduced",
                              getSupplyTemperature=unsupported)
    device = SimpleNamespace(getOutsideTemperature=lambda: 7.0, getBoilerTemperature=unsupported,
                             circuits=[circuit], burners=[SimpleNamespace(getActive=lambda: True)])
    values = viessmann.collect(device)
    assert values["Buitentemperatuur"] == (7.0, "°C")
    assert values["Kamertemperatuur"] == (20.5, "°C")
    assert values["Programma"] == ("Verlaagd", "")
    assert values["Brander"] == ("aan 🔥", "")
    assert "Keteltemperatuur" not in values and "Aanvoertemperatuur" not in values


def test_heating_log(tmp_path):
    db = tmp_path / "v.sqlite"
    energy_log.add_heating(time.time(), {"Kamertemperatuur": (20.5, "°C"), "Brander": ("aan", "")}, db)
    df = energy_log.load_heating(0, db)
    assert df.loc[0, "room_c"] == 20.5 and df["outside_c"].isna().all()
