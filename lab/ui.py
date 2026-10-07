"""Shared Streamlit helpers: theme, chart styling and cached data."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from .mining import cases, load

BLUE, BLUE_LIGHT, ORANGE, AQUA, GREY = "#2a78d6", "#b7d3f6", "#eb6834", "#1baf7a", "#9a9993"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
STATUS = {"Conforms: standard path": "#0ca30c", "Conforms: exception path": "#7cc47c",
          "Closed after intake": GREY, "Deviates: rework": "#d03b3b", "Deviates: incomplete": "#ec835a",
          "Deviates: skipped check (T02)": "#fab219", "Deviates: out of order": "#fab219",
          "Deviates: wrong start": "#d03b3b"}

CSS = """
<style>
  .block-container {padding-top: 2rem; max-width: 1400px;}
  [data-testid="stMetricValue"] {font-size: 1.7rem; font-weight: 650;}
  [data-testid="stMetricLabel"] p {font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #52514e;}
  .note {font-size:.92rem; color:#52514e;}
  .rec {border-left: 4px solid #1c5cab; background:#f3f2ee; padding: 14px 18px; border-radius: 6px; margin: 4px 0 18px;}
  .finding {border:1px solid #e6e5e0; border-radius:8px; padding:14px 16px; height:100%; background:#ffffff;}
  .finding h4 {margin:0 0 6px 0; font-size:1rem;}
  .finding p {margin:0; font-size:.9rem; color:#2b2b2a;}
  h1 {font-weight: 700; letter-spacing: -.02em;}
</style>
"""


def style(fig: go.Figure, height: int = 360, **kw) -> go.Figure:
    top = 40
    if "title" in kw:
        kw["title"] = {**kw["title"], "x": 0.01, "xanchor": "left", "y": 0.985, "yanchor": "top"}
        top = 78
    fig.update_layout(template="plotly_white", height=height, margin=dict(l=10, r=10, t=top, b=10),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=13, color=INK),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      hoverlabel=dict(bgcolor="white", font_size=12), **kw)
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED))
    return fig


@st.cache_data
def data():
    ev, cs = load()
    return ev, cases(ev, cs)
