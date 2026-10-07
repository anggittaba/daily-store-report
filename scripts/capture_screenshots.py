"""Recapture the README screenshots at 1280 px wide.

Starts the web app on a free local port, uploads the sample file through the
real form, captures four views, then stops the server.

  pip install playwright && playwright install chromium
  python scripts/capture_screenshots.py [--chrome /usr/bin/google-chrome]
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
SAMPLE = ROOT / "data" / "sample" / "daily_store_sales.xlsx"
REPORT = ROOT / "examples" / "daily_report_2026-10-06.html"
W = 1280


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_up(url: str, timeout: float = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"server did not start: {url}")


def shoot_section(page, selector: str, path: Path, until: str | None = None) -> None:
    """Full-width screenshot from the top of one section to the end of it (or of `until`)."""
    page.locator(selector).scroll_into_view_if_needed()
    top = page.evaluate(f"document.querySelector('{selector}').getBoundingClientRect().top + scrollY")
    end = page.evaluate(f"document.querySelector('{until or selector}').getBoundingClientRect().bottom + scrollY")
    y = top + 16  # sections carry 64 px of top padding; keep most of it as margin
    page.screenshot(path=str(path), full_page=True, clip={"x": 0, "y": y, "width": W, "height": end - y + 40})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default=None, help="path to a Chrome/Chromium binary (optional)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "STORE_REPORT_DISABLE_LLM": "1"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "store_report.web:app", "--port", str(port),
                               "--log-level", "warning"], cwd=ROOT, env=env)
    try:
        wait_up(f"{base}/healthz")
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
            page = browser.new_page(viewport={"width": W, "height": 800}, device_scale_factor=1)

            page.goto(f"{base}/", wait_until="networkidle")
            page.screenshot(path=str(OUT / "01_upload.png"))

            page.set_input_files("input[type=file]", str(SAMPLE))
            page.click("button[type=submit]")
            page.wait_for_selector("#attention")
            page.wait_for_load_state("networkidle")
            page.set_viewport_size({"width": W, "height": 900})
            page.screenshot(path=str(OUT / "02_dashboard.png"))

            shoot_section(page, "#attention", OUT / "03_stores_to_check.png")

            report = browser.new_page(viewport={"width": W, "height": 900}, device_scale_factor=1)
            report.goto(REPORT.resolve().as_uri(), wait_until="networkidle")
            shoot_section(report, "#trends", OUT / "04_report_trends.png", until="#stores tbody tr:nth-child(7)")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    for f in sorted(OUT.glob("*.png")):
        print("saved", f.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
