import json
import os

from solnexus_adapter import (
    AdapterError,
    parse_alert,
    signals_from_api_response,
    signals_from_file,
    to_freqtrade_signal,
)
from solnexus_adapter.schema import Bias

HERE = os.path.dirname(__file__)
EXAMPLE = os.path.join(HERE, "..", "example_alert.json")
FIXTURE = os.path.join(HERE, "fixtures", "next_actions_sample.json")


def test_parse_example():
    a = parse_alert(json.load(open(EXAMPLE)))
    assert a.token.symbol == "BONK"
    assert 0 <= a.ml_score <= 100
    assert a.plan.bias is Bias.BULLISH
    assert a.plan.tp_ladder[0].pct == 0.05


def test_signal_long():
    a = parse_alert(json.load(open(EXAMPLE)))
    s = to_freqtrade_signal(a)
    assert s is not None
    assert s.pair == "BONK/USDT"
    assert s.signal == 1
    assert s.stake_pct == a.plan.size_pct
    assert s.tag.startswith("solnexus:")


def test_min_score_filter():
    raw = json.load(open(EXAMPLE))
    raw["ml_score"] = 10
    a = parse_alert(raw)
    assert to_freqtrade_signal(a, min_score=55) is None


def test_invalid_score_raises():
    raw = json.load(open(EXAMPLE))
    raw["ml_score"] = 200
    try:
        parse_alert(raw)
        assert False, "expected AdapterError"
    except AdapterError:
        pass


def test_signals_from_file():
    sigs = signals_from_file(EXAMPLE)
    assert len(sigs) == 1
    assert sigs[0].side == "long"


def test_field_remap():
    raw = json.load(open(EXAMPLE))
    raw2 = {
        "signal": {"ml": 78},
        "token": raw["token"],
        "alert_id": "x",
        "confidence": 0.9,
        "signal_type": "whale_flow",
        "plan": raw["plan"],
    }
    fm = {"ml_score": "signal.ml"}
    a = parse_alert(raw2, field_map=fm)
    assert a.ml_score == 78


# --- Live API (`/alerts/next-actions`) mapping ---
def test_api_direction_mapping():
    resp = json.load(open(FIXTURE))
    items = resp["data"]["items"]
    assert len(items) == 18
    parsed = [parse_alert(it) for it in items]
    assert all(0 <= p.ml_score <= 100 for p in parsed)
    assert all(0.0 <= p.confidence <= 1.0 for p in parsed)

    drop = next(p for p in parsed if p.signal_type.value == "price_drop")
    assert drop.plan.bias is Bias.BEARISH
    surge = next(p for p in parsed if p.signal_type.value == "price_surge")
    assert surge.plan.bias is Bias.BULLISH


def test_confidence_normalized():
    resp = json.load(open(FIXTURE))
    for it in resp["data"]["items"]:
        a = parse_alert(it)
        assert 0.0 <= a.confidence <= 1.0
        assert abs(a.confidence * 100 - a.ml_score) <= 1.0


def test_watch_filtered_out():
    resp = json.load(open(FIXTURE))
    watch = next(
        it for it in resp["data"]["items"]
        if it["recommended_action"] == "watch"
    )
    assert to_freqtrade_signal(parse_alert(watch)) is None


def test_signals_from_api_response_counts():
    resp = json.load(open(FIXTURE))
    actionable = [
        it for it in resp["data"]["items"]
        if it["recommended_action"] == "swap"
    ]
    sigs = signals_from_api_response(resp, min_score=0)
    assert len(sigs) == len(actionable)
    assert all(s.side in ("long", "short") for s in sigs)


def test_swap_items_become_long_signals():
    # In this live snapshot every actionable alert is price_surge -> long.
    resp = json.load(open(FIXTURE))
    sigs = signals_from_api_response(resp, min_score=0)
    assert len(sigs) == 7
    assert all(s.side == "long" and s.signal == 1 for s in sigs)


def test_drop_swap_is_short():
    # Synthetic: prove the short path works even though the live
    # snapshot had no price_drop+swap alerts.
    item = {
        "alert_id": "x",
        "token": "BONK",
        "token_mint": "MintX",
        "type": "price_drop",
        "recommended_action": "swap",
        "confidence_score": 80.0,
        "created_at_epoch": 1784025818,
    }
    s = to_freqtrade_signal(parse_alert(item))
    assert s is not None
    assert s.side == "short" and s.signal == -1
    assert s.pair == "BONK/USDT"


if __name__ == "__main__":
    for fn in (
        test_parse_example,
        test_signal_long,
        test_min_score_filter,
        test_invalid_score_raises,
        test_signals_from_file,
        test_field_remap,
        test_api_direction_mapping,
        test_confidence_normalized,
        test_watch_filtered_out,
        test_signals_from_api_response_counts,
        test_swap_items_become_long_signals,
        test_drop_swap_is_short,
    ):
        fn()
    print("ALL OK")
