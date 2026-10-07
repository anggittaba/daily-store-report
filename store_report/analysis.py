"""KPI computation and explainable anomaly detection.

Method (deliberately simple so a store manager can follow it):
  * Baseline  = the store's own previous 7 calendar days. Days with 0 transactions
                (outages) are excluded so they don't drag the baseline down.
  * % vs 7d   = (today - baseline mean) / baseline mean
  * z-score   = (today - mean of previous 14 days) / std of previous 14 days
Rules:
  * 0 transactions                           -> critical (POS or connection probably down)
  * no row for a store that normally reports -> critical (data not received)
  * sales <= -25% vs 7d   (<= -50% critical)  -> high
  * z-score <= -3 but drop < 25%              -> medium
  * sales >= +50% vs 7d or z-score >= +3      -> medium (spike, validate)
  * stock-outs >= 2x 7d average AND +5 items  -> high
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .i18n import money_short, number, pct

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2}

ACTIONS = {
    "en": {
        "pos_offline": "Call the store manager and IT. Check the POS and the store’s connection, and confirm offline sales will sync.",
        "missing_data": "Check the daily upload from this store to the head-office server.",
        "sales_drop": "Ask the store manager about opening hours, power or till problems, empty shelves, or a new competitor nearby.",
        "below_pattern": "Watch it for one or two more days and compare it with other stores in the region.",
        "sales_spike": "Check for large single transactions or double posting. If it was a promotion or bulk order, note it.",
        "stockout_spike": "Check the delivery schedule from the distribution centre and the reorder settings. Restock the empty items first.",
    },
    "id": {
        "pos_offline": "Hubungi kepala toko dan tim IT. Cek POS dan koneksi toko, pastikan transaksi offline tersinkron.",
        "missing_data": "Cek proses upload data harian dari toko ini ke server pusat.",
        "sales_drop": "Tanyakan ke kepala toko soal jam buka, listrik atau kasir bermasalah, rak kosong, atau kompetitor baru.",
        "below_pattern": "Pantau 1–2 hari lagi dan bandingkan dengan toko lain di wilayah yang sama.",
        "sales_spike": "Cek transaksi besar atau double posting. Kalau promo atau pesanan borongan, catat sebagai referensi.",
        "stockout_spike": "Cek jadwal kirim dari DC dan parameter reorder. Isi ulang item yang kosong lebih dulu.",
    },
}


@dataclass
class Thresholds:
    baseline_days: int = 7
    z_window: int = 14
    drop_pct: float = 0.25
    critical_drop_pct: float = 0.50
    spike_pct: float = 0.50
    z_threshold: float = 3.0
    stockout_multiplier: float = 2.0
    stockout_min_delta: int = 5

    def to_dict(self) -> dict:
        return asdict(self)


def available_dates(df: pd.DataFrame) -> list[pd.Timestamp]:
    return [pd.Timestamp(d) for d in sorted(df["date"].unique())]


def store_metrics(df: pd.DataFrame, report_date, th: Thresholds | None = None) -> pd.DataFrame:
    """One row per store with the day's numbers and the store's own baseline."""
    th = th or Thresholds()
    report_date = pd.Timestamp(report_date).normalize()
    stores = df.drop_duplicates("store_code", keep="last")[["store_code", "store_name", "region"]]
    today = df[df["date"] == report_date].set_index("store_code")
    hist = df[(df["date"] < report_date) & (df["date"] >= report_date - pd.Timedelta(days=th.z_window))]
    hist_ok = hist[hist["transactions"] > 0]
    b_start = report_date - pd.Timedelta(days=th.baseline_days)
    yesterday = report_date - pd.Timedelta(days=1)

    out = []
    for _, s in stores.iterrows():
        code = s["store_code"]
        h = hist_ok[hist_ok["store_code"] == code]
        h7 = h[h["date"] >= b_start]
        row = {
            "store_code": code, "store_name": s["store_name"], "region": s["region"],
            "has_data": code in today.index,
            "reported_before": not hist[hist["store_code"] == code].empty,
        }
        if code in today.index:
            t = today.loc[code]
            row.update({"sales": float(t["sales"]), "transactions": int(t["transactions"]),
                        "avg_basket": float(t["avg_basket"]), "stockouts": int(t["stockouts"]),
                        "top_categories": t["top_categories"]})
        else:
            row.update({"sales": np.nan, "transactions": np.nan, "avg_basket": np.nan,
                        "stockouts": np.nan, "top_categories": ""})
        avg7 = h7["sales"].mean() if len(h7) else np.nan
        mean14 = h["sales"].mean() if len(h) else np.nan
        std14 = h["sales"].std(ddof=1) if len(h) >= 3 else np.nan
        y = df[(df["date"] == yesterday) & (df["store_code"] == code)]
        row.update({
            "sales_yesterday": float(y["sales"].iloc[0]) if len(y) else np.nan,
            "avg_7d": avg7,
            "transactions_avg_7d": h7["transactions"].mean() if len(h7) else np.nan,
            "stockouts_avg_7d": h7["stockouts"].mean() if len(h7) else np.nan,
            "mean_14d": mean14,
            "std_14d": std14,
        })
        p = row["sales"]
        row["vs_avg_7d"] = (p - avg7) / avg7 if avg7 and not np.isnan(avg7) and not np.isnan(p) else np.nan
        row["z_score"] = ((p - mean14) / std14
                          if std14 and not np.isnan(std14) and std14 > 0 and not np.isnan(p) else np.nan)
        out.append(row)
    return pd.DataFrame(out)


def _reason(kind: str, r, th: Thresholds, lang: str) -> str:
    L = lang
    z = r["z_score"]
    z_txt = "" if pd.isna(z) else (f"; z-score {number(z, 1, L)}")
    if kind == "missing_data":
        return ("No row for this date, although the store reported on the previous days." if L == "en" else
                "Tidak ada baris untuk tanggal ini, padahal toko rutin melapor di hari-hari sebelumnya.")
    if kind == "pos_offline":
        avg_tx = r["transactions_avg_7d"]
        if L == "en":
            extra = f" It normally records about {number(avg_tx, 0, L)} a day." if not pd.isna(avg_tx) else ""
            return f"No transactions recorded.{extra} The POS or the store’s connection is probably down."
        extra = f" Biasanya sekitar {number(avg_tx, 0, L)} transaksi per hari." if not pd.isna(avg_tx) else ""
        return f"Tidak ada transaksi tercatat.{extra} Kemungkinan POS atau koneksi toko mati."
    if kind == "sales_drop":
        if L == "en":
            return (f"Sales {money_short(r['sales'], L)}, {pct(-r['vs_avg_7d'], signed=False, lang=L)} below the "
                    f"7-day average of {money_short(r['avg_7d'], L)}{z_txt}.")
        return (f"Penjualan {money_short(r['sales'], L)}, turun {pct(-r['vs_avg_7d'], signed=False, lang=L)} dari "
                f"rata-rata 7 hari {money_short(r['avg_7d'], L)}{z_txt}.")
    if kind == "below_pattern":
        if L == "en":
            return (f"Sales {money_short(r['sales'], L)} are well below the last 14 days (z-score {number(z, 1, L)}; "
                    f"{pct(r['vs_avg_7d'], lang=L)} vs the 7-day average).")
        return (f"Penjualan {money_short(r['sales'], L)} jauh di bawah pola 14 hari terakhir (z-score {number(z, 1, L)}; "
                f"{pct(r['vs_avg_7d'], lang=L)} vs rata-rata 7 hari).")
    if kind == "sales_spike":
        if L == "en":
            return (f"Sales {money_short(r['sales'], L)}, {pct(r['vs_avg_7d'], signed=False, lang=L)} above the "
                    f"7-day average of {money_short(r['avg_7d'], L)}{z_txt}.")
        return (f"Penjualan {money_short(r['sales'], L)}, naik {pct(r['vs_avg_7d'], signed=False, lang=L)} dari "
                f"rata-rata 7 hari {money_short(r['avg_7d'], L)}{z_txt}.")
    if kind == "stockout_spike":
        so, avg = r["stockouts"], r["stockouts_avg_7d"]
        ratio = number(so / max(avg, 0.1), 1, L)
        if L == "en":
            return f"{number(so, 0, L)} items out of stock, {ratio}× the 7-day average of {number(avg, 1, L)}."
        return f"{number(so, 0, L)} item stock-out, {ratio}× rata-rata 7 hari ({number(avg, 1, L)})."
    raise ValueError(kind)


def detect_anomalies(metrics: pd.DataFrame, th: Thresholds | None = None, lang: str = "en") -> pd.DataFrame:
    """One row per finding: severity, kind, reason and next step (in `lang`)."""
    th = th or Thresholds()
    findings = []

    def add(r, severity, kind):
        findings.append({
            "store_code": r["store_code"], "store_name": r["store_name"], "region": r["region"],
            "severity": severity, "kind": kind, "reason": _reason(kind, r, th, lang),
            "action": ACTIONS[lang][kind], "sales": r["sales"], "avg_7d": r["avg_7d"],
            "vs_avg_7d": r["vs_avg_7d"], "z_score": r["z_score"], "stockouts": r["stockouts"],
        })

    for _, r in metrics.iterrows():
        if not r["has_data"]:
            if r["reported_before"]:
                add(r, "critical", "missing_data")
            continue
        p, z = r["vs_avg_7d"], r["z_score"]
        if r["transactions"] == 0:
            add(r, "critical", "pos_offline")
        else:
            if not pd.isna(p) and p <= -th.drop_pct:
                add(r, "critical" if p <= -th.critical_drop_pct else "high", "sales_drop")
            elif not pd.isna(z) and z <= -th.z_threshold:
                add(r, "medium", "below_pattern")
            if (not pd.isna(p) and p >= th.spike_pct) or (not pd.isna(z) and z >= th.z_threshold):
                add(r, "medium", "sales_spike")
        so, so_avg = r["stockouts"], r["stockouts_avg_7d"]
        if (not pd.isna(so_avg) and so >= th.stockout_multiplier * max(so_avg, 1)
                and so - so_avg >= th.stockout_min_delta):
            add(r, "high", "stockout_spike")

    cols = ["store_code", "store_name", "region", "severity", "kind", "reason", "action",
            "sales", "avg_7d", "vs_avg_7d", "z_score", "stockouts"]
    res = pd.DataFrame(findings, columns=cols)
    if not res.empty:
        res["_o"] = res["severity"].map(SEVERITY_ORDER)
        res = res.sort_values(["_o", "store_code"]).drop(columns="_o").reset_index(drop=True)
    return res


def stores_needing_attention(anomalies: pd.DataFrame) -> list[dict]:
    """Group findings per store: most severe first, all reasons kept."""
    if anomalies.empty:
        return []
    groups = []
    for code, g in anomalies.groupby("store_code", sort=False):
        top = g.iloc[g["severity"].map(SEVERITY_ORDER).argmin()]
        groups.append({
            "store_code": code, "store_name": top["store_name"], "region": top["region"],
            "severity": top["severity"], "reasons": g["reason"].tolist(),
            "actions": list(dict.fromkeys(g["action"].tolist())), "kinds": g["kind"].tolist(),
        })
    groups.sort(key=lambda x: (SEVERITY_ORDER[x["severity"]], x["store_code"]))
    return groups


def region_summary(metrics: pd.DataFrame) -> pd.DataFrame:
    m = metrics.copy()
    m["sales"] = m["sales"].fillna(0)
    g = m.groupby("region").agg(
        stores=("store_code", "count"), sales=("sales", "sum"), transactions=("transactions", "sum"),
        stockouts=("stockouts", "sum"), avg_7d=("avg_7d", "sum"),
    ).reset_index()
    total = g["sales"].sum()
    g["share"] = g["sales"] / total if total else 0
    g["vs_avg_7d"] = (g["sales"] - g["avg_7d"]) / g["avg_7d"]
    return g.sort_values("sales", ascending=False).reset_index(drop=True)


def overall_kpis(df: pd.DataFrame, metrics: pd.DataFrame, report_date, th: Thresholds | None = None) -> dict:
    th = th or Thresholds()
    report_date = pd.Timestamp(report_date).normalize()
    daily = df.groupby("date").agg(sales=("sales", "sum"), transactions=("transactions", "sum"),
                                   stockouts=("stockouts", "sum"))
    today = daily.loc[report_date] if report_date in daily.index else None
    prev = daily[(daily.index < report_date) & (daily.index >= report_date - pd.Timedelta(days=th.baseline_days))]

    def at(day, col):
        return float(daily.loc[day, col]) if day in daily.index else np.nan

    yesterday, last_week = report_date - pd.Timedelta(days=1), report_date - pd.Timedelta(days=7)
    sales = float(today["sales"]) if today is not None else 0.0
    tx = int(today["transactions"]) if today is not None else 0
    avg7 = float(prev["sales"].mean()) if len(prev) else np.nan
    y_sales, y_tx, lw_sales = at(yesterday, "sales"), at(yesterday, "transactions"), at(last_week, "sales")

    m = metrics[metrics["has_data"]]
    active = m[m["transactions"] > 0]
    cats = Counter()
    for s in active["top_categories"]:
        for i, c in enumerate([x.strip() for x in str(s).split(",") if x.strip()]):
            cats[c] += 3 - i  # weight: 1st=3, 2nd=2, 3rd=1
    best = active.loc[active["sales"].idxmax()] if len(active) else None
    region = region_summary(metrics)
    top_region = region.iloc[0] if len(region) else None

    def rel(a, b):
        return (a - b) / b if b and not np.isnan(b) else np.nan

    return {
        "date": report_date,
        "sales": sales, "transactions": tx, "avg_basket": sales / tx if tx else 0.0,
        "stockouts": int(today["stockouts"]) if today is not None else 0,
        "stores": int(len(metrics)), "stores_reporting": int(len(m)), "stores_trading": int(len(active)),
        "sales_yesterday": y_sales, "vs_yesterday": rel(sales, y_sales),
        "transactions_yesterday": y_tx, "transactions_vs_yesterday": rel(tx, y_tx),
        "sales_last_week": lw_sales, "vs_last_week": rel(sales, lw_sales),
        "avg_7d": avg7, "vs_avg_7d": rel(sales, avg7),
        "stockouts_avg_7d": float(prev["stockouts"].mean()) if len(prev) else np.nan,
        "top_store": None if best is None else {"name": best["store_name"], "sales": float(best["sales"])},
        "top_region": None if top_region is None else {
            "name": top_region["region"], "sales": float(top_region["sales"]), "share": float(top_region["share"])},
        "top_categories": [c for c, _ in cats.most_common(3)],
    }
