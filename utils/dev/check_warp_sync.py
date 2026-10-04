#!/usr/bin/env python3
"""Check the first 10.54 AU belt warp against client and server logs.

Both logs must cover the same run. The server logs whole-second timestamps;
allow two seconds for timestamp rounding and delivery latency.
"""

import argparse
import csv
from datetime import datetime, time, timezone
from pathlib import Path
import re


AU_METERS = 149597870700
REFERENCE_AU = 8.27
MAX_LAG_SECONDS = 2.0


def server_sample(path):
    pattern = re.compile(
        r"(\d\d:\d\d:\d\d) \[WarpTrace\] Destiny::Warp"
        r"(?:Accel|Cruise|Decel)\(\).*?with ([\d.]+) m left to go"
    )
    for line in path.read_text(errors="replace").splitlines():
        match = pattern.search(line)
        if match and abs(float(match.group(2)) / AU_METERS - REFERENCE_AU) < 0.01:
            return time.fromisoformat(match.group(1))
    raise ValueError("server log has no 8.27 AU warp sample")


def client_sample(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if ("Space::IndicateWarp" in row["message"]
                    and "Distance: 8.27 AU" in row["message"]):
                return datetime.fromisoformat(row["timestamp_utc"])
    raise ValueError("client log has no 8.27 AU warp sample")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server_log", type=Path)
    parser.add_argument("client_csv", type=Path)
    args = parser.parse_args()

    client_time = client_sample(args.client_csv)
    server_time = datetime.combine(
        client_time.date(), server_sample(args.server_log), timezone.utc
    )
    lag = (client_time - server_time).total_seconds()
    result = "FAIL" if abs(lag) >= MAX_LAG_SECONDS else "PASS"
    print(f"{result}: client/server warp progress offset {lag:.2f}s "
          f"(limit: {MAX_LAG_SECONDS:.0f}s)")
    return int(result == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
