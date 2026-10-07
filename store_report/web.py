"""Small server-rendered web app (FastAPI + Jinja2, no front-end build).

Run:  python -m store_report serve            (http://127.0.0.1:8000)
  or: uvicorn store_report.web:app --port 8000

Upload an .xlsx/.csv export, pick a date, read the report, download it as a
self-contained HTML file or the flags as CSV. Uploads are kept in memory only
(last MAX_UPLOADS files) and never written to disk.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import __version__
from .analysis import Thresholds, available_dates
from .i18n import date_long, date_short, norm_lang, number, t
from .loader import DataValidationError, load_sales_file
from .report import build_report, flags_csv, render_html, stylesheet, view_model

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample" / "daily_store_sales.xlsx"
TEMPLATES = Path(__file__).parent / "templates"
MAX_UPLOADS = 20
MAX_MB = 10

app = FastAPI(title="Daily Store Report Assistant", version=__version__, docs_url=None, redoc_url=None)
env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))

_DATA: OrderedDict[str, dict] = OrderedDict()
_REPORTS: OrderedDict[tuple, tuple] = OrderedDict()


def _remember(store: OrderedDict, key, value, limit: int) -> None:
    store[key] = value
    store.move_to_end(key)
    while len(store) > limit:
        store.popitem(last=False)


def _dataset(token: str) -> dict | None:
    if token == "sample" and "sample" not in _DATA and SAMPLE.exists():
        _remember(_DATA, "sample", {"df": load_sales_file(SAMPLE), "name": SAMPLE.name}, MAX_UPLOADS)
    return _DATA.get(token)


def _thresholds(drop: float | None, z: float | None) -> Thresholds:
    th = Thresholds()
    if drop is not None and 5 <= drop <= 90:
        th.drop_pct = drop / 100
        th.critical_drop_pct = max(th.critical_drop_pct, th.drop_pct)
    if z is not None and 1 <= z <= 6:
        th.z_threshold = z
    return th


def _report(token: str, data: dict, date, lang: str, th: Thresholds):
    key = (token, str(date), lang, th.drop_pct, th.z_threshold)
    if key not in _REPORTS:
        rep = build_report(data["df"], date, th, source_name=data["name"], lang=lang)
        _remember(_REPORTS, key, (rep, render_html(data["df"], rep)), 40)
    return _REPORTS[key]


def _upload_page(lang: str, error: str | None = None, status: int = 200) -> HTMLResponse:
    html = env.get_template("upload.html.j2").render(
        lang=lang, t=lambda k, **kw: t(k, lang, **kw), error=error, max_mb=MAX_MB, version=__version__,
        sample_available=SAMPLE.exists())
    return HTMLResponse(html, status_code=status)


@app.get("/assets/styles.css")
def css() -> Response:
    return Response(stylesheet(), media_type="text/css", headers={"Cache-Control": "max-age=300"})


@app.get("/healthz")
def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok")


@app.get("/", response_class=HTMLResponse)
def index(lang: str | None = None) -> HTMLResponse:
    return _upload_page(norm_lang(lang))


@app.post("/upload")
async def upload(file: UploadFile | None = File(None), lang: str = Form("en")):
    lang = norm_lang(lang)
    if file is None or not file.filename:
        return _upload_page(lang, t("err_empty", lang), 400)
    raw = await file.read()
    if len(raw) > MAX_MB * 1024 * 1024:
        return _upload_page(lang, t("err_size", lang, mb=MAX_MB), 413)
    if not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        return _upload_page(lang, t("err_format", lang), 400)
    try:
        df = load_sales_file(raw, filename=file.filename)
    except DataValidationError as exc:
        return _upload_page(lang, str(exc), 400)
    if df.empty:
        return _upload_page(lang, t("err_empty", lang), 400)
    token = uuid.uuid4().hex[:12]
    _remember(_DATA, token, {"df": df, "name": file.filename}, MAX_UPLOADS)
    return RedirectResponse(f"/report/{token}?lang={lang}", status_code=303)


@app.get("/sample")
def sample(lang: str | None = None):
    return RedirectResponse(f"/report/sample?lang={norm_lang(lang)}", status_code=303)


@app.get("/report/{token}", response_class=HTMLResponse)
def report_page(request: Request, token: str, date: str | None = None, lang: str | None = None,
                drop: float | None = None, z: float | None = None):
    lang = norm_lang(lang)
    data = _dataset(token)
    if data is None:
        return _upload_page(lang, t("err_expired", lang, n=MAX_UPLOADS), 404)
    df: pd.DataFrame = data["df"]
    dates = available_dates(df)
    chosen = pd.Timestamp(date) if date and pd.Timestamp(date) in dates else dates[-1]
    th = _thresholds(drop, z)
    rep, _ = _report(token, data, chosen, lang, th)
    params = {"date": chosen.strftime("%Y-%m-%d"), "drop": round(th.drop_pct * 100), "z": th.z_threshold}

    def qs(**over) -> str:
        return urlencode({**params, "lang": lang, **over})

    html = env.get_template("app.html.j2").render(
        vm=view_model(df, rep), token=token, lang=lang, qs=qs, params=params,
        dates=[(d.strftime("%Y-%m-%d"), date_long(d, lang)) for d in reversed(dates)],
        file_meta=t("file_meta", lang, name=data["name"], rows=number(len(df), 0, lang),
                    stores=df["store_code"].nunique(), first=date_short(dates[0], lang) + f" {dates[0].year}",
                    last=date_short(dates[-1], lang) + f" {dates[-1].year}"),
    )
    return HTMLResponse(html)


@app.get("/report/{token}/report.html")
def download_html(token: str, date: str | None = None, lang: str | None = None,
                  drop: float | None = None, z: float | None = None):
    lang = norm_lang(lang)
    data = _dataset(token)
    if data is None:
        return _upload_page(lang, t("err_expired", lang, n=MAX_UPLOADS), 404)
    dates = available_dates(data["df"])
    chosen = pd.Timestamp(date) if date and pd.Timestamp(date) in dates else dates[-1]
    rep, html = _report(token, data, chosen, lang, _thresholds(drop, z))
    name = f"daily_report_{chosen:%Y-%m-%d}{'' if lang == 'en' else '_' + lang}.html"
    return Response(html, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/report/{token}/flags.csv")
def download_csv(token: str, date: str | None = None, lang: str | None = None,
                 drop: float | None = None, z: float | None = None):
    lang = norm_lang(lang)
    data = _dataset(token)
    if data is None:
        return _upload_page(lang, t("err_expired", lang, n=MAX_UPLOADS), 404)
    dates = available_dates(data["df"])
    chosen = pd.Timestamp(date) if date and pd.Timestamp(date) in dates else dates[-1]
    rep, _ = _report(token, data, chosen, lang, _thresholds(drop, z))
    return Response(flags_csv(rep), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="flags_{chosen:%Y-%m-%d}.csv"'})
