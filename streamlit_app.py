"""🏠 Thuis dashboard: energie, verwarming, lampen, camera's en je wifi op één plek.

Starten (op een computer die met je thuiswifi verbonden is):

    pip install -r requirements.txt
    streamlit run streamlit_app.py

Op Windows kan het ook met een dubbelklik op start.bat.
"""

import streamlit as st

from collector import get_collector

st.set_page_config(page_title="Thuis dashboard", page_icon="🏠", layout="wide")

# Start de achtergrondtaak die verbruik en temperaturen opslaat (één keer per server).
get_collector()

page = st.navigation([
    st.Page("app_pages/overzicht.py", title="Overzicht", icon="🏠", default=True),
    st.Page("app_pages/energie.py", title="Energie", icon="⚡"),
    st.Page("app_pages/verwarming.py", title="Verwarming", icon="🌡️"),
    st.Page("app_pages/lampen.py", title="Lampen", icon="💡"),
    st.Page("app_pages/cameras.py", title="Camera's", icon="📷"),
    st.Page("app_pages/netwerk.py", title="Netwerk", icon="📡"),
    st.Page("app_pages/instellingen.py", title="Instellingen", icon="⚙️"),
])
page.run()
