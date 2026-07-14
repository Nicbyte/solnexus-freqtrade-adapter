"""Core conversion logic: SolNexus alert -> freqtrade signal."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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

QUOTE = "USDT"  # stake-currency quote; override per deployment

# Live API ``type`` values that carry a definite direction, copied from the
# SolNexus backend (alert_poller._signal_direction_from_alert).
_BULLISH_TYPES = {"price_surge", "smart_buy"}
_BEARISH_TYPES = {"price_drop", "smart_sell"}
# Fields that identify a live /api/v1/alerts/next-actions payload.
_API_MARKERS = ("confidence_score", "recommended_action", "type")
_SIGNAL_TYPE_VALUES = {s.value for s in SignalType}


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
    """Validate and normalize a raw SolNexus alert dict into a SolnexusAlert.

    Auto-detects the live API shape (``GET /api/v1/alerts/next-actions``)
    vs the generic rich shape and routes to the right parser. Pass
    ``field_map`` only for the generic shape when your API uses different key
    names.
    """
    if isinstance(raw, dict) and any(k in raw for k in _API_MARKERS):
        return _parse_api_alert(raw)
    return _parse_generic_alert(raw, field_map)


def _parse_api_alert(raw: Dict[str, Any]) -> SolnexusAlert:
    """Map a live ``next-actions`` item into the normalized model."""
    type_ = str(raw.get("type") or "").strip().lower()
    rec = str(raw.get("recommended_action") or "watch").strip().lower()

    if type_ in _BULLISH_TYPES:
        bias = Bias.BULLISH
    elif type_ in _BEARISH_TYPES:
        bias = Bias.BEARISH
    else:
        bias = Bias.NEUTRAL

    score_raw = float(raw.get("confidence_score", 0) or 0)
    ml_score = int(round(score_raw))
    if not (0 <= ml_score <= 100):
        raise AdapterError(f"confidence_score out of range: {score_raw}")
    confidence = round(score_raw / 100.0, 4)

    tok_raw = raw.get("token")
    if isinstance(tok_raw, dict):
        symbol = str(tok_raw.get("symbol", "")).upper()
        mint = tok_raw.get("mint")
    else:
        symbol = str(tok_raw or "").upper()
        mint = raw.get("token_mint")
    if not symbol:
        raise AdapterError("token symbol is required")

    ts = raw.get("created_at_epoch")
    received_at = (
        datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
        if ts is not None
        else None
    )

    invalidators = (
        [raw["invalidation_condition"]] if raw.get("invalidation_condition") else []
    )
    plan = Plan(
        bias=bias,
        entry_trigger=type_ or "",
        size_pct=0.0,
        tp_ladder=[],
        hard_stop_pct=0.05,
        invalidators=invalidators,
        review_windows=["+15m", "+1h", "+4h"],
    )

    signal_type = (
        SignalType(type_) if type_ in _SIGNAL_TYPE_VALUES else SignalType.UNKNOWN
    )

    meta = {
        "api_source": True,
        "recommended_action": rec,
        "confidence_label": raw.get("confidence_label"),
        "risk_level": raw.get("risk_level"),
        "source": raw.get("source"),
        "rationale": raw.get("action_rationale"),
        "age_minutes": raw.get("age_minutes"),
        "signal_type_raw": type_,
    }

    return SolnexusAlert(
        alert_id=str(raw.get("alert_id", "")),
        token=Token(symbol=symbol, mint=mint),
        ml_score=ml_score,
        confidence=confidence,
        signal_type=signal_type,
        plan=plan,
        context=Context(),
        received_at=received_at,
        meta=meta,
    )


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


def _parse_generic_alert(
    raw: Dict[str, Any], field_map: Optional[Dict[str, str]] = None
) -> SolnexusAlert:
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
    default_stake_pct: float = 0.1,
) -> Optional[FreqtradeSignal]:
    """Convert an alert into a freqtrade signal.

    Returns None when:
      * ``ml_score < min_score`` (noise filter; default 55 matches the
        SolNexus high-conviction floor), or
      * the alert came from the live API AND its ``recommended_action`` is not
        ``"swap"`` (``watch``/``ignore`` are monitor-only, never a trade).
        Generic rich alerts have no ``recommended_action`` and skip this gate.

    The live API reports ``confidence_score`` on a 0-100 scale; it is
    normalized to 0-1 on the model, so ``min_score`` stays on the 0-100
    scale everywhere.
    """
    if alert.ml_score < min_score:
        return None
    if alert.meta.get("api_source") and alert.meta.get("recommended_action") != "swap":
        return None

    side = "long" if alert.plan.bias is Bias.BULLISH else (
        "short" if alert.plan.bias is Bias.BEARISH else "long"
    )
    signal = 1 if side == "long" else -1
    tp = alert.plan.tp_ladder[0].pct if alert.plan.tp_ladder else 0.05
    stake = alert.plan.size_pct if alert.plan.size_pct > 0 else default_stake_pct

    return FreqtradeSignal(
        pair=f"{alert.token.symbol}/{quote}",
        side=side,
        signal=signal,
        stake_pct=stake,
        take_profit=tp,
        stop_loss=-abs(alert.plan.hard_stop_pct),
        tag=f"solnexus:{alert.alert_id}",
        metadata={
            "ml_score": alert.ml_score,
            "confidence": alert.confidence,
            "bias": alert.plan.bias.value,
            "signal_type": alert.signal_type.value,
            "recommended_action": alert.meta.get("recommended_action"),
            "confidence_label": alert.meta.get("confidence_label"),
            "risk_level": alert.meta.get("risk_level"),
            "rationale": alert.meta.get("rationale"),
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


def signals_from_api_response(
    response: Dict[str, Any],
    quote: str = QUOTE,
    min_score: int = 55,
    **kw: Any,
) -> List[FreqtradeSignal]:
    """Parse a raw ``GET /api/v1/alerts/next-actions`` JSON response.

    ``response`` is the full body: ``{"status": "ok", "data": {"items": [...]}}``.
    Returns only actionable freqtrade signals (the backend emits trades only on
    ``recommended_action == "swap"``; ``watch``/``ignore`` are filtered out).
    Malformed items are skipped rather than raising, so one bad alert can't
    sink the batch.
    """
    data = response.get("data", {}) if isinstance(response, dict) else {}
    items = data.get("items", []) if isinstance(data, dict) else []
    out: List[FreqtradeSignal] = []
    for it in items:
        try:
            a = parse_alert(it)
        except AdapterError:
            continue
        s = to_freqtrade_signal(a, quote=quote, min_score=min_score, **kw)
        if s is not None:
            out.append(s)
    return out
