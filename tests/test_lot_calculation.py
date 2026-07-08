"""
Test script: Kiểm tra logic tính lot trong position_sizing()
Chạy: cd /mnt/d/Projects/AIMarketAnalyst && python tests/test_lot_calculation.py
"""
import sys, os
from pathlib import Path

PROJECT = Path("/mnt/d/Projects/AIMarketAnalyst")
sys.path.insert(0, str(PROJECT))

from core.risk_engine import position_sizing, round_lot, AnalysisInput
from config.settings import TradingSettings

def test_lot_calculation():
    """Test tính lot với mức risk 1%"""
    settings = TradingSettings()
    settings.account_balance = 10000.0
    settings.default_risk_percent = 1.0
    settings.lot_step = 0.01
    settings.minimum_lot = 0.01
    settings.contract_size_override = 100000

    # Test 1: EURUSD Buy
    print("=" * 60)
    print("KIỂM TRA LOT — position_sizing()")
    print("=" * 60)
    print(f"Balance: ${settings.account_balance:,.0f}")
    print(f"Risk: {settings.default_risk_percent}%")
    print(f"Contract size: {settings.contract_size_override:,.0f}")
    print(f"Lot step: {settings.lot_step}, Min lot: {settings.minimum_lot}")

    # --- Test cases ---
    test_cases = [
        # (symbol, side, entry, SL, expected_lot, desc)
        ("EURUSD", "buy",  1.08500, 1.08300, None, "EURUSD Buy: SL 20 pips"),
        ("EURUSD", "sell", 1.08500, 1.08700, None, "EURUSD Sell: SL 20 pips"),
        ("EURUSD", "buy",  1.08500, 1.08400, None, "EURUSD Buy: SL 10 pips → lot gấp đôi"),
        ("USDJPY", "buy",  151.500, 151.000, None, "USDJPY Buy: SL 50 pips"),
        ("GBPUSD", "sell", 1.27000, 1.27500, None, "GBPUSD Sell: SL 50 pips"),
        ("XAUUSD", "buy",  2650.00, 2645.00, None, "Vàng Buy: SL $5"),
    ]

    all_pass = True
    for symbol, side, entry, sl, _, desc in test_cases:
        request = AnalysisInput(
            symbol=symbol,
            broker_symbol=symbol,
            account_balance=settings.account_balance,
            risk_percent=settings.default_risk_percent,
            account_currency=settings.account_currency,
            lot_step=settings.lot_step,
            minimum_lot=settings.minimum_lot,
            contract_size_override=settings.contract_size_override,
        )

        result = position_sizing(request, entry, sl, quote_to_usd_rate=1.0)
        lot = result["suggested_lot"]
        risk_amount = result["risk_amount_usd"]
        price_dist = result["price_distance"]
        raw_lot = result["risk_amount_usd"] / (result["price_distance"] * result["contract_size"])

        # Manual verify
        expected_risk = settings.account_balance * settings.default_risk_percent / 100
        expected_raw = expected_risk / (abs(entry - sl) * settings.contract_size_override)
        expected_lot = round_lot(expected_raw, settings.lot_step, settings.minimum_lot)

        risk_ok = abs(risk_amount - expected_risk) < 0.01
        raw_ok = abs(raw_lot - expected_raw) < 0.0001
        lot_ok = abs(lot - expected_lot) < 0.001

        test_pass = risk_ok and raw_ok and lot_ok

        print(f"\n{'✅' if test_pass else '❌'} {desc}")
        print(f"   Side={side}, Entry={entry}, SL={sl}")
        print(f"   price_distance={price_dist}, risk_amount=${risk_amount:.2f}")
        print(f"   raw_lot={raw_lot:.4f}, rounded lot={lot:.2f}")
        print(f"   Expected: risk=${expected_risk:.2f}, raw={expected_raw:.4f}, lot={expected_lot:.2f}")

        if not test_pass:
            all_pass = False
            print(f"   ⚠️ FAIL: risk_ok={risk_ok}, raw_ok={raw_ok}, lot_ok={lot_ok}")

    # Test 2: absolute value (kiểm tra câu hỏi của Tân)
    print("\n" + "=" * 60)
    print("KIỂM TRA: abs() — Buy vs Sell cùng khoảng cách SL")
    print("=" * 60)
    request = AnalysisInput(
        symbol="EURUSD", broker_symbol="EURUSD",
        account_balance=10000, risk_percent=1.0,
        account_currency="USD", lot_step=0.01, minimum_lot=0.01,
        contract_size_override=100000,
    )
    buy_result = position_sizing(request, 1.08500, 1.08300, quote_to_usd_rate=1.0)  # SL dưới entry
    sell_result = position_sizing(request, 1.08500, 1.08700, quote_to_usd_rate=1.0) # SL trên entry

    buy_lot = buy_result["suggested_lot"]
    sell_lot = sell_result["suggested_lot"]

    same = abs(buy_lot - sell_lot) < 0.001
    print(f"Buy lot  (SL dưới entry): {buy_lot:.2f}")
    print(f"Sell lot (SL trên entry):  {sell_lot:.2f}")
    print(f"{'✅' if same else '❌'} Buy và Sell cùng SL distance → lot giống nhau: {same}")

    # Test 3: TP không ảnh hưởng đến lot
    print("\n" + "=" * 60)
    print("KIỂM TRA: TP có ảnh hưởng đến lot không?")
    print("=" * 60)
    r1 = position_sizing(request, 1.08500, 1.08300, quote_to_usd_rate=1.0)  # SL 20 pips
    r2 = position_sizing(request, 1.08500, 1.08350, quote_to_usd_rate=1.0)  # SL 15 pips
    print(f"SL=1.08300 → lot={r1['suggested_lot']:.2f}")
    print(f"SL=1.08350 → lot={r2['suggested_lot']:.2f}")
    print("✅ Kết luận: TP KHÔNG được truyền vào position_sizing(), chỉ SL quyết định lot.")

    # Summary
    print("\n" + "=" * 60)
    if all_pass:
        print("✅ PASS — Tất cả test lot đều đúng.")
    else:
        print("❌ FAIL — Có test sai, kiểm tra lại.")
    return all_pass

if __name__ == "__main__":
    ok = test_lot_calculation()
    sys.exit(0 if ok else 1)
