"""Generate the CP1 report from the committed SD artifacts (task SD-C4).

Run:
    python -X utf8 scripts/smc_demote_report.py

The report is a *mechanical* rendering of already-committed numbers: it reads the
five result files, checks the replay-row hash, and writes ``report.md``.  It adds
no statistics beyond ``half_width``/``need``/``factor`` and the break-even TP rate,
carries no recommendation, and is byte-deterministic across runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_demote"
ANALYSIS_PATH = OUTPUT_DIR / "analysis.json"
SUMMARY_PATH = OUTPUT_DIR / "replay_summary.json"
MANIFEST_PATH = OUTPUT_DIR / "corpus_manifest.json"
CUTOFFS_PATH = OUTPUT_DIR / "cutoffs.json"
SCORER_CHECK_PATH = OUTPUT_DIR / "scorer_check.json"
REPORT_MD = OUTPUT_DIR / "report.md"

REGIMES = ("trending_up", "trending_down", "ranging", "volatile", "unknown")
COMPONENTS = ("trend", "momentum", "location", "smc_raw", "quality_score")
BUCKETED_COMPONENTS = ("trend", "momentum", "location", "smc_raw")
TP_SL_VALUES = ("tp_first", "sl_first", "unresolved", "not_filled", "plan_invalid", "None")
Q4_DIFF_FLOOR = -0.05
MINUS = "\u2212"
EM_DASH = "\u2014"
SQRT = "\u221a"


def fmt_num(value: Any) -> str:
    if value is None:
        return EM_DASH
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def fmt_pct(value: Any) -> str:
    if value is None:
        return EM_DASH
    return f"{float(value) * 100:.1f}%"


def mechanical_conclusion(pass1: bool, pass2: bool) -> str:
    """The one mechanical Q4 verdict sentence for the two condition flags."""

    if not pass1:
        return (
            "Không đạt điều kiện (1) → giữ nguyên TechnicalScore 4 thành phần; "
            "TL cân nhắc phương án B."
        )
    if not pass2:
        return "Đạt (1), không đạt (2) → chọn A; TL quyết định lại Q6."
    return "Đạt cả hai điều kiện → chọn A."


def q4_width_estimate(diff: float, low: float | None, high: float | None) -> dict[str, Any]:
    """``half_width``/``need``/``factor`` and the exact sentence to print."""

    half_width = None if low is None or high is None else (high - low) / 2.0
    need = diff - Q4_DIFF_FLOOR
    if need > 0 and half_width is not None:
        factor = (half_width / need) ** 2
        text = (
            "Ước tính thô: nếu chênh lệch giữ nguyên, cần khoảng "
            f"{factor:.1f} lần số pair hiện tại để cận dưới CI95 đạt "
            f"{MINUS}0,05 (giả định độ rộng CI tỷ lệ 1/{SQRT}n)."
        )
    else:
        factor = None
        text = f"Ước lượng điểm đã dưới ngưỡng {MINUS}0,05."
    return {"half_width": half_width, "need": need, "factor": factor, "text": text}


def hashes_match(analysis: dict[str, Any], summary: dict[str, Any]) -> bool:
    """Whether the replay-row hash agrees between the two committed files."""

    return (
        analysis.get("inputs", {}).get("rows_sha256")
        == summary.get("rows_sha256")
    )


def _ci(ci95: list[Any]) -> str:
    return f"[{fmt_num(ci95[0])}, {fmt_num(ci95[1])}]"


def _regime_counts(analysis: dict[str, Any]) -> dict[str, int]:
    distribution = analysis["regime_distribution"]["distribution"]
    return {regime: distribution[regime]["count"] for regime in REGIMES}


def _render_q4(analysis: dict[str, Any], min_rr: float) -> list[str]:
    lines: list[str] = []
    condition_1 = analysis["side_selection"]["q4_condition_1"]
    condition_2 = analysis["smc_tp_sl"]["q4_condition_2"]

    if condition_1["pass"]:
        result_1 = "ĐẠT"
    else:
        result_1 = "KHÔNG ĐẠT"
    if condition_2["insufficient_samples"]:
        result_2 = "KHÔNG ĐỦ MẪU"
    elif condition_2["pass"]:
        result_2 = "ĐẠT"
    else:
        result_2 = "KHÔNG ĐẠT"

    lines.append("| Điều kiện | Chỉ số | Giá trị | CI95 | Ngưỡng | Kết quả |")
    lines.append("|---|---|---:|---|---|---|")
    lines.append(
        "| (1) Chọn side | mean fwd 24h (ATR) side chọn bởi 3 thành phần "
        f"{MINUS} 4 thành phần, trên pair cả hai chọn được | "
        f"{fmt_num(condition_1['diff'])} | {_ci(condition_1['ci95'])} | "
        f"cận dưới ≥ {MINUS}0,05 | {result_1} |"
    )
    lines.append(
        "| (2) SMC phân biệt TP/SL | AUC `quality_score`, n resolved = "
        f"{condition_2['n_resolved']} (TP {condition_2['n_tp']} / SL "
        f"{condition_2['n_sl']}) | {fmt_num(condition_2['auc'])} | "
        f"{_ci(condition_2['ci95'])} | AUC ≥ 0,55 và cận dưới > 0,5; n ≥ 200 | "
        f"{result_2} |"
    )
    lines.append("")
    lines.append(
        "**Kết quả cơ học của quy tắc Q4:** "
        + mechanical_conclusion(condition_1["pass"], condition_2["pass"])
    )
    lines.append("")

    estimate = q4_width_estimate(
        condition_1["diff"], condition_1["ci95"][0], condition_1["ci95"][1]
    )
    parts = (
        "**Độ rộng khoảng tin cậy (1):** "
        f"half_width = {fmt_num(estimate['half_width'])}, "
        f"need = {fmt_num(estimate['need'])}"
    )
    if estimate["factor"] is not None:
        parts += f", factor = {estimate['factor']:.1f}."
    else:
        parts += "."
    lines.append(parts + " " + estimate["text"])
    lines.append("")
    return lines


def _render_data(
    analysis: dict[str, Any],
    summary: dict[str, Any],
    manifest: dict[str, Any],
    cutoffs: dict[str, Any],
    scorer_check: dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    symbols = manifest.get("symbols", {})
    ok_count = sum(1 for entry in symbols.values() if entry.get("status") == "ok")
    cutoff_summary = cutoffs["summary"]
    by_hour = cutoff_summary.get("by_hour", {})
    by_month = cutoff_summary.get("by_month", {})
    rejected = cutoff_summary.get("rejected", {})
    inputs = analysis["inputs"]
    error_types = summary.get("error_types", {})

    lines.append(f"- `fetched_at`: {manifest.get('fetched_at')}")
    lines.append(
        f"- Symbol: {ok_count} ok / {len(symbols)} tổng (manifest)"
    )
    lines.append(f"- `min_rr`: {fmt_num(manifest.get('min_rr'))}")
    lines.append(f"- Tổng cutoff: {cutoff_summary.get('total')}")
    lines.append(
        "- Cutoff theo giờ (UTC): "
        + ", ".join(
            f"{hour}h = {count}"
            for hour, count in sorted(by_hour.items(), key=lambda kv: int(kv[0]))
        )
    )
    lines.append(
        "- Cutoff theo tháng: "
        + ", ".join(f"{month} = {count}" for month, count in by_month.items())
    )
    lines.append(
        "- Cutoff bị bỏ theo lý do: "
        + ", ".join(f"{reason} = {count}" for reason, count in rejected.items())
    )
    lines.append(f"- Rows: {summary.get('rows')}")
    lines.append(
        f"- Errors: {summary.get('errors')} "
        f"({', '.join(f'{key}: {value}' for key, value in error_types.items())})"
    )
    lines.append(f"- Số cụm ngày: {inputs.get('day_clusters')}")
    lines.append(
        f"- `bootstrap_n`: {inputs.get('bootstrap_n')}, `seed`: {inputs.get('seed')}"
    )
    mismatches = len(scorer_check.get("mismatches", []))
    lines.append(
        f"- check-scorer: {scorer_check.get('checked')} side, {mismatches} mismatch"
    )
    lines.append("")
    lines.append("| regime | rows | fraction |")
    lines.append("|---|---:|---:|")
    distribution = analysis["regime_distribution"]["distribution"]
    for regime in REGIMES:
        entry = distribution[regime]
        lines.append(
            f"| {regime} | {entry['count']} | {fmt_pct(entry['fraction'])} |"
        )
    lines.append("")
    return lines


def _render_side_selection(analysis: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    side = analysis["side_selection"]
    counts = side["counts"]
    lines.append(
        f"- Số pair: both = {counts['both']}, only_no_smc = {counts['only_no_smc']}, "
        f"neither = {counts['neither']}, changed_side = {counts['changed_side']}"
    )
    lines.append("")
    lines.append("| metric | current | no_smc |")
    lines.append("|---|---:|---:|")
    for key in (
        "mean_fwd_24h",
        "mean_fwd_8h",
        "hit_rate",
        "median_gap",
        "gap_ok_count",
        "gap_ok_mean_fwd_24h",
        "gap_ok_hit_rate",
    ):
        lines.append(
            f"| {key} | {fmt_num(side['current'][key])} | {fmt_num(side['no_smc'][key])} |"
        )
    lines.append("")
    only = side["gap_ok_only_one_variant"]
    lines.append(
        f"- `gap_ok` chỉ ở current: {only['current_not_no_smc']}; "
        f"chỉ ở no_smc: {only['no_smc_not_current']}"
    )
    descriptive = side["descriptive_fwd_8h"]
    lines.append(
        f"- Chênh lệch fwd 8h (mô tả, không thuộc Q4): diff = "
        f"{fmt_num(descriptive['diff'])}, CI95 = {_ci(descriptive['ci95'])}"
    )
    lines.append(
        "- `only_no_smc_mean_fwd_24h` = "
        f"{fmt_num(side['only_no_smc_mean_fwd_24h'])}. "
        "Pair mà biến thể hiện tại không chấm được vì SMC data_unavailable ở ít "
        "nhất một side (fail-closed)."
    )
    lines.append("")
    lines.append("| regime | both | changed | mean_diff_fwd_24h |")
    lines.append("|---|---:|---:|---:|")
    for regime in REGIMES:
        entry = side["by_regime"][regime]
        lines.append(
            f"| {regime} | {entry['both']} | {entry['changed']} | "
            f"{fmt_num(entry['mean_diff_fwd_24h'])} |"
        )
    lines.append("")
    return lines


def _render_discrimination(analysis: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    all_blocks = analysis["component_discrimination"]["all"]
    lines.append("| component | n | spearman_fwd_8h | spearman_fwd_24h | auc_fwd_24h_pos |")
    lines.append("|---|---:|---:|---:|---:|")
    for component in COMPONENTS:
        block = all_blocks[component]
        lines.append(
            f"| {component} | {block['n']} | {fmt_num(block['spearman_fwd_8h'])} | "
            f"{fmt_num(block['spearman_fwd_24h'])} | {fmt_num(block['auc_fwd_24h_pos'])} |"
        )
    lines.append("")
    for component in BUCKETED_COMPONENTS:
        block = all_blocks[component]
        lines.append(f"### Bucket `{component}` (`fwd_24h_atr`)")
        lines.append("")
        lines.append("| bucket | n | hit_rate | mean_fwd_24h |")
        lines.append("|---|---:|---:|---:|")
        for bucket, item in block.get("hit_rate_by_bucket", {}).items():
            lines.append(
                f"| {bucket} | {item['n']} | {fmt_pct(item['hit_rate'])} | "
                f"{fmt_num(item['mean_fwd_24h'])} |"
            )
        lines.append("")
    lines.append(
        "Chi tiết theo regime: xem `reports/scanner/smc_demote/analysis.md`."
    )
    lines.append("")
    return lines


def _render_tp_sl(analysis: dict[str, Any], min_rr: float) -> list[str]:
    lines: list[str] = []
    smc = analysis["smc_tp_sl"]
    counts = smc["counts_total"]
    lines.append("| tp_sl | count |")
    lines.append("|---|---:|")
    for value in TP_SL_VALUES:
        lines.append(f"| {value} | {counts[value]} |")
    lines.append("")

    condition_2 = smc["q4_condition_2"]
    lines.append("| component | AUC | CI95 |")
    lines.append("|---|---:|---|")
    lines.append(
        f"| quality_score | {fmt_num(condition_2['auc'])} | {_ci(condition_2['ci95'])} |"
    )
    for component in ("quality_raw", "b", "q", "l", "c"):
        block = smc["auc_extra"][component]
        lines.append(
            f"| {component} | {fmt_num(block['auc'])} | {_ci(block['ci95'])} |"
        )
    lines.append("")

    lines.append("### Tỷ lệ `tp_first` theo bucket `quality_raw`")
    lines.append("")
    lines.append("| bucket | n | tp_first_rate |")
    lines.append("|---|---:|---:|")
    for bucket, item in smc["tp_first_rate_by_quality_raw_bucket"].items():
        lines.append(f"| {bucket} | {item['n']} | {fmt_pct(item['tp_first_rate'])} |")
    lines.append("")

    lines.append("### Tỷ lệ `tp_first` theo `readiness_status`")
    lines.append("")
    lines.append("| readiness_status | n | tp_first_rate |")
    lines.append("|---|---:|---:|")
    for status, item in smc["tp_first_rate_by_readiness_status"].items():
        lines.append(f"| {status} | {item['n']} | {fmt_pct(item['tp_first_rate'])} |")
    lines.append("")

    overall_rate = (
        smc["n_tp"] / smc["n_resolved"] if smc["n_resolved"] else None
    )
    lines.append(f"- Tỷ lệ `tp_first` chung = {fmt_pct(overall_rate)}")
    break_even = 1.0 / (1.0 + min_rr)
    lines.append(
        f"- Với R:R tối thiểu {fmt_num(min_rr)}, tỷ lệ TP-trước hòa vốn (bỏ qua "
        f"chi phí) là 1/(1+R:R) = {fmt_pct(break_even)}."
    )
    lines.append("")
    lines.append(
        "| nhãn | mean_mfe_r | mean_mae_r |"
    )
    lines.append("|---|---:|---:|")
    lines.append(
        f"| tp_first | {fmt_num(smc['mfe_r_mean_by_label']['tp_first'])} | "
        f"{fmt_num(smc['mae_r_mean_by_label']['tp_first'])} |"
    )
    lines.append(
        f"| sl_first | {fmt_num(smc['mfe_r_mean_by_label']['sl_first'])} | "
        f"{fmt_num(smc['mae_r_mean_by_label']['sl_first'])} |"
    )
    lines.append("")
    return lines


def _render_q6(analysis: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    q6 = analysis["q6_evidence"]
    distribution = q6["positive_distribution"]
    lines.append("| bucket | count |")
    lines.append("|---|---:|")
    lines.append(f"| None | {q6['n_none']} |")
    lines.append(f"| 0 | {q6['n_zero']} |")
    lines.append(f"| >0 | {q6['n_positive']} |")
    lines.append("")
    lines.append(
        f"- Phân phối giá trị >0: min = {fmt_num(distribution['min'])}, "
        f"p25 = {fmt_num(distribution['p25'])}, median = {fmt_num(distribution['median'])}, "
        f"p75 = {fmt_num(distribution['p75'])}, max = {fmt_num(distribution['max'])}"
    )
    lines.append("")
    lines.append("| smc_state | count |")
    lines.append("|---|---:|")
    for state, count in q6["counts_by_state"].items():
        lines.append(f"| {state} | {count} |")
    lines.append("")
    return lines


def _render_limits(
    analysis: dict[str, Any], summary: dict[str, Any], min_rr: float
) -> list[str]:
    inputs = analysis["inputs"]
    regime = _regime_counts(analysis)
    counts = analysis["smc_tp_sl"]["counts_total"]
    n_plan = sum(counts[value] for value in TP_SL_VALUES if value != "None")
    error_types = summary.get("error_types", {})
    error_types_text = ", ".join(f"{key}: {value}" for key, value in error_types.items())
    lines = [
        f"1. Quy mô nhỏ: {inputs['rows']} snapshot, {inputs['day_clusters']} ngày, "
        f"~3 tháng; regime gần như chỉ có trending (ranging {regime['ranging']}, "
        f"volatile {regime['volatile']}).",
        "2. Không tính spread/chi phí (Q9).",
        "3. fwd 8h/24h tính theo số nến H1 (nến thứ 8/24 sau cutoff), không theo "
        "giờ đồng hồ; qua cuối tuần thì dài hơn 24 giờ.",
        "4. TP/SL: entry là lệnh limit tại mép zone, giá khớp coi là đúng entry; "
        "nến khớp chỉ xét SL; cùng nến chạm TP và SL tính SL (STOP_FIRST); không "
        "khớp trong 48 H1 → not_filled.",
        f"5. Tỷ lệ chưa có kết quả: unresolved {counts['unresolved']}, "
        f"not_filled {counts['not_filled']} trên {n_plan} side có plan.",
        f"6. {summary.get('errors')} cutoff ({fmt_pct(summary.get('error_rate'))}) "
        f"lỗi pipeline SMC ({error_types_text}) bị loại khỏi phân tích.",
        "7. Trọng số 3 thành phần là mặc định chia lại tỷ lệ (Q5), chưa tối ưu.",
        "8. Không có bằng chứng lợi nhuận; mọi chỉ số chỉ mang tính so sánh tương đối.",
    ]
    return lines


def _render_changed_rows(analysis: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    rows = sorted(
        analysis["side_selection"]["changed_rows"],
        key=lambda item: (item["symbol"], item["cutoff"]),
    )
    lines.append(
        "| symbol | cutoff | regime | side hiện tại → mới | buy/sell (current) | "
        "buy/sell (no_smc) | smc_raw buy/sell | fwd 24h hiện tại → mới |"
    )
    lines.append("|---|---|---|---|---:|---:|---|---|")
    for item in rows:
        lines.append(
            f"| {item['symbol']} | {item['cutoff']} | {item['regime']} | "
            f"{item['side_current']} → {item['side_no_smc']} | "
            f"{item['buy_current']}/{item['sell_current']} | "
            f"{item['buy_no_smc']}/{item['sell_no_smc']} | "
            f"{item['smc_raw_buy']}/{item['smc_raw_sell']} | "
            f"{fmt_num(item['fwd_24h_current'])} → {fmt_num(item['fwd_24h_no_smc'])} |"
        )
    lines.append("")
    return lines


def render_report(
    analysis: dict[str, Any],
    summary: dict[str, Any],
    manifest: dict[str, Any],
    cutoffs: dict[str, Any],
    scorer_check: dict[str, Any],
) -> str:
    min_rr = float(manifest.get("min_rr"))
    rows_hash = analysis["inputs"]["rows_sha256"]
    lines: list[str] = [
        "# Báo cáo CP1 — SMC demote (Giai đoạn 1)",
        "",
        f"> Báo cáo sinh tự động bởi `scripts/smc_demote_report.py` từ "
        f"`analysis.json` (rows_sha256 `{rows_hash}`). Không chứa khuyến nghị; "
        f"quyết định thuộc TL/Owner tại CP1.",
        "",
        "## 1. Kết quả quy tắc Q4",
        "",
    ]
    lines.extend(_render_q4(analysis, min_rr))
    lines.append("## 2. Dữ liệu")
    lines.append("")
    lines.extend(_render_data(analysis, summary, manifest, cutoffs, scorer_check))
    lines.append("## 3. Chọn side: 4 thành phần (hiện tại) vs 3 thành phần (Q5)")
    lines.append("")
    lines.extend(_render_side_selection(analysis))
    lines.append("## 4. Khả năng phân biệt từng thành phần")
    lines.append("")
    lines.extend(_render_discrimination(analysis))
    lines.append("## 5. SMC trên side có plan (TP/SL)")
    lines.append("")
    lines.extend(_render_tp_sl(analysis, min_rr))
    lines.append("## 6. Ánh xạ Q6 (SMC → evidence_score) — dữ kiện")
    lines.append("")
    lines.extend(_render_q6(analysis))
    lines.append("## 7. Giới hạn")
    lines.append("")
    lines.extend(_render_limits(analysis, summary, min_rr))
    lines.append("")
    lines.append("## 8. Pair đổi side")
    lines.append("")
    lines.extend(_render_changed_rows(analysis))
    return "\n".join(lines)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="CP1 report generator (task SD-C4)")
    parser.parse_args()

    analysis = _load(ANALYSIS_PATH)
    summary = _load(SUMMARY_PATH)
    if not hashes_match(analysis, summary):
        print("BLOCKED: analysis.json rows_sha256 khác replay_summary.json")
        return 2
    manifest = _load(MANIFEST_PATH)
    cutoffs = _load(CUTOFFS_PATH)
    scorer_check = _load(SCORER_CHECK_PATH)

    text = render_report(analysis, summary, manifest, cutoffs, scorer_check)
    REPORT_MD.write_text(text, encoding="utf-8")
    print(f"report -> {REPORT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
