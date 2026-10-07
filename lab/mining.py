"""
Process mining engine: pure pandas, no external process-mining library.

Plain-English glossary
----------------------
Case          one thing flowing through the process (here: a permit application)
Event         one step done to a case, with a timestamp and who did it
Variant       the exact sequence of steps a case took. Many variants = an
              inconsistent process
Directly-follows graph (DFG)
              the process map: activity A -> activity B whenever B came straight after A
Waiting time  time between one step finishing and the next one finishing. In most
              office processes, work waits far longer than it is worked on
Rework        the same step done more than once on the same case
Conformance   does what actually happened match how the process is supposed to run?
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

START = "Confirmation of receipt"
TRACK_A = ["T02 Check confirmation of receipt", "T04 Determine confirmation of receipt",
           "T05 Print and send confirmation of receipt"]
TRACK_B = ["T06 Determine necessity of stop advice", "T10 Determine necessity to stop indication"]
CORE = [START] + TRACK_A + TRACK_B
EXCEPTION_PREFIXES = ("T07", "T08", "T09", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T20")


def short(activity: str) -> str:
    """'T02 Check confirmation of receipt' -> 'T02 Check confirmation…' for compact labels."""
    return activity if len(activity) <= 30 else activity[:28].rstrip() + "…"


def wrap(activity: str, width: int = 24) -> str:
    """Break a long activity name over lines for the process map (Graphviz newline escape)."""
    words, lines, cur = activity.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return "\\n".join(lines)


def load(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    ev = pd.read_csv(data_dir / "events.csv")
    ev["timestamp"] = pd.to_datetime(ev.timestamp, utc=True, format="ISO8601")
    cs = pd.read_csv(data_dir / "cases.csv")
    for col in ("startdate", "enddate", "enddate_planned", "deadline"):
        if col in cs:
            cs[col] = pd.to_datetime(cs[col], utc=True, format="ISO8601")
    return ev.sort_values(["case_id", "timestamp"]).reset_index(drop=True), cs


def enrich(ev: pd.DataFrame) -> pd.DataFrame:
    """Add the next activity, the wait until it, and whether this event repeats an earlier one."""
    e = ev.copy()
    g = e.groupby("case_id")
    e["prev_activity"] = g.activity.shift(1)
    e["next_activity"] = g.activity.shift(-1)
    e["wait_in_days"] = (e.timestamp - g.timestamp.shift(1)).dt.total_seconds() / 86400
    e["position"] = g.cumcount()
    e["is_repeat"] = e.groupby(["case_id", "activity"]).cumcount() > 0
    e["handover"] = e.resource != g.resource.shift(1)
    return e


# ---------------------------------------------------------------------------
# Case level
# ---------------------------------------------------------------------------
def classify(seq: list[str]) -> str:
    """Rule-based conformance against the intended process:
    receipt first, then two tracks that may interleave:
      A: T02 check -> T04 determine -> T05 print & send
      B: T06 stop advice -> T10 stop indication
    Exception paths (expert advice, extra documents, stop reports) are allowed."""
    if len(seq) == 1 and seq[0] == START:
        return "Closed after intake"
    if seq[0] != START:
        return "Deviates: wrong start"
    core_counts = pd.Series([s for s in seq if s in CORE]).value_counts()
    if (core_counts > 1).any():
        return "Deviates: rework"
    missing = [a for a in TRACK_A + TRACK_B if a not in seq]
    if TRACK_A[0] in missing and len(missing) == 1:
        return "Deviates: skipped check (T02)"
    if missing:
        return "Deviates: incomplete"
    for track in (TRACK_A, TRACK_B):
        pos = [seq.index(a) for a in track]
        if pos != sorted(pos):
            return "Deviates: out of order"
    if any(s.startswith(EXCEPTION_PREFIXES) for s in seq):
        return "Conforms: exception path"
    return "Conforms: standard path"


def cases(ev: pd.DataFrame, cs: pd.DataFrame) -> pd.DataFrame:
    e = enrich(ev)
    agg = e.groupby("case_id").agg(
        first_event=("timestamp", "min"), last_event=("timestamp", "max"), events=("activity", "size"),
        repeats=("is_repeat", "sum"), handovers=("handover", "sum"),
        rework_wait=("wait_in_days", lambda s: s[e.loc[s.index, "is_repeat"]].sum()))
    seqs = e.groupby("case_id").activity.apply(list)
    agg["variant"] = seqs.map(" → ".join)
    agg["conformance"] = seqs.map(classify)
    agg["standard_variant"] = seqs.map(lambda s: " → ".join(sorted(set(s), key=s.index)))
    df = cs.set_index("case_id").join(agg)
    df["processing_days"] = (df.last_event - df.first_event).dt.total_seconds() / 86400
    df["intake_queue_days"] = ((df.first_event - df.startdate).dt.total_seconds() / 86400).clip(lower=0)
    df["lead_days"] = df.intake_queue_days + df.processing_days
    df["allowed_days"] = (df.deadline - df.startdate).dt.total_seconds() / 86400
    df["late"] = df.lead_days > df.allowed_days
    df["has_rework"] = df.repeats > 0
    df["exception_path"] = df.variant.str.contains("|".join(EXCEPTION_PREFIXES))
    return df.reset_index()


def kpis(ct: pd.DataFrame, ev: pd.DataFrame) -> dict:
    span_years = (ev.timestamp.max() - ev.timestamp.min()).days / 365.25
    return {
        "cases": len(ct), "events": len(ev), "activities": ev.activity.nunique(),
        "variants": ct.variant.nunique(), "resources": ev.resource.nunique(),
        "from": ev.timestamp.min(), "to": ev.timestamp.max(),
        "cases_per_year": len(ct) / span_years if span_years else len(ct),
        "lead_median": ct.lead_days.median(), "lead_p90": ct.lead_days.quantile(0.9),
        "processing_median": ct.processing_days.median(), "intake_median": ct.intake_queue_days.median(),
        "late_share": ct.late.mean(), "rework_share": ct.has_rework.mean(),
        "intake_only_share": (ct.conformance == "Closed after intake").mean(),
        "conform_share": ct.conformance.str.startswith("Conforms").mean(),
    }


# ---------------------------------------------------------------------------
# Variants, process map, bottlenecks
# ---------------------------------------------------------------------------
def variants(ct: pd.DataFrame) -> pd.DataFrame:
    v = (ct.groupby("variant").agg(cases=("case_id", "size"), lead_median=("lead_days", "median"),
                                   processing_median=("processing_days", "median"), conformance=("conformance", "first"))
         .sort_values("cases", ascending=False).reset_index())
    v["share"] = v.cases / v.cases.sum()
    v["cumulative_share"] = v.share.cumsum()
    v["steps"] = v.variant.str.count("→") + 1
    v.insert(0, "rank", range(1, len(v) + 1))
    return v


def dfg(ev: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    e = enrich(ev)
    edges = (e.dropna(subset=["prev_activity"])
             .groupby(["prev_activity", "activity"]).wait_in_days
             .agg(count="size", median_wait="median", mean_wait="mean", total_wait="sum").reset_index()
             .rename(columns={"prev_activity": "source", "activity": "target"}))
    starts = e[e.position == 0].activity.value_counts()
    ends = e.groupby("case_id").tail(1).activity.value_counts()
    for name, counts, start in (("● start", starts, True), ("■ end", ends, False)):
        extra = pd.DataFrame({"source": name if start else counts.index, "target": counts.index if start else name,
                              "count": counts.values, "median_wait": 0.0, "mean_wait": 0.0, "total_wait": 0.0})
        edges = pd.concat([edges, extra], ignore_index=True)
    nodes = ev.activity.value_counts()
    return edges, nodes


def bottlenecks(ev: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """Where does calendar time go? Rank handoffs by total waiting days (frequency x wait)."""
    e, _ = dfg(ev)
    e = e[~e.source.isin(["● start"]) & ~e.target.isin(["■ end"])].copy()
    e["share_of_wait"] = e.total_wait / e.total_wait.sum()
    e["transition"] = e.source.map(short) + " → " + e.target.map(short)
    return e.sort_values("total_wait", ascending=False).head(top).reset_index(drop=True)


def process_map_dot(ev: pd.DataFrame, min_share: float = 0.02, metric: str = "frequency") -> str:
    """Graphviz DOT for the process map. Edges below min_share of cases are hidden to keep it readable.
    metric='frequency' labels edges with case counts; 'time' labels them with the mean wait and
    colours slow handoffs darker. (Mean, not median: most handoffs are instant, so the median is ~0
    almost everywhere and the delay lives in the tail.)"""
    edges, nodes = dfg(ev)
    n_cases = ev.case_id.nunique()
    edges = edges[edges["count"] >= max(1, min_share * n_cases)]
    keep = set(edges.source) | set(edges.target)
    max_count = edges["count"].max()
    waits = edges.loc[edges.mean_wait > 0, "mean_wait"]
    hi_wait = waits.quantile(0.9) if len(waits) else 1
    ramp = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

    lines = ['digraph G {', 'rankdir=TB; bgcolor="transparent"; nodesep=0.35; ranksep=0.45;',
             'node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=11 color="#bdbcb6" '
             'fillcolor="#ffffff" fontcolor="#0b0b0b" margin="0.18,0.08"];',
             'edge [fontname="Helvetica" fontsize=9 color="#9a9993" fontcolor="#52514e" arrowsize=0.6];']
    for name in keep:
        if name in ("● start", "■ end"):
            lines.append(f'"{name}" [shape=circle label="" width=0.22 style=filled fillcolor="#0b0b0b" color="#0b0b0b"];'
                         if name == "● start" else
                         f'"{name}" [shape=doublecircle label="" width=0.18 style=filled fillcolor="#0b0b0b" color="#0b0b0b"];')
        else:
            core = name in CORE
            lines.append(f'"{name}" [label="{wrap(name)}\\n{nodes.get(name, 0):,}×" '
                         f'fillcolor="{"#e8f1fc" if core else "#ffffff"}" penwidth={1.4 if core else 1}];')
    for r in edges.itertuples():
        width = 0.6 + 4.4 * (r.count / max_count)
        if metric == "time" and r.mean_wait > 0:
            idx = int(min(len(ramp) - 1, (r.mean_wait / hi_wait) * (len(ramp) - 1)))
            colour, label = ramp[idx], f"{r.mean_wait:.1f}d"
        else:
            colour, label = "#7f7e79", f"{r.count:,}"
        lines.append(f'"{r.source}" -> "{r.target}" [penwidth={width:.2f} color="{colour}" label=" {label}"];')
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rework, channels, people
# ---------------------------------------------------------------------------
def rework(ev: pd.DataFrame, ct: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    e = enrich(ev)
    rep = e[e.is_repeat].groupby("activity").agg(repeats=("case_id", "size"), cases=("case_id", "nunique"))
    rep = rep.sort_values("repeats", ascending=False).reset_index()
    with_rw, without = ct[ct.has_rework], ct[~ct.has_rework & (ct.events > 1)]
    impact = {"cases": int(ct.has_rework.sum()), "share": ct.has_rework.mean(),
              "lead_with": with_rw.lead_days.median(), "lead_without": without.lead_days.median(),
              "processing_with": with_rw.processing_days.median(), "processing_without": without.processing_days.median(),
              "late_with": with_rw.late.mean(), "late_without": without.late.mean(),
              "extra_events": int(e.is_repeat.sum())}
    return rep, impact


def channels(ct: pd.DataFrame) -> pd.DataFrame:
    return (ct.groupby("channel").agg(cases=("case_id", "size"), lead_median=("lead_days", "median"),
                                      intake_median=("intake_queue_days", "median"),
                                      processing_median=("processing_days", "median"),
                                      late_share=("late", "mean"), rework_share=("has_rework", "mean"))
            .sort_values("cases", ascending=False).reset_index())


def workload(ev: pd.DataFrame) -> pd.DataFrame:
    e = enrich(ev)
    w = e.groupby("resource").agg(events=("activity", "size"), cases=("case_id", "nunique"),
                                  activities=("activity", "nunique")).sort_values("events", ascending=False)
    w["share"] = w.events / w.events.sum()
    w["cumulative_share"] = w.share.cumsum()
    return w.reset_index()
