import itertools
import math
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import store

STYLESHEET = Path(__file__).resolve().parents[1] / "ledger" / "static" / "ledger.css"
MINIMUM_STATUS_DISTANCE = 0.10
MINIMUM_CANCELLED_DISTANCE = 0.10


def to_linear(channel):
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def to_oklab(value):
    red, green, blue = (to_linear(int(value[index:index + 2], 16) / 255) for index in (1, 3, 5))
    long_cone = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue) ** (1 / 3)
    medium_cone = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue) ** (1 / 3)
    short_cone = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue) ** (1 / 3)
    return (0.2104542553 * long_cone + 0.7936177850 * medium_cone - 0.0040720468 * short_cone,
            1.9779984951 * long_cone - 2.4285922050 * medium_cone + 0.4505937099 * short_cone,
            0.0259040371 * long_cone + 0.7827717662 * medium_cone - 0.8086757660 * short_cone)


def dark_theme_colors(prefix):
    dark_block = STYLESHEET.read_text(encoding="utf-8").split(":root[data-theme=\"light\"]")[0]
    return {name: value for name, value in re.findall(rf"--{prefix}-([a-z_]+):\s*(#[0-9a-fA-F]{{6}});", dark_block)}


class StatusColorTests(unittest.TestCase):
    def test_every_status_has_a_color(self):
        self.assertEqual(sorted(dark_theme_colors("status")), sorted(store.STATUSES))

    def test_no_two_statuses_look_alike(self):
        colors = dark_theme_colors("status")
        for first, second in itertools.combinations(colors, 2):
            distance = math.dist(to_oklab(colors[first]), to_oklab(colors[second]))
            self.assertGreaterEqual(distance, MINIMUM_STATUS_DISTANCE, f"{first} and {second} are too close ({distance:.3f})")

    def test_cancelled_is_not_mistaken_for_an_open_status(self):
        colors = dark_theme_colors("status")
        cancelled = to_oklab(colors["cancelled"])
        for name in store.STATUSES:
            if name in store.CLOSED_STATUSES:
                continue
            distance = math.dist(cancelled, to_oklab(colors[name]))
            self.assertGreaterEqual(distance, MINIMUM_CANCELLED_DISTANCE, f"cancelled looks like {name} ({distance:.3f})")

    def test_cancelled_does_not_share_a_color_with_any_priority(self):
        status, priority = dark_theme_colors("status"), dark_theme_colors("priority")
        self.assertNotIn(status["cancelled"].lower(), [value.lower() for value in priority.values()])


if __name__ == "__main__":
    unittest.main()
