"""Data model for a SolNexus on-chain alert.

Two shapes are supported and both normalize into this single model:

  * Generic "rich" alert (the documented trade-plan shape with a ``plan``
    block: bias, tp_ladder, size_pct, invalidators, ...).
  * Live API alert from ``GET /api/v1/alerts/next-actions`` -- flat fields
    (``type``, ``recommended_action``, ``confidence_score`` on a 0-100 scale,
    ``token`` as a bare symbol string + ``token_mint``, ...).

``parse_alert`` (in adapter.py) auto-detects which one you pass. The
direction mapping for live ``type`` values is copied verbatim from the
SolNexus backend (``alert_poller._signal_direction_from_alert``):

    price_surge / smart_buy  -> bullish (long)
    price_drop  / smart_sell  -> bearish (short)
    anything else               -> neutral
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Bias(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    CAUTIOUS = "cautious"


class SignalType(str, Enum):
    # generic rich-alert types
    WHALE_FLOW = "whale_flow"
    POOL_SHIFT = "pool_shift"
    BREAKOUT = "breakout"
    NEW_PAIR = "new_pair"
    # live /api/v1/alerts/next-actions types
    PRICE_SURGE = "price_surge"
    PRICE_DROP = "price_drop"
    VOLUME_SPIKE = "volume_spike"
    SMART_BUY = "smart_buy"
    SMART_SELL = "smart_sell"
    STABLE_SWAP = "stable_swap"
    UNKNOWN = "unknown"


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
    # Free-form carry-through for fields the live API sends but the rich model
    # does not model explicitly (recommended_action, risk_level, rationale, ...).
    # Also carries ``api_source=True`` for live-API alerts so the converter can
    # apply the swap-only gate without affecting generic alerts.
    meta: Dict[str, Any] = field(default_factory=dict)
