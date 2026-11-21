"""⚡ Energie: stroom en gas via de HomeWizard P1-meter."""

from __future__ import annotations

import time

import altair as alt
import pandas as pd
import streamlit as st

import energy_log
import home_store as hs
from collector import get_collector
from ui import GAS, STROOM, euro, fmt_time, live_p1, nl, not_configured

st.title("⚡ Energie")

settings = hs.load_settings()
host = settings.get("homewizard", {}).get("host")
prices = settings.get("prices", {})
if not host:
    not_configured("Stel eerst je HomeWizard P1-meter in. Daar kan ik hem ook automatisch voor je zoeken.")
    st.stop()

collector = get_collector()


def bar_chart(df: pd.DataFrame, col: str, unit: str, color: str, time_fmt: str, title: str) -> alt.Chart:
    return alt.Chart(df).mark_bar(color=color, cornerRadiusEnd=3).encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(format=time_fmt, labelAngle=0)),
        y=alt.Y(f"{col}:Q", title=unit),
        tooltip=[alt.Tooltip("time:T", title="Tijd", format="%d-%m %H:%M"),
                 alt.Tooltip(f"{col}:Q", title=title, format=".2f")],
    ).properties(height=260)


@st.fragment(run_every=10)
def live_tiles():
    reading, error = live_p1(host)
    if error:
        st.error(error, icon="🔌")
        return
    used, since = energy_log.usage_today(latest=reading)
    gas, imp, exp = used.get("gas_m3"), used.get("import_kwh"), used.get("export_kwh")

    c1, c2, c3, c4 = st.columns(4)
    power = reading.power_w or 0
    c1.metric("Stroom nu", f"{nl(abs(power), 0)} W",
              help="Negatief vermogen betekent dat je teruglevert (bv. zonnepanelen).",
              delta="teruglevering" if power < 0 else None, delta_arrow="off", border=True)
    c2.metric("Gas vandaag", f"{nl(gas, 2)} m³" if gas is not None else "-", border=True,
              delta=euro(gas * prices["gas"]) if gas is not None and prices.get("gas") else None,
              delta_color="off", delta_arrow="off")
    c3.metric("Stroom vandaag", f"{nl(imp, 2)} kWh" if imp is not None else "-", border=True,
              delta=euro(imp * prices["power"]) if imp is not None and prices.get("power") else None,
              delta_color="off", delta_arrow="off")
    c4.metric("Teruggeleverd vandaag", f"{nl(exp, 2)} kWh" if exp is not None else "-", border=True)
    st.caption(
        f"Meterstanden: gas {nl(reading.gas_m3, 3)} m³ · stroom {nl(reading.import_kwh, 1)} kWh. "
        + (f"Vandaag gemeten vanaf {fmt_time(since)}." if since and since > energy_log.midnight_ts() + 60 else "")
        + " Ververst elke 10 seconden."
    )


live_tiles()

if collector.errors.get("p1"):
    st.warning(f"Opslaan van metingen lukt niet: {collector.errors['p1']}")

period = st.segmented_control(
    "Periode", ["Vandaag", "7 dagen", "30 dagen", "1 jaar"], default="Vandaag", label_visibility="collapsed",
)
now = time.time()
start = {
    "Vandaag": energy_log.midnight_ts(), "7 dagen": now - 7 * 86400,
    "30 dagen": now - 30 * 86400, "1 jaar": now - 365 * 86400,
}[period or "Vandaag"]
df = energy_log.load_p1(start - 3600)

if len(df) < 2:
    st.info("Er zijn nog te weinig metingen voor grafieken. Het dashboard slaat elke minuut een meting op "
            "zolang het draait; over een uurtje zie je hier de eerste grafieken.", icon="⏳")
    st.stop()

freq, fmt = ("h", "%H:%M") if period in (None, "Vandaag") else ("D", "%d-%m")
usage = energy_log.usage_per(df, freq)
usage = usage[usage["time"] >= pd.Timestamp.fromtimestamp(start).floor(freq)]
per = "per uur" if freq == "h" else "per dag"

left, right = st.columns(2)
with left:
    st.markdown(f"##### Gas {per}")
    st.altair_chart(bar_chart(usage, "gas_m3", "m³", GAS, fmt, "Gas (m³)"), use_container_width=True)
with right:
    st.markdown(f"##### Stroom afgenomen {per}")
    st.altair_chart(bar_chart(usage, "import_kwh", "kWh", STROOM, fmt, "Stroom (kWh)"), use_container_width=True)

total_gas, total_imp, total_exp = (usage[c].sum() for c in ("gas_m3", "import_kwh", "export_kwh"))
summary = f"**Totaal {period.lower() if period else 'vandaag'}:** gas {nl(total_gas, 2)} m³, stroom {nl(total_imp, 1)} kWh"
if total_exp > 0:
    summary += f", teruggeleverd {nl(total_exp, 1)} kWh"
costs = [(total_gas, prices.get("gas")), (total_imp, prices.get("power")), (-total_exp, prices.get("export"))]
if any(p for _, p in costs):
    summary += f" · kosten ± {euro(sum(v * p for v, p in costs if p))}"
st.markdown(summary)

st.markdown("##### Vermogen")
recent = df[df["ts"] >= max(start, now - 2 * 86400)]
line = alt.Chart(recent).mark_line(color=STROOM, strokeWidth=2).encode(
    x=alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M" if freq == "h" else "%d-%m %H:%M", labelAngle=0)),
    y=alt.Y("power_w:Q", title="Watt"),
    tooltip=[alt.Tooltip("time:T", title="Tijd", format="%d-%m %H:%M"), alt.Tooltip("power_w:Q", title="Watt")],
).properties(height=240)
st.altair_chart(line, use_container_width=True)
st.caption("Vermogen per minuut (maximaal de laatste 2 dagen). Onder nul = teruglevering.")
