"""强度设计组合只用作用工况，雪只和同一倾角的风组合。"""

from __future__ import annotations

import unittest

from loads.tools.combinations import formula, strength_combinations


def _cases(*ids: str) -> list[dict]:
    return [{"id": item, "value": 1.0} for item in ids]


class CombinationTests(unittest.TestCase):
    def test_asce_strength_combinations(self) -> None:
        combos = strength_combinations(
            _cases("W_QP_0", "W_0_F", "W_60_90_G", "S_0", "D", "D_LINE", "W_0_F_LINE")
        )
        found = {item["id"]: formula(item) for item in combos}
        self.assertEqual(
            found,
            {
                "LRFD1": "1.4D",
                "LRFD2_S_0": "1.2D + 0.5S_0",
                "LRFD3_S_0": "1.2D + 1.6S_0",
                "LRFD3_S_0_W_0_F": "1.2D + 1.6S_0 + 0.5W_0_F",
                "LRFD4_W_0_F": "1.2D + 1.0W_0_F",
                "LRFD4_W_0_F_S_0": "1.2D + 1.0W_0_F + 0.5S_0",
                "LRFD4_W_60_90_G": "1.2D + 1.0W_60_90_G",
                "LRFD5_W_0_F": "0.9D + 1.0W_0_F",
                "LRFD5_W_60_90_G": "0.9D + 1.0W_60_90_G",
            },
        )

    def test_no_dead_load_gives_no_combinations(self) -> None:
        self.assertEqual(strength_combinations(_cases("W_0_F", "S_0")), [])


if __name__ == "__main__":
    unittest.main()
