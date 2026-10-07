"""Run with:  pytest -q"""

import json

import pandas as pd
import pytest

from lab.insights import findings
from lab.mining import (DATA_DIR, START, TRACK_A, TRACK_B, bottlenecks, cases, classify, dfg, enrich, kpis, load,
                        process_map_dot, rework, variants)
from lab.whatif import CostModel, Levers, compare, default_minutes, replay, to_business_case
from lab.xes import read_xes

STD = [START] + TRACK_A + TRACK_B


@pytest.fixture(scope="module")
def log():
    ev, cs = load()
    return ev, cases(ev, cs)


# --- Toy log: hand-checkable ------------------------------------------------
def toy():
    t = lambda d: pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=d)
    ev = pd.DataFrame([
        ("c1", "A", t(0), "r1"), ("c1", "B", t(1), "r2"), ("c1", "C", t(4), "r2"),
        ("c2", "A", t(0), "r1"), ("c2", "B", t(2), "r1"), ("c2", "B", t(3), "r3"), ("c2", "C", t(5), "r2"),
    ], columns=["case_id", "activity", "timestamp", "resource"])
    return ev


def test_enrich_waits_and_repeats():
    e = enrich(toy())
    c2 = e[e.case_id == "c2"]
    assert c2.wait_in_days.tolist()[1:] == [2, 1, 2]
    assert c2.is_repeat.tolist() == [False, False, True, False]


def test_dfg_counts_and_waits():
    edges, nodes = dfg(toy())
    ab = edges[(edges.source == "A") & (edges.target == "B")].iloc[0]
    assert ab["count"] == 2 and ab.median_wait == pytest.approx(1.5)
    assert nodes["B"] == 3


# --- Conformance rules --------------------------------------------------------
@pytest.mark.parametrize("seq,verdict", [
    (STD, "Conforms: standard path"),
    ([START, TRACK_B[0], TRACK_A[0], TRACK_B[1], TRACK_A[1], TRACK_A[2]], "Conforms: standard path"),  # interleaved
    (STD + ["T11 Create document X request unlicensed"], "Conforms: exception path"),
    ([START], "Closed after intake"),
    (STD + [TRACK_A[0]], "Deviates: rework"),
    ([START] + TRACK_A[1:] + TRACK_B, "Deviates: skipped check (T02)"),
    ([START, TRACK_A[1], TRACK_A[0], TRACK_A[2]] + TRACK_B, "Deviates: out of order"),
    ([TRACK_A[0], START], "Deviates: wrong start"),
])
def test_classify(seq, verdict):
    assert classify(seq) == verdict


# --- Real log -----------------------------------------------------------------
def test_xes_reader_matches_csv(log):
    ev, ct = log
    raw_ev, raw_cs = read_xes(DATA_DIR / "raw" / "receipt.xes")
    assert len(raw_ev) == len(ev) == 8577
    assert len(raw_cs) == len(ct) == 1434


def test_kpis_are_consistent(log):
    ev, ct = log
    k = kpis(ct, ev)
    assert k["variants"] == len(variants(ct))
    assert 0 < k["conform_share"] < 1
    assert (ct.lead_days >= ct.processing_days - 1e-9).all()


def test_variant_shares_sum_to_one(log):
    _, ct = log
    v = variants(ct)
    assert v.share.sum() == pytest.approx(1)
    assert v.cumulative_share.iloc[-1] == pytest.approx(1)


def test_bottleneck_shares(log):
    ev, _ = log
    b = bottlenecks(ev, top=200)
    assert b.share_of_wait.sum() == pytest.approx(1)
    assert b.total_wait.is_monotonic_decreasing


def test_rework_cases_are_slower(log):
    ev, ct = log
    _, impact = rework(ev, ct)
    assert impact["lead_with"] > impact["lead_without"]


def test_process_map_is_valid_dot(log):
    ev, _ = log
    dot = process_map_dot(ev, 0.02, "time")
    assert dot.startswith("digraph") and dot.rstrip().endswith("}")
    assert START in dot


def test_findings_are_generated(log):
    ev, ct = log
    fs = findings(ev, ct)
    assert len(fs) >= 6 and all(title and body for title, body in fs)


# --- What-if ------------------------------------------------------------------
def test_no_levers_changes_nothing(log):
    ev, ct = log
    r = replay(ev, ct, Levers())
    assert (r.new_lead - r.lead_days).abs().max() < 1e-6


def test_levers_only_ever_reduce_lead_time(log):
    ev, ct = log
    lv = Levers(intake_cut=0.5, rework_prevented=1.0,
                handoff_cuts={("T05 Print and send confirmation of receipt", "T06 Determine necessity of stop advice"): 0.5})
    r = replay(ev, ct, lv)
    assert (r.new_lead <= r.lead_days + 1e-9).all()
    assert r.new_lead.median() < r.lead_days.median()


def test_automation_saves_effort_and_exports(log):
    ev, ct = log
    cm = CostModel(default_minutes(ev.activity.unique()), hourly_rate=30)
    res = compare(ev, ct, Levers(automate=("T05 Print and send confirmation of receipt",)), cm)
    assert res["labour_saving"] > 0
    case = json.loads(to_business_case("t", res["annual_saving"], 1000, 1000, 100))
    assert {"title", "assumptions", "options"} <= set(case)
    assert case["options"][1]["annual_benefit"] == round(res["annual_saving"])
