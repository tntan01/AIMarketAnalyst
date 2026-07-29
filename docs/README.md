# Tài liệu dự án AI Market Analyst

Cập nhật cấu trúc: **29/07/2026**.

Thư mục này là nguồn tham chiếu cho ứng dụng desktop PyQt6 AI Market Analyst.
Khi tài liệu và code khác nhau, ưu tiên theo thứ tự:

1. Domain model, controller và test đang chạy.
2. Tài liệu contract/kiến trúc hiện hành.
3. Tài liệu kế hoạch, review, proposal và archive lịch sử.

## Lối đọc nhanh

| Nhu cầu | Bắt đầu từ |
|---|---|
| Hiểu sản phẩm | `product/product_spec.md` |
| Hiểu kiến trúc tổng thể | `architecture/architecture.md` |
| Cài đặt và sử dụng | `guides/installation_guide.md`, `guides/USER_GUIDE.md` |
| Vận hành Backtest -> Scanner -> Rollout | `guides/workflow_guide.md` |
| Scanner runtime contract | `scanner/scanner-flow.md` |
| Chấm điểm Scanner V2 | `scanner/technical-scoring-architecture.md` |
| Backtest runtime/validation | `backtest/system_backtest_design.md` |
| Thiết kế UI và baseline kiểm thử | `ui/screen_design.md`, `ui/style-guide.md` |

## Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `product/` | Đặc tả sản phẩm và hành vi cấp cao. |
| `architecture/` | Kiến trúc tổng thể, trạng thái runtime, baseline dữ liệu runtime. |
| `guides/` | Hướng dẫn cài đặt, sử dụng và vận hành. |
| `scanner/` | Scanner V2, scoring, SMC và kế hoạch tối ưu quét. |
| `backtest/` | Thiết kế Backtest, runbook release, review, simplification và điều tra validation. |
| `trading/` | Quản lý lệnh, R:R và contract liên quan giao dịch. |
| `macro/` | Macro score, economic calendar và đề xuất UI macro. |
| `ui/` | Thiết kế màn hình, style guide, audit/report/lock/baseline UI. |
| `archive/` | Tài liệu lịch sử, không phải runtime contract hiện hành. |

## Tài liệu hiện hành quan trọng

- `scanner/scanner-flow.md`: contract luồng Scanner V2.
- `scanner/technical-scoring-architecture.md`: contract chấm điểm và ranking.
- `backtest/system_backtest_design.md`: thiết kế Backtest hiện hành.
- `backtest/backtest-release-runbook.md`: quy trình golden, shadow, forward-demo và release.
- `architecture/runtime-status.md`: trạng thái rollout/settings thực tế trên máy hiện tại.
- `ui/style-guide.md`: quy tắc UI sau chuẩn hóa style/density.

## Bằng chứng kiểm thử UI

- `ui/style/`: baseline, lock và allowlist cho style audit.
- `ui/density/`: baseline và lock cho density audit.
- `ui/reports/`: report responsive/dark-surface máy đọc được.
- `ui/baseline/`: ảnh baseline visual QA và manifest.

Các file này không phải tài liệu đọc chính, nhưng đang được tools/tests dùng để khóa regressions UI.

## Quy tắc cập nhật

- Thay đổi hành vi Scanner phải cập nhật tối thiểu `scanner/scanner-flow.md`,
  tài liệu kỹ thuật liên quan và test.
- Thay đổi Backtest validation/release phải cập nhật `backtest/system_backtest_design.md`
  hoặc runbook tương ứng.
- Thay đổi UI contract phải cập nhật `ui/style-guide.md` và các lock/report nếu cần.
- Tài liệu proposal hoặc archive phải ghi rõ trạng thái để không bị hiểu là runtime contract.
