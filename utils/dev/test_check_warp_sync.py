"""Read-only regression checks for the warp log comparison tool."""

import contextlib
from datetime import datetime, timedelta, timezone
import io
import math
import unittest

from check_warp_sync import Warp, client_warps, compare, progress_offsets, server_warps


BASE = datetime(2026, 10, 9, 5, 12, tzinfo=timezone.utc)


class TextPath:
    def __init__(self, text):
        self.text = text

    def read_text(self, errors=None):
        return self.text

    def open(self, **kwargs):
        return io.StringIO(self.text)


def stamp(moment):
    return moment.strftime("%H:%M:%S.%f")


def fixture(offsets):
    """Generate valid deceleration traces with independent clock offsets."""
    server_lines = []
    client_lines = ["timestamp_utc,flags_raw,message_length_raw,message"]
    # Extra client-only login warp: must not be paired with any server sample.
    login = BASE - timedelta(seconds=30)
    client_lines.append(f'{login.isoformat()},1,0,"Action:       WarpTo 1 - current: 1 (140000208,)"')
    for index, offset in enumerate(offsets):
        command = BASE + timedelta(seconds=60 * index)
        start = command + timedelta(seconds=10 if index == 0 else 7)
        client_command = command + timedelta(milliseconds=600)
        server_lines.append(f"server | {stamp(command)} [WarpTrace] Destiny::WarpTo() toBubble:19 from:21")
        server_lines.append(f"server | {stamp(start)} [WarpTrace] Destiny::InitWarp():  Ship(140000208) has initialized warp.")
        client_lines.append(f'{client_command.isoformat()},1,0,"Action:       WarpTo {index+2} - current: {index+2} (140000208,)"')
        for second in range(9):
            server_time = start + timedelta(seconds=9 + second)
            distance_km = int(round(10_000_000 * math.exp(-second)))
            server_lines.append(f"server | {stamp(server_time)} [WarpTrace] Destiny::WarpDecel(): Ship - "
                                f"Warp Decelerating with {distance_km * 1000:.2f} m left to go.")
            client_time = server_time - timedelta(seconds=offset)
            client_lines.append(f'{client_time.isoformat()},1,0,"Space::IndicateWarp Distance: {distance_km:,} km"')
    return TextPath("\n".join(server_lines)), TextPath("\n".join(client_lines))


class WarpSyncTests(unittest.TestCase):
    def test_three_warps_flag_only_delayed_turn(self):
        server, client = fixture([8.0, 0.0, 0.2])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = compare(server, client, 1.0)
        self.assertEqual(result, 1)
        self.assertIn("FAIL warp 1", output.getvalue())
        self.assertIn("PASS warp 2", output.getvalue())
        self.assertIn("PASS warp 3", output.getvalue())
        self.assertIn("deviation +7.800s", output.getvalue())

    def test_synchronized_warps_with_clock_skew_pass(self):
        server, client = fixture([0.5, 0.55, 0.6])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(compare(server, client, 1.0), 0)

    def test_old_early_server_warp_is_also_detected(self):
        server, client = fixture([-8.0, 0.0, 0.2])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(compare(server, client, 1.0), 1)
        self.assertIn("FAIL warp 1", output.getvalue())
        self.assertIn("deviation -8.000s", output.getvalue())

    def test_one_warp_cannot_establish_clock_baseline(self):
        server, client = fixture([8.0])
        with self.assertRaisesRegex(ValueError, "at least two warps"):
            compare(server, client, 1.0)

    def test_distance_interpolation_and_units(self):
        server = Warp(BASE, distances=[(BASE, 10_000_000_000),
                                        (BASE + timedelta(seconds=1), 10_000_000_000 / math.e)])
        client = Warp(BASE, distances=[(BASE + timedelta(seconds=0.5),
                                        10_000_000_000 / math.sqrt(math.e))])
        self.assertAlmostEqual(progress_offsets(server, client)[0], 0, places=5)
        csv_log = TextPath("timestamp_utc,flags_raw,message_length_raw,message\n"
                           f'{BASE.isoformat()},1,0,"Action:       WarpTo 1 - current: 1 (140000208,)"\n'
                           f"{BASE.isoformat()},1,0,Space::IndicateWarp Distance: 3.11 AU\n"
                           f'{BASE.isoformat()},1,0,"Space::IndicateWarp Distance: 1,234 km"\n')
        self.assertEqual([distance for _, distance in client_warps(csv_log)[0].distances],
                         [3.11 * 149597870700, 1_234_000])

    def test_parses_whole_second_server_timestamps(self):
        text = TextPath("server | 05:12:05 [WarpTrace] Destiny::WarpTo() toBubble:19 from:21\n"
                        "server | 05:12:12 [WarpTrace] Destiny::InitWarp(): Ship has initialized warp\n")
        self.assertEqual(server_warps(text, BASE.date())[0].start.second, 12)


if __name__ == "__main__":
    unittest.main()
