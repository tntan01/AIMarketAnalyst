"""
Tai hien loi: TP2 gan nhu trung TP1 (cach nhau < 1 pip) cho cap AUDNZD.

Scenario bao cao:
  TP2:       1.21703  <- chi cach TP1 0.4 pips!
  TP1:       1.21699
  Entry+:    1.21507
  Current:   1.21502
  Entry-:    1.21479
  SL:        1.21433

Van de: TP2 - TP1 = 0.00004 (0.4 pips) — gan nhu trung nhau.
next_target() tim resistance zone gan nhat > TP1, nhung KHONG CO
minimum distance check. Neu resistance zone nam sat ngay tren TP1,
TP2 se gan nhu trung TP1.
"""
import unittest
from unittest.mock import MagicMock, patch


class TestTp2TooCloseToTp1(unittest.TestCase):

    # ── Reproduction: AUDNZD scenario ─────────────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_tp2_too_close_to_tp1_audnzd(self, mock_cs, mock_qusd, mock_eval):
        """Tai hien: TP2 chi cach TP1 0.4 pips."""
        from core.risk_engine import build_trade_plan, AnalysisInput

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = AnalysisInput(
            symbol="AUDNZD", broker_symbol="AUDNZD",
            account_balance=10000.0, risk_percent=2.0,
            account_currency="USD", lot_step=0.01, minimum_lot=0.01,
        )

        # Mo phong so lieu AUDNZD
        technical = {
            "price": 1.21502,
            "atr_h4": 0.0012,
            "atr_d1": 0.0015,
            "support_zones": [
                {"level": 1.21493, "low": 1.21400, "high": 1.21550, "source": "technical"},
            ],
            "resistance_zones": [
                {"level": 1.21699, "low": 1.21600, "high": 1.21750, "source": "technical"},
                {"level": 1.21703, "low": 1.21680, "high": 1.21730, "source": "technical"},
                {"level": 1.22000, "low": 1.21900, "high": 1.22100, "source": "technical"},
            ],
        }
        smc = {"H4": {"swings": {}, "demand_zones": [], "supply_zones": [], "liquidity_pools": {}}}

        plan = build_trade_plan("buy", request, technical, smc)

        if plan is not None:
            tp_list = plan["take_profit"]
            print(f"\n  === AUDNZD reproduction ===")
            print(f"  entry_zone = {plan['entry_zone']}")
            print(f"  take_profit = {tp_list}")
            print(f"  stop_loss = {plan['stop_loss']}")

            if len(tp_list) >= 2 and tp_list[0] is not None and tp_list[1] is not None:
                tp1, tp2 = tp_list[0], tp_list[1]
                gap = tp2 - tp1
                atr_value = 0.0012
                gap_pct_atr = gap / atr_value * 100

                print(f"  TP1 = {tp1}")
                print(f"  TP2 = {tp2}")
                print(f"  GAP = {gap:.6f} ({gap_pct_atr:.1f}% ATR)")

                if gap < atr_value * 0.10:
                    print(f"\n  >>> BUG CONFIRMED <<<")
                    print(f"  TP2 ({tp2}) chi cach TP1 ({tp1}) {gap:.6f}")
                    print(f"  = {gap_pct_atr:.1f}% ATR — gan nhu trung nhau!")
                    print(f"  Nguyen nhan: next_target() tim resistance > TP1")
                    print(f"  nhung KHONG CO minimum distance check")
        else:
            print(f"\n  Plan=None — khong tao duoc plan (co the do guard moi)")

    # ── Unit test: next_target behavior ────────────────────────────

    def test_next_target_no_minimum_distance(self):
        """next_target tra ve level sat ngay tren TP1."""
        from core.risk_engine import next_target

        # Gia su resistance zones co level sat nhau
        zones = [
            {"level": 1.21699},  # = TP1
            {"level": 1.21703},  # chi cach 0.4 pips!
            {"level": 1.22000},
        ]

        tp1 = 1.21699
        tp2 = next_target(zones, tp1, above=True)

        self.assertIsNotNone(tp2)
        self.assertEqual(tp2, 1.21703)

        gap = tp2 - tp1
        print(f"\n  next_target test:")
        print(f"  TP1 = {tp1}")
        print(f"  TP2 = {tp2}")
        print(f"  GAP = {gap:.6f}")

        # Gap < 1 pip -> khong co y nghia thuc te
        self.assertLess(gap, 0.00010,
                        f"TP2-TP1 gap ({gap}) < 1 pip — vo nghia")

    # ── Pham vi anh huong ─────────────────────────────────────────

    def test_next_target_all_scenarios(self):
        """Khao sat next_target voi cac khoang cach khac nhau."""
        from core.risk_engine import next_target

        test_cases = [
            # (tp1, zones_above, expected_gap_pips)
            (1.21699, [1.21703, 1.22000], 0.4),   # < 1 pip
            (1.21699, [1.21710, 1.22000], 1.1),   # ~1 pip
            (1.21699, [1.21800, 1.22000], 10.1),  # ~10 pips — OK
            (1.21699, [1.22000], 30.1),            # ~30 pips — OK
        ]

        print(f"\n  next_target gap analysis:")
        for tp1, above_levels, expected_pips in test_cases:
            zones = [{"level": lv} for lv in above_levels]
            tp2 = next_target(zones, tp1, above=True)
            gap = tp2 - tp1
            gap_pips = gap / 0.0001
            status = "BUG" if gap_pips < 3 else "OK"
            print(f"  TP1={tp1}, zones={above_levels} -> TP2={tp2}, "
                  f"gap={gap_pips:.1f}pips -> {status}")

        # Tat ca deu khong bi chan — next_target khong co minimum gap
        print(f"\n  Ket luan: next_target() KHONG CO minimum distance check.")
        print(f"  Bat ky resistance zone > TP1 deu duoc chap nhan,")
        print(f"  ke ca khi chi cach 0.4 pips.")

    # ── SELL side cung bi anh huong ───────────────────────────────

    def test_sell_side_same_issue(self):
        """SELL: next_target tra ve support zone sat ngay duoi TP1."""
        from core.risk_engine import next_target

        zones = [
            {"level": 1.21699},  # = TP1
            {"level": 1.21695},  # chi cach 0.4 pips!
            {"level": 1.21000},
        ]

        tp1 = 1.21699
        tp2 = next_target(zones, tp1, above=False)

        self.assertIsNotNone(tp2)
        self.assertEqual(tp2, 1.21695)

        gap = tp1 - tp2
        print(f"\n  SELL next_target:")
        print(f"  TP1 = {tp1}, TP2 = {tp2}, GAP = {gap:.6f}")
        print(f"  Same bug: no minimum distance for SELL TP2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
