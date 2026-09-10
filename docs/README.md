# Tài liệu dự án AI Market Analyst

Cập nhật cấu trúc: **09/09/2026**.

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
| Scanner runtime contract | `scanner/scanner-architecture.md` — live từ 15/08/2026 |
| Luồng Scanner lịch sử | `scanner/scanner-flow.md` — tham khảo (pre-cutover) |
| Chấm điểm Scanner | `scanner/scanner-architecture.md` §3; `scanner/technical-scoring-architecture.md` giữ nội dung legacy có nhãn |
| Nâng cấp Location và plan cho CODER | [Location scoring upgrade plan](plans/location-scoring-upgrade-plan.md) — runtime đã nối sau H01/H02; R5 đã được Tech Lead duyệt ngày 10/09/2026 |
| Macro scoring hiện hành | `macro/macro_score_architecture.md` |
| Vận hành/re-validate VIX theo pair | `macro/macro_score_architecture.md`, mục Bước 7 |
| Thiết kế UI và baseline kiểm thử | `ui/screen_design.md`, `ui/style-guide.md` |

## Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `product/` | Đặc tả sản phẩm và hành vi cấp cao. |
| `architecture/` | Kiến trúc tổng thể, trạng thái runtime, baseline dữ liệu runtime. |
| `guides/` | Hướng dẫn cài đặt, sử dụng và vận hành. |
| `scanner/` | Runtime Scanner và kiến trúc đích Scanner. |
| `trading/` | Quản lý lệnh, R:R và contract liên quan giao dịch. |
| `macro/` | Macro runtime, economic calendar và VIX pair sensitivity. |
| `plans/` | Kế hoạch, task và bằng chứng review; trạng thái nằm trong từng plan. |
| `ui/` | Thiết kế màn hình, style guide, audit/report/lock/baseline UI. |

## Tài liệu hiện hành quan trọng

- `scanner/scanner-architecture.md`: runtime contract hiện hành của Scanner
  (live từ 15/08/2026): TechnicalScore chỉ gồm Trend/Momentum/Location/SMC, Risk
  và Macro là gate, order policy owner-accepted.
- `scanner/scanner-flow.md`: luồng Scanner legacy (historical); §11 ghi guard
  chain thực thi live; §13 ghi luồng canonical và tích hợp Location runtime.
- `scanner/technical-scoring-architecture.md`: chấm điểm/ranking legacy;
  §13 tóm tắt canonical và §14 ghi contract Location runtime; R5 đã được Tech Lead duyệt ngày 10/09/2026.
- `architecture/runtime-status.md`: trạng thái settings/thực thi thực tế trên máy hiện tại.
- `macro/macro_score_architecture.md`: contract chấm điểm macro hiện hành.
- `ui/style-guide.md`: quy tắc UI sau chuẩn hóa style/density.

## Location: runtime đã nối, R5 đã duyệt — 10/09/2026

**ĐÃ NỐI RUNTIME, TECH LEAD ĐÃ DUYỆT R5.** Scanner truyền cutoff cố định từ
packet qua analysis tới snapshot; Location dùng H1/H4 đã đóng, detail versioned
và card UI dùng template/palette semantic. Tech Lead xác nhận R5 sau review code,
regression và smoke fixture; chi tiết bằng chứng được ghi trong plan.

- Đặc tả thuật toán, cấu hình khởi đầu và hướng dẫn từng task:
  [Location upgrade plan](plans/location-scoring-upgrade-plan.md).
- Ranh giới kiến trúc và tác động lên quyết định:
  [Scanner architecture](scanner/scanner-architecture.md), mục Location runtime.
- Input/raw/rounding: [Features spec](scanner/scanner-features-spec.md), §0.1
  “Location runtime”.
- Luồng tích hợp: [Scanner flow](scanner/scanner-flow.md), phụ lục Location.
- Hiển thị: [Screen design](ui/screen_design.md) và [Style guide](ui/style-guide.md),
  phần Location runtime.
- Ảnh hưởng đối với người dùng: [User guide](guides/USER_GUIDE.md), §3.1.

CODER dùng code để xác minh **hiện trạng**, dùng plan và các mục runtime này để
đối chiếu thay đổi đã thống nhất. R5 chưa có smoke production và chưa cho phép
gửi lệnh; các giới hạn này không thay đổi phạm vi Trend/Momentum/SMC hay gate.

Sau task **8, 14, 21, 28, 32**, CODER **phải dừng, hỏi và chờ xác nhận**
Tech Lead/người dùng theo plan §11.2. Bản đầu không cần database, replay,
backtest sâu, gate entry mới hoặc tối ưu threshold.

## Bằng chứng kiểm thử UI

- `ui/style/`: baseline, lock và allowlist cho style audit.
- `ui/density/`: baseline và lock cho density audit.
- `ui/reports/`: report responsive/dark-surface máy đọc được.
- `ui/baseline/`: ảnh baseline visual QA và manifest.

Các file này không phải tài liệu đọc chính, nhưng đang được tools/tests dùng để khóa regressions UI.

## Quy tắc cập nhật

- Thay đổi hành vi Scanner phải cập nhật tối thiểu `scanner/scanner-flow.md`,
  tài liệu kỹ thuật liên quan và test.
- Tính năng Backtest đã bị loại bỏ (2026-09-09): thay đổi phân quyền quét/auto-trade
  cập nhật `guides/USER_GUIDE.md`.
- Thay đổi UI contract phải cập nhật `ui/style-guide.md` và các lock/report nếu cần.
- Thay đổi macro scoring phải cập nhật `macro/macro_score_architecture.md`; nếu
  liên quan calibration/TTL/map runtime thì cập nhật mục Bước 7 trong cùng file.
- Mỗi bước Scanner phải được phân tích và cập nhật vào
  `scanner/scanner-architecture.md` trước khi sửa code.
- Scanner direct-cutover không dùng dual scoring/shadow. Tài liệu
  runtime chỉ được cập nhật khi code, test và version của bước tương ứng
  đã hoàn tất.
- Với Location, chỉ đổi mục target thành runtime sau chuyển caller và kiểm
  tra thực tế theo plan; nghiệm thu cuối phải có xác nhận R5. Không thay các
  số test lịch sử bằng kết quả chưa chạy.

## Tài liệu đã hợp nhất hoặc loại bỏ

Các proposal năm thành phần, SMC migration plan/log và build-evidence bundle,
MVP coding guide, Order Management review/implementation plan đã hoàn tất được
loại khỏi cây tài liệu. Contract còn hiệu lực đã được giữ trong tài liệu
canonical tương ứng; lịch sử chi tiết vẫn truy được qua Git.
