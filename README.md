# solnexus-freqtrade-adapter

Bridge **[SolNexus Trade](https://solnexus.xyz)** ML-scored on-chain alerts into your **[freqtrade](https://www.freqtrade.io/)** bot.

SolNexus watches live Solana whale/pool flow, scores each event 0–100 with an ML model, and emits an AI trading plan (entry trigger, size, take-profit ladder, hard stop, invalidators). This adapter turns that alert into a freqtrade-compatible signal so you can act on on-chain context inside the bot stack you already run — without handing custody to anyone.

> **This is a connector, not a profitable strategy.** It moves signal context from SolNexus into freqtrade. It makes no return claims and ships no "secret alpha." You stay in control of execution and risk.

## Why

freqtrade users typically trade off exchange candles. SolNexus adds a layer most bots lack: on-chain *signal context* (who is moving, how big vs baseline, what the plan says). This repo is the thin, auditable glue between them.

## Install

```bash
pip install -e .
# optional, for the example strategy:
pip install freqtrade
```

## Quickstart

```python
from solnexus_adapter import signals_from_file

for s in signals_from_file("example_alert.json"):
    print(s.to_dict())
    # {'pair': 'BONK/USDT', 'side': 'long', 'signal': 1,
    #  'stake_pct': 2.0, 'take_profit': 0.05, 'stop_loss': -0.05,
    #  'tag': 'solnexus:cf7ceb5658cd439c', 'metadata': {...}}
```

Alerts below `min_score` (default 55, aligned with SolNexus' long-entry threshold) are filtered out as noise. Override per deployment:

```python
from solnexus_adapter import parse_alert, to_freqtrade_signal
alert = parse_alert(raw_alert)
sig = to_freqtrade_signal(alert, quote="USDT", min_score=60)
```

## Alert schema

| Field | Type | Notes |
|---|---|---|
| `alert_id` | str | unique id |
| `signal_type` | str | `whale_flow` \| `pool_shift` \| `breakout` \| `new_pair` |
| `ml_score` | int | 0–100 |
| `confidence` | float | 0.0–1.0 |
| `token.symbol` | str | e.g. `BONK` |
| `token.mint` | str? | Solana mint |
| `context` | obj | `pool`, `size_usd`, `baseline_deviation_pct`, `follow_through_blocks` |
| `plan.bias` | str | `bullish` \| `bearish` \| `neutral` \| `cautious` |
| `plan.entry_trigger` | str | human/ML-readable entry condition |
| `plan.size_pct` | float | stake % |
| `plan.tp_ladder` | list | `[{pct, close_fraction}]` |
| `plan.hard_stop_pct` | float | stop distance |
| `plan.invalidators` | list[str] | conditions that void the plan |
| `plan.review_windows` | list[str] | e.g. `["+15m","+1h","+4h"]` |

If your live SolNexus API uses different key names, pass a `field_map` to `parse_alert` — no code fork. See `tests/test_adapter.py::test_field_remap`.

## freqtrade wiring

`examples/freqtrade_strategy.py` is a scaffold `IStrategy` that reads the latest adapter output and emits entries. Set the path via `SOLNEXUS_SIGNAL_FILE` and noise floor via `SOLNEXUS_MIN_SCORE`. Tune to your own risk model — do not trade it untested.

## Built by SolNexus Trade

Solana-native execution layer: ML scores live on-chain alerts → hands off to a freqtrade bot for Jupiter on-chain execution, with a per-signal review loop (+15m/+1h/+4h). Wallet-native crypto checkout, no card gate.

**Founding access (waitlist + discounts):** https://linktr.ee/solnexushq

## License

MIT — see [LICENSE](LICENSE). Fork it, wire your own logic, send a PR.
