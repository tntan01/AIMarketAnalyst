# Tài liệu dự án AI Market Analyst

## Mục tiêu tài liệu

Bộ tài liệu này là nguồn tham chiếu gọn cho ứng dụng desktop PyQt6 AI Market Analyst.

Stack công nghệ chính:

* PyQt6 làm app desktop.
* `QWebEngineView` nhúng chart web/HTML.
* Core Python xử lý MT5, AI, indicator, scoring và quản trị rủi ro.

Tài liệu phải giúp đạt 3 mục tiêu:

1. Chương trình có độ hoàn thiện cao về tính năng và giao diện.
2. Dễ nâng cấp, chỉnh sửa và test sau này.
3. Dễ đóng gói, cài đặt và chạy trên máy tính khác.

## Danh sách tài liệu

1. `product_spec.md` — Đặc tả sản phẩm, phạm vi 28 cặp Forex + XAU/USD + XAG/USD + BTC/USD, quy tắc MT5/AI/scoring và phụ lục auto trade hiện tại.
2. `architecture.md` — Kiến trúc module, dependency, runtime data, chart nhúng, Telegram alert, auto-entry MT5 và packaging.
3. `screen_design.md` — Thiết kế chi tiết các màn hình PyQt6, gồm hành vi Scanner auto-scan/auto-entry.
4. `installation_guide.md` — Hướng dẫn cài môi trường, chạy app, đóng gói và checklist an toàn trước khi bật auto trade.
5. `mvp_coding_guide.md` — Thứ tự code MVP theo từng giai đoạn và quy tắc triển khai auto trade/Telegram.

## Nguyên tắc cập nhật

Khi thay đổi kiến trúc, màn hình, database, quy trình cài đặt hoặc cách đóng gói, cập nhật trực tiếp vào một trong 5 file trên. Không tạo thêm file nhỏ nếu nội dung có thể đặt vào tài liệu hiện có.
