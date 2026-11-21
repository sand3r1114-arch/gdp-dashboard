"""🏠 Overzicht: het belangrijkste uit huis op één scherm."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

import energy_log
import home_store as hs
from collector import get_collector
from integrations import weather
from ui import ago, camera_snapshot, euro, known_lamps, live_p1, nl, toggle_lamp, weather_now

DAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
          "september", "oktober", "november", "december"]

settings = hs.load_settings()
now = datetime.now()
st.title("🏠 Thuis")
st.caption(f"{DAYS[now.weekday()].capitalize()} {now.day} {MONTHS[now.month - 1]} {now.year}")


def card_title(text: str, page: str) -> None:
    c1, c2 = st.columns([4, 1])
    c1.markdown(f"##### {text}")
    c2.page_link(page, label="→", help="Meer details")


def setup_hint(text: str) -> None:
    st.caption(text)
    st.page_link("app_pages/instellingen.py", label="Instellen", icon="⚙️")


# --------------------------------------------------------------------------- #
@st.fragment(run_every=15)
def top_row():
    w, e, h, n = st.columns(4)

    with w.container(border=True, height=250):
        st.markdown("##### 🌤️ Weer")
        loc = settings.get("location")
        if not loc:
            setup_hint("Stel je woonplaats in.")
        else:
            data, error = weather_now(loc["lat"], loc["lon"])
            if error:
                st.caption(error)
            else:
                cur, daily = data["current"], data["daily"]
                desc, icon = weather.describe(cur.get("weather_code"))
                st.markdown(f"<span style='font-size:2.2rem'>{icon} {nl(cur['temperature_2m'], 0)}°</span>",
                            unsafe_allow_html=True)
                st.caption(f"{desc} · voelt als {nl(cur['apparent_temperature'], 0)}° · {loc['name']}  \n"
                           f"Vandaag {nl(daily['temperature_2m_min'][0], 0)}° / {nl(daily['temperature_2m_max'][0], 0)}°, "
                           f"{nl(daily['precipitation_sum'][0], 1)} mm regen")

    with e.container(border=True, height=250):
        card_title("⚡ Energie", "app_pages/energie.py")
        host = settings.get("homewizard", {}).get("host")
        if not host:
            setup_hint("Koppel je HomeWizard P1-meter.")
        else:
            reading, error = live_p1(host)
            if error:
                st.caption("P1-meter niet bereikbaar.")
            else:
                used, _ = energy_log.usage_today(latest=reading)
                prices = settings.get("prices", {})
                st.metric("Stroom nu", f"{nl(reading.power_w, 0)} W")
                gas = used.get("gas_m3")
                extra = f" ({euro(gas * prices['gas'])})" if gas is not None and prices.get("gas") else ""
                st.caption(f"Gas vandaag: **{nl(gas, 2)} m³**{extra}  \n"
                           f"Stroom vandaag: **{nl(used.get('import_kwh'), 2)} kWh**")

    with h.container(border=True, height=250):
        card_title("🌡️ Verwarming", "app_pages/verwarming.py")
        vi = settings.get("viessmann", {})
        heating = get_collector().heating
        if not vi.get("client_id"):
            setup_hint("Koppel je Viessmann-ketel.")
        elif not heating:
            st.caption("Gegevens worden opgehaald…" if not get_collector().errors.get("heating")
                       else "Ophalen mislukt, zie de pagina Verwarming.")
        else:
            vals = heating["values"]
            room = vals.get("Kamertemperatuur", (None,))[0]
            out = vals.get("Buitentemperatuur", (None,))[0]
            st.metric("Binnen" if room is not None else "Buiten",
                      f"{nl(room if room is not None else out, 1)} °C")
            lines = []
            if room is not None and out is not None:
                lines.append(f"Buiten: **{nl(out, 1)} °C**")
            if "Warm water (boiler)" in vals:
                lines.append(f"Warm water: **{nl(vals['Warm water (boiler)'][0], 0)} °C**")
            if "Brander" in vals:
                lines.append(f"Brander: **{vals['Brander'][0]}**")
            st.caption("  \n".join(lines))

    with n.container(border=True, height=250):
        card_title("📡 Netwerk", "app_pages/netwerk.py")
        scan, store = hs.load_last_scan(), hs.load_devices()
        if not scan:
            st.caption("Nog niet gescand.")
        else:
            rows = hs.build_rows(store, scan)
            online = [r for r in rows if r["online"]]
            unknown = [r for r in online if not r["trusted"]]
            st.metric("Apparaten online", len(online))
            st.caption(("⚠️ " if unknown else "✅ ") + f"{len(unknown)} onbekend  \nscan {ago(scan['started_at'])}")


top_row()


# --------------------------------------------------------------------------- #
@st.fragment(run_every=15)
def lamps_card():
    with st.container(border=True):
        card_title("💡 Lampen", "app_pages/lampen.py")
        lamps = [lamp for lamp in known_lamps() if lamp["online"]]
        if not lamps:
            st.caption("Geen WiZ-lampen gevonden.")
            return
        on = sum(1 for lamp in lamps if lamp["state"].get("state"))
        st.caption(f"{on} van {len(lamps)} aan")
        cols = st.columns(2)
        for i, lamp in enumerate(lamps):
            key = f"ov_lamp_{lamp['mac']}"
            is_on = bool(lamp["state"].get("state"))
            cols[i % 2].toggle(f"{'💡' if is_on else '⚫'} {lamp['label']}", value=is_on, key=key,
                               on_change=toggle_lamp, args=(lamp["ip"], key))


left, right = st.columns([2, 3])
with left:
    lamps_card()
with right:
    cams = settings.get("cameras", [])
    with st.container(border=True):
        card_title("📷 Camera's", "app_pages/cameras.py")
        if not cams:
            st.caption("Nog geen camera's toegevoegd.")
            st.page_link("app_pages/cameras.py", label="Camera toevoegen", icon="📷")
        else:
            @st.fragment(run_every=10)
            def cam_row():
                cols = st.columns(min(len(cams), 2))
                for i, cam in enumerate(cams[:2]):
                    img, error = camera_snapshot(cam["url"])
                    with cols[i]:
                        if img:
                            st.image(img, caption=cam["name"], use_container_width=True)
                        else:
                            st.caption(f"{cam['name']}: {error}")

            cam_row()
