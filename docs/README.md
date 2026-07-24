# Tài liệu dự án AI Market Analyst

Cập nhật đồng bộ gần nhất: **24/07/2026**.

Thư mục này là nguồn tham chiếu cho ứng dụng desktop PyQt6 AI Market Analyst. Khi tài liệu và chương trình khác nhau, ưu tiên theo thứ tự:

1. Domain model, controller và test đang chạy.
2. Tài liệu kiến trúc/luồng có nhãn **hiện hành**.
3. Tài liệu review, kế hoạch, đề xuất và hướng dẫn MVP lịch sử.

## Tài liệu hiện hành

| Tài liệu | Phạm vi |
|---|---|
| `product_spec.md` | Đặc tả hành vi sản phẩm đang triển khai. |
| `architecture.md` | Kiến trúc tổng thể, module và dependency. |
| `scanner-flow.md` | Luồng Scanner V2 từ scan đến revalidation và rollout. |
| `technical-scoring-architecture.md` | Ý nghĩa các lớp điểm, strategy branch, trạng thái và ranking. |
| `workflow_guide.md` | Quy trình vận hành Backtest → Scanner → rollout. |
| `runtime-status.md` | Trạng thái rollout/settings thực tế đang lưu trên máy hiện tại. |
| `screen_design.md` | Thiết kế các màn hình; phần Scanner phải tuân theo `scanner-flow.md`. |
| `installation_guide.md` | Cài đặt, chạy, đóng gói và checklist an toàn. |
| `order_management.md` | Quản lý lệnh và trạng thái giao dịch. |
| `system_backtest_design.md` | Thiết kế hệ thống backtest và validation. |

## Tài liệu đánh giá và lịch sử

| Tài liệu | Trạng thái |
|---|---|
| `scanner-scoring-review.md` | Review, kế hoạch 9 giai đoạn (0–8) và nhật ký hoàn thành Scanner V2. Code/tooling đã hoàn tất; validation thực tế trước production còn mở. |
| `mvp_coding_guide.md` | Hướng dẫn triển khai MVP lịch sử; không phải runtime contract của Scanner V2. |
| `macro_score_architecture.md` | Kiến trúc chấm điểm macro chuyên biệt. |
| `macro_ui_enhancement_proposal.md` | Đề xuất cải tiến UI, không mặc nhiên là tính năng đã triển khai. |
| `design_economic_calendar_fix.md` | Tài liệu thiết kế/sửa lỗi lịch kinh tế tại thời điểm viết. |

## Trạng thái Scanner V2

- Chín giai đoạn, đánh số **0 đến 8**, đã hoàn tất về code và test chuyên biệt.
- Mã nguồn, settings mới và settings migrate mặc định ở rollout stage
  `SHADOW`; stage này không gửi lệnh.
- Runtime trên máy hiện tại đã chọn `PRODUCTION`, bật ba feature flag V2 và
  dùng SMC v2. Đây chỉ là stage đã lưu; release gate hiện vẫn
  `ready=false`, nên chưa có quyền gửi lệnh thật.
- Nút auto-entry khả dụng trong chế độ quét định kỳ, mặc định không chọn và bị
  reset khi chuyển sang quét một lần. Khi người dùng chủ động bật, request có
  `auto_trade_enabled=true`; auto trade và lệnh thủ công đều đi qua shared
  execution path cùng toàn bộ safety gate.
- Chưa được xem là production-ready cho tới khi đủ bằng chứng shadow, demo, canary, OOS/demo performance và rollback.
- Backtest chỉ tạo một strategy branch khi config hợp lệ; nó không được ghi đè Decision Engine, execution gate hoặc portfolio gate.
- Mọi lệnh Scanner, kể cả thao tác thủ công từ giao diện Scanner, phải đi qua `ScannerController.execute_order_candidate()`.

## Quy tắc cập nhật

- Thay đổi hành vi Scanner phải cập nhật tối thiểu `scanner-flow.md`, tài liệu kỹ thuật tương ứng và test.
- Không mô tả `opportunity_score` là quyết định vào lệnh; đây chỉ là compatibility alias của ranking hiện tại.
- Không dùng tên “nhánh có/không backtest” nếu chưa nói rõ trạng thái validation. Ba branch chuẩn là `BACKTEST_VALIDATED`, `DEFAULT_RULES` và `BACKTEST_INVALID`.
- Tài liệu đề xuất hoặc lịch sử phải ghi rõ trạng thái để không bị hiểu là runtime contract.
