import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab.mining import CORE, TRACK_A, TRACK_B, START, enrich, short
from lab.ui import BLUE, MUTED, STATUS, data, style

ev, ct = data()

st.title("Conformance & cases")
st.markdown("<p class='note'>Does what actually happened match how the process is meant to run? The intended process "
            "is written as explicit rules, so every case gets a clear verdict and every deviation can be traced to a real application.</p>",
            unsafe_allow_html=True)

with st.expander("The intended process (reference model)", expanded=True):
    st.markdown(f"""
1. **{START}** comes first.
2. Two tracks then run **in parallel** and may interleave:
   - **Track A:** {" → ".join(TRACK_A)}
   - **Track B:** {" → ".join(TRACK_B)}
3. Each core step happens **once**. A repeat counts as rework.
4. Exception steps (T07–T20: expert advice, extra documents, stop reports) are **allowed** when needed.
""")

order = ["Conforms: standard path", "Conforms: exception path", "Closed after intake", "Deviates: out of order",
         "Deviates: skipped check (T02)", "Deviates: incomplete", "Deviates: rework", "Deviates: wrong start"]
summary = (ct.groupby("conformance").agg(cases=("case_id", "size"), lead=("lead_days", "median"), late=("late", "mean"))
           .reindex([o for o in order if o in set(ct.conformance)]).reset_index())
left, right = st.columns([1.2, 1])
with left:
    s = summary.iloc[::-1]
    fig = go.Figure(go.Bar(x=s.cases, y=s.conformance, orientation="h",
                           marker=dict(color=[STATUS.get(c, MUTED) for c in s.conformance], cornerradius=4),
                           text=[f"{n:,} ({n / len(ct):.0%})" for n in s.cases], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}: %{x} cases<extra></extra>"))
    style(fig, 330, title=dict(text="Cases by conformance verdict", font=dict(size=15)))
    fig.update_xaxes(range=[0, s.cases.max() * 1.25])
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.dataframe(summary, hide_index=True, use_container_width=True,
                 column_config={"conformance": "Verdict", "cases": "Cases",
                                "lead": st.column_config.NumberColumn("Median lead (days)", format="%.1f"),
                                "late": st.column_config.NumberColumn("Missed deadline", format="percent")})
    st.caption("Conforming isn't the same as fast: most of the lead time sits in the intake queue, which every path shares.")

st.subheader("Case explorer")
c = st.columns([1, 1, 2])
verdict = c[0].selectbox("Verdict", ["All"] + list(summary.conformance))
pool = ct if verdict == "All" else ct[ct.conformance == verdict]
pool = pool.sort_values("lead_days", ascending=False)
case_id = c[1].selectbox("Case (slowest first)", pool.case_id.head(200))
row = ct.set_index("case_id").loc[case_id]
c[2].markdown(f"**{row.conformance}** · channel {row.channel} · {row.events} steps · lead {row.lead_days:.1f} days "
              f"(intake {row.intake_queue_days:.1f} + processing {row.processing_days:.1f}) · "
              f"{'🔴 missed deadline' if row.late else '🟢 within deadline'}")

e = enrich(ev[ev.case_id == case_id])
e["label"] = e.activity.map(short)
fig = go.Figure()
if pd.notna(row.startdate):
    fig.add_trace(go.Scatter(x=[row.startdate, e.timestamp.min()], y=["Application start", e.label.iloc[0]],
                             mode="lines", line=dict(color=MUTED, dash="dot", width=1.5), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=[row.startdate], y=["Application start"], mode="markers", marker=dict(size=10, color=MUTED, symbol="diamond"),
                             showlegend=False, hovertemplate="Application start %{x|%d %b %Y}<extra></extra>"))
fig.add_trace(go.Scatter(x=e.timestamp, y=e.label, mode="lines+markers", showlegend=False,
                         line=dict(color=BLUE, width=1.5), marker=dict(size=10, color=["#d03b3b" if r else BLUE for r in e.is_repeat],
                                                                      line=dict(color="white", width=2)),
                         customdata=e[["resource", "wait_in_days"]],
                         hovertemplate="%{y}<br>%{x|%d %b %Y %H:%M}<br>by %{customdata[0]}<br>waited %{customdata[1]:.1f} days<extra></extra>"))
if pd.notna(row.deadline):
    fig.add_vline(x=row.deadline, line=dict(color="#d03b3b", dash="dash", width=1))
    fig.add_annotation(x=row.deadline, y=1, yref="paper", text="Deadline", showarrow=False, xanchor="left",
                       font=dict(color="#d03b3b", size=11))
style(fig, max(300, 34 * (e.label.nunique() + 2)), title=dict(text=f"Timeline of {case_id} (red = repeated step)", font=dict(size=15)))
fig.update_yaxes(categoryorder="array", categoryarray=list(dict.fromkeys(["Application start"] + list(e.label)))[::-1])
st.plotly_chart(fig, use_container_width=True)
