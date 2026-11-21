"""💡 Lampen: WiZ-lampen vinden, aan/uit zetten en dimmen."""

from __future__ import annotations

import streamlit as st

import home_store as hs
from integrations import wiz
from ui import dim_lamp, find_lamps, known_lamps, toggle_lamp

st.title("💡 Lampen")
st.caption("WiZ-lampen worden automatisch gevonden op je wifi. Je hebt er geen account voor nodig.")

top = st.columns([1, 1, 1, 3])
if top[0].button("🔍 Opnieuw zoeken", use_container_width=True):
    find_lamps.clear()


def set_all(on: bool) -> None:
    for lamp in known_lamps():
        if lamp["online"]:
            try:
                wiz.set_on(lamp["ip"], on)
            except Exception:  # noqa: BLE001
                pass
    find_lamps.clear()


top[1].button("🌙 Alles uit", on_click=set_all, args=(False,), use_container_width=True)
top[2].button("☀️ Alles aan", on_click=set_all, args=(True,), use_container_width=True)

with st.spinner("Lampen zoeken…"):
    lamps = known_lamps()

if not lamps:
    st.info(
        "Geen WiZ-lampen gevonden. Controleer of de lampen aan de stroom zitten, en of in de WiZ-app "
        "bij **Instellingen → Beveiliging** de optie **Lokale communicatie toestaan** aan staat.",
        icon="💡",
    )
    st.stop()

on_count = sum(1 for lamp in lamps if lamp["state"].get("state"))
st.markdown(f"**{on_count}** van **{len(lamps)}** lampen aan")

rooms = sorted({lamp["room"] for lamp in lamps}, key=lambda r: (r == hs.UNASSIGNED, r))
for room in rooms:
    st.markdown(f"#### {room}")
    room_lamps = [lamp for lamp in lamps if lamp["room"] == room]
    cols = st.columns(3)
    for i, lamp in enumerate(room_lamps):
        with cols[i % 3].container(border=True):
            state = lamp["state"]
            if not lamp["online"]:
                st.markdown(f"⚪ **{lamp['label']}**  \n<span style='opacity:.6'>niet bereikbaar</span>",
                            unsafe_allow_html=True)
                continue
            is_on = bool(state.get("state"))
            st.toggle(f"{'💡' if is_on else '⚫'} **{lamp['label']}**", value=is_on,
                      key=f"lamp_on_{lamp['mac']}", on_change=toggle_lamp,
                      args=(lamp["ip"], f"lamp_on_{lamp['mac']}"))
            st.slider("Helderheid", 10, 100, int(state.get("dimming", 100)), step=10, format="%d%%",
                      key=f"lamp_dim_{lamp['mac']}", on_change=dim_lamp,
                      args=(lamp["ip"], f"lamp_dim_{lamp['mac']}"), disabled=not is_on)

with st.expander("✏️ Namen en kamers aanpassen"):
    settings = hs.load_settings()
    saved = settings.setdefault("lamps", {})
    room_options = settings["rooms"] + [hs.UNASSIGNED]
    with st.form("lamp_names"):
        for lamp in lamps:
            c1, c2, c3 = st.columns([3, 3, 2])
            c1.text_input("Naam", value=lamp.get("name", ""), key=f"name_{lamp['mac']}",
                          placeholder=lamp["label"])
            room = lamp["room"] if lamp["room"] in room_options else hs.UNASSIGNED
            c2.selectbox("Kamer", room_options, index=room_options.index(room), key=f"room_{lamp['mac']}")
            c3.caption(f"{lamp.get('ip', '-')}\n\n{lamp['mac']}")
        if st.form_submit_button("💾 Opslaan", type="primary"):
            for lamp in lamps:
                entry = saved.setdefault(lamp["mac"], {})
                entry["name"] = st.session_state[f"name_{lamp['mac']}"].strip()
                entry["room"] = st.session_state[f"room_{lamp['mac']}"]
            hs.save_settings(settings)
            st.rerun()
