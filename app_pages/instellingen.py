"""⚙️ Instellingen: woonplaats, HomeWizard, energieprijzen en Viessmann."""

from __future__ import annotations

import streamlit as st

import home_store as hs
from collector import get_collector
from integrations import homewizard, weather
from ui import nl

st.title("⚙️ Instellingen")
settings = hs.load_settings()

# --------------------------------------------------------------------------- #
st.subheader("🌤️ Woonplaats (voor het weer)")
loc = settings.get("location", {})
with st.form("location"):
    place = st.text_input("Woonplaats", value=loc.get("name", ""), placeholder="Bijv. Utrecht")
    if st.form_submit_button("💾 Opslaan"):
        try:
            found = weather.geocode(place.strip()) if place.strip() else None
        except Exception as exc:  # noqa: BLE001
            st.error(f"Opzoeken lukt niet: {exc}")
        else:
            if found:
                settings["location"] = found
                hs.save_settings(settings)
                st.success(f"Opgeslagen: {found['name']} ({found['region']}).")
            else:
                st.error("Die plaats kon ik niet vinden.")
if loc:
    st.caption(f"Nu ingesteld: {loc['name']} ({loc.get('region', '')})")

# --------------------------------------------------------------------------- #
st.divider()
st.subheader("⚡ HomeWizard P1-meter")
st.markdown(
    "Zet eerst in de **HomeWizard Energy**-app de lokale API aan: "
    "**Instellingen → Meters → je P1-meter → Lokale API**."
)
hw = settings.setdefault("homewizard", {})
c1, c2 = st.columns([3, 2])
host = c1.text_input("IP-adres van de P1-meter", value=hw.get("host", ""), placeholder="Bijv. 192.168.1.42")
c2.write("")
c2.write("")
if c2.button("🔍 Zoek automatisch", use_container_width=True):
    import network_scanner as ns

    scan = hs.load_last_scan()
    with st.spinner("HomeWizard zoeken op je netwerk… (dit kan een halve minuut duren)"):
        if not scan:
            scan = ns.scan_network(scan_ports=False).to_dict()
        devices = homewizard.find_devices([d["ip"] for d in scan["devices"] if not d.get("is_self")])
    if devices:
        hw["host"] = devices[0]["host"]
        hs.save_settings(settings)
        st.success("Gevonden: " + ", ".join(f"{d.get('product_name', d['product_type'])} op {d['host']}" for d in devices))
        st.rerun()
    else:
        st.error("Geen HomeWizard gevonden. Staat de lokale API aan in de app?")

b1, b2 = st.columns([1, 4])
if b1.button("💾 Opslaan en testen", key="hw_save", type="primary"):
    try:
        r = homewizard.read_p1(host.strip())
    except Exception as exc:  # noqa: BLE001
        st.error(f"Geen verbinding met {host}: {exc}")
    else:
        hw["host"] = host.strip()
        hs.save_settings(settings)
        st.success(f"Werkt! Nu {nl(r.power_w, 0)} W, gasmeter {nl(r.gas_m3, 3)} m³.")

# --------------------------------------------------------------------------- #
st.divider()
st.subheader("💶 Energieprijzen (optioneel)")
st.caption("Vul je prijzen inclusief belasting in om kosten te zien. Je vindt ze in de app of op de factuur van je leverancier.")
prices = settings.setdefault("prices", {})
with st.form("prices"):
    p1, p2, p3 = st.columns(3)
    gas = p1.number_input("Gas (€ per m³)", min_value=0.0, value=float(prices.get("gas", 0.0)), step=0.01, format="%.3f")
    power = p2.number_input("Stroom (€ per kWh)", min_value=0.0, value=float(prices.get("power", 0.0)), step=0.01, format="%.3f")
    export = p3.number_input("Teruglevering (€ per kWh)", min_value=0.0, value=float(prices.get("export", 0.0)), step=0.01, format="%.3f")
    if st.form_submit_button("💾 Opslaan"):
        settings["prices"] = {"gas": gas, "power": power, "export": export}
        hs.save_settings(settings)
        st.success("Prijzen opgeslagen.")

# --------------------------------------------------------------------------- #
st.divider()
st.subheader("🌡️ Viessmann (ViCare)")
vi = settings.setdefault("viessmann", {})
with st.expander("Hoe kom ik aan een client-ID? (eenmalig, ± 5 minuten, gratis)", expanded=not vi.get("client_id")):
    st.markdown("""
1. Ga naar **https://app.developer.viessmann.com/** en log in met je **ViCare-account**
   (hetzelfde e-mailadres en wachtwoord als in de ViCare-app).
2. Klik op **Clients** en dan op **Add** (nieuwe client).
3. Vul in:
   - **Name:** `Thuis dashboard`
   - **Google reCAPTCHA:** uit
   - **Redirect URI:** `vicare://oauth-callback/everest`
4. Klik op **Save** en kopieer het **Client ID** dat verschijnt.
5. Vul hieronder je e-mail, wachtwoord en dat client-ID in.

Het gratis abonnement heeft een daglimiet. Het dashboard vraagt daarom maar één keer per kwartier gegevens op.
""")
with st.form("viessmann"):
    email = st.text_input("ViCare e-mail", value=vi.get("email", ""))
    password = st.text_input("ViCare wachtwoord", value=vi.get("password", ""), type="password")
    client_id = st.text_input("Client ID", value=vi.get("client_id", ""))
    if st.form_submit_button("💾 Opslaan en verbinden", type="primary"):
        settings["viessmann"] = {"email": email.strip(), "password": password, "client_id": client_id.strip()}
        hs.save_settings(settings)
        get_collector().refresh_heating_now()
        st.success("Opgeslagen. Kijk op de pagina Verwarming of het werkt.")

# --------------------------------------------------------------------------- #
st.divider()
st.caption(
    f"🔒 Alles wordt alleen op deze computer bewaard, in `{hs.DATA_DIR}`. Dat geldt ook voor je wachtwoorden en "
    "camera-adressen (zonder versleuteling). Deel die map dus niet."
)
