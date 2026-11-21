"""🌡️ Verwarming: Viessmann-ketel via de ViCare-API."""

from __future__ import annotations

import time

import altair as alt
import streamlit as st

import energy_log
import home_store as hs
from collector import get_collector
from ui import ago, nl, not_configured

st.title("🌡️ Verwarming")

cfg = hs.load_settings().get("viessmann", {})
if not (cfg.get("email") and cfg.get("password") and cfg.get("client_id")):
    not_configured("Koppel eerst je Viessmann-ketel. Bij Instellingen staat stap voor stap hoe je dat doet.")
    st.stop()

collector = get_collector()
heating = collector.heating
error = collector.errors.get("heating")

if heating is None and not error:
    with st.spinner("Gegevens ophalen bij Viessmann…"):
        collector.refresh_heating_now()
        for _ in range(30):
            time.sleep(0.5)
            heating, error = collector.heating, collector.errors.get("heating")
            if heating or error:
                break

if error:
    st.error(f"Ophalen bij Viessmann mislukt: {error}", icon="🔥")
    st.caption("Controleer je e-mail, wachtwoord en client-ID bij Instellingen.")
if not heating:
    st.stop()

st.caption(f"{heating['model']} · bijgewerkt {ago(heating['ts'])} · ververst elk kwartier")
values = heating["values"]
numbers = [(k, v, u) for k, (v, u) in values.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
texts = [(k, v) for k, (v, u) in values.items() if not (isinstance(v, (int, float)) and not isinstance(v, bool))]

for row in range(0, len(numbers), 4):
    cols = st.columns(4)
    for col, (label, value, unit) in zip(cols, numbers[row:row + 4]):
        col.metric(label, f"{nl(value, 1)} {unit}", border=True)
if texts:
    st.markdown(" · ".join(f"**{k}:** {v}" for k, v in texts))

if st.button("🔄 Nu verversen"):
    collector.refresh_heating_now()
    time.sleep(3)
    st.rerun()

st.markdown("##### Temperaturen afgelopen 2 dagen")
df = energy_log.load_heating(time.time() - 2 * 86400)
series = {"room_c": "Kamer", "outside_c": "Buiten", "target_c": "Gewenst"}
long = df.melt(id_vars=["time"], value_vars=list(series), var_name="serie", value_name="temp").dropna()
long["serie"] = long["serie"].map(series)
if long["time"].nunique() < 2:
    st.info("De grafiek vult zich vanzelf: elk kwartier komt er een meting bij.", icon="⏳")
else:
    chart = alt.Chart(long).mark_line(strokeWidth=2).encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(format="%d-%m %H:%M", labelAngle=0)),
        y=alt.Y("temp:Q", title="°C", scale=alt.Scale(zero=False)),
        color=alt.Color("serie:N", title=None, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=["Kamer", "Buiten", "Gewenst"],
                                        range=["#c2410c", "#2a78d6", "#8a8a8a"])),
        strokeDash=alt.condition(alt.datum.serie == "Gewenst", alt.value([4, 3]), alt.value([1, 0])),
        tooltip=[alt.Tooltip("time:T", title="Tijd", format="%d-%m %H:%M"), "serie:N",
                 alt.Tooltip("temp:Q", title="°C", format=".1f")],
    ).properties(height=280)
    st.altair_chart(chart, use_container_width=True)
