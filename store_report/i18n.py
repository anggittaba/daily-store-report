"""Language support: English (default) and Indonesian.

Pick the language with the `lang` argument, the CLI flag `--lang`, the web
query parameter `?lang=`, or the environment variable STORE_REPORT_LANG.
Number formatting follows the language: "Rp 325.1M" in English,
"Rp 325,1 juta" in Indonesian.
"""

from __future__ import annotations

import math
import os
from datetime import date, datetime

import pandas as pd

LANGS = ("en", "id")
MINUS = "\u2212"  # typographic minus for display


def default_lang() -> str:
    lang = os.getenv("STORE_REPORT_LANG", "en").strip().lower()
    return lang if lang in LANGS else "en"


def norm_lang(lang: str | None) -> str:
    lang = (lang or default_lang()).strip().lower()
    return lang if lang in LANGS else "en"


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def number(x, decimals: int = 0, lang: str = "en") -> str:
    if _missing(x):
        return "–"
    s = f"{abs(x):,.{decimals}f}"
    if lang == "id":
        s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return (MINUS if x < 0 and round(abs(x), decimals) != 0 else "") + s


def money(x, lang: str = "en") -> str:
    if _missing(x):
        return "–"
    return f"Rp\u00a0{number(x, 0, lang)}"


def money_short(x, lang: str = "en") -> str:
    """Rp 325.1M / Rp 1.25B (en) — Rp 325,1 juta / Rp 1,25 miliar (id)."""
    if _missing(x):
        return "–"
    a = abs(x)
    if lang == "id":
        units = [(1e9, "miliar", 2), (1e6, "juta", 1), (1e3, "ribu", 0)]
        for div, unit, d in units:
            if a >= div:
                return f"Rp\u00a0{number(x / div, d, lang)}\u00a0{unit}"
    else:
        units = [(1e9, "B", 2), (1e6, "M", 1), (1e3, "K", 0)]
        for div, unit, d in units:
            if a >= div:
                return f"Rp\u00a0{number(x / div, d, lang)}{unit}"
    return money(x, lang)


def pct(x, signed: bool = True, decimals: int = 1, lang: str = "en") -> str:
    """0.123 -> '+12.3%'; -0.138 -> '−13.8%'."""
    if _missing(x):
        return "–"
    body = number(abs(x) * 100, decimals, lang)
    if not signed:
        return f"{body}%"
    if round(abs(x) * 100, decimals) == 0:
        return f"{body}%"
    return f"{'+' if x > 0 else MINUS}{body}%"


DAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "id": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"],
}
MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "id": ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
           "September", "Oktober", "November", "Desember"],
}


def _as_date(d) -> date:
    if isinstance(d, str):
        d = pd.Timestamp(d)
    if isinstance(d, (pd.Timestamp, datetime)):
        d = d.date()
    return d


def weekday(d, lang: str = "en") -> str:
    return DAYS[lang][_as_date(d).weekday()]


def date_long(d, lang: str = "en") -> str:
    """'Tuesday, 6 October 2026' / 'Selasa, 6 Oktober 2026'."""
    d = _as_date(d)
    return f"{DAYS[lang][d.weekday()]}, {d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def date_short(d, lang: str = "en") -> str:
    d = _as_date(d)
    return f"{d.day} {MONTHS[lang][d.month - 1][:3]}"


# --------------------------------------------------------------------------- UI strings
T = {
    "en": {
        "product": "Store Report",
        "doc_title": "Daily store report",
        "stores_reporting": "{n} stores reporting",
        "lede_att": "{a} of {n} stores need attention.",
        "lede_att_1": "1 of {n} stores needs attention.",
        "lede_none": "All {n} stores are within their normal range.",
        "lede_below": "Sales were {p} below the 7-day average.",
        "lede_above": "Sales were {p} above the 7-day average.",
        "need_attention_n": "{n} need attention",
        "none_need_attention": "none need attention",
        "lede_sales": "sales {sales}, {pct} against the 7-day average",
        "kpi_sales": "Sales",
        "kpi_transactions": "Transactions",
        "kpi_basket": "Average basket",
        "kpi_stockouts": "Items out of stock",
        "kpi_attention": "Need attention",
        "vs_7d": "{v} vs 7-day average",
        "vs_last_week": "{v} vs last {day}",
        "vs_yesterday": "{v} vs yesterday",
        "per_tx": "per transaction",
        "of_stores": "of {n} stores",
        "stores_trading": "{n} stores trading",
        "summary": "Summary",
        "summary_source": "Written by {src}.",
        "attention": "Stores that need attention",
        "attention_none": "No store crossed a detection threshold on this date.",
        "action": "Next step",
        "sales_vs_baseline": "Sales by store against each store’s 7-day average",
        "trend": "Total sales, last 30 days",
        "trend_legend_ma": "7-day moving average",
        "trend_legend_day": "report date",
        "regions": "Sales by region",
        "regions_table": "Regions",
        "all_stores": "All stores",
        "col_store": "Store", "col_region": "Region", "col_sales": "Sales", "col_avg7": "7-day avg",
        "col_vs7": "vs 7-day", "col_z": "z-score", "col_tx": "Transactions", "col_basket": "Avg basket",
        "col_stockouts": "Stock-outs", "col_status": "Status", "col_stores": "Stores", "col_share": "Share",
        "status_normal": "Normal",
        "method": "How stores are flagged",
        "method_intro": "Each store is compared with its own recent history, so a small store is not flagged just for being small. "
                        "The baseline is the store’s previous {b} days; days with zero transactions (outages) are left out. "
                        "The z-score compares today with the previous {z} days.",
        "rule": "Rule", "severity": "Severity",
        "rule_zero_tx": "No transactions for the day",
        "rule_missing": "Store missing from the file but present in previous days",
        "rule_drop": "Sales {d}% or more below the 7-day average ({c}% or more is critical)",
        "rule_below": "z-score of −{z} or lower (drop under {d}%)",
        "rule_spike": "Sales {s}% or more above the 7-day average, or z-score of +{z} or higher",
        "rule_stockout": "Stock-outs at least {m}× the 7-day average and up by {k} items or more",
        "generated": "Generated {ts}",
        "synthetic": "Synthetic sample data",
        "footer_tool": "Daily Store Report Assistant v{v}",
        # web
        "upload_title": "Daily store report",
        "upload_lede": "Upload the daily sales export. One row per store per day, as .xlsx or .csv. "
                       "The report compares each store with its own last 7 days and lists the ones that need a call today.",
        "upload_label": "Sales export",
        "upload_help": "Required columns: date, store_code, store_name, region, sales, transactions, stockouts. "
                       "Indonesian headers (tanggal, kode_toko, …) also work.",
        "choose_file": "Choose file",
        "no_file": "No file chosen",
        "build": "Build report",
        "building": "Building…",
        "use_sample": "Open the sample file",
        "sample_title": "Sample data",
        "sample_note": "20 stores, 60 days, synthetic data with four planted problems on the last day.",
        "cli_hint": "Same report from the command line:",
        "report_date": "Report date",
        "thresholds": "Detection thresholds",
        "drop_threshold": "Drop vs 7-day avg (%)",
        "z_threshold": "z-score",
        "apply": "Apply",
        "new_file": "Upload another file",
        "download_html": "Download report",
        "download_csv": "Flags as CSV",
        "file_meta": "{name} · {rows} rows · {stores} stores · {first} to {last}",
        "err_title": "That file could not be read.",
        "err_format": "The file must be .xlsx or .csv. Export the sheet in one of those formats and upload it again.",
        "err_size": "The file is larger than {mb} MB. Split it by month and upload one month at a time.",
        "err_empty": "No file was attached. Choose a file, then select Build report.",
        "err_expired": "That upload is no longer in memory (the server keeps the last {n}). Upload the file again.",
        "language": "Language",
    },
    "id": {
        "product": "Store Report",
        "doc_title": "Laporan harian toko",
        "stores_reporting": "{n} toko melapor",
        "lede_att": "{a} dari {n} toko perlu perhatian.",
        "lede_att_1": "1 dari {n} toko perlu perhatian.",
        "lede_none": "Semua {n} toko dalam batas normal.",
        "lede_below": "Penjualan {p} di bawah rata-rata 7 hari.",
        "lede_above": "Penjualan {p} di atas rata-rata 7 hari.",
        "need_attention_n": "{n} perlu perhatian",
        "none_need_attention": "tidak ada yang perlu perhatian",
        "lede_sales": "penjualan {sales}, {pct} dibanding rata-rata 7 hari",
        "kpi_sales": "Penjualan",
        "kpi_transactions": "Transaksi",
        "kpi_basket": "Rata-rata belanja",
        "kpi_stockouts": "Item stock-out",
        "kpi_attention": "Perlu perhatian",
        "vs_7d": "{v} vs rata-rata 7 hari",
        "vs_last_week": "{v} vs {day} lalu",
        "vs_yesterday": "{v} vs kemarin",
        "per_tx": "per transaksi",
        "of_stores": "dari {n} toko",
        "stores_trading": "{n} toko bertransaksi",
        "summary": "Ringkasan",
        "summary_source": "Ditulis oleh {src}.",
        "attention": "Toko yang perlu perhatian",
        "attention_none": "Tidak ada toko yang melewati ambang deteksi pada tanggal ini.",
        "action": "Langkah berikutnya",
        "sales_vs_baseline": "Penjualan per toko dibanding rata-rata 7 hari masing-masing",
        "trend": "Total penjualan, 30 hari terakhir",
        "trend_legend_ma": "rata-rata bergerak 7 hari",
        "trend_legend_day": "tanggal laporan",
        "regions": "Penjualan per wilayah",
        "regions_table": "Wilayah",
        "all_stores": "Semua toko",
        "col_store": "Toko", "col_region": "Wilayah", "col_sales": "Penjualan", "col_avg7": "Rata-rata 7 hari",
        "col_vs7": "vs 7 hari", "col_z": "z-score", "col_tx": "Transaksi", "col_basket": "Rata-rata belanja",
        "col_stockouts": "Stock-out", "col_status": "Status", "col_stores": "Toko", "col_share": "Porsi",
        "status_normal": "Normal",
        "method": "Cara toko ditandai",
        "method_intro": "Setiap toko dibandingkan dengan riwayatnya sendiri, jadi toko kecil tidak ditandai hanya karena kecil. "
                        "Baseline adalah {b} hari sebelumnya; hari dengan 0 transaksi (gangguan) tidak dihitung. "
                        "z-score membandingkan hari ini dengan {z} hari sebelumnya.",
        "rule": "Aturan", "severity": "Tingkat",
        "rule_zero_tx": "Tidak ada transaksi sepanjang hari",
        "rule_missing": "Toko tidak ada di file padahal ada di hari-hari sebelumnya",
        "rule_drop": "Penjualan turun {d}% atau lebih dari rata-rata 7 hari ({c}% atau lebih = kritis)",
        "rule_below": "z-score −{z} atau lebih rendah (turun kurang dari {d}%)",
        "rule_spike": "Penjualan naik {s}% atau lebih dari rata-rata 7 hari, atau z-score +{z} atau lebih",
        "rule_stockout": "Stock-out minimal {m}× rata-rata 7 hari dan bertambah {k} item atau lebih",
        "generated": "Dibuat {ts}",
        "synthetic": "Data contoh sintetis",
        "footer_tool": "Daily Store Report Assistant v{v}",
        "upload_title": "Laporan harian toko",
        "upload_lede": "Upload file ekspor penjualan harian. Satu baris per toko per hari, format .xlsx atau .csv. "
                       "Laporan membandingkan setiap toko dengan 7 hari terakhirnya dan menampilkan toko yang perlu dihubungi hari ini.",
        "upload_label": "File ekspor penjualan",
        "upload_help": "Kolom wajib: date, store_code, store_name, region, sales, transactions, stockouts. "
                       "Header bahasa Indonesia (tanggal, kode_toko, …) juga bisa.",
        "choose_file": "Pilih file",
        "no_file": "Belum ada file",
        "build": "Buat laporan",
        "building": "Memproses…",
        "use_sample": "Buka file contoh",
        "sample_title": "Data contoh",
        "sample_note": "20 toko, 60 hari, data sintetis dengan empat masalah yang disisipkan di hari terakhir.",
        "cli_hint": "Laporan yang sama dari command line:",
        "report_date": "Tanggal laporan",
        "thresholds": "Ambang deteksi",
        "drop_threshold": "Turun vs rata-rata 7 hari (%)",
        "z_threshold": "z-score",
        "apply": "Terapkan",
        "new_file": "Upload file lain",
        "download_html": "Unduh laporan",
        "download_csv": "Temuan (CSV)",
        "file_meta": "{name} · {rows} baris · {stores} toko · {first} s/d {last}",
        "err_title": "File tidak bisa dibaca.",
        "err_format": "File harus .xlsx atau .csv. Ekspor ulang sheet dalam salah satu format itu, lalu upload lagi.",
        "err_size": "Ukuran file lebih dari {mb} MB. Pecah per bulan dan upload satu bulan sekaligus.",
        "err_empty": "Belum ada file yang dipilih. Pilih file, lalu tekan Buat laporan.",
        "err_expired": "Upload itu sudah tidak ada di memori (server menyimpan {n} terakhir). Upload ulang file-nya.",
        "language": "Bahasa",
    },
}

SEVERITY_LABEL = {
    "en": {"critical": "Critical", "high": "High", "medium": "Medium"},
    "id": {"critical": "Kritis", "high": "Tinggi", "medium": "Sedang"},
}


def t(key: str, lang: str = "en", **kw) -> str:
    s = T[lang].get(key) or T["en"][key]
    return s.format(**kw) if kw else s


def severity_label(code: str, lang: str = "en") -> str:
    return SEVERITY_LABEL[lang].get(code, code)
