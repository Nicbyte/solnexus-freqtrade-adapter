import json
import os

from solnexus_adapter import (
    AdapterError,
    parse_alert,
    signals_from_file,
    to_freqtrade_signal,
)
from solnexus_adapter.schema import Bias

HERE = os.path.dirname(__file__)
EXAMPLE = os.path.join(HERE, "..", "example_alert.json")


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
    # Simulate a live API that nests score under "signal.ml".
    # Only override ml_score; all other keys keep their default names.
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


if __name__ == "__main__":
    test_parse_example()
    test_signal_long()
    test_min_score_filter()
    test_invalid_score_raises()
    test_signals_from_file()
    test_field_remap()
    print("ALL OK")
