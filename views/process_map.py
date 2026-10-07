import plotly.graph_objects as go
import streamlit as st

from lab.mining import process_map_dot, variants
from lab.ui import BLUE, BLUE_LIGHT, MUTED, active_data, noun, style

ev, ct = active_data()

st.title("Process map & variants")
st.markdown("<p class='note'>The map is drawn automatically from timestamps: a box for every step, an arrow wherever "
            "one step directly followed another. Thicker arrows = more cases. Switch to <b>time</b> to colour arrows "
            "by how long work waits at each handoff.</p>", unsafe_allow_html=True)

c = st.columns([1, 1, 2])
metric = c[0].radio("Label arrows by", ["frequency", "time"], horizontal=True,
                    format_func=lambda m: "Case count" if m == "frequency" else "Mean wait (days)")
min_share = c[1].slider("Hide paths used by fewer than", 0.0, 0.10, 0.02, 0.005, format="%.3f",
                        help="Share of cases. Raise it to see the main road; lower it to see every detour.")
from lab.mining import is_reference_log
c[2].caption("Blue-shaded boxes are the core steps every application should pass through. "
             "White boxes are exception paths (expert advice, extra documents, stop reports)." if is_reference_log(ev) else
             "Blue-shaded boxes are the steps on the most common path. White boxes are detours from it.")

with st.container(border=True):
    st.graphviz_chart(process_map_dot(ev, min_share, metric), use_container_width=True)

st.subheader("Variants: how many different ways does work actually flow?")
v = variants(ct)
left, right = st.columns([1.2, 1])
with left:
    top = v.head(25)
    fig = go.Figure(go.Bar(x=top["rank"], y=top.cases, marker=dict(color=BLUE, cornerradius=3),
                           text=[f"{c:.0%}" for c in top.cumulative_share], textposition="outside", cliponaxis=False,
                           textfont=dict(size=10, color=MUTED), customdata=top[["variant", "cumulative_share"]],
                           hovertemplate="Variant %{x}: %{y} cases (top %{x} = %{customdata[1]:.0%})<br>%{customdata[0]}<extra></extra>"))
    style(fig, 360, title=dict(text="Top 25 variants (label = cumulative share of cases)", font=dict(size=15)))
    fig.update_xaxes(title="Variant rank", dtick=1); fig.update_yaxes(title="Cases", range=[0, top.cases.max() * 1.12])
    st.plotly_chart(fig, use_container_width=True)
with right:
    n80 = int((v.cumulative_share < 0.8).sum()) + 1
    st.metric("Variants", len(v))
    st.metric("Variants covering 80% of cases", n80)
    st.metric("Variants used by a single case", int((v.cases == 1).sum()))
    st.caption("Lots of one-off variants is normal. What matters is whether the common ones are healthy and whether "
               "the rare ones are legitimate exceptions or errors.")

st.dataframe(v.head(40)[["rank", "cases", "share", "cumulative_share", "steps", "lead_median", "conformance", "variant"]],
             hide_index=True, use_container_width=True,
             column_config={"rank": "#", "cases": "Cases", "share": st.column_config.NumberColumn("Share", format="percent"),
                            "cumulative_share": st.column_config.NumberColumn("Cumulative", format="percent"),
                            "steps": "Steps", "lead_median": st.column_config.NumberColumn("Median lead (days)", format="%.1f"),
                            "conformance": "Conformance", "variant": st.column_config.TextColumn("Path", width="large")})
