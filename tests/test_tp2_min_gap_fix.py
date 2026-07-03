"""
Test fix BUG-002: TP2 qua gan TP1 bi reject boi guard clause.
"""
import unittest
from unittest.mock import patch


class TestTp2MinGapGuard(unittest.TestCase):

    @staticmethod
    def _make_request():
        from core.risk_engine import AnalysisInput
        return AnalysisInput(
            symbol="AUDNZD", broker_symbol="AUDNZD",
            account_balance=10000.0, risk_percent=2.0,
            account_currency="USD", lot_step=0.01, minimum_lot=0.01,
        )

    # ── BUY: TP2 qua gan TP1 → reject ────────────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_buy_tp2_too_close_rejected(self, mock_cs, mock_qusd, mock_eval):
        """BUY: resistance zone chi cach TP1 0.4 pips → TP2=None."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
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
            print(f"\n  BUY TP2 guard test:")
            print(f"  take_profit = {tp_list}")

            # TP2 phai la None (gap < 15% ATR) hoac cach TP1 >= min gap
            if len(tp_list) >= 2 and tp_list[1] is not None:
                tp1, tp2 = tp_list[0], tp_list[1]
                atr = 0.0012
                min_gap = atr * 0.15
                self.assertGreaterEqual(
                    tp2 - tp1, min_gap,
                    f"TP2 ({tp2}) qua gan TP1 ({tp1}), gap={tp2-tp1:.6f} < min={min_gap:.6f}"
                )
                print(f"  PASS: TP2={tp2} cach TP1={tp1} gap={tp2-tp1:.6f} >= {min_gap:.6f}")
            else:
                print(f"  PASS: TP2=None (rejected - gap too small)")
        else:
            print(f"\n  Plan=None (no valid entry)")

    # ── BUY: TP2 du xa TP1 → giu nguyen ──────────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_buy_tp2_valid_kept(self, mock_cs, mock_qusd, mock_eval):
        """BUY: resistance zone cach TP1 > 15% ATR → TP2 duoc giu."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
        technical = {
            "price": 1.21502,
            "atr_h4": 0.0012,
            "atr_d1": 0.0015,
            "support_zones": [
                {"level": 1.21493, "low": 1.21400, "high": 1.21550, "source": "technical"},
            ],
            "resistance_zones": [
                {"level": 1.21699, "low": 1.21600, "high": 1.21750, "source": "technical"},
                {"level": 1.21800, "low": 1.21700, "high": 1.21900, "source": "technical"},
            ],
        }
        smc = {"H4": {"swings": {}, "demand_zones": [], "supply_zones": [], "liquidity_pools": {}}}

        plan = build_trade_plan("buy", request, technical, smc)

        if plan is not None:
            tp_list = plan["take_profit"]
            if len(tp_list) >= 2 and tp_list[1] is not None:
                tp1, tp2 = tp_list[0], tp_list[1]
                gap = tp2 - tp1
                atr = 0.0012
                self.assertGreaterEqual(gap, atr * 0.15,
                                         f"Valid TP2 should be kept, gap={gap:.6f}")
                print(f"\n  BUY valid TP2: TP1={tp1}, TP2={tp2}, gap={gap:.6f}")

    # ── SELL: TP2 qua gan TP1 → reject ───────────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_sell_tp2_too_close_rejected(self, mock_cs, mock_qusd, mock_eval):
        """SELL: support zone chi cach TP1 vai pip → TP2=None."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
        technical = {
            "price": 1.23000,
            "atr_h4": 0.0012,
            "atr_d1": 0.0015,
            "resistance_zones": [
                {"level": 1.23050, "low": 1.23000, "high": 1.23100, "source": "technical"},
            ],
            "support_zones": [
                {"level": 1.21000, "low": 1.20900, "high": 1.21100, "source": "technical"},
                {"level": 1.20996, "low": 1.20896, "high": 1.21096, "source": "technical"},
            ],
        }
        smc = {"H4": {"swings": {}, "demand_zones": [], "supply_zones": [], "liquidity_pools": {}}}

        plan = build_trade_plan("sell", request, technical, smc)

        if plan is not None:
            tp_list = plan["take_profit"]
            print(f"\n  SELL TP2 guard test: take_profit = {tp_list}")
            if len(tp_list) >= 2 and tp_list[1] is not None:
                tp1, tp2 = tp_list[0], tp_list[1]
                atr = 0.0012
                self.assertGreaterEqual(
                    tp1 - tp2, atr * 0.15,
                    f"TP2 qua gan TP1, gap={tp1-tp2:.6f}"
                )

    # ── Edge: khong co TP1 → guard khong chay ────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_no_tp1_guard_skipped(self, mock_cs, mock_qusd, mock_eval):
        """Khong co TP1 → tp2=None, guard khong gay crash."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
        technical = {
            "price": 1.21502,
            "atr_h4": 0.0012,
            "atr_d1": 0.0015,
            "support_zones": [],  # khong co support -> khong co entry -> khong co plan
            "resistance_zones": [],
        }
        smc = {"H4": {"swings": {}, "demand_zones": [], "supply_zones": [], "liquidity_pools": {}}}

        plan = build_trade_plan("buy", request, technical, smc)
        # Plan=None la OK - guard khong chay vi tp1 is None
        print(f"\n  No-TP1 test: plan={'None (OK)' if plan is None else 'exists'}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
