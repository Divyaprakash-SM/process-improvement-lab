"""
Minimal XES (eXtensible Event Stream) reader.

XES is the IEEE standard format for event logs: every case (here, a permit
application) is a <trace>, and every step taken on it is an <event> with an
activity name, a timestamp and who did it. This reader turns a log into two
tidy tables without any process-mining library:

  events.csv  one row per event: case_id, activity, timestamp, resource, group
  cases.csv   one row per case: case attributes (channel, deadline, ...)

Run:  python -m lab.xes data/raw/receipt.xes
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _attrs(el: ET.Element) -> dict:
    return {c.get("key"): c.get("value") for c in el if c.tag in {"string", "date", "int", "float", "boolean"}}


def read_xes(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = ET.parse(path).getroot()
    events, cases = [], []
    for trace in root.iter("trace"):
        ca = _attrs(trace)
        cid = ca.get("concept:name")
        cases.append({"case_id": cid, **{k: v for k, v in ca.items() if k != "concept:name"}})
        for ev in trace.iter("event"):
            ea = _attrs(ev)
            events.append({"case_id": cid, "activity": ea.get("concept:name"), "timestamp": ea.get("time:timestamp"),
                           "resource": ea.get("org:resource"), "group": ea.get("org:group"),
                           "lifecycle": ea.get("lifecycle:transition")})
    ev = pd.DataFrame(events)
    ev["timestamp"] = pd.to_datetime(ev.timestamp, utc=True, format="ISO8601")
    cs = pd.DataFrame(cases)
    for col in ("startdate", "enddate", "enddate_planned", "deadline"):
        if col in cs:
            cs[col] = pd.to_datetime(cs[col], utc=True, format="ISO8601")
    return ev.sort_values(["case_id", "timestamp"]).reset_index(drop=True), cs


def main(path: str) -> None:
    ev, cs = read_xes(path)
    ev.to_csv(DATA_DIR / "events.csv", index=False)
    cs.to_csv(DATA_DIR / "cases.csv", index=False)
    print(f"{len(cs)} cases, {len(ev)} events, {ev.activity.nunique()} activities -> data/events.csv, data/cases.csv")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(DATA_DIR / "raw" / "receipt.xes"))
