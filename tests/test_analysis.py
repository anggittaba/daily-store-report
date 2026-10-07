import pandas as pd

from store_report.analysis import (Thresholds, detect_anomalies, overall_kpis, region_summary, store_metrics,
                                   stores_needing_attention)

END = pd.Timestamp("2026-10-06")


def _flags(df, date=END, th=None, lang="en"):
    m = store_metrics(df, date, th)
    return m, detect_anomalies(m, th, lang)


def test_all_planted_problems_on_last_day_are_found(sample):
    df, injected = sample
    _, an = _flags(df)
    found = set(zip(an["store_code"], an["kind"]))
    planted = {(a.store_code, a.kind) for a in injected if pd.Timestamp(a.date) == END}
    assert planted == {("ST007", "sales_drop"), ("ST013", "pos_offline"),
                       ("ST018", "stockout_spike"), ("ST011", "sales_spike")}
    assert planted <= found


def test_no_false_positives_on_last_day(sample):
    df, _ = sample
    _, an = _flags(df)
    assert set(an["store_code"]) == {"ST007", "ST013", "ST018", "ST011"}


def test_historical_planted_problems_are_found(sample):
    df, injected = sample
    for a in injected:
        d = pd.Timestamp(a.date)
        if d == END:
            continue
        _, an = _flags(df, d)
        assert a.store_code in set(an["store_code"]), (a.store_code, a.kind, d)


def test_severity_and_order(sample):
    df, _ = sample
    _, an = _flags(df)
    att = stores_needing_attention(an)
    assert [a["severity"] for a in att] == ["critical", "critical", "high", "medium"]
    sev = dict(zip(an["store_code"], an["severity"]))
    assert sev["ST013"] == "critical" and sev["ST007"] == "critical"


def test_clean_data_has_no_flags():
    from store_report.data_generator import generate_sales_data
    df, _ = generate_sales_data(end_date="2026-10-06", inject_anomalies=False)
    _, an = _flags(df)
    assert an.empty


def test_thresholds_change_sensitivity(sample):
    df, _ = sample
    _, loose = _flags(df, th=Thresholds(drop_pct=0.10, z_threshold=1.5))
    _, strict = _flags(df, th=Thresholds(drop_pct=0.60, z_threshold=6.0))
    assert len(loose) > len(strict)


def test_reasons_are_english_by_default_and_indonesian_on_request(sample):
    df, _ = sample
    _, en = _flags(df)
    _, idn = _flags(df, lang="id")
    r_en = en.set_index("store_code").loc["ST007", "reason"]
    r_id = idn.set_index("store_code").loc["ST007", "reason"]
    assert "below the 7-day average" in r_en and "Rp 6.6M" in r_en.replace("\u00a0", " ")
    assert "rata-rata 7 hari" in r_id


def test_kpis_and_regions(sample):
    df, _ = sample
    m = store_metrics(df, END)
    k = overall_kpis(df, m, END)
    assert k["stores"] == 20 and k["stores_trading"] == 19
    assert k["sales"] == df.loc[df["date"] == END, "sales"].sum()
    reg = region_summary(m)
    assert reg["share"].sum() == __import__("pytest").approx(1.0)
    assert reg["stores"].sum() == 20
