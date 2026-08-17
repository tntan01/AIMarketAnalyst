# Tài liệu dự án AI Market Analyst

Cập nhật cấu trúc: **11/08/2026**.

Thư mục này là nguồn tham chiếu cho ứng dụng desktop PyQt6 AI Market Analyst.
Khi tài liệu và code khác nhau, ưu tiên theo thứ tự:

1. Domain model, controller và test đang chạy.
2. Tài liệu contract/kiến trúc hiện hành.
3. Tài liệu target đã được phê duyệt nhưng chưa implement.
4. Git history cho kế hoạch/review/migration đã hoàn tất.

## Lối đọc nhanh

| Nhu cầu | Bắt đầu từ |
|---|---|
| Hiểu sản phẩm | `product/product_spec.md` |
| Hiểu kiến trúc tổng thể | `architecture/architecture.md` |
| Cài đặt và sử dụng | `guides/installation_guide.md`, `guides/USER_GUIDE.md` |
| Vận hành Backtest -> Scanner -> Rollout | `guides/workflow_guide.md` |
| Scanner runtime contract | `scanner/scanner-flow.md` |
| Chấm điểm Scanner V3 hiện hành | `scanner/technical-scoring-architecture.md` |
| Kiến trúc đích Scanner V4 | `scanner/scanner-v4-architecture.md` — approved design, chưa phải runtime |
| Backtest runtime/validation | `backtest/system_backtest_design.md` |
| Macro scoring hiện hành | `macro/macro_score_architecture.md` |
| Vận hành/re-validate VIX theo pair | `macro/macro_score_architecture.md`, mục Bước 7 |
| Thiết kế UI và baseline kiểm thử | `ui/screen_design.md`, `ui/style-guide.md` |

## Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `product/` | Đặc tả sản phẩm và hành vi cấp cao. |
| `architecture/` | Kiến trúc tổng thể, trạng thái runtime, baseline dữ liệu runtime. |
| `guides/` | Hướng dẫn cài đặt, sử dụng và vận hành. |
| `scanner/` | Runtime Scanner V3 và kiến trúc đích Scanner V4. |
| `backtest/` | Thiết kế Backtest hiện hành và runbook release. |
| `trading/` | Quản lý lệnh, R:R và contract liên quan giao dịch. |
| `macro/` | Macro runtime, economic calendar và VIX pair sensitivity. |
| `ui/` | Thiết kế màn hình, style guide, audit/report/lock/baseline UI. |

## Tài liệu hiện hành quan trọng

- `scanner/scanner-v4-architecture.md`: runtime contract hiện hành của Scanner V4
  (live từ 15/08/2026): TechnicalScore chỉ gồm Trend/Momentum/Location/SMC, Risk
  và Macro là gate, order policy owner-accepted.
- `scanner/scanner-flow.md`: luồng Scanner V3 legacy (historical); §11 ghi guard
  chain thực thi live.
- `scanner/technical-scoring-architecture.md`: contract chấm điểm và ranking.
- `backtest/system_backtest_design.md`: thiết kế Backtest hiện hành.
- `backtest/backtest-release-runbook.md`: quy trình golden, shadow, forward-demo và release.
- `architecture/runtime-status.md`: trạng thái settings/thực thi thực tế trên máy hiện tại.
- `macro/macro_score_architecture.md`: contract chấm điểm macro hiện hành.
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
- Thay đổi macro scoring phải cập nhật `macro/macro_score_architecture.md`; nếu
  liên quan calibration/TTL/map runtime thì cập nhật mục Bước 7 trong cùng file.
- Mỗi bước Scanner V4 phải được phân tích và cập nhật vào
  `scanner/scanner-v4-architecture.md` trước khi sửa code.
- Scanner V4 direct-cutover không dùng dual scoring/shadow v3-v4. Tài liệu
  runtime V3 chỉ được đổi thành V4 khi code, test và version của bước tương ứng
  đã hoàn tất.

## Tài liệu đã hợp nhất hoặc loại bỏ

Các proposal năm thành phần, SMC migration plan/log và build-evidence bundle,
MVP coding guide, Order Management review/implementation plan đã hoàn tất được
loại khỏi cây tài liệu. Contract còn hiệu lực đã được giữ trong tài liệu
canonical tương ứng; lịch sử chi tiết vẫn truy được qua Git.
