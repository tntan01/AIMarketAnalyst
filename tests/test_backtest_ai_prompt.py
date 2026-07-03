"""Standalone test runner for backtest AI analysis logic changes.

Run directly: py tests/test_backtest_ai_prompt.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.screens.backtest_screen import BacktestScreen


def make_screen():
    return BacktestScreen.__new__(BacktestScreen)


def main():
    passed = 0
    failed = 0

    def check(condition, name):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")

    print("\n=== Test 1: Full data prompt structure ===")

    s = make_screen()
    s.result = {
        "summary": {
            "total_trades": 50, "win_rate": 52.0, "expectancy_r": 0.35,
            "profit_factor": 1.45, "max_drawdown_r": -8.5, "total_r": 17.5,
            "wins": 26, "losses": 20, "expired": 2, "breakeven": 2,
            "max_consecutive_wins": 6, "max_consecutive_losses": 4,
            "average_win_r": 1.8, "average_loss_r": -0.95, "average_holding_bars": 12,
        },
        "breakdowns": {
            "by_market_regime": {
                "aligned": {"total_trades": 30, "win_rate": 60.0, "expectancy_r": 0.55,
                            "profit_factor": 1.8, "max_drawdown_r": -5.0, "total_r": 16.5},
                "neutral": {"total_trades": 15, "win_rate": 40.0, "expectancy_r": 0.05,
                            "profit_factor": 1.05, "max_drawdown_r": -8.5, "total_r": 0.75},
            },
            "by_side": {
                "BUY": {"total_trades": 25, "win_rate": 56.0, "expectancy_r": 0.45,
                        "profit_factor": 1.6, "max_drawdown_r": -6.0, "total_r": 11.25},
                "SELL": {"total_trades": 25, "win_rate": 48.0, "expectancy_r": 0.25,
                         "profit_factor": 1.3, "max_drawdown_r": -8.5, "total_r": 6.25},
            },
            "by_final_score_bucket": {
                "40-50": {"total_trades": 10, "win_rate": 40.0, "expectancy_r": -0.20,
                          "profit_factor": 0.80, "max_drawdown_r": -5.0, "total_r": -2.0},
                "50-60": {"total_trades": 20, "win_rate": 50.0, "expectancy_r": 0.30,
                          "profit_factor": 1.30, "max_drawdown_r": -8.5, "total_r": 6.0},
                "60-70": {"total_trades": 15, "win_rate": 60.0, "expectancy_r": 0.60,
                          "profit_factor": 1.80, "max_drawdown_r": -4.0, "total_r": 9.0},
                "70-80": {"total_trades": 5, "win_rate": 80.0, "expectancy_r": 0.90,
                          "profit_factor": 2.50, "max_drawdown_r": -2.0, "total_r": 4.5},
            },
            "by_expected_effective_rr": {
                "1.0-1.5": {"total_trades": 20, "win_rate": 45.0, "expectancy_r": 0.15,
                            "profit_factor": 1.15, "max_drawdown_r": -8.5, "total_r": 3.0},
                "1.5-2.0": {"total_trades": 20, "win_rate": 55.0, "expectancy_r": 0.50,
                            "profit_factor": 1.60, "max_drawdown_r": -6.0, "total_r": 10.0},
            },
        },
        "diagnostics": {
            "gate_funnel": {"snapshots_evaluated": 500, "setup_detected": 80, "trade_opened": 50},
        },
        "request": {"symbol": "EUR/USD", "start": "2024-01-01T00:00:00Z", "end": "2024-12-31T00:00:00Z"},
    }

    prompt = s._build_analysis_prompt()
    check(isinstance(prompt, str) and len(prompt) > 200, "prompt is non-empty string")
    check("QUY ĐỊNH BẮT BUỘC" in prompt.upper(), "has mandatory format rules header")
    check("KHÔNG" in prompt.upper() and "DÙNG" in prompt.upper(), "has prohibition/forbidden rules")
    check("PHẦN 1" in prompt.upper() and "TỔNG QUAN" in prompt.upper(), "has Section 1 overview")
    check("PHẦN 2" in prompt.upper() and "KHOẢNG ĐIỂM" in prompt.upper(), "has Section 2 score breakdown")
    check("PHẦN 3" in prompt.upper() and "HƯỚNG" in prompt.upper(), "has Section 3 direction analysis")
    check("PHẦN 7" in prompt.upper() and "KHUYẾN NGHỊ" in prompt.upper(), "has Section 7 recommendations")
    check("min_score" in prompt and "min_rr" in prompt, "recommends min_score and min_rr config")
    check("BUY" in prompt and "SELL" in prompt, "has BUY/SELL direction breakdown")

    print("\n=== Test 2: Zero-trades prompt ===")

    s2 = make_screen()
    s2.result = {
        "summary": {"total_trades": 0},
        "breakdowns": {},
        "diagnostics": {},
        "request": {"symbol": "EUR/USD", "start": "2024-01-01", "end": "2024-06-01"},
    }
    prompt2 = s2._build_analysis_prompt()
    check(isinstance(prompt2, str) and len(prompt2) > 50, "zero-trades prompt is non-empty")
    check("QUY ĐỊNH" in prompt2.upper(), "zero-trades has format rules")
    check("0 lệnh" in prompt2.lower() or "không có lệnh" in prompt2.lower(), "zero-trades mentions no orders")

    print("\n=== Test 3: Sparse data conditional sections ===")

    s3 = make_screen()
    s3.result = {
        "summary": {
            "total_trades": 10, "win_rate": 50.0, "expectancy_r": 0.20,
            "profit_factor": 1.20, "max_drawdown_r": -5.0, "total_r": 2.0,
            "wins": 5, "losses": 5, "expired": 0, "breakeven": 0,
            "max_consecutive_wins": 2, "max_consecutive_losses": 3,
            "average_win_r": 1.5, "average_loss_r": -1.1, "average_holding_bars": 8,
        },
        "breakdowns": {
            "by_side": {
                "BUY": {"total_trades": 10, "win_rate": 50.0, "expectancy_r": 0.20,
                        "profit_factor": 1.20, "max_drawdown_r": -5.0, "total_r": 2.0},
            },
        },
        "diagnostics": {},
        "request": {"symbol": "XAU/USD"},
    }
    prompt3 = s3._build_analysis_prompt()
    check("PHẦN 2" not in prompt3.upper(), "no score section when no score breakdown data")
    check("PHẦN 3" in prompt3.upper(), "has direction section when side data exists")
    check("PHẦN 4" not in prompt3.upper(), "no regime section when no regime data")
    check("PHẦN 5" not in prompt3.upper(), "no RR section when no RR data")
    check("PHẦN 6" in prompt3.upper(), "always has risk section")
    check("PHẦN 7" in prompt3.upper(), "always has recommendations section")

    print("\n=== Test 4: Markdown stripping in HTML formatter ===")

    raw = "TONG QUAN:\n- Co **loi the** ro ret +0.35R\n- He so __1.45__\n"
    html_out = BacktestScreen._format_ai_to_html(raw, light=False)
    check("**" not in html_out, "double asterisks stripped")
    check("__" not in html_out, "double underscores stripped")
    check("loi the" in html_out, "Vietnamese content preserved")
    check("+0.35R" in html_out, "R value preserved in HTML")

    print("\n=== Test 5: Empty input HTML ===")

    html_out2 = BacktestScreen._format_ai_to_html("", light=False)
    check(isinstance(html_out2, str) and len(html_out2) > 0, "empty input returns wrapper div")

    print("\n=== Test 6: Heading detection in HTML ===")

    raw2 = "TONG QUAN KET QUA:\n- Bullet 1\n- Bullet 2\n"
    html_out3 = BacktestScreen._format_ai_to_html(raw2, light=False)
    check("font-weight:700" in html_out3, "headings get bold style")
    check("<ul" in html_out3, "bullets wrapped in <ul>")
    check("<li" in html_out3, "items wrapped in <li>")

    print("\n=== Test 7: Numbered list in HTML ===")

    raw3 = "CAC BUOC:\n1. Buoc mot\n2. Buoc hai\n3. Buoc ba\n"
    html_out4 = BacktestScreen._format_ai_to_html(raw3, light=False)
    check("<ol" in html_out4, "numbered items in <ol>")
    check(html_out4.count("<li") == 3, "three <li> items generated")

    print("\n=== Test 8: Number highlighting ===")

    raw4 = "- Ky vong +0.35R, ti le 52.0%, PF 1.45"
    html_out5 = BacktestScreen._format_ai_to_html(raw4, light=False)
    check("+0.35R" in html_out5, "R value present and highlighted")
    check("52.0%" in html_out5, "percentage present and highlighted")

    print("\n=== Test 9: None values do not crash ===")

    s9 = make_screen()
    s9.result = {
        "summary": {
            "total_trades": None, "win_rate": None, "expectancy_r": None,
            "profit_factor": None, "max_drawdown_r": None, "total_r": None,
            "wins": None, "losses": None, "expired": None, "breakeven": None,
            "max_consecutive_wins": None, "max_consecutive_losses": None,
            "average_win_r": None, "average_loss_r": None, "average_holding_bars": None,
        },
        "breakdowns": {},
        "diagnostics": {},
        "request": {},
    }
    prompt9 = s9._build_analysis_prompt()
    check(isinstance(prompt9, str) and len(prompt9) > 50, "None values handled without crash")

    print("\n=== Test 10: No English words in Vietnamese instructions ===")

    s10 = make_screen()
    s10.result = {
        "summary": {
            "total_trades": 30, "win_rate": 55.0, "expectancy_r": 0.40,
            "profit_factor": 1.50, "max_drawdown_r": -7.0, "total_r": 12.0,
            "wins": 17, "losses": 10, "expired": 1, "breakeven": 2,
            "max_consecutive_wins": 5, "max_consecutive_losses": 3,
            "average_win_r": 1.6, "average_loss_r": -1.0, "average_holding_bars": 10,
        },
        "breakdowns": {
            "by_market_regime": {
                "aligned": {"total_trades": 20, "win_rate": 60.0, "expectancy_r": 0.50,
                            "profit_factor": 1.6, "max_drawdown_r": -5.0, "total_r": 10.0},
            },
            "by_side": {
                "BUY": {"total_trades": 15, "win_rate": 60.0, "expectancy_r": 0.50,
                        "profit_factor": 1.6, "max_drawdown_r": -5.0, "total_r": 7.5},
            },
            "by_final_score_bucket": {
                "50-60": {"total_trades": 30, "win_rate": 55.0, "expectancy_r": 0.40,
                          "profit_factor": 1.50, "max_drawdown_r": -7.0, "total_r": 12.0},
            },
            "by_expected_effective_rr": {
                "1.5-2.0": {"total_trades": 30, "win_rate": 55.0, "expectancy_r": 0.40,
                            "profit_factor": 1.50, "max_drawdown_r": -7.0, "total_r": 12.0},
            },
        },
        "diagnostics": {},
        "request": {"symbol": "EUR/USD"},
    }
    prompt10 = s10._build_analysis_prompt()
    instruction_part = prompt10.split("===\n")[-1] if "===\n" in prompt10 else prompt10
    forbidden_english = ["edge", "drawdown", "setup", "please", "note that"]
    found = [w for w in forbidden_english if w.lower() in instruction_part.lower()]
    check(len(found) == 0, f"no English in instructions (found: {found})")

    print("\n=== Test 11: Part numbering is sequential and complete ===")

    s11 = make_screen()
    s11.result = {
        "summary": {
            "total_trades": 30, "win_rate": 55.0, "expectancy_r": 0.40,
            "profit_factor": 1.50, "max_drawdown_r": -7.0, "total_r": 12.0,
            "wins": 17, "losses": 10, "expired": 1, "breakeven": 2,
            "max_consecutive_wins": 5, "max_consecutive_losses": 3,
            "average_win_r": 1.6, "average_loss_r": -1.0, "average_holding_bars": 10,
        },
        "breakdowns": {
            "by_market_regime": {
                "aligned": {"total_trades": 20, "win_rate": 60.0, "expectancy_r": 0.50,
                            "profit_factor": 1.6, "max_drawdown_r": -5.0, "total_r": 10.0},
            },
            "by_side": {
                "BUY": {"total_trades": 15, "win_rate": 60.0, "expectancy_r": 0.50,
                        "profit_factor": 1.6, "max_drawdown_r": -5.0, "total_r": 7.5},
            },
            "by_final_score_bucket": {
                "50-60": {"total_trades": 30, "win_rate": 55.0, "expectancy_r": 0.40,
                          "profit_factor": 1.50, "max_drawdown_r": -7.0, "total_r": 12.0},
            },
            "by_expected_effective_rr": {
                "1.5-2.0": {"total_trades": 30, "win_rate": 55.0, "expectancy_r": 0.40,
                            "profit_factor": 1.50, "max_drawdown_r": -7.0, "total_r": 12.0},
            },
        },
        "diagnostics": {},
        "request": {"symbol": "EUR/USD"},
    }
    prompt11 = s11._build_analysis_prompt()
    import re
    part_nums = [int(m.group(1)) for m in re.finditer(r'PHẦN (\d)', prompt11)]
    check(part_nums == sorted(part_nums), f"parts appear in order: {part_nums}")
    check(len(part_nums) == 7, f"all 7 parts present: found {len(part_nums)}")

    # ── Summary ──
    total = passed + failed
    print(f"\n{'=' * 50}")
    print(f"RESULTS: {passed}/{total} PASS, {failed}/{total} FAIL")
    print(f"{'=' * 50}")

    if failed:
        print("\nFAILURE DETAILS ABOVE")
    else:
        print("ALL TESTS PASSED")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
