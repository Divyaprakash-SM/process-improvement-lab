"""Headline findings, written from the data (no hard-coded numbers)."""

from __future__ import annotations

import pandas as pd

from .mining import bottlenecks, channels, kpis, rework, variants, workload


def dur(days: float) -> str:
    """0.03 -> '45 min', 0.4 -> '9.6 hours', 3.2 -> '3.2 days'."""
    if days < 1 / 24:
        return f"{days * 1440:.0f} min"
    if days < 1:
        return f"{days * 24:.1f} hours"
    return f"{days:.1f} days"


def findings(ev: pd.DataFrame, ct: pd.DataFrame) -> list[tuple[str, str]]:
    k = kpis(ct, ev)
    v = variants(ct)
    b = bottlenecks(ev, top=3)
    rw, ri = rework(ev, ct)
    ch = channels(ct)
    w = workload(ev)
    out = []

    if k["has_intake"]:
        intake_share = ct.intake_queue_days.sum() / ct.lead_days.sum()
        out.append(("Work waits before it is touched",
                    f"Median lead time is **{k['lead_median']:.0f} days**, but the recorded work itself takes a median of "
                    f"**{k['processing_median'] * 24:.1f} hours**. {intake_share:.0%} of all lead time passes before the first "
                    f"step is logged. The biggest gain is in the intake queue, not in working faster."))
    else:
        tail = ct.processing_days.quantile(0.9) / max(ct.processing_days.median(), 1e-9)
        out.append(("The slow tail is the problem",
                    f"The median case takes **{dur(k['processing_median'])}** end to end, but the slowest 10% take "
                    f"over **{dur(ct.processing_days.quantile(0.9))}**{f', {tail:.0f}× longer' if tail < 1e6 else ''}. "
                    "Customers remember the tail, so look at what those cases have in common."))

    n80 = int((v.cumulative_share < 0.8).sum()) + 1
    out.append(("Many variants, one real process",
                f"{k['variants']} different paths look chaotic, but the top {n80} cover 80% of cases"
                + (", and most of those are the same steps done in a different order across two parallel tracks"
                   if k["reference_model"] else "") +
                f". **{k['conform_share']:.0%} of cases conform** to the "
                + ("intended process." if k["reference_model"] else "most common ('happy') path or the same steps in another order.")))

    top = b.iloc[0]
    out.append((f"One handoff holds {top.share_of_wait:.0%} of the waiting",
                f"**{top.source} → {top.target}** happens {int(top['count']):,} times with a mean wait of {top.mean_wait:.1f} days, "
                f"which is **{top.share_of_wait:.0%} of all in-process waiting**. Fixing this single handoff beats "
                f"optimising every other step."))

    if ri["cases"]:
        deadline = (f" and are **{ri['late_with'] / max(ri['late_without'], 1e-9):.1f}× as likely to miss the deadline**"
                    if k["has_deadlines"] and ri["late_without"] > 0 else "")
        out.append(("Rework slows cases down",
                    f"**{ri['share']:.0%} of cases** loop back. They take a median {dur(ri['lead_with'])} vs "
                    f"{dur(ri['lead_without'])}{deadline}. Most-repeated step: {rw.iloc[0].activity}."))

    web = ch[ch.channel == "Internet"]
    slow = ch[(ch.channel != "Internet") & (ch.cases >= 20)].sort_values("lead_median", ascending=False)
    if k["has_channels"] and not web.empty and not slow.empty:
        s = slow.iloc[0]
        out.append(("Paper channels are slower",
                    f"Online applications ({web.cases.iloc[0]:,} cases) take a median {web.lead_median.iloc[0]:.0f} days; "
                    f"{s.channel} takes {s.lead_median:.0f}. Moving the remaining "
                    f"{int(ch[ch.channel != 'Internet'].cases.sum())} non-digital cases online is a cheap win."))

    n_half = int((w.cumulative_share < 0.5).sum()) + 1
    if len(w) > 3:
        out.append(("Key-person risk",
                    f"**{n_half} of {len(w)} people** handle half of all steps, and the busiest person alone does "
                    f"{w.iloc[0].share:.0%}. If they are off, the process slows down. This is a resilience risk as well as a capacity one."))

    if k["reference_model"]:
        out.append(("Some cases never progress",
                    f"**{k['intake_only_share']:.0%} of applications** were closed after the receipt step alone. "
                    "It's worth checking whether these are withdrawn, duplicates or incomplete submissions that "
                    "better validation at the point of entry could prevent."))
    return out
