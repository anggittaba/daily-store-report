"""Synthetic daily sales data generator for a fictional minimarket chain.

Everything here is made up: store names use generic "Store NNN <town>" labels,
numbers are random but shaped to look realistic (weekly pattern, payday effect,
noise, per-store size). A few anomalies are injected on purpose so the report
pipeline has something to detect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

STORES = [
    ("ST001", "Store 001 Rangkasbitung", "Banten"),
    ("ST002", "Store 002 Serang", "Banten"),
    ("ST003", "Store 003 Cilegon", "Banten"),
    ("ST004", "Store 004 Pandeglang", "Banten"),
    ("ST005", "Store 005 Tangerang", "Greater Jakarta"),
    ("ST006", "Store 006 Bekasi", "Greater Jakarta"),
    ("ST007", "Store 007 Depok", "Greater Jakarta"),
    ("ST008", "Store 008 Bogor", "Greater Jakarta"),
    ("ST009", "Store 009 Cibinong", "Greater Jakarta"),
    ("ST010", "Store 010 Ciputat", "Greater Jakarta"),
    ("ST011", "Store 011 Bandung", "West Java"),
    ("ST012", "Store 012 Cimahi", "West Java"),
    ("ST013", "Store 013 Sukabumi", "West Java"),
    ("ST014", "Store 014 Cianjur", "West Java"),
    ("ST015", "Store 015 Garut", "West Java"),
    ("ST016", "Store 016 Semarang", "Central Java"),
    ("ST017", "Store 017 Solo", "Central Java"),
    ("ST018", "Store 018 Magelang", "Central Java"),
    ("ST019", "Store 019 Tegal", "Central Java"),
    ("ST020", "Store 020 Purwokerto", "Central Java"),
]

CATEGORIES = {
    "Beverages": 0.17,
    "Snacks": 0.15,
    "Staples": 0.14,
    "Tobacco": 0.12,
    "Instant noodles": 0.09,
    "Dairy": 0.08,
    "Personal care": 0.07,
    "Household": 0.07,
    "Bakery": 0.06,
    "Frozen food": 0.05,
}

# Monday=0 ... Sunday=6
DOW_FACTOR = {0: 0.97, 1: 0.95, 2: 0.96, 3: 0.98, 4: 1.05, 5: 1.18, 6: 1.14}

COLUMNS = [
    "date", "store_code", "store_name", "region", "sales",
    "transactions", "avg_basket", "top_categories", "stockouts",
]


@dataclass
class InjectedAnomaly:
    date: date
    store_code: str
    kind: str
    description: str


def _store_list(n_stores: int) -> list[tuple[str, str, str]]:
    stores = list(STORES[:n_stores])
    regions = ["Banten", "Greater Jakarta", "West Java", "Central Java"]
    for i in range(len(stores) + 1, n_stores + 1):
        stores.append((f"ST{i:03d}", f"Store {i:03d} Branch {i}", regions[i % 4]))
    return stores


def _anomaly_plan(n_days: int) -> list[tuple[int, str, str, str]]:
    """(day_index, store_code, kind, description). day_index -1 = last day."""
    plan = [
        (-1, "ST007", "sales_drop", "Sales cut to ~50% (simulated operational problem)"),
        (-1, "ST013", "pos_offline", "POS offline all day, zero transactions recorded"),
        (-1, "ST018", "stockout_spike", "Stock-out spike (simulated late delivery from the distribution centre)"),
        (-1, "ST011", "sales_spike", "Sales up ~65% (simulated bulk order)"),
    ]
    if n_days >= 22:
        plan.append((-21, "ST004", "pos_offline", "POS offline all day (historical)"))
    if n_days >= 16:
        plan.append((-15, "ST016", "sales_drop", "Sales cut to ~60% (historical, simulated power cut)"))
    if n_days >= 37:
        for k in (-36, -35, -34):
            plan.append((k, "ST010", "stockout_spike", "High stock-outs three days in a row (historical)"))
    return plan


def generate_sales_data(
    n_stores: int = 20,
    n_days: int = 60,
    end_date: date | str | None = None,
    seed: int = 42,
    inject_anomalies: bool = True,
) -> tuple[pd.DataFrame, list[InjectedAnomaly]]:
    """Return (sales dataframe, list of injected anomalies)."""
    if end_date is None:
        end_date = date.today() - timedelta(days=1)
    end_ts = pd.Timestamp(end_date).normalize()
    dates = pd.date_range(end=end_ts, periods=n_days, freq="D")
    rng = np.random.default_rng(seed)
    stores = _store_list(n_stores)
    cat_names = list(CATEGORIES)
    cat_base = np.array(list(CATEGORIES.values()))

    rows = []
    for code, name, region in stores:
        base_sales = rng.uniform(9e6, 24e6)
        base_basket = rng.uniform(42_000, 78_000)
        stock_lambda = rng.uniform(1.2, 3.5)
        trend = rng.normal(0, 0.0012)
        prefs = rng.dirichlet(cat_base * 60)
        for i, d in enumerate(dates):
            factor = DOW_FACTOR[d.weekday()]
            if d.day >= 25 or d.day <= 2:  # payday effect
                factor *= 1.07
            noise = rng.lognormal(0, 0.055)
            sales = base_sales * factor * (1 + trend * i) * noise
            basket = base_basket * rng.normal(1, 0.035) * (1.04 if d.weekday() >= 5 else 1.0)
            tx = max(1, int(round(sales / basket)))
            sales = round(sales / 100) * 100
            daily_pref = prefs * rng.lognormal(0, 0.15, len(prefs))
            top3 = [cat_names[j] for j in np.argsort(daily_pref)[::-1][:3]]
            rows.append({
                "date": d,
                "store_code": code,
                "store_name": name,
                "region": region,
                "sales": float(sales),
                "transactions": tx,
                "avg_basket": 0.0,
                "top_categories": ", ".join(top3),
                "stockouts": int(rng.poisson(stock_lambda)),
            })

    df = pd.DataFrame(rows)
    injected: list[InjectedAnomaly] = []
    if inject_anomalies:
        for day_idx, code, kind, desc in _anomaly_plan(n_days):
            if code not in df["store_code"].values:
                continue
            d = dates[day_idx]
            m = (df["date"] == d) & (df["store_code"] == code)
            if kind == "sales_drop":
                f = 0.50 if day_idx == -1 else 0.60
                df.loc[m, "sales"] = (df.loc[m, "sales"] * f).round(-2)
                df.loc[m, "transactions"] = (df.loc[m, "transactions"] * (f + 0.05)).round().astype(int)
            elif kind == "pos_offline":
                df.loc[m, ["sales", "transactions"]] = 0
                df.loc[m, "top_categories"] = ""
            elif kind == "stockout_spike":
                df.loc[m, "stockouts"] = int(rng.integers(19, 27))
                df.loc[m, "sales"] = (df.loc[m, "sales"] * 0.88).round(-2)
                df.loc[m, "transactions"] = (df.loc[m, "transactions"] * 0.9).round().astype(int)
            elif kind == "sales_spike":
                df.loc[m, "sales"] = (df.loc[m, "sales"] * 1.65).round(-2)
                df.loc[m, "transactions"] = (df.loc[m, "transactions"] * 1.25).round().astype(int)
            injected.append(InjectedAnomaly(d.date(), code, kind, desc))

    tx = df["transactions"].replace(0, np.nan)
    df["avg_basket"] = (df["sales"] / tx).fillna(0).round(0)
    df["transactions"] = df["transactions"].astype(int)
    df = df[COLUMNS].sort_values(["date", "store_code"]).reset_index(drop=True)
    return df, injected


def save_sales_data(df: pd.DataFrame, injected: list[InjectedAnomaly], out_dir: str | Path,
                    basename: str = "daily_store_sales") -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    xlsx = out / f"{basename}.xlsx"
    csv = out / f"{basename}.csv"
    truth = out / "planted_anomalies.csv"
    export = df.copy()
    export["date"] = export["date"].dt.date
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        export.to_excel(writer, sheet_name="daily_sales", index=False)
        ws = writer.sheets["daily_sales"]
        widths = {"A": 12, "B": 11, "C": 26, "D": 16, "E": 13, "F": 13, "G": 12, "H": 40, "I": 11}
        for col, w in widths.items():
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"
    export.to_csv(csv, index=False)
    pd.DataFrame([a.__dict__ for a in injected]).to_csv(truth, index=False)
    return {"xlsx": xlsx, "csv": csv, "ground_truth": truth}
