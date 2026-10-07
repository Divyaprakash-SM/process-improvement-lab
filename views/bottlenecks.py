import plotly.graph_objects as go
import streamlit as st

from lab.mining import bottlenecks, channels, rework, short, workload
from lab.ui import BLUE, BLUE_LIGHT, MUTED, ORANGE, data, style

ev, ct = data()

st.title("Bottlenecks & rework")
st.markdown("<p class='note'>In most office processes, work spends far longer <i>waiting</i> than being worked on. "
            "Ranking handoffs by <b>total waiting days</b> (how often × how long) shows where calendar time is really lost.</p>",
            unsafe_allow_html=True)

b = bottlenecks(ev, top=10)
left, right = st.columns([1.5, 1])
with left:
    s = b.iloc[::-1]
    fig = go.Figure(go.Bar(x=s.total_wait, y=s.transition, orientation="h", marker=dict(color=BLUE, cornerradius=4),
                           text=[f"{x:.0%}" for x in s.share_of_wait], textposition="outside", cliponaxis=False,
                           customdata=s[["count", "median_wait", "mean_wait"]],
                           hovertemplate="%{y}<br>%{customdata[0]:,} times · median %{customdata[1]:.1f}d · mean %{customdata[2]:.1f}d"
                                         "<br>Total %{x:,.0f} waiting days<extra></extra>"))
    style(fig, 440, title=dict(text="Top 10 handoffs by total waiting days (label = share of all waiting)", font=dict(size=15)))
    fig.update_xaxes(title="Total waiting days", range=[0, s.total_wait.max() * 1.15])
    st.plotly_chart(fig, use_container_width=True)
with right:
    t = b.iloc[0]
    st.markdown(f"""<div class="rec"><b>Biggest bottleneck</b><br>{t.source} → {t.target}<br>
    {int(t['count']):,} handoffs · mean wait {t.mean_wait:.1f} days · <b>{t.share_of_wait:.0%}</b> of all in-process waiting.</div>""",
                unsafe_allow_html=True)
    st.markdown("**Why mean and median differ:** the median handoff is quick, but a long tail of cases waits days or weeks. "
                "Those few slow cases drive the totals, so look at the tail, not the typical case.")

with st.expander("Bottleneck table"):
    st.dataframe(b[["source", "target", "count", "median_wait", "mean_wait", "total_wait", "share_of_wait"]],
                 hide_index=True, use_container_width=True,
                 column_config={"source": "From", "target": "To", "count": "Times",
                                "median_wait": st.column_config.NumberColumn("Median wait (d)", format="%.2f"),
                                "mean_wait": st.column_config.NumberColumn("Mean wait (d)", format="%.1f"),
                                "total_wait": st.column_config.NumberColumn("Total waiting days", format="%.0f"),
                                "share_of_wait": st.column_config.NumberColumn("Share", format="percent")})

st.subheader("Rework")
rw, ri = rework(ev, ct)
c = st.columns(4)
c[0].metric("Cases with rework", f"{ri['cases']} ({ri['share']:.1%})")
c[1].metric("Extra steps performed", f"{ri['extra_events']:,}")
c[2].metric("Median lead: with / without", f"{ri['lead_with']:.0f}d / {ri['lead_without']:.0f}d")
c[3].metric("Missed deadline: with / without", f"{ri['late_with']:.0%} / {ri['late_without']:.0%}")
left, right = st.columns([1.2, 1])
with left:
    s = rw.head(8).iloc[::-1]
    fig = go.Figure(go.Bar(x=s.repeats, y=s.activity.map(short), orientation="h", marker=dict(color=ORANGE, cornerradius=4),
                           text=[f"{n} cases" for n in s.cases], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}<br>%{x} repeat executions<extra></extra>"))
    style(fig, 320, title=dict(text="Most-repeated steps", font=dict(size=15)))
    fig.update_xaxes(title="Repeat executions", range=[0, s.repeats.max() * 1.25])
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.markdown("**Reading this:** a repeated *check* or *determine* step usually means the first attempt was incomplete "
                "or wrong. Fixing it at source (better input validation, a checklist, clearer criteria) removes the loop "
                "and its waiting time.")

st.subheader("Channels and people")
left, right = st.columns(2)
with left:
    ch = channels(ct)
    ch = ch[ch.cases >= 5]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=ch.channel, y=ch.intake_median, name="Intake queue", marker=dict(color=BLUE, cornerradius=0)))
    fig.add_trace(go.Bar(x=ch.channel, y=ch.processing_median, name="Processing", marker=dict(color=BLUE_LIGHT, cornerradius=0)))
    style(fig, 340, barmode="stack", bargap=0.45, title=dict(text="Median days by submission channel", font=dict(size=15)))
    for r in ch.itertuples():
        fig.add_annotation(x=r.channel, y=r.intake_median + r.processing_median, text=f"{r.cases:,} cases",
                           showarrow=False, yshift=10, font=dict(size=11, color=MUTED))
    st.plotly_chart(fig, use_container_width=True)
with right:
    w = workload(ev)
    n = list(range(1, len(w) + 1))
    n_half = int((w.cumulative_share < 0.5).sum()) + 1
    fig = go.Figure(go.Scatter(x=n, y=w.cumulative_share, mode="lines+markers", line=dict(color=BLUE, width=2),
                               marker=dict(size=5), customdata=w.resource,
                               hovertemplate="Busiest %{x} people do %{y:.0%} of all steps<extra></extra>"))
    fig.add_shape(type="line", x0=0, x1=len(w), y0=0, y1=1, line=dict(color=MUTED, dash="dot", width=1))
    fig.add_annotation(x=len(w) * 0.72, y=0.62, text="Perfectly even workload", showarrow=False, font=dict(color=MUTED, size=11))
    fig.add_annotation(x=n_half, y=0.5, text=f"{n_half} people = 50%", showarrow=True, arrowhead=0, ax=40, ay=30,
                       font=dict(size=12))
    style(fig, 340, title=dict(text=f"Workload concentration across {len(w)} people", font=dict(size=15)))
    fig.update_xaxes(title="People, busiest first", range=[0, len(w) + 1]); fig.update_yaxes(tickformat=".0%", range=[0, 1.02])
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"The busiest person alone does {w.iloc[0].share:.0%} of all steps.")
