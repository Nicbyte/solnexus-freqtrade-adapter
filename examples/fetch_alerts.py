#!/usr/bin/env python3
"""Pull live SolNexus next-actions and print freqtrade signals.

Usage:
    export SOLNEXUS_API_KEY=snx_xxx
    python3 examples/fetch_alerts.py [limit]

Zero external dependencies (uses urllib from the stdlib). Requires an
active Pro/Overmind subscription. Only ``recommended_action == "swap"``
alerts become signals; ``watch``/``ignore`` are monitor-only.
"""
import json
import os
import sys
import urllib.error
import urllib.request

# Allow running as a script without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solnexus_adapter import signals_from_api_response, write_alerts_file

# Default matches freqtrade_strategy.py's SOLNEXUS_SIGNAL_FILE, so the file the
# fetch step writes is exactly the one the strategy reads.
SIGNAL_FILE = os.environ.get("SOLNEXUS_SIGNAL_FILE", "solnexus_signals.json")

BASE_URL = "https://solnexus.xyz"


def main() -> int:
    key = os.environ.get("SOLNEXUS_API_KEY")
    if not key:
        sys.stderr.write("Set SOLNEXUS_API_KEY in the environment.\n")
        return 2

    limit = sys.argv[1] if len(sys.argv) > 1 else "20"
    url = f"{BASE_URL}/api/v1/alerts/next-actions?limit={limit}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"HTTP {e.code}: {e.read().decode()[:300]}\n")
        return 1

    alerts = body.get("data", {}).get("items", [])
    signals = signals_from_api_response(body, min_score=55)
    print(f"Fetched {len(alerts)} alerts -> {len(signals)} actionable signals\n")
    for s in signals:
        print(json.dumps(s.to_dict(), indent=2))

    n = write_alerts_file(SIGNAL_FILE, alerts)
    print(f"\nWrote {n} raw alerts -> {SIGNAL_FILE}")
    print("freqtrade_strategy.py reads this file via SOLNEXUS_SIGNAL_FILE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
