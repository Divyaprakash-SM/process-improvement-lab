"""Load any event log: an XES file, or a CSV with one row per event.

A CSV needs three columns (names are matched loosely, case-insensitive):
  case id    e.g. case_id, case, case:concept:name, order id, ticket
  activity   e.g. activity, concept:name, event, step, status
  timestamp  e.g. timestamp, time:timestamp, date, time, completed at
Optional: resource (resource, org:resource, user, owner).
Case-level columns are picked up if present: start date, deadline, channel.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd

from .xes import read_xes

ALIASES = {
    "case_id": ["case_id", "case id", "case", "case:concept:name", "caseid", "order id", "ticket", "ticket id", "id"],
    "activity": ["activity", "concept:name", "event", "step", "status", "activity name", "task"],
    "timestamp": ["timestamp", "time:timestamp", "date", "time", "datetime", "completed at", "end time", "complete timestamp"],
    "resource": ["resource", "org:resource", "user", "owner", "agent", "assignee"],
    "startdate": ["startdate", "start date", "case start", "submitted", "created"],
    "deadline": ["deadline", "due date", "sla date", "target date"],
    "channel": ["channel", "source", "origin"],
}


def _match(columns) -> dict:
    low = {c.strip().lower(): c for c in columns}
    out = {}
    for std, names in ALIASES.items():
        for n in names:
            if n in low and low[n] not in out.values():
                out[std] = low[n]
                break
    return out


def read_csv_log(data: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(io.BytesIO(data))
    m = _match(raw.columns)
    missing = [k for k in ("case_id", "activity", "timestamp") if k not in m]
    if missing:
        raise ValueError(f"The CSV needs columns for {', '.join(missing)}. Found: {', '.join(map(str, raw.columns))}")
    ev = pd.DataFrame({"case_id": raw[m["case_id"]].astype(str), "activity": raw[m["activity"]].astype(str),
                       "timestamp": pd.to_datetime(raw[m["timestamp"]], utc=True, errors="coerce", format="mixed"),
                       "resource": raw[m["resource"]].astype(str) if "resource" in m else "n/a"})
    bad = ev.timestamp.isna().sum()
    ev = ev.dropna(subset=["timestamp"]).sort_values(["case_id", "timestamp"]).reset_index(drop=True)
    if ev.empty:
        raise ValueError("No rows had a readable timestamp.")
    case_cols = {k: m[k] for k in ("startdate", "deadline", "channel") if k in m}
    cs = raw.assign(case_id=raw[m["case_id"]].astype(str)).groupby("case_id").first()[list(case_cols.values())]
    cs = cs.rename(columns={v: k for k, v in case_cols.items()}).reset_index()
    for c in ("startdate", "deadline"):
        if c in cs:
            cs[c] = pd.to_datetime(cs[c], utc=True, errors="coerce", format="mixed")
    ev.attrs["dropped_rows"] = int(bad)
    return ev, cs


def read_any(data: bytes, name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if name.lower().endswith(".xes"):
        tmp = Path(tempfile.mkdtemp()) / "log.xes"
        tmp.write_bytes(data)
        return read_xes(tmp)
    return read_csv_log(data)
