"""
What-if simulation: replay every real case under an improved process.

Rather than guessing "it'll be 30% faster", we take each of the 1,434 real cases,
apply the proposed changes to *its own* timeline, and re-measure. Levers:

  intake_cut       share of the intake queue removed (time before the first recorded step)
  handoff_cuts     {(from, to): share} waiting time removed on specific handoffs
  rework_prevented share of repeat work (and its waiting time) eliminated
  automate         activities whose manual effort is removed entirely

The labour model converts effort minutes per activity into £ per year, which can
be exported straight into the Business Case Builder as an investment option.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .mining import CORE, enrich

DEFAULT_MINUTES = {a: 15 for a in CORE}
DEFAULT_MINUTES.update({"Confirmation of receipt": 10, "T05 Print and send confirmation of receipt": 12})
EXCEPTION_MINUTES = {"T07": 60, "T08": 45, "T09": 30}  # drafting advice takes longer; other exception steps 20


def default_minutes(activities) -> dict:
    out = {}
    for a in activities:
        if a in DEFAULT_MINUTES:
            out[a] = DEFAULT_MINUTES[a]
        else:
            out[a] = next((m for p, m in EXCEPTION_MINUTES.items() if a.startswith(p)), 20)
    return out


@dataclass
class Levers:
    intake_cut: float = 0.0
    handoff_cuts: dict = field(default_factory=dict)  # {(source, target): share}
    rework_prevented: float = 0.0
    automate: tuple = ()


@dataclass
class CostModel:
    minutes: dict
    hourly_rate: float = 30.0       # fully loaded cost of a case officer, £/hour
    cost_per_late_case: float = 0.0  # complaints, escalations, statutory penalties


def replay(ev: pd.DataFrame, ct: pd.DataFrame, lv: Levers) -> pd.DataFrame:
    """Per-case lead time before and after the levers are applied."""
    e = enrich(ev)
    cut = pd.Series(0.0, index=e.index)
    for (src, tgt), share in lv.handoff_cuts.items():
        cut[(e.prev_activity == src) & (e.activity == tgt)] = share
    wait = e.wait_in_days.fillna(0) * (1 - cut)
    wait = np.where(e.is_repeat, wait * (1 - lv.rework_prevented), wait)
    new_processing = pd.Series(wait, index=e.index).groupby(e.case_id).sum()
    out = ct.set_index("case_id")[["lead_days", "intake_queue_days", "processing_days", "allowed_days", "late",
                                   "channel"]].copy()
    out["new_intake"] = out.intake_queue_days * (1 - lv.intake_cut)
    out["new_processing"] = new_processing.reindex(out.index).fillna(0)
    out["new_lead"] = out.new_intake + out.new_processing
    out["new_late"] = out.new_lead > out.allowed_days
    return out.reset_index()


def effort(ev: pd.DataFrame, lv: Levers, cm: CostModel, years: float) -> dict:
    e = enrich(ev)
    mins = e.activity.map(cm.minutes).fillna(20)
    base = mins.sum()
    saved_rework = (mins * e.is_repeat).sum() * lv.rework_prevented
    saved_auto = (mins * e.activity.isin(lv.automate) * ~e.is_repeat).sum()
    new = base - saved_rework - saved_auto
    per_year = lambda m: m / 60 / years
    return {"hours_before": per_year(base), "hours_after": per_year(new),
            "hours_saved_rework": per_year(saved_rework), "hours_saved_automation": per_year(saved_auto),
            "cost_before": per_year(base) * cm.hourly_rate, "cost_after": per_year(new) * cm.hourly_rate}


def compare(ev: pd.DataFrame, ct: pd.DataFrame, lv: Levers, cm: CostModel) -> dict:
    years = (ev.timestamp.max() - ev.timestamp.min()).days / 365.25
    r = replay(ev, ct, lv)
    eff = effort(ev, lv, cm, years)
    late_before, late_after = r.late.sum() / years, r.new_late.sum() / years
    labour_saving = eff["cost_before"] - eff["cost_after"]
    late_saving = (late_before - late_after) * cm.cost_per_late_case
    return {
        "replay": r, "effort": eff, "years": years,
        "lead_median": (r.lead_days.median(), r.new_lead.median()),
        "lead_mean": (r.lead_days.mean(), r.new_lead.mean()),
        "lead_p90": (r.lead_days.quantile(0.9), r.new_lead.quantile(0.9)),
        "late_share": (r.late.mean(), r.new_late.mean()),
        "late_per_year": (late_before, late_after),
        "annual_saving": labour_saving + late_saving,
        "labour_saving": labour_saving, "late_saving": late_saving,
    }


def lever_contributions(ev, ct, lv: Levers, cm: CostModel) -> pd.DataFrame:
    """Each lever applied on its own: how many days of average lead time does it remove?"""
    base = compare(ev, ct, Levers(), cm)["lead_mean"][0]
    singles = {"Faster handoffs": Levers(handoff_cuts=lv.handoff_cuts),
               "Less rework": Levers(rework_prevented=lv.rework_prevented)}
    if lv.intake_cut:
        singles = {"Faster intake": Levers(intake_cut=lv.intake_cut), **singles}
    rows = [{"lever": k, "days_saved": base - compare(ev, ct, v, cm)["lead_mean"][1]} for k, v in singles.items()]
    return pd.DataFrame(rows)


def to_business_case(title: str, annual_benefit: float, upfront: float, year1: float, run_cost: float,
                     risk_uplift: float = 0.10) -> str:
    """JSON in the Business Case Builder's save format: load it there with 'Load a saved case'."""
    case = {
        "title": title,
        "assumptions": {"years": 5, "discount_rate": 0.035, "cost_optimism_bias": 0.15, "benefit_haircut": 0.10},
        "options": [
            {"name": "Do minimum (current process)", "upfront_cost": 0, "year1_cost": 0, "annual_run_cost": 0,
             "annual_benefit": 0, "ramp_years": 1, "benefit_start_year": 1, "delivery_risk_uplift": 0.0},
            {"name": "Process improvement programme", "upfront_cost": round(upfront), "year1_cost": round(year1),
             "annual_run_cost": round(run_cost), "annual_benefit": round(annual_benefit), "ramp_years": 2,
             "benefit_start_year": 1, "delivery_risk_uplift": risk_uplift},
        ],
    }
    return json.dumps(case, indent=2)
