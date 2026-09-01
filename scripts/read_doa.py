#!/usr/bin/env python3
"""Print timestamped XVF3800 direction-of-arrival observations as JSON."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from ears import DeviceNotFoundError, XVF3800, XVF3800Error


def parse_args() -> argparse.Namespace:
    """Parse polling options from the command line."""
    parser = argparse.ArgumentParser(
        description="Read passive direction-of-arrival telemetry from XVF3800.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between observations; default: 1.0.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Read one observation and exit.",
    )
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    return args


def emit_observation(device: XVF3800) -> None:
    """Read one observation and emit a stable JSON record."""
    observation = device.direction_of_arrival()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "azimuth_degrees": observation.azimuth_degrees,
        "speech_detected": observation.speech_detected,
    }
    print(json.dumps(record, separators=(",", ":")), flush=True)


def main() -> int:
    """Run the DoA polling loop until completion or interruption."""
    args = parse_args()
    try:
        with XVF3800.open() as device:
            while True:
                emit_observation(device)
                if args.once:
                    return 0
                time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130
    except (DeviceNotFoundError, XVF3800Error) as error:
        print(json.dumps({"error": str(error)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
