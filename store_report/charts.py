"""Charts as inline SVG.

Every colour and font comes from CSS classes defined in templates/styles.css,
which read the design tokens. No colour values live in this file, so the
charts follow the theme in both the web app and the standalone report.
"""

from __future__ import annotations

import math
from html import escape

import pandas as pd

from .i18n import date_short, money_short, number


def _axis_money(v: float, lang: str) -> str:
    s = money_short(v, lang)
    return s.replace(".0M", "M").replace(",0\u00a0juta", "\u00a0juta")


def _nice_max(v: float, ticks: int = 5) -> tuple[float, float]:
    if v <= 0:
        return 1.0, 0.25
    raw = v / ticks
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return step * math.ceil(v / step), step


def _text_w(texts, size: float) -> int:
    """Rough width of the widest label in px (IBM Plex Sans averages ~0.56 em per glyph)."""
    return int(max((len(x) for x in texts), default=0) * size * 0.56) + 1


def _svg(w: int, h: int, title: str, body: str, cls: str) -> str:
    return (f'<svg class="chart {cls}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}" preserveAspectRatio="xMinYMin meet" '
            f'xmlns="http://www.w3.org/2000/svg"><title>{escape(title)}</title>{body}</svg>')


def trend_chart(df: pd.DataFrame, report_date, title: str, lang: str = "en", days: int = 30) -> str:
    report_date = pd.Timestamp(report_date)
    daily = df.groupby("date")["sales"].sum()
    ma7 = daily.rolling(7, min_periods=3).mean()
    d = daily[(daily.index > report_date - pd.Timedelta(days=days)) & (daily.index <= report_date)]
    m = ma7.loc[d.index]
    W, H, l, r, t, b = 720, 250, 70, 8, 10, 30
    pw, ph = W - l - r, H - t - b
    ymax, step = _nice_max(max(d.max(), m.max() if len(m) else 0))
    n = max(len(d), 1)
    slot = pw / n
    bw = slot * 0.68
    y = lambda v: t + ph - (v / ymax) * ph  # noqa: E731
    out = []
    v = 0.0
    while v <= ymax + 1e-6:
        yy = y(v)
        out.append(f'<line class="chart-grid" x1="{l}" x2="{W - r}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        out.append(f'<text class="chart-axis" x="{l - 8}" y="{yy + 4:.1f}" text-anchor="end">{escape(_axis_money(v, lang))}</text>')
        v += step
    for i, (day, val) in enumerate(d.items()):
        x = l + i * slot + (slot - bw) / 2
        cls = "bar bar--current" if day == report_date else "bar"
        out.append(f'<rect class="{cls}" x="{x:.1f}" y="{y(val):.1f}" width="{bw:.1f}" height="{t + ph - y(val):.1f}">'
                   f'<title>{escape(date_short(day, lang))}: {escape(money_short(val, lang))}</title></rect>')
        if i % 5 == (n - 1) % 5:
            out.append(f'<text class="chart-axis" x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle">'
                       f'{escape(date_short(day, lang))}</text>')
    pts = " ".join(f"{l + i * slot + slot / 2:.1f},{y(val):.1f}" for i, val in enumerate(m.values) if val == val)
    out.append(f'<polyline class="line-ma" points="{pts}"/>')
    return _svg(W, H, title, "".join(out), "chart--trend")


def store_chart(metrics: pd.DataFrame, severity: dict[str, str], title: str, no_sales: str,
                lang: str = "en") -> str:
    m = metrics.copy()
    m["sales"] = m["sales"].fillna(0)
    m = m.sort_values("sales", ascending=False)
    vals = [money_short(v, lang) if v > 0 else no_sales for v in m["sales"]]
    row, W, label_w, t = 22, 470, 158, 4
    value_w = _text_w(vals, 12) + 10
    H = t + row * len(m) + 4
    x0, x1 = label_w, W - value_w
    vmax = max(m["sales"].max(), m["avg_7d"].max(), 1)
    sx = lambda v: x0 + (v / vmax) * (x1 - x0)  # noqa: E731
    out = []
    for i, (_, s) in enumerate(m.iterrows()):
        yy = t + i * row
        sev = severity.get(s["store_code"])
        cls = f"bar bar--{sev}" if sev else "bar"
        out.append(f'<text class="chart-label" x="{label_w - 10}" y="{yy + row / 2 + 4:.1f}" text-anchor="end">'
                   f'{escape(s["store_name"])}</text>')
        if s["sales"] > 0:
            out.append(f'<rect class="{cls}" x="{x0}" y="{yy + 5}" width="{sx(s["sales"]) - x0:.1f}" height="{row - 9}"/>')
        val = vals[i]
        if s["avg_7d"] == s["avg_7d"]:
            bx = sx(s["avg_7d"])
            out.append(f'<line class="tick-baseline" x1="{bx:.1f}" x2="{bx:.1f}" y1="{yy + 2}" y2="{yy + row - 2}"/>')
        vcls = "chart-value chart-value--flag" if sev else "chart-value"
        out.append(f'<text class="{vcls}" x="{W - 2}" y="{yy + row / 2 + 4:.1f}" text-anchor="end">{escape(val)}</text>')
    return _svg(W, H, title, "".join(out), "chart--stores")


def region_chart(region: pd.DataFrame, title: str, lang: str = "en") -> str:
    vals = [f'{money_short(r["sales"], lang)} · {number(r["share"] * 100, 0, lang)}%' for _, r in region.iterrows()]
    row, W, label_w, t = 32, 380, 110, 4
    value_w = _text_w(vals, 12) + 10
    H = t + row * len(region) + 4
    x0, x1 = label_w, W - value_w
    vmax = max(region["sales"].max(), 1)
    out = []
    for i, (_, r) in enumerate(region.iterrows()):
        yy = t + i * row
        w = (r["sales"] / vmax) * (x1 - x0)
        out.append(f'<text class="chart-label" x="{label_w - 10}" y="{yy + row / 2 + 4:.1f}" text-anchor="end">{escape(r["region"])}</text>')
        out.append(f'<rect class="bar" x="{x0}" y="{yy + 8}" width="{w:.1f}" height="{row - 16}"/>')
        out.append(f'<text class="chart-value" x="{W - 2}" y="{yy + row / 2 + 4:.1f}" text-anchor="end">'
                   f'{escape(vals[i])}</text>')
    return _svg(W, H, title, "".join(out), "chart--regions")
