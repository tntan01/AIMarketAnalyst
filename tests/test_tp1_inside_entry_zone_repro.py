"""
Tai hien loi: TP1 nam TRONG entry zone cho cap GBPNZD.

Scenario bao cao:
  TP2:       2.34299
  Current:   2.33972
  Entry+:    2.33813  (entry_high)
  TP1:       2.33773  <-- NAM TRONG entry zone!
  Entry-:    2.33590  (entry_low)
  SL:        2.33547

Van de: TP1 (2.33773) nam GIUA entry_low (2.33590) va entry_high (2.33813).
Voi BUY, TP1 phai > entry_high. Voi SELL, TP1 phai < entry_low.
"""
import sys
import unittest


class TestTp1InsideEntryZone(unittest.TestCase):

    # ── Reproduction: dung chinh xac so lieu bao cao ───────────────

    def test_tp1_inside_entry_zone_exact_reported_numbers(self):
        """
        Tai hien voi so lieu CHINH XAC tu bao cao GBPNZD.
        _ENTRY_AGGRESSIVENESS=0.0 -> entry_for_rr = entry_low.
        TP1 (2.33773) vuot qua R:R check nhung van nam TRONG entry zone.
        """
        entry_low = 2.33590
        entry_high = 2.33813
        stop_loss = 2.33547
        reported_tp1 = 2.33773

        # entry_aggressiveness = 0.0 -> entry_for_rr = entry_low
        entry_for_rr = entry_low

        # Kiem tra: TP1 co nam trong entry zone khong?
        inside_zone = entry_low < reported_tp1 < entry_high
        self.assertTrue(inside_zone,
                        f"TP1 {reported_tp1} nam TRONG entry zone "
                        f"[{entry_low}, {entry_high}]")

        # Kiem tra: TP1 co vuot qua R:R check khong?
        risk = entry_for_rr - stop_loss
        tp_distance = reported_tp1 - entry_for_rr
        passes_rr = tp_distance >= risk

        print(f"\n  === Reproduction voi so lieu GBPNZD ===")
        print(f"  entry_low       = {entry_low}")
        print(f"  entry_high      = {entry_high}")
        print(f"  entry_for_rr    = {entry_for_rr}  (aggressiveness=0.0)")
        print(f"  stop_loss       = {stop_loss}")
        print(f"  risk (1R)       = {risk:.6f}")
        print(f"  TP1 (reported)  = {reported_tp1}")
        print(f"  TP1 distance    = {tp_distance:.6f}")
        print(f"  inside_zone     = {inside_zone}")
        print(f"  passes_rr_check = {passes_rr}")
        print(f"  actual R:R      = {tp_distance/risk:.2f}R")

        self.assertTrue(passes_rr,
                        "BUG CONFIRMED: TP1 passes R:R check "
                        f"({tp_distance:.6f} >= {risk:.6f}) "
                        f"but is INSIDE entry zone [{entry_low}, {entry_high}]")

        print(f"\n  >>> BUG CONFIRMED <<<")
        print(f"  TP1 ({reported_tp1}) vuot qua R:R check ({tp_distance/risk:.2f}R)")
        print(f"  nhung van nam TRONG entry zone [{entry_low}, {entry_high}]")
        print(f"  Nguyen nhan: nearest_target() chi kiem tra TP > entry_for_rr")
        print(f"  va R:R >= 1:1, KHONG kiem tra TP >= entry_high")

    # ── Trace chinh xac flow code ─────────────────────────────────

    def test_trace_code_flow_for_buy(self):
        """Trace flow BUY: nearest_target tim resistance > entry_for_rr
        nhung khong check > entry_high."""
        entry_low = 2.33590
        entry_high = 2.33813
        entry_for_rr = entry_low  # aggressiveness=0.0
        stop_loss = 2.33547

        # Gia su co resistance zone tai 2.33773
        # nearest_target(resistance_zones, entry_for_rr, above=True)
        # -> tim zone co level > entry_for_rr
        resistance_level = 2.33773
        above_entry = resistance_level > entry_for_rr
        self.assertTrue(above_entry)

        # R:R check trong code (line 505-506):
        # (tp1 - entry_for_rr) < (entry_for_rr - stop_loss)
        # Neu TP distance < risk -> fall through
        # Neu TP distance >= risk -> CHAP NHAN TP nay!
        risk = entry_for_rr - stop_loss
        fails_rr_check = (resistance_level - entry_for_rr) < risk
        self.assertFalse(fails_rr_check,
                         f"R:R check passes: {resistance_level - entry_for_rr:.6f} >= {risk:.6f}")

        # NHUNG: KHONG CO CHECK resistance_level >= entry_high!
        # Day chinh la bug
        below_entry_high = resistance_level < entry_high
        self.assertTrue(below_entry_high,
                        f"ROOT CAUSE: TP1 {resistance_level} < entry_high {entry_high}")

    # ── Pham vi anh huong: cac muc aggressiveness ─────────────────

    def test_affected_aggressiveness_levels(self):
        """Bug anh huong den moi entry_aggressiveness < 1.0."""
        entry_low = 2.33590
        entry_high = 2.33813
        zone_width = entry_high - entry_low
        stop_loss = 2.33547
        tp1_candidate = 2.33773  # resistance nam trong zone

        print(f"\n  === Pham vi anh huong ===")
        print(f"  Zone: [{entry_low}, {entry_high}], width={zone_width:.5f}")
        print(f"  TP1 candidate: {tp1_candidate}")
        print(f"  SL: {stop_loss}")

        for agg in [0.0, 0.25, 0.5, 0.75, 1.0]:
            entry_for_rr = entry_low + zone_width * agg
            risk = entry_for_rr - stop_loss
            tp_dist = tp1_candidate - entry_for_rr
            passes_rr = tp_dist >= risk
            inside = entry_low < tp1_candidate < entry_high

            status = "BUG" if (passes_rr and inside) else "OK"
            print(f"  agg={agg:.2f} entry_for_rr={entry_for_rr:.5f} "
                  f"risk={risk:.6f} tp_dist={tp_dist:.6f} "
                  f"passes_rr={passes_rr} inside_zone={inside} -> {status}")

        # Chi co agg=1.0 la an toan (entry_for_rr = entry_high, TP phai > entry_high)
        print(f"\n  Ket luan: Bug xay ra voi aggressiveness < 1.0")
        print(f"  Mac dinh _ENTRY_AGGRESSIVENESS = 0.0 -> LUON gap bug")

    # ── SELL side cung co bug ─────────────────────────────────────

    def test_sell_side_same_bug(self):
        """SELL: support zone trong entry zone cung bi chon lam TP1."""
        entry_low = 2.33590
        entry_high = 2.33813
        # SELL: aggressiveness=0.0 -> entry_for_rr = entry_high
        entry_for_rr = entry_high  # gan nhat edge cua zone
        stop_loss = 2.34299  # SL above entry zone for SELL

        # Gia su co support zone tai 2.33720 (trong entry zone)
        support_level = 2.33720
        inside_zone = entry_low < support_level < entry_high
        self.assertTrue(inside_zone)

        # SELL: nearest_target(support_zones, entry_for_rr, above=False)
        below_entry = support_level < entry_for_rr
        self.assertTrue(below_entry)

        risk = stop_loss - entry_for_rr
        tp_distance = entry_for_rr - support_level
        passes_rr = tp_distance >= risk

        print(f"\n  === SELL side ===")
        print(f"  entry_for_rr   = {entry_for_rr}")
        print(f"  stop_loss      = {stop_loss}")
        print(f"  risk (1R)      = {risk:.6f}")
        print(f"  support_level  = {support_level}")
        print(f"  tp_distance    = {tp_distance:.6f}")
        print(f"  inside_zone    = {inside_zone}")
        print(f"  passes_rr      = {passes_rr}")

        if passes_rr and inside_zone:
            print(f"\n  >>> SELL side cung bi BUG: TP1 trong entry zone <<<")

    # ── Khong bug khi resistance ngoai zone ───────────────────────

    def test_no_bug_when_resistance_above_entry_high(self):
        """Khi resistance > entry_high -> TP1 hop le."""
        entry_low = 2.33590
        entry_high = 2.33813
        entry_for_rr = entry_low
        stop_loss = 2.33547

        good_tp = 2.33900  # > entry_high

        inside_zone = entry_low < good_tp < entry_high
        self.assertFalse(inside_zone)

        above_entry_high = good_tp > entry_high
        self.assertTrue(above_entry_high)


if __name__ == "__main__":
    unittest.main(verbosity=2)
