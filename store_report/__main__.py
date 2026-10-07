"""Command line interface.

  python -m store_report generate --out data/sample --end-date 2026-10-06
  python -m store_report report --input data/sample/daily_store_sales.xlsx --out examples
  python -m store_report report --input data/sample/daily_store_sales.xlsx --lang id
  python -m store_report serve --port 8000
"""

from __future__ import annotations

import argparse
import sys

from .analysis import Thresholds
from .data_generator import generate_sales_data, save_sales_data
from .delivery import deliver
from .i18n import LANGS, date_long, default_lang, money, severity_label, t
from .loader import DataValidationError, load_sales_file
from .report import build_report, save_report


def cmd_generate(a) -> int:
    df, injected = generate_sales_data(a.stores, a.days, a.end_date, a.seed, not a.no_anomalies)
    paths = save_sales_data(df, injected, a.out)
    print(f"Wrote {len(df)} rows ({df['store_code'].nunique()} stores x {df['date'].nunique()} days, "
          f"{df['date'].min().date()} to {df['date'].max().date()})")
    for k, p in paths.items():
        print(f"  {k:13s} {p}")
    print(f"  {len(injected)} planted anomalies, listed in {paths['ground_truth'].name}")
    return 0


def cmd_report(a) -> int:
    try:
        df = load_sales_file(a.input)
    except (DataValidationError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    th = Thresholds(drop_pct=a.drop_pct, z_threshold=a.z)
    rep = build_report(df, a.date, th, use_llm=not a.no_llm, source_name=str(a.input), lang=a.lang)
    paths = save_report(df, rep, a.out)
    print(f"Report for {date_long(rep.date, 'en')}")
    print(f"  Sales            {money(rep.kpis['sales'], 'en')}")
    print(f"  Need attention   {len(rep.attention)} stores")
    for x in rep.attention:
        print(f"    {severity_label(x['severity'], 'en'):8s} {x['store_name']}: {x['reasons'][0]}")
    print(f"  Summary          written by {rep.summary_source}")
    for k, p in paths.items():
        print(f"  {k:16s} {p}")
    if a.send:
        title = f"{t('doc_title', a.lang)} · {date_long(rep.date, a.lang)}"
        for r in deliver(title, rep.summary, paths["html"]):
            print(f"  send[{r.channel}]  {r.detail}")
    return 0


def cmd_serve(a) -> int:
    import uvicorn

    print(f"Serving on http://{a.host}:{a.port}  (Ctrl+C to stop)")
    uvicorn.run("store_report.web:app", host=a.host, port=a.port, log_level="warning")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="store_report",
                                description="Daily Store Report Assistant: turn a daily sales export "
                                            "into a one-page report that lists the stores to check.")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write a synthetic sales file (.xlsx + .csv)")
    g.add_argument("--stores", type=int, default=20)
    g.add_argument("--days", type=int, default=60)
    g.add_argument("--end-date", default=None, help="YYYY-MM-DD (default: yesterday)")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--no-anomalies", action="store_true", help="do not plant the four test problems")
    g.add_argument("--out", default="data/sample")
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("report", help="build the HTML report from an .xlsx/.csv file")
    r.add_argument("--input", required=True)
    r.add_argument("--date", default=None, help="YYYY-MM-DD (default: last date in the file)")
    r.add_argument("--out", default="output")
    r.add_argument("--lang", choices=LANGS, default=default_lang(),
                   help="report language (default: en, or STORE_REPORT_LANG)")
    r.add_argument("--drop-pct", type=float, default=0.25, help="flag sales this far below the 7-day average")
    r.add_argument("--z", type=float, default=3.0, help="z-score threshold")
    r.add_argument("--no-llm", action="store_true", help="always use the rule-based summary")
    r.add_argument("--send", action="store_true",
                   help="send via Telegram/e-mail (only if DELIVERY_ENABLED=true, otherwise a dry run)")
    r.set_defaults(func=cmd_report)

    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
