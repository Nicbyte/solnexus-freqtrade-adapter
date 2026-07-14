"""Example freqtrade strategy that consumes SolNexus adapter output.

This is a SCAFFOLD showing the bridge, not a profitable strategy. Drop it in
user_data/strategies/, point SOLNEXUS_SIGNAL_FILE at the JSON your pipeline
writes (via solnexus_adapter.signals_from_file), and tune to your risk model.

Requires freqtrade:  pip install freqtrade
"""
import os

try:
    from freqtrade.strategy import IStrategy
except ImportError:  # pragma: no cover - example only
    IStrategy = object

from solnexus_adapter import signals_from_file

SIGNAL_FILE = os.environ.get("SOLNEXUS_SIGNAL_FILE", "solnexus_signals.json")
MIN_SCORE = int(os.environ.get("SOLNEXUS_MIN_SCORE", "55"))


class SolnexusBridgeStrategy(IStrategy):
    # Conservative defaults — replace with your own risk model.
    stoploss = -0.05
    timeframe = "5m"
    minimal_roi = {"0": 0.05, "30": 0.03, "60": 0.015}

    def populate_entry_trend(self, dataframe, metadata):
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        try:
            sigs = signals_from_file(SIGNAL_FILE, min_score=MIN_SCORE)
        except FileNotFoundError:
            return dataframe
        pair = metadata["pair"]
        for s in sigs:
            if s.pair != pair:
                continue
            if s.side == "long":
                dataframe.loc[:, "enter_long"] = 1
            elif s.side == "short":
                dataframe.loc[:, "enter_short"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe
