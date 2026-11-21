"""🏠 Thuis dashboard: zie welke apparaten er op je wifi zitten, per kamer.

Starten (op een computer die met je thuiswifi verbonden is):

    pip install -r requirements.txt
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

import home_store as hs
import network_scanner as ns

st.set_page_config(page_title="Thuis dashboard", page_icon="🏠", layout="wide")


# --------------------------------------------------------------------------- #
# Hulpjes


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


@st.cache_data(show_spinner=False)
def default_network() -> str:
    return ns.guess_network(ns.get_local_ip())


# --------------------------------------------------------------------------- #
# Zijbalk: scannen en instellingen

settings = hs.load_settings()

with st.sidebar:
    st.header("📡 Wifi scannen")
    demo = st.toggle(
        "Voorbeeldgegevens tonen",
        help="Bekijk het dashboard met nep-apparaten, zonder je netwerk te scannen.",
        key="demo",
    )
    network = st.text_input(
        "Netwerk", value=default_network(),
        help="Je thuisnetwerk in CIDR-notatie. Meestal klopt de gok, bv. 192.168.1.0/24.",
        disabled=demo,
    )
    deep = st.toggle(
        "Ook open poorten bekijken", value=True, disabled=demo,
        help="Helpt om te herkennen wát een apparaat is (printer, Chromecast, iPhone…). Iets trager.",
    )
    scan_clicked = st.button("🔍 Scan nu", type="primary", use_container_width=True, disabled=demo)
    st.caption("Scan alleen je eigen netwerk, of een netwerk waarvoor je toestemming hebt.")

    st.divider()
    st.subheader("🏭 Fabrikantenlijst")
    oui_db = ns.load_oui_db(hs.OUI_FILE)
    if oui_db:
        st.caption(f"✅ {len(oui_db):,} fabrikanten geladen.".replace(",", "."))
    else:
        st.caption("Nog niet gedownload. Hiermee zie je van welk merk een apparaat is (Apple, Samsung, Philips…).")
    if st.button("⬇️ Download / bijwerken", use_container_width=True):
        with st.spinner("Downloaden (± 5 MB)…"):
            try:
                n = ns.download_oui_db(hs.OUI_FILE)
                st.success(f"{n} fabrikanten opgeslagen. Scan opnieuw om ze te zien.")
                oui_db = ns.load_oui_db(hs.OUI_FILE)
            except RuntimeError as exc:
                st.error(str(exc))


# --------------------------------------------------------------------------- #
# Gegevens laden (echt of demo) en eventueel scannen

if scan_clicked:
    bar = st.progress(0.0, text="Scan starten…")
    try:
        result = ns.scan_network(
            network.strip(), scan_ports=deep, oui_db=oui_db,
            progress=lambda frac, msg: bar.progress(min(frac, 1.0), text=msg),
        )
    except ValueError as exc:
        bar.empty()
        st.error(f"Kan dit netwerk niet scannen: {exc}")
        st.stop()
    bar.empty()
    scan = result.to_dict()
    store = hs.load_devices()
    new_keys = hs.merge_scan(store, scan)
    hs.save_devices(store)
    hs.save_last_scan(scan)
    st.toast(f"Scan klaar: {len(scan['devices'])} apparaten online, {len(new_keys)} nieuw.", icon="📡")

if demo:
    if "demo_data" not in st.session_state:
        st.session_state.demo_data = hs.demo_data()
    scan, store = st.session_state.demo_data
else:
    scan, store = hs.load_last_scan(), hs.load_devices()

rooms = settings["rooms"]
rows = hs.build_rows(store, scan)


# --------------------------------------------------------------------------- #
# Kop en kerncijfers

st.title("🏠 Thuis dashboard")

if demo:
    st.info("Je bekijkt **voorbeeldgegevens**. Zet ze uit in de zijbalk en klik op *Scan nu* om je eigen wifi te scannen.")

if not scan:
    st.markdown(
        "Nog geen scan gedaan. Klik links op **🔍 Scan nu** om te zien wat er met je wifi verbonden is, "
        "of zet **Voorbeeldgegevens tonen** aan om eerst rond te kijken."
    )
    st.stop()

st.caption(
    f"Netwerk **{scan['network']}** · router **{scan.get('gateway') or 'onbekend'}** · "
    f"laatste scan {ago(scan['started_at'])} ({fmt_time(scan['started_at'])}, {scan['duration_s']:.0f} s)"
)

online_rows = [r for r in rows if r["online"]]
unknown_online = [r for r in online_rows if not r["trusted"]]
rooms_used = {r["room"] for r in rows if r["room"] != hs.UNASSIGNED}

c1, c2, c3, c4 = st.columns(4)
c1.metric("Nu online", len(online_rows), border=True)
c2.metric("Onbekend / niet vertrouwd", len(unknown_online), border=True)
c3.metric("Offline (eerder gezien)", len(rows) - len(online_rows), border=True)
c4.metric("Kamers met apparaten", len(rooms_used), border=True)

if unknown_online:
    names = ", ".join(f"{r['icon']} {r['display']} ({r['ip']})" for r in unknown_online)
    st.warning(
        f"**{len(unknown_online)} {'apparaat' if len(unknown_online) == 1 else 'apparaten'} "
        f"die je nog niet als vertrouwd hebt gemarkeerd:** {names}. "
        "Herken je ze? Geef ze een naam en vink *Vertrouwd* aan in het tabblad *Alle apparaten*.",
        icon="⚠️",
    )

tab_rooms, tab_all, tab_stats, tab_settings = st.tabs(
    ["🏠 Per kamer", "📋 Alle apparaten", "📊 Overzicht", "⚙️ Kamers beheren"]
)


# --------------------------------------------------------------------------- #
# Per kamer

with tab_rooms:
    show_offline = st.toggle("Ook offline apparaten tonen", value=True)
    order = rooms + [r for r in {row["room"] for row in rows} if r not in rooms and r != hs.UNASSIGNED] + [hs.UNASSIGNED]
    groups = [(room, [r for r in rows if r["room"] == room and (show_offline or r["online"])]) for room in order]
    groups = [(room, devs) for room, devs in groups if devs]
    cols = st.columns(3)
    for i, (room, devs) in enumerate(groups):
        n_on = sum(d["online"] for d in devs)
        with cols[i % 3].container(border=True):
            st.markdown(f"#### {room}")
            st.caption(f"{n_on} van {len(devs)} online")
            for d in devs:
                status = "🟢" if d["online"] else "⚪"
                flag = "" if d["trusted"] else " ⚠️"
                when = d["ip"] if d["online"] else f"offline · {ago(d['last_seen'])}"
                sub = when if d["display"] == d["type"] else f"{d['type']} · {when}"
                st.markdown(f"{status} {d['icon']} **{d['display']}**{flag}  \n"
                            f"<span style='opacity:.65;font-size:.85em'>{sub}</span>",
                            unsafe_allow_html=True)
    if any(room == hs.UNASSIGNED for room, _ in groups):
        st.caption("Tip: deel apparaten in per kamer via het tabblad *Alle apparaten*.")


# --------------------------------------------------------------------------- #
# Alle apparaten (bewerkbaar)

with tab_all:
    only_online = st.toggle("Alleen online apparaten", value=False)
    view = [r for r in rows if r["online"] or not only_online]
    df = pd.DataFrame([{
        "key": r["key"],
        "Status": "🟢 online" if r["online"] else "⚪ offline",
        "Naam": r["name"],
        "Kamer": r["room"],
        "Vertrouwd": r["trusted"],
        "Type": f"{r['icon']} {r['type']}",
        "IP-adres": r["ip"],
        "Hostnaam": r["hostname"],
        "Fabrikant": r["vendor"],
        "MAC-adres": r["mac"],
        "Open poorten": r["ports"],
        "Eerst gezien": fmt_time(r["first_seen"]),
        "Laatst gezien": ago(r["last_seen"]),
    } for r in view])

    room_options = rooms + sorted({r["room"] for r in rows} - set(rooms) - {hs.UNASSIGNED}) + [hs.UNASSIGNED]
    edited = st.data_editor(
        df,
        hide_index=True,
        use_container_width=True,
        height=min(38 * (len(df) + 1) + 4, 640),
        column_config={
            "key": None,
            "Naam": st.column_config.TextColumn(help="Geef het apparaat een herkenbare naam", width="medium"),
            "Kamer": st.column_config.SelectboxColumn(options=room_options, required=True),
            "Vertrouwd": st.column_config.CheckboxColumn(help="Vink aan als je dit apparaat kent"),
        },
        disabled=[c for c in df.columns if c not in ("Naam", "Kamer", "Vertrouwd")],
        key=f"editor_{demo}",
    )

    if st.button("💾 Wijzigingen opslaan", type="primary"):
        for rec in edited.to_dict("records"):
            entry = store[rec["key"]]
            entry["name"] = (rec["Naam"] or "").strip()
            entry["room"] = rec["Kamer"] or hs.UNASSIGNED
            entry["trusted"] = bool(rec["Vertrouwd"])
        if demo:
            st.session_state.demo_data = (scan, store)
            st.toast("Opgeslagen (alleen tijdelijk, dit zijn voorbeeldgegevens).", icon="💾")
        else:
            hs.save_devices(store)
            st.toast("Opgeslagen.", icon="💾")
        st.rerun()

    with st.expander("Wat betekenen de open poorten?"):
        st.table(pd.DataFrame(
            [{"Poort": p, "Wat het meestal is": name} for p, name in ns.COMMON_PORTS.items()]
        ).set_index("Poort"))


# --------------------------------------------------------------------------- #
# Overzicht

with tab_stats:
    left, right = st.columns([3, 2])
    with left:
        st.markdown("##### Soorten apparaten (online)")
        counts = Counter(r["type"] for r in online_rows)
        chart_df = pd.DataFrame(
            {"Type": list(counts), "Aantal": list(counts.values())}
        ).sort_values("Aantal", ascending=False)
        chart = alt.Chart(chart_df).mark_bar(color="#2a78d6", cornerRadiusEnd=4, height=18).encode(
            y=alt.Y("Type:N", sort="-x", title=None, axis=alt.Axis(labelLimit=300)),
            x=alt.X("Aantal:Q", title="Aantal apparaten", axis=alt.Axis(tickMinStep=1, format="d")),
            tooltip=["Type", "Aantal"],
        ).properties(height=max(160, 30 * len(chart_df)))
        st.altair_chart(chart, use_container_width=True)
    with right:
        st.markdown("##### Netwerk")
        st.table(pd.DataFrame({
            "": ["Netwerk", "Router", "Deze computer", "Apparaten ooit gezien", "Met privé-MAC",
                 "Fabrikant bekend"],
            "Waarde": [
                scan["network"], scan.get("gateway") or "onbekend", scan["local_ip"], str(len(rows)),
                str(sum(1 for r in rows if r["vendor"] == "(privé-MAC)")),
                str(sum(1 for r in rows if r["vendor"] and r["vendor"] != "(privé-MAC)")),
            ],
        }).set_index(""))
        st.caption(
            "**Privé-MAC:** telefoons en laptops verzinnen per wifi-netwerk een eigen MAC-adres. "
            "Daardoor is het merk onbekend, maar het adres blijft op jouw netwerk meestal hetzelfde."
        )


# --------------------------------------------------------------------------- #
# Kamers beheren

with tab_settings:
    st.markdown("Eén kamer per regel. Apparaten in een verwijderde kamer blijven gewoon zichtbaar.")
    text = st.text_area("Kamers", value="\n".join(rooms), height=280, label_visibility="collapsed")
    if st.button("💾 Kamers opslaan"):
        settings["rooms"] = [r.strip() for r in text.splitlines() if r.strip()]
        hs.save_settings(settings)
        st.toast("Kamers opgeslagen.", icon="🏠")
        st.rerun()
    st.caption(f"Je gegevens staan lokaal in `{hs.DATA_DIR}` en gaan nergens anders heen.")
