"""Closed-loop smoke test: fetch (write) -> file -> strategy reads entries.

Runs with zero external dependencies (no freqtrade, no pandas) so it stays
green in CI. The example strategy falls back to ``IStrategy = object`` when
freqtrade is absent; we drive ``populate_entry_trend`` with a tiny dataframe
stub that mimics the slice-assignment the real pandas path uses
(``dataframe.loc[:, "enter_long"] = 1``).
"""
import importlib.util
import os
import sys
import tempfile

from solnexus_adapter import signals_from_file, write_alerts_file

HERE = os.path.dirname(os.path.abspath(__file__))
STRATEGY_PATH = os.path.join(HERE, "..", "examples", "freqtrade_strategy.py")


class FakeDataFrame:
    """Minimal stand-in for a freqtrade pandas DataFrame."""

    def __init__(self) -> None:
        self._cols: dict = {}
        # Mirror how the real strategy assigns: dataframe.loc[:, "col"] = v
        self.loc = self

    def __setitem__(self, key, value):
        # Support both ``df["col"] = v`` and ``df.loc[:, "col"] = v``.
        col = key[1] if isinstance(key, tuple) else key
        self._cols[col] = value

    def __getitem__(self, key):
        return self._cols[key]


def _sample_items() -> list:
    # One long (price_surge+swap) and one short (price_drop+swap) alert.
    return [
        {
            "alert_id": "smoke_long",
            "token": "SOL",
            "token_mint": "So11111111111111111111111111111111111111112",
            "type": "price_surge",
            "recommended_action": "swap",
            "confidence_score": 82.0,
            "created_at_epoch": 1784025818,
        },
        {
            "alert_id": "smoke_short",
            "token": "BONK",
            "token_mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "type": "price_drop",
            "recommended_action": "swap",
            "confidence_score": 79.0,
            "created_at_epoch": 1784025818,
        },
    ]


def _load_strategy():
    # Env must be set BEFORE importing: SIGNAL_FILE/MIN_SCORE are read at import.
    spec = importlib.util.spec_from_file_location(
        "freqtrade_strategy_smoke", STRATEGY_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["freqtrade_strategy_smoke"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_write_then_read_roundtrip():
    items = _sample_items()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "solnexus_signals.json")
        n = write_alerts_file(path, items)
        assert n == 2
        sigs = signals_from_file(path, min_score=55)
        assert len(sigs) == 2
        by_pair = {s.pair: s for s in sigs}
        assert by_pair["SOL/USDT"].side == "long"
        assert by_pair["SOL/USDT"].signal == 1
        assert by_pair["BONK/USDT"].side == "short"
        assert by_pair["BONK/USDT"].signal == -1


def test_bridge_strategy_sets_entries():
    items = _sample_items()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "solnexus_signals.json")
        write_alerts_file(path, items)
        os.environ["SOLNEXUS_SIGNAL_FILE"] = path
        os.environ["SOLNEXUS_MIN_SCORE"] = "55"
        strat = _load_strategy().SolnexusBridgeStrategy()

        out = strat.populate_entry_trend(FakeDataFrame(), {"pair": "SOL/USDT"})
        assert out["enter_long"] == 1
        assert out["enter_short"] == 0

        out = strat.populate_entry_trend(FakeDataFrame(), {"pair": "BONK/USDT"})
        assert out["enter_short"] == 1
        assert out["enter_long"] == 0

        out = strat.populate_entry_trend(FakeDataFrame(), {"pair": "DOGE/USDT"})
        assert out["enter_long"] == 0
        assert out["enter_short"] == 0


def test_bridge_strategy_missing_file_is_safe():
    with tempfile.TemporaryDirectory() as d:
        os.environ["SOLNEXUS_SIGNAL_FILE"] = os.path.join(d, "missing.json")
        strat = _load_strategy().SolnexusBridgeStrategy()
        out = strat.populate_entry_trend(FakeDataFrame(), {"pair": "SOL/USDT"})
        # No crash, no entry when the signal file is absent.
        assert out["enter_long"] == 0
        assert out["enter_short"] == 0


if __name__ == "__main__":
    for fn in (
        test_write_then_read_roundtrip,
        test_bridge_strategy_sets_entries,
        test_bridge_strategy_missing_file_is_safe,
    ):
        fn()
    print("ALL OK")
