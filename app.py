"""
Process Improvement Lab: entry point.

Run locally:  streamlit run app.py
"""

import streamlit as st

from lab.ui import CSS

st.set_page_config(page_title="Process Improvement Lab", page_icon="🔍", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

pages = st.navigation([
    st.Page("views/overview.py", title="Overview & findings", icon="🔍", default=True),
    st.Page("views/process_map.py", title="Process map & variants", icon="🗺️"),
    st.Page("views/bottlenecks.py", title="Bottlenecks & rework", icon="⏳"),
    st.Page("views/conformance.py", title="Conformance & cases", icon="✅"),
    st.Page("views/whatif.py", title="What-if & business case", icon="💷"),
])

with st.sidebar:
    st.caption("**Data:** real event log of 1,434 building-permit applications from a Dutch municipality "
               "(Buijs, 2014, 4TU.ResearchData, CoSeLoG project). Resources are anonymised in the source.")

pages.run()
