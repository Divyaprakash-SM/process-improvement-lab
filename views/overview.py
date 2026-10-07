import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab.insights import dur, findings
from lab.mining import kpis
from lab.ui import BLUE, BLUE_LIGHT, GREY, MUTED, active_data, noun, style

ev, ct = active_data()
k = kpis(ct, ev)

st.title("Process Improvement Lab")
if st.session_state.get("log_upload") is None:
    intro = ("Process mining on a <b>real public event log</b>: the receipt phase of a building-permit process in a "
             "Dutch municipality")
else:
    intro = f"Process mining on <b>your event log</b> ({st.session_state.log_upload.name})"
st.markdown(f"<p class='note'>{intro}, {k['from']:%b %Y} to {k['to']:%b %Y}. Every number below is "
            "reconstructed from system timestamps, not from interviews or opinions.</p>", unsafe_allow_html=True)
if ev.attrs.get("dropped_rows"):
    st.warning(f"{ev.attrs['dropped_rows']} rows had no readable timestamp and were left out.")

c = st.columns(6)
c[0].metric(noun().capitalize(), f"{k['cases']:,}")
c[1].metric("Recorded steps", f"{k['events']:,}")
c[2].metric("Distinct paths", k["variants"])
c[3].metric("Median lead time", dur(k["lead_median"]))
if k["has_deadlines"]:
    c[4].metric("Missed deadline", f"{k['late_share']:.1%}")
else:
    c[4].metric("90% finish within", dur(k["lead_p90"]))
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


def lead_split():
    parts = pd.DataFrame({"part": ["Waiting before first step (intake queue)", "Recorded processing span"],
                          "days": [ct.intake_queue_days.mean(), ct.processing_days.mean()]})
    fig = go.Figure(go.Bar(x=parts.days, y=parts.part, orientation="h", marker=dict(color=[BLUE, BLUE_LIGHT], cornerradius=4),
                           text=[f"{d:.1f} days ({d / parts.days.sum():.0%})" for d in parts.days], textposition="outside",
                           cliponaxis=False, hovertemplate="%{y}: %{x:.1f} days<extra></extra>"))
    style(fig, 260, title=dict(text="Average lead time, split by phase", font=dict(size=15)))
    fig.update_xaxes(range=[0, parts.days.max() * 1.45], title="Days")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Intake queue = time from the case's start date to the first recorded step. The source does not "
               "document exactly what happens in that gap. Treat it as the first question to ask the process owner.")


def lead_histogram():
    cap = float(max(ct.lead_days.quantile(0.98), 1.0))
    s = ct.lead_days.clip(upper=cap)
    fig = go.Figure(go.Histogram(x=s, nbinsx=30, marker=dict(color=BLUE, line=dict(color="white", width=1)),
                                 hovertemplate="%{x} days: %{y} cases<extra></extra>"))
    fig.add_vline(x=ct.lead_days.median(), line=dict(color="#0b0b0b", width=1),
                  annotation_text=f"Median {ct.lead_days.median():.1f}d", annotation_position="top right")
    if k["has_deadlines"]:
        fig.add_vline(x=ct.allowed_days.median(), line=dict(color="#d03b3b", width=1, dash="dash"),
                      annotation_text=f"Typical deadline {ct.allowed_days.median():.0f}d", annotation_position="top left")
    style(fig, 260, bargap=0.02, title=dict(text=f"Lead time per {noun()[:-1]}", font=dict(size=15)))
    fig.update_xaxes(title=f"Days (capped at {cap:.0f})"); fig.update_yaxes(title=noun().capitalize())
    st.plotly_chart(fig, use_container_width=True)


if k["has_intake"]:
    left, right = st.columns(2)
    with left:
        lead_split()
    with right:
        lead_histogram()
else:
    lead_histogram()

st.subheader("Volume over time")
started = ct.startdate.fillna(ct.first_event) if "startdate" in ct else ct.first_event
m = ct.assign(month=started.dt.tz_convert(None).dt.to_period("M").dt.to_timestamp()).groupby("month").agg(
    cases=("case_id", "size"), lead=("lead_days", "median")).reset_index()
fig = go.Figure(go.Bar(x=m.month, y=m.cases, marker=dict(color=BLUE, cornerradius=3),
                       hovertemplate="%{x|%b %Y}: %{y} " + noun() + "<extra></extra>"))
style(fig, 240)
fig.update_yaxes(title=f"{noun().capitalize()} started")
st.plotly_chart(fig, use_container_width=True)
