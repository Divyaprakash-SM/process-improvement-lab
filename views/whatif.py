import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lab.mining import bottlenecks, short
from lab.insights import dur
from lab.ui import BLUE, BLUE_LIGHT, INK, MUTED, active_data, noun, style
from lab.whatif import CostModel, Levers, compare, default_minutes, lever_contributions, to_business_case

ev, ct = active_data()

st.title("What-if & business case")
st.markdown(f"<p class='note'>Every one of the {len(ct):,} real {noun()} is replayed through the improved process: its own "
            "waits are shortened, its own rework is removed, and it is re-measured"
            + (" against its own deadline" if ct.allowed_days.notna().any() else "") +
            ". No averages are assumed. The result exports straight into the <b>Business Case Builder</b>.</p>",
            unsafe_allow_html=True)

b = bottlenecks(ev, top=10)
st.subheader("1 · Choose the improvements")
c = st.columns(2)
has_intake = bool((ct.intake_queue_days > 0).any())
has_deadlines = bool(ct.allowed_days.notna().any())
with c[0]:
    intake_cut = (st.slider("Cut the intake queue by", 0, 90, 50, 5, format="%d%%",
                            help="E.g. instant digital acknowledgement and same-day triage of new applications.") / 100
                  if has_intake else 0.0)
    picked = st.multiselect("Speed up these handoffs", list(b.transition), default=list(b.transition[:2]),
                            help="Ranked by total waiting days. E.g. a work queue with a service-level target.")
    handoff_cut = st.slider("…by", 0, 90, 50, 5, format="%d%%") / 100
with c[1]:
    rework_prevented = st.slider("Prevent rework by", 0, 100, 50, 5, format="%d%%",
                                 help="E.g. validation at submission and a checklist for the check step.") / 100
    acts = sorted(ev.activity.unique(), key=lambda a: -int((ev.activity == a).sum()))
    automate = st.multiselect("Automate these steps (manual effort removed)", acts,
                              default=[a for a in ["T05 Print and send confirmation of receipt"] if a in acts],
                              help="E.g. send the confirmation digitally instead of printing and posting it.")

with st.expander("Cost assumptions (edit to match your organisation)"):
    cc = st.columns(2)
    rate = cc[0].number_input("Fully loaded cost of a case officer (£/hour)", 10.0, 150.0, 30.0, 1.0)
    late_cost = (cc[1].number_input("Cost of each missed deadline (£)", 0.0, 5000.0, 150.0, 10.0,
                                    help="Complaint handling, escalations, statutory penalties. Set to 0 to count labour only.")
                 if has_deadlines else 0.0)
    mins = default_minutes(acts)
    m_df = st.data_editor(pd.DataFrame({"activity": list(mins), "minutes": list(mins.values())}), hide_index=True,
                          use_container_width=True, height=260,
                          column_config={"activity": st.column_config.TextColumn("Step", disabled=True),
                                         "minutes": st.column_config.NumberColumn("Hands-on minutes per execution", min_value=0)})
    st.caption("Default effort estimates are assumptions; the event log records when steps finished, not how long people worked on them.")

handoffs = {(r.source, r.target): handoff_cut for r in b.itertuples() if r.transition in picked}
lv = Levers(intake_cut=intake_cut, handoff_cuts=handoffs, rework_prevented=rework_prevented, automate=tuple(automate))
cm = CostModel(dict(zip(m_df.activity, m_df.minutes)), rate, late_cost)
res = compare(ev, ct, lv, cm)
r = res["replay"]

st.subheader("2 · What changes")
k = st.columns(5)
fmt = lambda a, b, f: (f(b), f(b - a))
k[0].metric("Median lead time", dur(res['lead_median'][1]), f"{res['lead_median'][1] - res['lead_median'][0]:+.1f} days", delta_color="inverse")
k[1].metric("90th percentile", f"{res['lead_p90'][1]:.1f} days", f"{res['lead_p90'][1] - res['lead_p90'][0]:+.1f} days", delta_color="inverse")
if has_deadlines:
    k[2].metric("Missed deadlines", f"{res['late_share'][1]:.1%}", f"{(res['late_share'][1] - res['late_share'][0]) * 100:+.1f} pts", delta_color="inverse")
else:
    k[2].metric("Mean lead time", f"{res['lead_mean'][1]:.1f} days", f"{res['lead_mean'][1] - res['lead_mean'][0]:+.1f} days", delta_color="inverse")
k[3].metric("Officer hours / year", f"{res['effort']['hours_after']:,.0f}",
            f"{res['effort']['hours_after'] - res['effort']['hours_before']:+,.0f} h", delta_color="inverse")
k[4].metric("Annual saving", f"£{res['annual_saving']:,.0f}",
            f"labour £{res['labour_saving']:,.0f} · deadlines £{res['late_saving']:,.0f}", delta_color="off", delta_arrow="off")

left, right = st.columns([1.4, 1])
with left:
    x = np.linspace(0, float(max(r.lead_days.quantile(0.98), 1.0)), 181)
    before = [(r.lead_days <= d).mean() for d in x]
    after = [(r.new_lead <= d).mean() for d in x]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=before, name="Today", line=dict(color=BLUE_LIGHT, width=3),
                             hovertemplate="Today: %{y:.0%} done within %{x:.0f} days<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=after, name="Improved", line=dict(color=BLUE, width=3),
                             hovertemplate="Improved: %{y:.0%} done within %{x:.0f} days<extra></extra>"))
    if has_deadlines:
        fig.add_vline(x=ct.allowed_days.median(), line=dict(color="#d03b3b", dash="dash", width=1),
                      annotation_text="Typical deadline", annotation_position="bottom right")
    style(fig, 380, hovermode="x unified", title=dict(text=f"Share of {noun()} finished within X days", font=dict(size=15)))
    fig.update_xaxes(title="Days from start"); fig.update_yaxes(tickformat=".0%", range=[0, 1.02])
    st.plotly_chart(fig, use_container_width=True)
with right:
    contrib = lever_contributions(ev, ct, lv, cm)
    base_mean, new_mean = res["lead_mean"]
    labels = ["Today (mean)"] + list(contrib.lever) + ["Combined"]
    fig = go.Figure(go.Waterfall(
        x=labels, measure=["absolute"] + ["relative"] * len(contrib) + ["total"],
        y=[base_mean] + list(-contrib.days_saved) + [0],
        text=[f"{base_mean:.1f}"] + [f"−{d:.1f}" for d in contrib.days_saved] + [f"{new_mean:.1f}"], textposition="outside",
        decreasing=dict(marker=dict(color=BLUE)), totals=dict(marker=dict(color=INK)), increasing=dict(marker=dict(color="#d03b3b")),
        connector=dict(line=dict(color=MUTED, width=1, dash="dot")), cliponaxis=False))
    style(fig, 380, showlegend=False, title=dict(text="Days of mean lead time removed, by lever", font=dict(size=15)))
    fig.update_yaxes(title="Days", range=[0, base_mean * 1.2])
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Each lever measured on its own. They overlap slightly, so the parts may not sum exactly to the combined result.")

st.subheader("3 · Export to the Business Case Builder")
st.markdown("Add what the change would cost. The saving above becomes the annual benefit of a new investment option.")
c = st.columns(4)
upfront = c[0].number_input("Upfront cost (£)", 0, 1_000_000, 12_000, 1000, help="E.g. workflow configuration, form redesign")
year1 = c[1].number_input("Year-1 implementation (£)", 0, 1_000_000, 8_000, 1000, help="Training, process redesign, change management")
run = c[2].number_input("Annual running cost (£)", 0, 1_000_000, 2_000, 500, help="Licences, support")
title = c[3].text_input("Decision title", "Redesign the permit receipt process" if noun() == "applications" else "Redesign the process")

benefit = res["annual_saving"]
flows = np.array([-upfront, -year1 - run + benefit * 0.5] + [-run + benefit] * 4)
npv = float(np.sum(flows / 1.035 ** np.arange(6)))
st.markdown(f"""<div class="rec">Quick check, before optimism bias: annual benefit <b>£{benefit:,.0f}</b>, five-year NPV at
3.5% <b>£{npv:,.0f}</b>. {'It pays back.' if npv > 0 else 'It does not pay back at this cost: scale the change across more processes or cut the cost.'}
Load the file below into the Business Case Builder for the full appraisal, risk simulation and Word business case.</div>""",
            unsafe_allow_html=True)
st.download_button("Download case for the Business Case Builder (JSON)",
                   to_business_case(title, benefit, upfront, year1, run), "process_improvement_case.json",
                   "application/json", type="primary")
