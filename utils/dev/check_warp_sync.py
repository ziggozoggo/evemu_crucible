#!/usr/bin/env python3
"""Compare warp progress in server and client logs from the same run.

Match each warp command, then use the exponential deceleration segment to
compare *positions*, not the times when the UI effect and server Stop fire.
The median offset across warps absorbs clock skew; a single warp cannot
distinguish skew from desync. No server or client process is started.
"""

import argparse
import csv
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
import math
from pathlib import Path
import re
from statistics import median


AU_METERS = 149597870700
COMMAND_WINDOW_SECONDS = 3.0
MIN_DISTANCE_METERS = 10_000_000  # avoid destination/stop-distance rounding
MAX_DISTANCE_METERS = 10_000_000_000
MIN_SAMPLES = 3

SERVER_COMMAND = re.compile(r"(\d\d:\d\d:\d\d(?:\.\d+)?) \[WarpTrace\] Destiny::WarpTo\(\) toBubble:")
SERVER_START = re.compile(r"(\d\d:\d\d:\d\d(?:\.\d+)?) \[WarpTrace\] Destiny::InitWarp\(\): .* has initialized warp")
SERVER_DECEL = re.compile(r"(\d\d:\d\d:\d\d(?:\.\d+)?) \[WarpTrace\] Destiny::WarpDecel\(\).*?with ([\d.]+) m left")
CLIENT_COMMAND = re.compile(r"Action:\s+WarpTo \d+ - current: \d+ \((\d+),")
CLIENT_DISTANCE = re.compile(r"Space::IndicateWarp .*Distance: ([\d,]+(?:\.\d+)?) (AU|km|m)\b")


@dataclass
class Warp:
    command: datetime
    start: datetime | None = None
    distances: list[tuple[datetime, float]] = field(default_factory=list)


def server_warps(path: Path, date):
    warps = []
    for line in path.read_text(errors="replace").splitlines():
        command = SERVER_COMMAND.search(line)
        start = SERVER_START.search(line)
        decel = SERVER_DECEL.search(line)
        match = command or start or decel
        if match is None:
            continue
        stamp = datetime.combine(date, time.fromisoformat(match[1]), timezone.utc)
        if command:
            warps.append(Warp(stamp))
        elif warps and start:
            warps[-1].start = stamp
        elif warps and decel:
            warps[-1].distances.append((stamp, float(decel[2])))
    return warps


def client_warps(path: Path):
    warps = []
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            message = row["message"]
            stamp = datetime.fromisoformat(row["timestamp_utc"])
            command = CLIENT_COMMAND.search(message)
            distance = CLIENT_DISTANCE.search(message)
            if command:
                warps.append(Warp(stamp))
            elif warps and distance:
                value = float(distance[1].replace(",", ""))
                scale = {"AU": AU_METERS, "km": 1000, "m": 1}[distance[2]]
                warps[-1].distances.append((stamp, value * scale))
    return warps


def progress_offsets(server: Warp, client: Warp):
    """Server time minus client time at equal distance, in seconds."""
    samples = server.distances
    offsets = []
    for client_time, distance in client.distances:
        if not MIN_DISTANCE_METERS < distance < MAX_DISTANCE_METERS:
            continue
        for (before_time, before), (after_time, after) in zip(samples, samples[1:]):
            if not after <= distance <= before:
                continue
            fraction = math.log(before / distance) / math.log(before / after)
            matching_time = before_time + (after_time - before_time) * fraction
            offsets.append((matching_time - client_time).total_seconds())
            break
    return offsets


def compare(server_log: Path, client_csv: Path, limit: float):
    client = client_warps(client_csv)
    if not client:
        raise ValueError("no client WarpTo actions found")
    server = server_warps(server_log, client[0].command.date())
    if not server:
        raise ValueError("no server WarpTo commands found")

    matches = []
    used = set()
    for server_warp in server:
        candidates = [(abs((server_warp.command - warp.command).total_seconds()), i, warp)
                      for i, warp in enumerate(client) if i not in used]
        if not candidates:
            raise ValueError("server warp has no client command")
        difference, i, client_warp = min(candidates)
        if difference > COMMAND_WINDOW_SECONDS:
            raise ValueError(f"unmatched server warp at {server_warp.command.isoformat()}")
        used.add(i)
        offsets = progress_offsets(server_warp, client_warp)
        if server_warp.start is None or len(offsets) < MIN_SAMPLES:
            raise ValueError(f"insufficient deceleration samples for warp at {server_warp.command.isoformat()}")
        matches.append((server_warp, client_warp, median(offsets), len(offsets)))

    if len(matches) < 2:
        raise ValueError("at least two warps are needed to distinguish clock skew from desync")
    baseline = median(offset for _, _, offset, _ in matches)
    failed = False
    for index, (server_warp, client_warp, offset, count) in enumerate(matches, 1):
        deviation = offset - baseline
        result = "FAIL" if abs(deviation) > limit else "PASS"
        failed |= result == "FAIL"
        server_align = (server_warp.start - server_warp.command).total_seconds()
        client_start = server_warp.start.timestamp() - offset
        client_align = client_start - client_warp.command.timestamp()
        print(f"{result} warp {index}: offset {offset:+.3f}s, deviation {deviation:+.3f}s "
              f"({count} samples); command-to-warp server {server_align:.2f}s, "
              f"client ~{client_align:.2f}s")
    print(f"Baseline (median server-client clock/progress offset): {baseline:+.3f}s; limit {limit:.1f}s")
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("server_log", type=Path)
    parser.add_argument("client_csv", type=Path)
    parser.add_argument("--limit", type=float, default=1.0, help="maximum deviation from the median, in seconds")
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be positive")
    try:
        return compare(args.server_log, args.client_csv, args.limit)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
