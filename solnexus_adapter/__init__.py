"""SolNexus Trade -> freqtrade adapter.

Bridges SolNexus ML-scored on-chain alerts into a freqtrade-compatible signal.
Zero hard dependencies (Python 3.9+ stdlib). The example freqtrade strategy
lives in examples/ and requires freqtrade itself.
"""
from .adapter import (
    AdapterError,
    FreqtradeSignal,
    alerts_from_file,
    parse_alert,
    signals_from_api_response,
    signals_from_file,
    to_freqtrade_signal,
)
from .schema import Bias, SolnexusAlert

__version__ = "0.1.0"
__all__ = [
    "AdapterError",
    "FreqtradeSignal",
    "alerts_from_file",
    "parse_alert",
    "signals_from_api_response",
    "signals_from_file",
    "to_freqtrade_signal",
    "Bias",
    "SolnexusAlert",
]
