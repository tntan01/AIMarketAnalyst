# Runtime Status

Cập nhật: **24/07/2026 22:38 (Asia/Ho_Chi_Minh)**.

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
| Feature flags | `scanner_architecture_v2=true`, `auto_trade_v2=true`, `backtest_config_v2=true` |

Settings hiện có bản ghi cấu hình riêng cho **31 symbol**. Danh sách
`trading.enabled_symbols` đang rỗng; trường này chỉ đánh dấu các cấu hình
Backtest đã duyệt, không phải danh sách symbol mà Scanner được phép quét.
Scanner vẫn lấy phạm vi mặc định từ 31 mã trong `SUPPORTED_SYMBOLS`. Việc một
symbol được quét hoặc có cấu hình không tự yêu cầu đặt lệnh.

## Trạng thái gửi lệnh

Nút **Tự động vào lệnh MT5** trên màn hình Quét thị trường hiện bị disable và
luôn được reset về unchecked. `ScannerScreen.AUTO_TRADE_UI_ENABLED=false` làm
mọi request tạo từ UI mang `ScannerRequest.auto_trade_enabled=false`; Scanner
không thể tự động gửi lệnh, kể cả khi đang quét định kỳ và rollout stage là
`PRODUCTION`.

Ngoài khóa UI trên, release readiness hiện vẫn là `ready=false`. Lệnh thủ công
từ Scanner vì vậy cũng bị rollout guard trả `RELEASE_GATE_NOT_READY` trước khi
gọi MT5.

Các block code hiện tại:

- `DEMO_ORDER_SAMPLE_INSUFFICIENT` — `0/20` lệnh demo;
- `CANARY_ORDER_SAMPLE_INSUFFICIENT` — `0/5` lệnh canary;
- `OOS_EVIDENCE_MISSING`;
- `DEMO_EVIDENCE_MISSING`.

Snapshot metrics lúc cập nhật tài liệu có `364/100` shadow samples, không có
side mismatch/unsafe disagreement và
rollback drill đã đạt. Những kết quả này chưa thay thế bằng chứng demo, canary,
OOS và demo performance còn thiếu.

## Ý nghĩa vận hành

`stage=PRODUCTION` là lựa chọn rollout đã lưu, không phải quyền bỏ qua release
gate. Lệnh thật chỉ có thể được gửi khi tất cả điều kiện sau cùng đạt:

```text
Auto-entry được yêu cầu từ một client được cấp quyền (UI Scanner hiện không yêu cầu)
AND candidate READY_NOW/auto_trade_candidate
AND production approval
AND release readiness = true
AND rollout/kill switch cho phép
AND execution revalidation, news, account và portfolio đều đạt
```

Không sửa trực tiếp rollout metrics hoặc hạ ngưỡng để giả lập bằng chứng phát
hành.

## Khôi phục cấu hình trước khi chuyển stage

Bản sao cấu hình trước thay đổi được lưu tại:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\settings.before-production-20260724.json
```

Mã nguồn và settings mới/migrate vẫn mặc định `SHADOW`. Chỉ runtime settings
trên máy này đang chọn `PRODUCTION`.
