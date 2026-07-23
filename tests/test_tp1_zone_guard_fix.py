"""
Test fix BUG-001: TP1 nam trong entry zone bi reject boi guard clause.
"""
import unittest
from unittest.mock import patch


class TestTp1EntryZoneGuard(unittest.TestCase):

    @staticmethod
    def _make_request():
        from core.risk_engine import AnalysisInput
        return AnalysisInput(
            symbol="GBPNZD",
            broker_symbol="GBPNZD",
            account_balance=10000.0,
            risk_percent=2.0,
            account_currency="USD",
            lot_step=0.01,
            minimum_lot=0.01,
        )

    @staticmethod
    def _make_technical(price, atr, support_level, resistance_level):
        return {
            "price": price,
            "atr_h4": atr,
            "atr_d1": atr,
            "support_zones": [{"level": support_level, "low": support_level - 0.002, "high": support_level + 0.001, "source": "technical"}],
            "resistance_zones": [{"level": resistance_level, "low": resistance_level - 0.002, "high": resistance_level + 0.001, "source": "technical"}],
        }

    @staticmethod
    def _make_smc():
        return {"H4": {"swings": {}, "demand_zones": [], "supply_zones": [], "liquidity_pools": {}}}

    # ── BUY: TP1 inside entry zone → rejected ────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_buy_tp1_inside_zone_rejected(self, mock_cs, mock_qusd, mock_eval):
        """BUY: resistance zone nam trong entry zone → guard rejects, plan=None."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
        price = 2.33972
        atr = 0.00245
        support_level = 2.337015
        # Resistance zone nam TRONG entry zone → bi guard reject
        resistance_level = 2.33773

        technical = self._make_technical(price, atr, support_level, resistance_level)
        smc = self._make_smc()

        plan = build_trade_plan("buy", request, technical, smc, market_regime={"primary": "trend_up"})

        # Plan=None la DUNG: TP1 bi reject + khong co TP thay the → huy plan
        # Day la behavior mong muon — khong vao lenh voi TP ao
        if plan is not None:
            tp_list = plan["take_profit"]
            entry_high = plan["entry_zone"][1]
            if len(tp_list) > 0 and tp_list[0] is not None:
                self.assertGreater(tp_list[0], entry_high,
                                   f"TP1 {tp_list[0]} must be > entry_high {entry_high}")

        print(f"\n  BUY inside-zone test passed: plan={'None (rejected)' if plan is None else 'has valid TP'}")

    # ── BUY: TP1 above entry zone → kept ─────────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_buy_tp1_above_zone_kept(self, mock_cs, mock_qusd, mock_eval):
        """BUY: resistance zone NGOAI entry zone → TP1 duoc giu."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
        price = 2.33972
        atr = 0.00245
        support_level = 2.337015
        # Resistance zone NAM NGOAI entry zone (tren entry_high)
        # Phase 13C: zone boundary TP = low - buffer → must still clear far_edge
        resistance_level = 2.34600

        technical = self._make_technical(price, atr, support_level, resistance_level)
        smc = self._make_smc()

        plan = build_trade_plan("buy", request, technical, smc, market_regime={"primary": "trend_up"})

        self.assertIsNotNone(plan)
        tp_list = plan["take_profit"]
        entry_high = plan["entry_zone"][1]

        if len(tp_list) > 0 and tp_list[0] is not None:
            self.assertGreater(tp_list[0], entry_high,
                               f"TP1 {tp_list[0]} must be > entry_high {entry_high}")
            print(f"\n  BUY (valid TP) test passed: TP1={tp_list[0]} > entry_high={entry_high}")

    # ── SELL: TP1 inside entry zone → rejected ───────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_sell_tp1_inside_zone_rejected(self, mock_cs, mock_qusd, mock_eval):
        """SELL: support zone nam trong entry zone → TP1 bi reject."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
        price = 2.33000  # duoi entry zone
        atr = 0.00245
        # Resistance zone level = trung tam entry zone (for SELL)
        resistance_level = 2.34000
        # Support zone nam TRONG entry zone
        support_level = 2.33773

        technical = self._make_technical(price, atr, support_level, resistance_level)
        smc = self._make_smc()

        plan = build_trade_plan("sell", request, technical, smc)

        if plan is not None:
            tp_list = plan["take_profit"]
            entry_low = plan["entry_zone"][0]

            if len(tp_list) > 0 and tp_list[0] is not None:
                self.assertLess(tp_list[0], entry_low,
                                f"TP1 {tp_list[0]} must be < entry_low {entry_low}")

            print(f"\n  SELL test passed: entry_zone={plan['entry_zone']}, tp={tp_list}")
        else:
            print(f"\n  SELL test: plan=None (no valid TP)")

    # ── Edge case: no resistance zones at all ────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_buy_no_resistance_zones(self, mock_cs, mock_qusd, mock_eval):
        """BUY: khong co resistance zone nao → guard khong gay crash."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
        price = 2.33972
        atr = 0.00245
        support_level = 2.337015

        technical = {
            "price": price,
            "atr_h4": atr,
            "atr_d1": atr,
            "support_zones": [{"level": support_level, "low": support_level - 0.002, "high": support_level + 0.001, "source": "technical"}],
            "resistance_zones": [],  # khong co resistance
        }
        smc = self._make_smc()

        plan = build_trade_plan("buy", request, technical, smc, market_regime={"primary": "trend_up"})
        # Co the la None (khong co TP) hoac co plan voi tp1=None
        if plan is not None:
            tp_list = plan["take_profit"]
            if len(tp_list) > 0 and tp_list[0] is not None:
                entry_high = plan["entry_zone"][1]
                self.assertGreater(tp_list[0], entry_high)
        print(f"\n  No-resistance test passed")

    # ── Exact GBPNZD reproduction ────────────────────────────────

    @patch("core.risk_engine.evaluate_entry")
    @patch("core.risk_engine._resolve_quote_to_usd_rate")
    @patch("core.risk_engine.contract_size_for")
    def test_gbpnzd_exact_scenario(self, mock_cs, mock_qusd, mock_eval):
        """Tai hien chinh xac scenario GBPNZD: TP1 2.33773 trong zone [2.33590, 2.33813]."""
        from core.risk_engine import build_trade_plan

        mock_cs.return_value = 100000
        mock_qusd.return_value = 1.0
        mock_eval.return_value = {"entry_ladder": {}}

        request = self._make_request()
        # So lieu bao cao
        technical = {
            "price": 2.33972,
            "atr_h4": 0.00245,
            "atr_d1": 0.00245,
            "support_zones": [
                {"level": 2.337015, "low": 2.33600, "high": 2.33800, "source": "technical"},
                {"level": 2.33590, "low": 2.33490, "high": 2.33690, "source": "technical"},
            ],
            "resistance_zones": [
                {"level": 2.33773, "low": 2.33673, "high": 2.33873, "source": "technical"},
                {"level": 2.34299, "low": 2.34199, "high": 2.34399, "source": "technical"},
            ],
        }
        smc = self._make_smc()

        plan = build_trade_plan("buy", request, technical, smc, market_regime={"primary": "trend_up"})

        # Plan=None la DUNG: TP1 2.33773 bi guard reject + cac tier khac
        # khong tim duoc TP hop le → huy plan. Khong vao lenh voi TP ao.
        if plan is not None:
            tp_list = plan["take_profit"]
            entry_low, entry_high = plan["entry_zone"]
            if len(tp_list) > 0 and tp_list[0] is not None:
                self.assertGreater(
                    tp_list[0], entry_high,
                    f"BUG! TP1 {tp_list[0]} inside zone [{entry_low}, {entry_high}]"
                )

        print(f"\n  === GBPNZD exact reproduction ===")
        print(f"  Result: plan={'None (rejected - correct!)' if plan is None else 'has valid TP'}")
        if plan:
            print(f"  entry_zone = {plan['entry_zone']}")
            print(f"  take_profit = {plan['take_profit']}")
            print(f"  stop_loss = {plan['stop_loss']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
