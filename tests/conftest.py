import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from store_report.data_generator import generate_sales_data  # noqa: E402

END = "2026-10-06"


@pytest.fixture(scope="session")
def sample():
    df, injected = generate_sales_data(n_stores=20, n_days=60, end_date=END, seed=42)
    return df, injected


@pytest.fixture(autouse=True)
def no_secrets(monkeypatch):
    """Tests must never call an LLM or send anything."""
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "DELIVERY_ENABLED", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
              "SMTP_HOST", "EMAIL_FROM", "EMAIL_TO", "STORE_REPORT_LANG", "STORE_REPORT_DISABLE_LLM"):
        monkeypatch.delenv(k, raising=False)
