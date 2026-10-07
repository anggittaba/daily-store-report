"""End-to-end daily report: data -> KPIs -> flags -> summary -> HTML.

The same view model feeds the standalone HTML report and the web app, so the
two always show the same numbers.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import __version__
from .analysis import (Thresholds, available_dates, detect_anomalies, overall_kpis, region_summary,
                       store_metrics, stores_needing_attention)
from .charts import region_chart, store_chart, trend_chart
from .i18n import date_long, money, money_short, norm_lang, number, pct, severity_label, t, weekday
from .summary import build_context, generate_summary

TEMPLATES = Path(__file__).parent / "templates"


@dataclass
class DailyReport:
    date: pd.Timestamp
    lang: str
    metrics: pd.DataFrame
    anomalies: pd.DataFrame
    attention: list[dict]
    kpis: dict
    region: pd.DataFrame
    summary: str
    summary_source: str
    thresholds: Thresholds
    source_name: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def severity_by_store(self) -> dict[str, str]:
        return {a["store_code"]: a["severity"] for a in self.attention}


def build_report(df: pd.DataFrame, report_date=None, thresholds: Thresholds | None = None,
                 use_llm: bool = True, source_name: str = "", lang: str | None = None) -> DailyReport:
    lang = norm_lang(lang)
    th = thresholds or Thresholds()
    report_date = pd.Timestamp(report_date if report_date is not None else available_dates(df)[-1]).normalize()
    metrics = store_metrics(df, report_date, th)
    anomalies = detect_anomalies(metrics, th, lang)
    attention = stores_needing_attention(anomalies)
    kpis = overall_kpis(df, metrics, report_date, th)
    region = region_summary(metrics)
    summary, source = generate_summary(build_context(kpis, attention, region, lang), use_llm=use_llm)
    return DailyReport(report_date, lang, metrics, anomalies, attention, kpis, region, summary, source, th, source_name)


_BULLET = re.compile(r"^\s*[-*•] ")


def _strip_bullet(line: str) -> str:
    return _BULLET.sub("", line)


def text_to_html(text: str) -> str:
    """Tiny, safe markdown subset -> HTML: paragraphs, '- ' bullets, **bold**. Input is escaped first."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        esc = [re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(ln, quote=False)) for ln in lines]
        bullets = [ln for ln in esc if _BULLET.match(ln)]
        head = [ln for ln in esc if not _BULLET.match(ln)]
        if head:
            out.append("<p>" + "<br>".join(head) + "</p>")
        if bullets:
            out.append("<ul>" + "".join(f"<li>{_strip_bullet(ln)}</li>" for ln in bullets) + "</ul>")
    return "\n".join(out)


def _trend(v) -> str:
    if v is None or v != v or abs(v) < 0.0005:
        return "flat"
    return "up" if v > 0 else "down"


def view_model(df: pd.DataFrame, rep: DailyReport) -> dict:
    """Everything the templates need, already formatted for rep.lang."""
    L, k, th = rep.lang, rep.kpis, rep.thresholds
    sev = rep.severity_by_store
    n_att = len(rep.attention)
    n_st = k["stores_reporting"]
    lede = [t("lede_att_1", L, n=n_st) if n_att == 1 else
            t("lede_att", L, a=n_att, n=n_st) if n_att else t("lede_none", L, n=n_st)]
    if k["vs_avg_7d"] == k["vs_avg_7d"]:
        lede.append(t("lede_below" if k["vs_avg_7d"] < 0 else "lede_above", L,
                      p=pct(abs(k["vs_avg_7d"]), signed=False, lang=L)))
    so_delta = k["stockouts"] - k["stockouts_avg_7d"] if k["stockouts_avg_7d"] == k["stockouts_avg_7d"] else float("nan")
    kpis = [
        {"label": t("kpi_sales", L), "value": money_short(k["sales"], L), "lead": True,
         "notes": [(t("vs_7d", L, v=pct(k["vs_avg_7d"], lang=L)), _trend(k["vs_avg_7d"])),
                   (t("vs_last_week", L, v=pct(k["vs_last_week"], lang=L), day=weekday(k["date"], L)), _trend(k["vs_last_week"]))]},
        {"label": t("kpi_transactions", L), "value": number(k["transactions"], 0, L),
         "notes": [(t("vs_yesterday", L, v=pct(k["transactions_vs_yesterday"], lang=L)), _trend(k["transactions_vs_yesterday"]))]},
        {"label": t("kpi_basket", L), "value": money(k["avg_basket"], L), "notes": [(t("per_tx", L), "flat")]},
        {"label": t("kpi_stockouts", L), "value": number(k["stockouts"], 0, L),
         "notes": [(t("vs_7d", L, v=("+" if so_delta > 0 else "") + number(so_delta, 1, L)),
                    {"up": "down", "down": "up"}.get(_trend(so_delta), "flat"))]},
        {"label": t("kpi_attention", L), "value": str(n_att), "notes": [(t("of_stores", L, n=k["stores"]), "flat"),
                                                                        (t("stores_trading", L, n=k["stores_trading"]), "flat")]},
    ]
    attention = [{**a, "severity_label": severity_label(a["severity"], L)} for a in rep.attention]
    stores = []
    for _, s in rep.metrics.sort_values("store_code").iterrows():
        code = s["store_code"]
        stores.append({
            "name": s["store_name"], "code": code, "region": s["region"],
            "sales": money(s["sales"], L), "avg_7d": money(s["avg_7d"], L),
            "vs_7d": pct(s["vs_avg_7d"], lang=L), "vs_7d_trend": _trend(s["vs_avg_7d"]),
            "z": number(s["z_score"], 1, L), "tx": number(s["transactions"], 0, L),
            "basket": money(s["avg_basket"], L), "stockouts": number(s["stockouts"], 0, L),
            "severity": sev.get(code), "severity_label": severity_label(sev[code], L) if code in sev else t("status_normal", L),
        })
    regions = [{"name": r["region"], "stores": int(r["stores"]), "sales": money(r["sales"], L),
                "share": pct(r["share"], signed=False, decimals=0, lang=L), "vs_7d": pct(r["vs_avg_7d"], lang=L),
                "vs_7d_trend": _trend(r["vs_avg_7d"]), "tx": number(r["transactions"], 0, L),
                "stockouts": number(r["stockouts"], 0, L)} for _, r in rep.region.iterrows()]
    d, c, s_, z, m, kk = (round(th.drop_pct * 100), round(th.critical_drop_pct * 100), round(th.spike_pct * 100),
                          number(th.z_threshold, 1, L), number(th.stockout_multiplier, 0, L), th.stockout_min_delta)
    rules = [
        (t("rule_zero_tx", L), "critical"), (t("rule_missing", L), "critical"),
        (t("rule_drop", L, d=d, c=c), "high"), (t("rule_below", L, z=z, d=d), "medium"),
        (t("rule_spike", L, s=s_, z=z), "medium"), (t("rule_stockout", L, m=m, k=kk), "high"),
    ]
    no_sales = "no sales" if L == "en" else "tanpa penjualan"
    return {
        "lang": L, "t": lambda key, **kw: t(key, L, **kw),
        "date_long": date_long(rep.date, L), "date_iso": rep.date.strftime("%Y-%m-%d"),
        "lede": " ".join(lede), "kpis": kpis, "attention": attention,
        "summary_html": text_to_html(rep.summary), "summary_source": rep.summary_source,
        "chart_trend": trend_chart(df, rep.date, t("trend", L), L),
        "chart_stores": store_chart(rep.metrics, sev, t("sales_vs_baseline", L), no_sales, L),
        "chart_regions": region_chart(rep.region, t("regions", L), L),
        "stores": stores, "regions": regions,
        "sev_labels": {c: severity_label(c, L) for c in ("critical", "high", "medium")},
        "rules": [{"text": r, "severity": s, "severity_label": severity_label(s, L)} for r, s in rules],
        "method_intro": t("method_intro", L, b=th.baseline_days, z=th.z_window),
        "version": __version__, "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))


def stylesheet() -> str:
    return (TEMPLATES / "tokens.css").read_text(encoding="utf-8") + "\n" + (TEMPLATES / "styles.css").read_text(encoding="utf-8")


def render_html(df: pd.DataFrame, rep: DailyReport) -> str:
    """Standalone, self-contained HTML report (CSS and charts inline)."""
    return _env().get_template("report.html.j2").render(vm=view_model(df, rep), css=stylesheet())


def flags_csv(rep: DailyReport) -> str:
    """Flags table as CSV, numbers rounded for people rather than machines."""
    out = rep.anomalies.copy()
    for col, nd in (("sales", 0), ("avg_7d", 0), ("vs_avg_7d", 4), ("z_score", 2)):
        if col in out:
            out[col] = out[col].round(nd)
    return out.to_csv(index=False)


def save_report(df: pd.DataFrame, rep: DailyReport, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d = rep.date.strftime("%Y-%m-%d")
    suffix = "" if rep.lang == "en" else f"_{rep.lang}"
    html_path = out / f"daily_report_{d}{suffix}.html"
    html_path.write_text(render_html(df, rep), encoding="utf-8")
    flags_path = out / f"flags_{d}{suffix}.csv"
    flags_path.write_text(flags_csv(rep), encoding="utf-8")
    summary_path = out / f"summary_{d}{suffix}.md"
    summary_path.write_text(f"# {date_long(rep.date, rep.lang)}\n\n{rep.summary}\n\n"
                            f"_{t('summary_source', rep.lang, src=rep.summary_source)}_\n", encoding="utf-8")
    return {"html": html_path, "flags": flags_path, "summary": summary_path}
