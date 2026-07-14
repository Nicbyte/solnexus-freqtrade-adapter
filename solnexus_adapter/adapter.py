"""Core conversion logic: SolNexus alert -> freqtrade signal."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .schema import (
    Bias,
    Context,
    Plan,
    SignalType,
    SolnexusAlert,
    TakeProfit,
    Token,
)

# Map abstract keys -> live API JSON keys. Override per deployment if your
# SolNexus API uses different field names; no code fork required.
DEFAULT_FIELD_MAP: Dict[str, str] = {
    "alert_id": "alert_id",
    "received_at": "received_at",
    "token": "token",
    "ml_score": "ml_score",
    "confidence": "confidence",
    "signal_type": "signal_type",
    "plan": "plan",
    "context": "context",
}

QUOTE = "USDT"  # stake-currency quote; override per deployment


class AdapterError(ValueError):
    """Raised when an alert payload cannot be parsed/validated."""


def _get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for p in path.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def parse_alert(
    raw: Dict[str, Any], field_map: Optional[Dict[str, str]] = None
) -> SolnexusAlert:
    """Validate and normalize a raw SolNexus alert dict into a SolnexusAlert."""
    fm = field_map or DEFAULT_FIELD_MAP

    def g(key: str, default: Any = None) -> Any:
        src = fm.get(key, key)
        return _get(raw, src, default)

    try:
        token_raw = g("token") or {}
        token = Token(
            symbol=str(token_raw.get("symbol", "")).upper(),
            mint=token_raw.get("mint"),
            chain=token_raw.get("chain", "solana"),
        )
        if not token.symbol:
            raise AdapterError("token.symbol is required")

        plan_raw = g("plan") or {}
        tp_raw = plan_raw.get("tp_ladder", []) or []
        tp = [
            TakeProfit(
                pct=float(t.get("pct", 0.0)),
                close_fraction=float(t.get("close_fraction", t.get("close", 1.0))),
            )
            for t in tp_raw
        ]
        plan = Plan(
            bias=Bias(plan_raw.get("bias", "neutral")),
            entry_trigger=str(plan_raw.get("entry_trigger", "")),
            size_pct=float(plan_raw.get("size_pct", 0.0)),
            tp_ladder=tp,
            hard_stop_pct=float(plan_raw.get("hard_stop_pct", 0.05)),
            invalidators=list(plan_raw.get("invalidators", []) or []),
            review_windows=list(plan_raw.get("review_windows", ["+15m", "+1h", "+4h"])),
        )

        ctx_raw = g("context") or {}
        context = Context(
            pool=ctx_raw.get("pool"),
            size_usd=ctx_raw.get("size_usd"),
            baseline_deviation_pct=ctx_raw.get("baseline_deviation_pct"),
            follow_through_blocks=ctx_raw.get("follow_through_blocks"),
        )

        score = int(g("ml_score", 0))
        if not (0 <= score <= 100):
            raise AdapterError(f"ml_score out of range: {score}")
        conf = float(g("confidence", 0.0))
        if not (0.0 <= conf <= 1.0):
            raise AdapterError(f"confidence out of range: {conf}")

        return SolnexusAlert(
            alert_id=str(g("alert_id", "")),
            token=token,
            ml_score=score,
            confidence=conf,
            signal_type=SignalType(g("signal_type", "whale_flow")),
            plan=plan,
            context=context,
            received_at=g("received_at"),
        )
    except (KeyError, ValueError, TypeError) as e:
        raise AdapterError(f"invalid SolNexus alert: {e}") from e


@dataclass
class FreqtradeSignal:
    pair: str
    side: str           # "long" | "short"
    signal: int         # freqtrade convention: 1 long, -1 short, 0 none
    stake_pct: float
    take_profit: float
    stop_loss: float
    tag: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def to_freqtrade_signal(
    alert: SolnexusAlert,
    quote: str = QUOTE,
    min_score: int = 55,
) -> Optional[FreqtradeSignal]:
    """Convert an alert into a freqtrade signal.

    Returns None when ml_score < min_score (noise filter). The default 55 aligns
    with SolNexus' long-entry threshold; tune to your risk model.
    """
    if alert.ml_score < min_score:
        return None

    side = "long" if alert.plan.bias is Bias.BULLISH else (
        "short" if alert.plan.bias is Bias.BEARISH else "long"
    )
    signal = 1 if side == "long" else -1
    tp = alert.plan.tp_ladder[0].pct if alert.plan.tp_ladder else 0.05

    return FreqtradeSignal(
        pair=f"{alert.token.symbol}/{quote}",
        side=side,
        signal=signal,
        stake_pct=alert.plan.size_pct,
        take_profit=tp,
        stop_loss=-abs(alert.plan.hard_stop_pct),
        tag=f"solnexus:{alert.alert_id}",
        metadata={
            "ml_score": alert.ml_score,
            "confidence": alert.confidence,
            "bias": alert.plan.bias.value,
            "signal_type": alert.signal_type.value,
            "invalidators": alert.plan.invalidators,
            "review_windows": alert.plan.review_windows,
        },
    )


def alerts_from_file(path: str, **kw: Any) -> List[SolnexusAlert]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return [parse_alert(a, **kw) for a in data]


def signals_from_file(
    path: str, quote: str = QUOTE, min_score: int = 55
) -> List[FreqtradeSignal]:
    return [
        s
        for a in alerts_from_file(path)
        if (s := to_freqtrade_signal(a, quote=quote, min_score=min_score)) is not None
    ]
