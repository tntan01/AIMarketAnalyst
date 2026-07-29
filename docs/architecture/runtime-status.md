# Runtime Status

Cập nhật: **25/07/2026 (Asia/Ho_Chi_Minh)**.

Tài liệu này ghi trạng thái cấu hình đang lưu trên máy hiện tại. Đây không
phải giá trị mặc định của mã nguồn và không thay thế contract trong
`scanner-flow.md`.

## Scanner rollout

| Thuộc tính | Giá trị hiện tại |
|---|---|
| Stage | `PRODUCTION` |
| Kill switch | `false` |
| Shadow comparison | `true` |
| Production approved | `true` |
| Bắt buộc tài khoản demo | `false` |
| Allowlist rollout | Rỗng; `PRODUCTION` không giới hạn symbol bằng allowlist |
| SMC scoring mode | `v2` |
| Feature flags runtime | `scanner_architecture_v2=true`, `auto_trade_v2=true`; hai flag Backtest cũ không còn được runtime sử dụng |

`backtest_config_v2` hoặc `backtest_engine_v2` có thể vẫn còn trong file
Settings được tạo bởi bản cũ. Loader hiện bỏ qua hai key này và lần lưu Settings
tiếp theo sẽ không ghi lại; Strategy Router không phụ thuộc vào chúng.

Settings hiện có bản ghi cấu hình riêng cho **31 symbol**. Danh sách
`trading.enabled_symbols` đang rỗng; trường này chỉ đánh dấu các cấu hình
Backtest đã duyệt, không phải danh sách symbol mà Scanner được phép quét.
Scanner vẫn lấy phạm vi mặc định từ 31 mã trong `SUPPORTED_SYMBOLS`. Việc một
symbol được quét hoặc có cấu hình không tự yêu cầu đặt lệnh.

## Trạng thái gửi lệnh

Nút **Tự động vào lệnh MT5** trên màn hình Quét thị trường đã được mở cho chế
độ quét theo khoảng thời gian (`ScannerScreen.AUTO_TRADE_UI_ENABLED=true`).
Nút mặc định **không được chọn** mỗi khi tạo màn hình; người dùng phải chủ động
bật. Khi bật trong auto-scan, request mang
`ScannerRequest.auto_trade_enabled=true`. Chuyển sang quét một lần sẽ disable
và reset nút về unchecked.

Release readiness hiện vẫn là `ready=false`. Vì vậy auto trade vẫn bị rollout
guard trả `RELEASE_GATE_NOT_READY` trước khi gọi MT5. Theo yêu cầu trực tiếp
ngày 25/07/2026, thao tác **Vào lệnh** thủ công trong dialog Scanner được phép
bỏ qua riêng block này khi stage là `PRODUCTION` và đã có production approval.
Override không áp dụng cho auto trade và không bỏ qua kill switch, stage khác,
kết nối/quyền MT5, giá mới, spread, news, R:R hay portfolio guard.

Các block code hiện tại:

- `DEMO_ORDER_SAMPLE_INSUFFICIENT` — `0/20` lệnh demo;
- `CANARY_ORDER_SAMPLE_INSUFFICIENT` — `0/5` lệnh canary;
- `OOS_EVIDENCE_MISSING`;
- `DEMO_EVIDENCE_MISSING`.

Snapshot metrics lúc cập nhật tài liệu có `572/100` shadow samples, không có
side mismatch/unsafe disagreement và
rollback drill đã đạt. Những kết quả này chưa thay thế bằng chứng demo, canary,
OOS và demo performance còn thiếu.

## Ý nghĩa vận hành

`stage=PRODUCTION` là lựa chọn rollout đã lưu, không phải quyền bỏ qua release
gate. Lệnh thật chỉ có thể được gửi khi tất cả điều kiện sau cùng đạt:

```text
Auto-entry được người dùng chủ động bật trong chế độ quét định kỳ
AND candidate READY_NOW/auto_trade_candidate
AND production approval
AND release readiness = true
AND rollout/kill switch cho phép
AND execution revalidation, news, account và portfolio đều đạt

Lệnh thủ công từ dialog cần candidate hợp lệ và production approval; release
readiness không chặn riêng thao tác này, nhưng mọi điều kiện còn lại vẫn bắt
buộc đạt.
```

Không sửa trực tiếp rollout metrics hoặc hạ ngưỡng để giả lập bằng chứng phát
hành.

## Khôi phục cấu hình trước khi chuyển stage

Bản sao cấu hình trước thay đổi được lưu tại:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\settings.before-live-20260724-231015.json
```

Mã nguồn và settings mới/migrate vẫn mặc định `SHADOW`. Chỉ runtime settings
trên máy này đang chọn `PRODUCTION`.
