import io
import json
import urllib.error

import pytest

from store_report import summary as summary_mod
from store_report.i18n import date_long, money, money_short, pct
from store_report.report import build_report

NB = "\u00a0"


def test_money_formats():
    assert money_short(325_064_200) == f"Rp{NB}325.1M"
    assert money_short(1_250_000_000) == f"Rp{NB}1.25B"
    assert money(59_372) == f"Rp{NB}59,372"
    assert money_short(325_064_200, "id") == f"Rp{NB}325,1{NB}juta"
    assert pct(-0.138) == "\u221213.8%"
    assert date_long("2026-10-06") == "Tuesday, 6 October 2026"
    assert date_long("2026-10-06", "id") == "Selasa, 6 Oktober 2026"


def test_every_english_key_has_an_indonesian_twin():
    from store_report.i18n import T
    assert set(T["en"]) == set(T["id"])


def test_rule_based_summary_english(sample):
    df, _ = sample
    rep = build_report(df, use_llm=False)
    s = rep.summary.replace(NB, " ")
    assert s.startswith("20 stores sold Rp 325.1M across 5,475 transactions on Tuesday, 6 October 2026")
    assert "4 stores need attention" in s
    assert "Store 013 Sukabumi" in s
    assert rep.summary_source == "the rule-based template (no API key set)"


def test_summary_has_no_slop(sample):
    df, _ = sample
    for lang in ("en", "id"):
        rep = build_report(df, use_llm=False, lang=lang)
        text = rep.summary.lower()
        for word in ("seamless", "leverage", "empower", "unlock", "robust", "delve", "**"):
            assert word not in text
        assert not any(ord(ch) > 0x2600 for ch in rep.summary), "no emoji"


def test_indonesian_summary(sample):
    df, _ = sample
    rep = build_report(df, use_llm=False, lang="id")
    assert "Selasa, 6 Oktober 2026" in rep.summary
    assert "perlu perhatian" in rep.summary


def test_env_var_switches_default_language(sample, monkeypatch):
    df, _ = sample
    monkeypatch.setenv("STORE_REPORT_LANG", "id")
    assert build_report(df, use_llm=False).lang == "id"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_openai_path_mocked(sample, monkeypatch):
    df, _ = sample
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    seen = {}

    def fake(req, timeout=0):
        seen["url"], seen["auth"] = req.full_url, req.headers.get("Authorization")
        seen["prompt"] = json.loads(req.data)["messages"][0]["content"]
        return _Resp(json.dumps({"choices": [{"message": {"content": "Sales fell 13.8%."}}]}).encode())

    monkeypatch.setattr(summary_mod.urllib.request, "urlopen", fake)
    rep = build_report(df)
    assert rep.summary == "Sales fell 13.8%."
    assert rep.summary_source.startswith("OpenAI ")
    assert seen["url"].endswith("/chat/completions") and seen["auth"] == "Bearer test-key"
    assert "Store 007 Depok" in seen["prompt"]


def test_gemini_path_mocked(sample, monkeypatch):
    df, _ = sample
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    body = {"candidates": [{"content": {"parts": [{"text": "Ringkas."}]}}]}
    monkeypatch.setattr(summary_mod.urllib.request, "urlopen", lambda req, timeout=0: _Resp(json.dumps(body).encode()))
    rep = build_report(df, lang="id")
    assert rep.summary == "Ringkas." and rep.summary_source.startswith("Gemini ")


def test_llm_failure_falls_back(sample, monkeypatch):
    df, _ = sample
    monkeypatch.setenv("OPENAI_API_KEY", "bad")

    def boom(req, timeout=0):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(summary_mod.urllib.request, "urlopen", boom)
    rep = build_report(df)
    assert rep.summary.startswith("20 stores sold")
    assert "OpenAI request failed" in rep.summary_source


def test_disable_flag_skips_llm(sample, monkeypatch):
    df, _ = sample
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("STORE_REPORT_DISABLE_LLM", "1")
    monkeypatch.setattr(summary_mod.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network call"))
    assert build_report(df).summary_source == summary_mod.OFFLINE["en"]
