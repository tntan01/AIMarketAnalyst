# Runtime Status

Cập nhật trạng thái runtime: **09/08/2026 (Asia/Ho_Chi_Minh)**. Ghi chú target
Scanner V4: **11/08/2026**.

Tài liệu này ghi trạng thái cấu hình đang lưu trên máy hiện tại. Đây không
phải giá trị mặc định của mã nguồn và không thay thế contract trong
[`scanner-flow.md`](../scanner/scanner-flow.md).

> **Scanner V4 chưa phải runtime:** kiến trúc V4 đã được phê duyệt ở mức thiết kế,
> nhưng chưa được triển khai. Các trạng thái và số liệu Scanner bên dưới vẫn mô tả
> runtime V3 hiện hành. Target V4 dùng direct cutover, không coi shadow comparison
> giữa V3/V4 là yêu cầu migration. Xem
> [`scanner-v4-architecture.md`](../scanner/scanner-v4-architecture.md).

## Order Management V2

Contract runtime đã được triển khai trong code và đang chờ release validation,
xem
[`order-management-contract.md`](../trading/order-management-contract.md). Các
contract snapshot MT5, postcondition position/pending, state machine,
persistence account-scoped và `OrderManagementService` single-executor đã được
triển khai cùng targeted automated test.

Targeted final suite ngày 09/08/2026 đạt **191 passed in 3.15s** trên 17 file
liên quan, bao phủ broker/pending contract, state machine, persistence,
service/executor, settings/UI và integration boundary.

Full suite cuối cùng đạt **2740 passed, 8 skipped, 17 xfailed, 5 warnings in
178.62s (179.5s wall)**. Full-suite gate đã đạt cho worktree tích hợp hiện tại.

`AppController` sở hữu và shutdown service; `MainWindow` start service; Scanner
reconcile position broker rồi register vào service; Orders UI đọc cache và nhận
Qt signals thay vì gọi native MetaTrader5. Service load/persist/flush state theo
account, phát health/operation events và đưa broker I/O qua một executor tuần tự.
Pending cancel/modify, manual/partial close, scoped frozen close-all và frozen
flatten cũng đi qua boundary này.

Mặc định mã nguồn/settings migrate là `order_management_v2=false`, stage
`SHADOW`, `require_demo_account=true`, `production_approved=false` và phạm vi
`AMA`. Đây là default fail-safe, không phải mô tả giá trị đã lưu trên máy nếu
người dùng đã thay đổi Settings. Feature/stage/account/CANARY/PRODUCTION gate
điều khiển automation; thao tác manual vẫn cần dialog xác nhận riêng. Kill switch
chặn cả automation lẫn manual mutation. Settings cập nhật policy của service
đang chạy mà không cần restart.

Order Management V2 hiện **chưa live-safe, chưa GA**. Forward demo qua nhiều
phiên/reconnect MT5 vẫn là release blocker cuối chưa có evidence. Targeted/full
suite không thay thế bằng chứng Qt + broker thật. Release blockers và checklist
còn mở được hợp nhất tại
[`order-management-contract.md`](../trading/order-management-contract.md), mục 10;
kế hoạch/rà soát nguồn chỉ còn trong Git history.

## Scanner rollout

| Thuộc tính | Giá trị hiện tại |
|---|---|
| Stage | `PRODUCTION` |
| Kill switch | `false` |
| Shadow comparison | `true` |
| Production approved | `true` |
| Bắt buộc tài khoản demo | `false` |
| Allowlist rollout | Rỗng; `PRODUCTION` không giới hạn symbol bằng allowlist |
| SMC scorer | `smc-v2` (canonical duy nhất, không có mode để chọn) |
| Feature flags runtime | `scanner_architecture_v2=true`, `auto_trade_v2=true`; `vix_pair_aware_enabled=false` hiệu lực do settings cũ chưa có key; hai flag Backtest cũ không còn được runtime sử dụng |

`backtest_config_v2` hoặc `backtest_engine_v2` có thể vẫn còn trong file
Settings được tạo bởi bản cũ. Loader hiện bỏ qua hai key này và lần lưu Settings
tiếp theo sẽ không ghi lại; Strategy Router không phụ thuộc vào chúng.

Settings hiện có bản ghi cấu hình riêng cho **31 symbol**. Danh sách
`trading.enabled_symbols` đang rỗng; trường này chỉ đánh dấu các cấu hình
Backtest đã duyệt, không phải danh sách symbol mà Scanner được phép quét.
Scanner vẫn lấy phạm vi mặc định từ 31 mã trong `SUPPORTED_SYMBOLS`. Việc một
symbol được quét hoặc có cấu hình không tự yêu cầu đặt lệnh.

## Trạng thái VIX pair sensitivity

Settings đang lưu trên máy hiện tại chưa có key
`advanced.vix_pair_aware_enabled`. Loader dùng default `false`, vì vậy Bước 7
đang **OFF** và VIX contribution vẫn phẳng ở runtime mặc định.

Probe loader ngày 09/08/2026 cho thấy:

- APPDATA có một seed map cũ; runtime từ chối với
  `seed_or_unverified_origin` rồi tiếp tục candidate kế tiếp;
- `data/vix_pair_sensitivity.json` trong repo là schema-2 map eligible và được
  dùng làm fallback, gồm 31/31 pair đủ mẫu;
- map được tạo lúc `2026-08-09T07:15:01.945180Z`, TTL 90 ngày và sẽ stale xấp
  xỉ `2026-11-07T07:15:01.945180Z`;
- ba pair actionable theo raw gate là BTC/USD, XAG/USD và XAU/USD; cả 7 JPY
  pairs cùng AUD/NZD đều non-actionable.

Map hợp lệ không tự bật feature. Kết quả hiện tại không xác nhận mục tiêu JPY,
nên không có phê duyệt bật toàn cục được suy ra từ việc map load thành công.
Quy trình calibration và vận hành: xem
[`macro_score_architecture.md`](../macro/macro_score_architecture.md), mục
**Bước 7 — VIX Pair Sensitivity**.

Gap vận hành đang mở: lần re-validation đủ dữ liệu nhưng `0 actionable` không
overwrite map trước. Trước khi contract tombstone/disable được sửa, phải tắt
flag trước re-validation và giữ OFF nếu hypothesis không được xác nhận.

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
