"""Load and validate daily sales files (.xlsx or .csv).

Canonical column names are English. The older Indonesian names and a few
common alternatives are mapped automatically, so a file exported with
`tanggal, kode_toko, nama_toko, ...` loads the same as `date, store_code, ...`.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

REQUIRED = ["date", "store_code", "store_name", "region", "sales", "transactions", "stockouts"]
OPTIONAL = ["avg_basket", "top_categories"]

ALIASES = {
    # Indonesian (v1 of this project)
    "tanggal": "date", "tgl": "date",
    "kode_toko": "store_code", "kode": "store_code",
    "nama_toko": "store_name", "toko": "store_name",
    "wilayah": "region", "area": "region",
    "penjualan": "sales", "omzet": "sales",
    "jumlah_transaksi": "transactions", "transaksi": "transactions", "struk": "transactions",
    "rata_rata_belanja": "avg_basket",
    "kategori_teratas": "top_categories",
    "jumlah_stockout": "stockouts", "stockout": "stockouts",
    # English alternatives
    "store_id": "store_code", "store": "store_name", "net_sales": "sales", "revenue": "sales",
    "transaction_count": "transactions", "receipts": "transactions",
    "average_basket": "avg_basket", "basket": "avg_basket",
    "categories": "top_categories", "stock_outs": "stockouts", "stock_out": "stockouts",
}


class DataValidationError(ValueError):
    pass


def _normalise_header(c: str) -> str:
    key = str(c).strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(key, key)


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise headers, types and derived columns. Raises DataValidationError."""
    df = df.rename(columns={c: _normalise_header(c) for c in df.columns})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise DataValidationError(
            "Missing required columns: " + ", ".join(missing)
            + ". Expected: " + ", ".join(REQUIRED) + " (Indonesian names such as tanggal or kode_toko also work)."
        )
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    if df["date"].isna().any():
        raise DataValidationError(f"{int(df['date'].isna().sum())} rows have a date that could not be read. "
                                  "Use YYYY-MM-DD.")
    for c in ["sales", "transactions", "stockouts"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["transactions"] = df["transactions"].astype(int)
    df["stockouts"] = df["stockouts"].astype(int)
    for c in ["store_code", "store_name", "region"]:
        df[c] = df[c].astype(str).str.strip()
    if "top_categories" not in df.columns:
        df["top_categories"] = ""
    df["top_categories"] = df["top_categories"].fillna("").astype(str)
    tx = df["transactions"].where(df["transactions"] > 0)
    df["avg_basket"] = (df["sales"] / tx).fillna(0).round(0)
    df = df.drop_duplicates(subset=["date", "store_code"], keep="last")
    cols = REQUIRED + OPTIONAL
    return df[cols].sort_values(["date", "store_code"]).reset_index(drop=True)


def load_sales_file(source, filename: str | None = None) -> pd.DataFrame:
    """Load from a path, or from bytes / a file-like object (e.g. an upload)."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        name, data = path.name, path
    else:
        name = filename or getattr(source, "name", "upload.xlsx")
        raw = source if isinstance(source, bytes) else source.read()
        data = io.BytesIO(raw)
    lower = name.lower()
    try:
        if lower.endswith(".csv"):
            df = pd.read_csv(data)
        elif lower.endswith((".xlsx", ".xls")):
            df = pd.read_excel(data)
        else:
            raise DataValidationError("The file must be .xlsx or .csv.")
    except DataValidationError:
        raise
    except Exception as exc:  # corrupt file, wrong encoding, …
        raise DataValidationError(f"The file could not be parsed ({type(exc).__name__}). "
                                  "Check that it is a real .xlsx or .csv export.") from exc
    return prepare(df)
