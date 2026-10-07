import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab.insights import findings
from lab.mining import kpis
from lab.ui import BLUE, BLUE_LIGHT, GREY, MUTED, data, style

ev, ct = data()
k = kpis(ct, ev)

st.title("Process Improvement Lab")
st.markdown("<p class='note'>Process mining on a <b>real public event log</b>: the receipt phase of a building-permit "
            f"process in a Dutch municipality, {k['from']:%b %Y} to {k['to']:%b %Y}. Every number below is "
            "reconstructed from system timestamps, not from interviews or opinions.</p>", unsafe_allow_html=True)

c = st.columns(6)
c[0].metric("Applications", f"{k['cases']:,}")
c[1].metric("Recorded steps", f"{k['events']:,}")
c[2].metric("Distinct paths", k["variants"])
c[3].metric("Median lead time", f"{k['lead_median']:.0f} days")
c[4].metric("Missed deadline", f"{k['late_share']:.1%}")
c[5].metric("Follow intended process", f"{k['conform_share']:.0%}")

st.subheader("What the data says")
fs = findings(ev, ct)
for row in range(0, len(fs), 3):
    cols = st.columns(3)
    for col, (title, body) in zip(cols, fs[row:row + 3]):
        with col.container(border=True, height="stretch"):
            st.markdown(f"**{title}**")
            st.markdown(f"<span style='font-size:.92rem'>{body}</span>", unsafe_allow_html=True)

st.subheader("Where the time goes")
left, right = st.columns([1, 1])
with left:
    parts = pd.DataFrame({"part": ["Waiting before first step (intake queue)", "Recorded processing span"],
                          "days": [ct.intake_queue_days.mean(), ct.processing_days.mean()]})
    fig = go.Figure(go.Bar(x=parts.days, y=parts.part, orientation="h", marker=dict(color=[BLUE, BLUE_LIGHT], cornerradius=4),
                           text=[f"{d:.1f} days ({d / parts.days.sum():.0%})" for d in parts.days], textposition="outside",
                           cliponaxis=False, hovertemplate="%{y}: %{x:.1f} days<extra></extra>"))
    style(fig, 260, title=dict(text="Average lead time, split by phase", font=dict(size=15)))
    fig.update_xaxes(range=[0, parts.days.max() * 1.45], title="Days")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Intake queue = time from the application's start date to the first recorded step. The source does not "
               "document exactly what happens in that gap. Treat it as the first question to ask the process owner.")
with right:
    s = ct.lead_days.clip(upper=120)
    fig = go.Figure(go.Histogram(x=s, xbins=dict(start=0, end=120, size=4), marker=dict(color=BLUE, line=dict(color="white", width=1)),
                                 hovertemplate="%{x} days: %{y} cases<extra></extra>"))
    fig.add_vline(x=ct.lead_days.median(), line=dict(color="#0b0b0b", width=1),
                  annotation_text=f"Median {ct.lead_days.median():.0f}d", annotation_position="top right")
    fig.add_vline(x=ct.allowed_days.median(), line=dict(color="#d03b3b", width=1, dash="dash"),
                  annotation_text=f"Typical deadline {ct.allowed_days.median():.0f}d", annotation_position="top left")
    style(fig, 260, bargap=0.02, title=dict(text="Lead time per application", font=dict(size=15)))
    fig.update_xaxes(title="Days (capped at 120)"); fig.update_yaxes(title="Applications")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Volume over time")
m = ct.assign(month=ct.startdate.dt.tz_convert(None).dt.to_period("M").dt.to_timestamp()).groupby("month").agg(
    cases=("case_id", "size"), lead=("lead_days", "median")).reset_index()
fig = go.Figure(go.Bar(x=m.month, y=m.cases, marker=dict(color=BLUE, cornerradius=3),
                       hovertemplate="%{x|%b %Y}: %{y} applications<extra></extra>"))
style(fig, 240)
fig.update_yaxes(title="Applications started")
st.plotly_chart(fig, use_container_width=True)
