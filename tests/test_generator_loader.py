import io

import pandas as pd
import pytest

from store_report.data_generator import COLUMNS, save_sales_data
from store_report.loader import DataValidationError, load_sales_file

INDONESIAN = {"date": "tanggal", "store_code": "kode_toko", "store_name": "nama_toko", "region": "wilayah",
              "sales": "penjualan", "transactions": "jumlah_transaksi", "avg_basket": "rata_rata_belanja",
              "top_categories": "kategori_teratas", "stockouts": "jumlah_stockout"}


def test_generator_shape_and_english_columns(sample):
    df, injected = sample
    assert list(df.columns) == COLUMNS
    assert len(df) == 20 * 60
    assert df["store_code"].nunique() == 20
    assert df["date"].max() == pd.Timestamp("2026-10-06")
    assert len(injected) >= 4
    assert not df["store_name"].str.contains("Mart|Market", case=False).any()


def test_generator_is_deterministic():
    from store_report.data_generator import generate_sales_data
    a, _ = generate_sales_data(end_date="2026-10-06", seed=7)
    b, _ = generate_sales_data(end_date="2026-10-06", seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_save_and_reload_xlsx_csv(sample, tmp_path):
    df, injected = sample
    paths = save_sales_data(df, injected, tmp_path)
    for key in ("xlsx", "csv"):
        back = load_sales_file(paths[key])
        assert len(back) == len(df)
        assert back["sales"].sum() == pytest.approx(df["sales"].sum())
    assert paths["xlsx"].name == "daily_store_sales.xlsx"


def test_loader_accepts_indonesian_headers(sample):
    df, _ = sample
    old = df.rename(columns=INDONESIAN)
    buf = io.BytesIO(old.to_csv(index=False).encode())
    back = load_sales_file(buf, filename="penjualan.csv")
    assert {"date", "store_code", "sales", "transactions", "stockouts"} <= set(back.columns)
    assert len(back) == len(df)


def test_loader_accepts_messy_headers():
    raw = "Date,Store Code,Store Name,Region,Sales,Transactions,Stockouts\n2026-10-06,ST001,A,B,100,2,0\n"
    back = load_sales_file(io.BytesIO(raw.encode()), filename="x.csv")
    assert back.loc[0, "store_code"] == "ST001"


def test_loader_rejects_missing_columns():
    raw = "date,store_code,sales\n2026-10-06,ST001,100\n"
    with pytest.raises(DataValidationError, match="Missing required columns"):
        load_sales_file(io.BytesIO(raw.encode()), filename="x.csv")


def test_loader_rejects_garbage():
    with pytest.raises(DataValidationError):
        load_sales_file(io.BytesIO(b"\x00\x01not a spreadsheet"), filename="x.xlsx")
