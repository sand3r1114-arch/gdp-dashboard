"""📷 Camera's: stilstaande beelden via RTSP (eufy en andere merken)."""

from __future__ import annotations

import streamlit as st

import home_store as hs
from integrations.camera import mask_url
from ui import camera_snapshot

st.title("📷 Camera's")

settings = hs.load_settings()
cameras: list[dict] = settings.setdefault("cameras", [])

EUFY_HELP = """
**Zo zet je RTSP aan bij eufy**

1. Open de **eufy Security**-app en tik op de camera.
2. Tik rechtsboven op ⚙️ **Instellingen** en ga naar **Opslag** (soms **Video-instellingen**).
3. Zet **NAS (RTSP)** aan en kies een gebruikersnaam en wachtwoord voor de stream.
4. De app toont nu het adres, bijvoorbeeld `rtsp://gebruiker:wachtwoord@192.168.1.50/live0`.
   Kopieer het en plak het hieronder.

**Deurbel:** alleen sommige bedrade eufy-deurbellen ondersteunen RTSP. Zie je de optie
*NAS (RTSP)* niet, dan kan je deurbel geen beeld naar het dashboard sturen.
Batterijdeurbellen (via de HomeBase) kunnen dat meestal niet.

**Tip:** geef de camera in je router een vast IP-adres, dan blijft het adres kloppen.
"""

if cameras:
    auto = st.toggle("Beelden automatisch verversen (elke 10 s)", value=True)

    @st.fragment(run_every=10 if auto else None)
    def show_cameras():
        cols = st.columns(2 if len(cameras) > 1 else 1)
        for i, cam in enumerate(cameras):
            with cols[i % len(cols)].container(border=True):
                st.markdown(f"**{cam['name']}**")
                img, error = camera_snapshot(cam["url"])
                if img:
                    st.image(img, use_container_width=True)
                else:
                    st.error(error, icon="📷")
                    st.caption(mask_url(cam["url"]))

    show_cameras()
    if not auto and st.button("🔄 Nu verversen"):
        camera_snapshot.clear()
        st.rerun()
else:
    st.info("Nog geen camera's toegevoegd. Zet RTSP aan in de eufy-app en voeg je camera hieronder toe.", icon="📷")

st.divider()
left, right = st.columns([3, 2])
with left:
    with st.form("add_camera", clear_on_submit=True):
        st.markdown("##### Camera toevoegen")
        name = st.text_input("Naam", placeholder="Bijv. Woonkamer of Voordeur")
        url = st.text_input("RTSP-adres", placeholder="rtsp://gebruiker:wachtwoord@192.168.1.50/live0",
                            type="password", help="Wordt alleen op deze computer opgeslagen.")
        if st.form_submit_button("➕ Toevoegen en testen", type="primary"):
            if not name or not url.startswith("rtsp://"):
                st.error("Vul een naam in en een adres dat begint met rtsp://")
            else:
                with st.spinner("Verbinding maken met de camera…"):
                    img, error = camera_snapshot(url)
                if error:
                    st.error(f"Test mislukt: {error}")
                else:
                    cameras.append({"name": name.strip(), "url": url.strip()})
                    hs.save_settings(settings)
                    st.success("Toegevoegd!")
                    st.rerun()
    if cameras:
        st.markdown("##### Camera verwijderen")
        for i, cam in enumerate(cameras):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"{cam['name']}  \n<span style='opacity:.6;font-size:.85em'>{mask_url(cam['url'])}</span>",
                        unsafe_allow_html=True)
            if c2.button("🗑️", key=f"del_cam_{i}", help=f"{cam['name']} verwijderen"):
                cameras.pop(i)
                hs.save_settings(settings)
                st.rerun()
with right:
    st.markdown(EUFY_HELP)
