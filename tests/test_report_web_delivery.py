import io
import re

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from store_report import web
from store_report.__main__ import main
from store_report.delivery import deliver
from store_report.report import build_report, render_html, save_report

INDONESIAN = {"date": "tanggal", "store_code": "kode_toko", "store_name": "nama_toko", "region": "wilayah",
              "sales": "penjualan", "transactions": "jumlah_transaksi", "stockouts": "jumlah_stockout"}


@pytest.fixture(scope="module")
def client():
    return TestClient(web.app)


def _xlsx_bytes(df):
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


# ---------- HTML report ----------

def test_html_report_is_self_contained_and_english(sample):
    df, _ = sample
    html = render_html(df, build_report(df, use_llm=False))
    assert '<html lang="en">' in html
    assert "Tuesday, 6 October 2026" in html
    assert "4 of 20 stores need attention. Sales were 13.8% below the 7-day average.<" in html
    assert "Stores that need attention" in html
    assert "<svg" in html and "<img" not in html
    assert "Store 013 Sukabumi" in html
    assert "<script" not in html


def test_html_report_follows_design_rules(sample):
    df, _ = sample
    html = render_html(df, build_report(df, use_llm=False))
    css = html[html.index("<style>"):html.index("</style>")]
    assert "Hallmark" in css and "macrostructure" in css
    assert "transition: all" not in css and "gradient" not in css
    assert "overflow-x: clip" in css
    rules = css.split("--font-mono")[-1]
    # every colour outside the token block goes through var()
    after_tokens = css[css.index("/* ---------- base"):]
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b|rgb\(|oklch\(", after_tokens)
    assert not re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", html), "no emoji"
    assert rules


def test_html_report_indonesian(sample):
    df, _ = sample
    html = render_html(df, build_report(df, use_llm=False, lang="id"))
    assert '<html lang="id">' in html and "Selasa, 6 Oktober 2026" in html


def test_save_report_files(sample, tmp_path):
    df, _ = sample
    paths = save_report(df, build_report(df, use_llm=False), tmp_path)
    assert paths["html"].name == "daily_report_2026-10-06.html"
    flags = pd.read_csv(paths["flags"])
    assert set(flags["store_code"]) == {"ST007", "ST013", "ST018", "ST011"}
    assert "20 stores sold" in paths["summary"].read_text()


# ---------- web app ----------

def test_upload_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Daily store report" in r.text and 'type="file"' in r.text
    assert client.get("/?lang=id").text.count('lang="id"') >= 1
    assert client.get("/assets/styles.css").headers["content-type"].startswith("text/css")
    assert client.get("/healthz").text == "ok"


def test_sample_report_and_downloads(client):
    r = client.get("/sample", follow_redirects=True)
    assert r.status_code == 200
    assert "Stores that need attention" in r.text and "Download report" in r.text
    d = client.get("/report/sample/report.html?date=2026-10-06")
    assert d.status_code == 200 and "attachment" in d.headers["content-disposition"]
    assert "<style>" in d.text
    c = client.get("/report/sample/flags.csv?date=2026-10-06")
    assert "ST013" in c.text and c.headers["content-type"].startswith("text/csv")


def test_date_threshold_and_language_controls(client):
    r = client.get("/report/sample?date=2026-09-15&lang=id&drop=25&z=3")
    assert r.status_code == 200 and "Selasa, 15 September 2026" in r.text
    assert 'value="2026-09-15" selected' in r.text
    strict = client.get("/report/sample?date=2026-10-06&drop=90&z=6").text
    assert "Store 013 Sukabumi" in strict  # zero transactions is always flagged


def test_upload_xlsx_with_indonesian_headers(client, sample):
    df, _ = sample
    old = df[list(INDONESIAN)].rename(columns=INDONESIAN)
    r = client.post("/upload", files={"file": ("penjualan.xlsx", _xlsx_bytes(old))}, data={"lang": "en"},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"])
    assert "penjualan.xlsx" in page.text and "Store 007 Depok" in page.text


def test_upload_errors(client):
    r = client.post("/upload", files={"file": ("notes.txt", b"hello")}, data={"lang": "en"})
    assert r.status_code == 400 and ".xlsx or .csv" in r.text and 'role="alert"' in r.text
    bad = b"date,store_code\n2026-10-06,ST001\n"
    r = client.post("/upload", files={"file": ("bad.csv", bad)}, data={"lang": "en"})
    assert r.status_code == 400 and "Missing required columns" in r.text
    assert client.get("/report/doesnotexist").status_code == 404


# ---------- delivery + CLI ----------

def test_delivery_is_dry_run_by_default(tmp_path, monkeypatch):
    f = tmp_path / "r.html"
    f.write_text("<html></html>")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("must not send"))
    res = deliver("Daily store report", "text", f)
    assert len(res) == 1 and res[0].channel == "dry-run" and not res[0].sent
    assert "nothing was sent" in res[0].detail


def test_delivery_enabled_without_credentials(tmp_path, monkeypatch):
    f = tmp_path / "r.html"
    f.write_text("x")
    monkeypatch.setenv("DELIVERY_ENABLED", "true")
    assert deliver("t", "s", f)[0].channel == "none"


def test_cli_generate_and_report(tmp_path, capsys):
    assert main(["generate", "--out", str(tmp_path / "d"), "--end-date", "2026-10-06"]) == 0
    assert main(["report", "--input", str(tmp_path / "d" / "daily_store_sales.xlsx"), "--out", str(tmp_path / "o"),
                 "--no-llm", "--send"]) == 0
    out = capsys.readouterr().out
    assert "Need attention   4 stores" in out and "send[dry-run]" in out
    assert (tmp_path / "o" / "daily_report_2026-10-06.html").exists()
    assert main(["report", "--input", str(tmp_path / "missing.xlsx")]) == 2
