"""Short written summary of the day: optional LLM, rule-based fallback.

* OPENAI_API_KEY set  -> OpenAI Chat Completions (OPENAI_MODEL, default gpt-4o-mini)
* GEMINI_API_KEY set  -> Gemini generateContent (GEMINI_MODEL, default gemini-2.5-flash)
* neither, or any error/timeout -> rule-based summary, fully offline

Only the aggregated figures and the list of flagged stores are sent to the
LLM, never the uploaded file. STORE_REPORT_DISABLE_LLM=1 forces the offline
summary even when a key is set.
"""

from __future__ import annotations

import json
import os
import urllib.request

from .i18n import date_long, money, money_short, number, pct, severity_label, weekday

TIMEOUT = 30


def build_context(kpis: dict, attention: list[dict], region, lang: str = "en") -> dict:
    """Facts used by both the rule-based and the LLM summary (already formatted)."""
    L = lang
    return {
        "lang": L,
        "date": date_long(kpis["date"], L),
        "weekday": weekday(kpis["date"], L),
        "stores": kpis["stores"],
        "stores_trading": kpis["stores_trading"],
        "sales": money_short(kpis["sales"], L),
        "transactions": number(kpis["transactions"], 0, L),
        "avg_basket": money(kpis["avg_basket"], L),
        "vs_avg_7d": pct(kpis["vs_avg_7d"], lang=L),
        "vs_last_week": pct(kpis["vs_last_week"], lang=L),
        "vs_yesterday": pct(kpis["vs_yesterday"], lang=L),
        "stockouts": number(kpis["stockouts"], 0, L),
        "stockouts_avg_7d": number(kpis["stockouts_avg_7d"], 1, L),
        "top_store": kpis["top_store"] and {"name": kpis["top_store"]["name"],
                                            "sales": money_short(kpis["top_store"]["sales"], L)},
        "top_region": kpis["top_region"] and {"name": kpis["top_region"]["name"],
                                              "sales": money_short(kpis["top_region"]["sales"], L),
                                              "share": pct(kpis["top_region"]["share"], signed=False, decimals=0, lang=L)},
        "regions": [{"name": r["region"], "sales": money_short(r["sales"], L), "vs_avg_7d": pct(r["vs_avg_7d"], lang=L)}
                    for _, r in region.iterrows()],
        "top_categories": kpis["top_categories"],
        "flagged": [{"store": a["store_name"], "region": a["region"], "severity": severity_label(a["severity"], L).lower(),
                     "reasons": a["reasons"], "actions": a["actions"]} for a in attention],
        "_vs_avg_7d": kpis["vs_avg_7d"],
        "_vs_last_week": kpis["vs_last_week"],
    }


def _direction_en(v, label: str) -> str:
    if v is None or v != v:
        return ""
    if abs(v) < 0.005:
        return f"level with {label}"
    return f"{pct(abs(v), signed=False)} {'above' if v > 0 else 'below'} {label}"


def _direction_id(v, label: str) -> str:
    if v is None or v != v:
        return ""
    if abs(v) < 0.005:
        return f"setara {label}"
    return f"{'naik' if v > 0 else 'turun'} {pct(abs(v), signed=False, lang='id')} dari {label}"


def _join(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    conj = " and " if lang == "en" else " dan "
    return ", ".join(items[:-1]) + conj + items[-1]


def rule_based_summary(c: dict) -> str:
    if c["lang"] == "id":
        return _rule_based_id(c)
    parts = []
    cmp_ = [x for x in (_direction_en(c["_vs_avg_7d"], "the 7-day average"),
                        _direction_en(c["_vs_last_week"], f"last {c['weekday']}")) if x]
    p1 = (f"{c['stores']} stores sold {c['sales']} across {c['transactions']} transactions on {c['date']}"
          + (f", {_join(cmp_, 'en')}" if cmp_ else "") + f". The average basket was {c['avg_basket']}.")
    parts.append(p1)
    p2 = []
    if c["top_region"]:
        r = c["top_region"]
        p2.append(f"{r['name']} was the largest region at {r['sales']} ({r['share']} of sales).")
    if c["top_store"]:
        p2.append(f"{c['top_store']['name']} had the highest sales ({c['top_store']['sales']}).")
    if c["top_categories"]:
        p2.append(f"{_join(c['top_categories'], 'en')} appeared most often in stores’ top three categories.")
    if p2:
        parts.append(" ".join(p2))
    flagged = c["flagged"]
    if not flagged:
        parts.append("No store crossed a detection threshold. Every store is within its usual range "
                     "compared with its own previous 7 days.")
        return "\n\n".join(parts)
    n = len(flagged)
    parts.append(f"{n} {'store needs' if n == 1 else 'stores need'} attention. "
                 f"Stock-outs totalled {c['stockouts']} items against a 7-day average of {c['stockouts_avg_7d']}.")
    parts.append("\n".join(f"- {f['store']} ({f['severity']}): {f['reasons'][0]}" for f in flagged))
    parts.append("Next steps:\n" + "\n".join(f"- {f['store']}: {f['actions'][0]}" for f in flagged[:4]))
    return "\n\n".join(parts)


def _rule_based_id(c: dict) -> str:
    parts = []
    cmp_ = [x for x in (_direction_id(c["_vs_avg_7d"], "rata-rata 7 hari"),
                        _direction_id(c["_vs_last_week"], f"{c['weekday']} lalu")) if x]
    parts.append(f"Pada {c['date']}, {c['stores']} toko menjual {c['sales']} dari {c['transactions']} transaksi"
                 + (f", {_join(cmp_, 'id')}" if cmp_ else "") + f". Rata-rata belanja {c['avg_basket']} per transaksi.")
    p2 = []
    if c["top_region"]:
        r = c["top_region"]
        p2.append(f"{r['name']} menjadi wilayah terbesar dengan {r['sales']} ({r['share']} dari total).")
    if c["top_store"]:
        p2.append(f"Penjualan tertinggi: {c['top_store']['name']} ({c['top_store']['sales']}).")
    if c["top_categories"]:
        p2.append(f"Kategori yang paling sering masuk tiga besar: {_join(c['top_categories'], 'id')}.")
    if p2:
        parts.append(" ".join(p2))
    flagged = c["flagged"]
    if not flagged:
        parts.append("Tidak ada toko yang melewati ambang deteksi. Semua toko berada dalam rentang biasanya "
                     "dibanding 7 hari sebelumnya.")
        return "\n\n".join(parts)
    parts.append(f"{len(flagged)} toko perlu perhatian. Total stock-out {c['stockouts']} item "
                 f"(rata-rata 7 hari: {c['stockouts_avg_7d']}).")
    parts.append("\n".join(f"- {f['store']} ({f['severity']}): {f['reasons'][0]}" for f in flagged))
    parts.append("Langkah berikutnya:\n" + "\n".join(f"- {f['store']}: {f['actions'][0]}" for f in flagged[:4]))
    return "\n\n".join(parts)


PROMPTS = {
    "en": """You write the daily sales summary for an area manager of a minimarket chain.
Write plain, specific English, at most 180 words. Use ONLY the facts in the JSON below and do not
invent numbers or causes. No headings, no emoji, no exclamation marks, no filler words such as
"seamless", "leverage", "robust" or "insights". Format: one short paragraph on overall sales,
one short paragraph on regions and categories, then a "- " bullet per flagged store with the reason,
then a line "Next steps:" followed by 2-4 "- " bullets with concrete actions.

DATA:
{data}
""",
    "id": """Kamu menulis ringkasan penjualan harian untuk manajer area jaringan minimarket.
Tulis dalam Bahasa Indonesia yang lugas dan spesifik, maksimal 180 kata. Gunakan HANYA fakta di JSON
berikut, jangan mengarang angka atau penyebab. Tanpa judul, tanpa emoji, tanpa tanda seru, tanpa kata
klise. Format: satu paragraf pendek tentang penjualan, satu paragraf pendek tentang wilayah dan kategori,
lalu satu poin "- " per toko yang ditandai beserta alasannya, lalu baris "Langkah berikutnya:" dan
2-4 poin "- " berisi tindakan konkret.

DATA:
{data}
""",
}


def _post_json(url: str, payload: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 (fixed https endpoints)
        return json.loads(resp.read().decode())


def _call_openai(prompt: str, key: str) -> tuple[str, str]:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    data = _post_json(f"{base}/chat/completions",
                      {"model": model, "temperature": 0.2, "messages": [{"role": "user", "content": prompt}]},
                      {"Authorization": f"Bearer {key}"})
    return data["choices"][0]["message"]["content"].strip(), f"OpenAI {model}"


def _call_gemini(prompt: str, key: str) -> tuple[str, str]:
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    data = _post_json(url, {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}},
                      {"x-goog-api-key": key})
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    return text.strip(), f"Gemini {model}"


def llm_provider() -> str | None:
    """Which provider would be used right now (None = offline)."""
    if os.getenv("STORE_REPORT_DISABLE_LLM", "").lower() in ("1", "true", "yes"):
        return None
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    return None


OFFLINE = {"en": "the rule-based template (no API key set)", "id": "template berbasis aturan (tanpa API key)"}
FALLBACK = {"en": "the rule-based template ({p} request failed: {e})",
            "id": "template berbasis aturan (permintaan ke {p} gagal: {e})"}


def generate_summary(ctx: dict, use_llm: bool = True) -> tuple[str, str]:
    """Return (summary_text, source_label)."""
    lang = ctx.get("lang", "en")
    provider = llm_provider() if use_llm else None
    if provider:
        facts = {k: v for k, v in ctx.items() if not k.startswith("_") and k != "lang"}
        prompt = PROMPTS[lang].format(data=json.dumps(facts, ensure_ascii=False, indent=1))
        try:
            if provider == "openai":
                return _call_openai(prompt, os.environ["OPENAI_API_KEY"])
            return _call_gemini(prompt, os.environ["GEMINI_API_KEY"])
        except Exception as exc:  # network error, quota, bad key … never break the report
            name = "OpenAI" if provider == "openai" else "Gemini"
            return rule_based_summary(ctx), FALLBACK[lang].format(p=name, e=type(exc).__name__)
    return rule_based_summary(ctx), OFFLINE[lang]
