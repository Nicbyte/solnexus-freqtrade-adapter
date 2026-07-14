"""Data model for a SolNexus on-chain alert.

Field names match the documented SolNexus alert shape. If the live API uses
different keys, pass a `field_map` to `parse_alert` (see adapter.py) rather than
forking this model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Bias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    CAUTIOUS = "cautious"


class SignalType(str, Enum):
    WHALE_FLOW = "whale_flow"
    POOL_SHIFT = "pool_shift"
    BREAKOUT = "breakout"
    NEW_PAIR = "new_pair"


@dataclass
class TakeProfit:
    pct: float
    close_fraction: float


@dataclass
class Plan:
    bias: Bias
    entry_trigger: str
    size_pct: float
    tp_ladder: List[TakeProfit] = field(default_factory=list)
    hard_stop_pct: float = 0.05
    invalidators: List[str] = field(default_factory=list)
    review_windows: List[str] = field(default_factory=lambda: ["+15m", "+1h", "+4h"])


@dataclass
class Context:
    pool: Optional[str] = None
    size_usd: Optional[float] = None
    baseline_deviation_pct: Optional[float] = None
    follow_through_blocks: Optional[int] = None


@dataclass
class Token:
    symbol: str
    mint: Optional[str] = None
    chain: str = "solana"


@dataclass
class SolnexusAlert:
    alert_id: str
    token: Token
    ml_score: int          # 0-100
    confidence: float      # 0.0-1.0
    signal_type: SignalType
    plan: Plan
    context: Context = field(default_factory=Context)
    received_at: Optional[str] = None
