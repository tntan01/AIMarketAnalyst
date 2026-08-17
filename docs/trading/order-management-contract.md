# Runtime contract quản lý lệnh V2

- Cập nhật contract: 09/08/2026; hợp nhất tài liệu lịch sử: 11/08/2026;
  chuyển sang chạy thật: 15/08/2026
- Trạng thái contract: **đang chạy live** (theo quyết định của owner, phần mềm
  cá nhân — không qua rollout)
- Lịch sử thiết kế: nội dung của kế hoạch triển khai và báo cáo rà soát đầu vào đã
  được hợp nhất vào contract này. Hai tài liệu nguồn đã được gỡ khỏi cây tài liệu
  hiện hành và vẫn có thể truy xuất qua Git history.

Tài liệu này định nghĩa contract fail-closed cho việc đọc trạng thái broker, quản
lý Break-even/Trailing Stop và xác minh thao tác SL/TP/close. Các primitive
broker, state machine, persistence, service runtime và đường nối
AppController–Scanner–UI đã có implementation cùng automated test. Từ
15/08/2026 hệ thống chạy thật trên tài khoản của owner: SL/BE/trailing sửa lệnh
trực tiếp trên broker; an toàn còn lại là feature flag, `account.trade_allowed`,
các invariant fail-closed trong contract này và các guard kỹ thuật — không còn
stage ladder, kill switch hay release gate.

## 1. Nguyên tắc bắt buộc

1. Broker là nguồn dữ liệu chuẩn cho position, pending order, SL, TP, volume và
   account identity.
2. “Không có position” và “không đọc được position” là hai trạng thái khác nhau.
3. Retcode chấp nhận request không phải là bằng chứng postcondition đã đạt.
4. State giao dịch chỉ chuyển sau khi trạng thái broker mới xác nhận kết quả.
5. Không có đường xử lý nào được làm SL kém bảo vệ hơn hoặc thay đổi TP ngoài ý
   muốn.
6. Snapshot unavailable, kết quả mutation unknown và account mismatch đều phải
   fail-closed: giữ state, ngừng mutation mới và phát trạng thái có thể quan sát.
7. Tắt V2 không được khôi phục engine automation legacy; fallback là thao tác
   manual có xác nhận. Service shutdown chuyển toàn bộ mutation sang read-only
   (đây là phanh phần mềm duy nhất còn lại sau khi kill switch được gỡ bỏ ngày
   15/08/2026).

Các từ **phải**, **không được** và **chỉ khi** trong tài liệu này là yêu cầu
runtime, không phải mô tả tùy chọn.

## 2. Contract snapshot broker

`services/order_management_models.py` định nghĩa các snapshot typed. Collection
dùng tuple bất biến; mỗi snapshot mang thời điểm quan sát UTC, lỗi broker nếu có
và account identity khi có thể xác định.

### 2.1 Trạng thái snapshot

| Trạng thái | Ý nghĩa | Consumer được phép làm gì |
|---|---|---|
| `AVAILABLE` | Lệnh đọc broker hoàn tất; collection rỗng thực sự có nghĩa là không có item | Render, reconcile và cleanup item đã được xác nhận không còn tồn tại |
| `UNAVAILABLE` | Không import/kết nối được MT5, không xác định được account hoặc API trả `None`/lỗi | Giữ tracking, đánh dấu stale, không cleanup và không gửi mutation mới |
| `STALE` | Có quan sát trước đó nhưng đã quá freshness budget | Chỉ hiển thị dữ liệu cũ kèm cảnh báo; không dùng làm bằng chứng đóng/xóa |

`positions_snapshot()` và `pending_orders_snapshot()` không được mã hóa lỗi
thành `[]`. API legacy `get_open_positions()`/`get_pending_orders()` còn tồn tại
cho consumer cũ nhưng không thuộc contract V2.

Một position chỉ được chuyển sang `CLOSED` hoặc xóa tracking khi có snapshot
`AVAILABLE`, đúng account và ticket được xác nhận không còn tồn tại. Một tuple
rỗng trong snapshot `UNAVAILABLE` không có ý nghĩa nghiệp vụ.

### 2.2 Dữ liệu position và pending order

Position typed phải giữ tối thiểu:

- `position_id`/ticket và `identifier`;
- `broker_symbol` riêng với `app_symbol`;
- side, volume, open/current price, SL, TP, profit, swap và commission;
- magic, comment và open time;
- metadata symbol: digits, point, trade tick size, stop/freeze level, filling mode
  và volume constraints.

Pending order typed phải giữ order ticket, broker/app symbol, raw type và type đã
chuẩn hóa, current/initial volume, entry, SL, TP, magic, comment, setup/expiration
time cùng metadata symbol. Các loại limit, stop và stop-limit không được gom
thành một nhãn mơ hồ.

Tick typed phải mang cả Bid và Ask. Tick unavailable không được thay bằng giá
cache rồi âm thầm gửi lệnh.

Position, pending-order và tick snapshot dùng trong cùng vòng quản lý phải có
cùng account fingerprint. Snapshot chéo tài khoản bị chuyển sang `STALE`, ẩn
khỏi cache thao tác và không được dùng để cleanup hoặc tạo mutation.

## 3. Account identity và trade mode

`AccountIdentity` gồm `broker`, `server`, `login`, `trade_mode` typed
(`DEMO`, `CONTEST`, `REAL`, `UNKNOWN`), currency, balance và trạng thái
`trade_allowed` khi MT5 xác định được.

- Fingerprint logic được tạo từ bộ ba broker/server/login; trade mode không thay
  thế account identity.
- Không suy đoán demo/live từ tên server. Trade mode thuộc account identity
  nhưng không còn là gate thực thi.
- (Đã gỡ từ 15/08/2026: gate `require_demo_account`.) Account `REAL` lẫn `DEMO`
  đều nhận mutation automation như nhau khi feature flag bật và
  `trade_allowed=true`. Manual vẫn cần xác nhận riêng.
- Automation fail-closed khi quyền giao dịch account/terminal không được xác
  nhận là `true`.
- Account mismatch không được attach state cũ vào ticket trùng số, không được
  cleanup state của account trước và phải tạo cảnh báo rõ ràng.
- Event/log chỉ cần fingerprint, không cần ghi credential hay dữ liệu nhạy cảm.

## 4. Contract state machine

`core/order_management_state_machine.py` là hàm thuần, không import MT5, PyQt,
persistence hoặc widget. `evaluate()` chỉ tạo decision/intent; caller thực thi
intent rồi đưa quan sát hậu kiểm vào `apply_confirmation()`.

Các phase hiện hành:

```text
UNMANAGED -> WAITING_BE -> BE_ACTIVE -> TRAIL_WIDE -> TRAIL_TIGHT
                 |              |
                 +--------------+--> PAUSED / STALE
                                    ERROR_RETRYABLE
                                    ERROR_NON_RETRYABLE
                                    CLOSED
```

### 4.1 Invariant giá và lifecycle

- BUY dùng Bid để đo lợi nhuận có thể đóng; SELL dùng Ask.
- `WAITING_BE` là hard gate: chưa có xác nhận BE thì không tính/gửi trailing.
- BUY chỉ đề xuất SL mới bảo vệ hơn SL broker; SELL áp dụng hướng ngược lại.
- Broker SL luôn thắng cache. State machine không lưu `current_sl` làm nguồn
  chuẩn.
- Nếu SL bị user/EA nới xuống dưới BE sau khi BE/trailing đã active, state quay
  lại `WAITING_BE` và khôi phục BE trước khi tính trailing tiếp.
- Desired action mang TP broker hiện tại trong `preserve_tp`.
- Target được clamp theo mức lớn hơn giữa stop level và freeze level, rồi làm
  tròn bảo thủ theo tick size/digits.
- Một `pending_action` không được phát lại trong lúc chờ xác nhận.
- ATR unavailable không được âm thầm chuyển sang fixed-pip trailing; decision
  trả `atr_unavailable` và không tạo mutation.
- Snapshot/tick không fresh chuyển state sang `STALE`, không phải `CLOSED`.
- Chỉ fresh snapshot xác nhận ticket không tồn tại mới chuyển `CLOSED`.
- Phase tight không hạ về wide khi lợi nhuận co lại.

### 4.2 Confirmation và retry

`CONFIRMED` chỉ được áp dụng khi effective SL ít nhất bảo vệ bằng target và
effective TP bằng TP trước request trong tolerance của tick. Sai SL/TP
postcondition là lỗi non-retryable.

Lỗi retryable dùng exponential backoff có giới hạn số lần và trần delay. Kết quả
`UNKNOWN` chuyển sang `STALE`; snapshot fresh kế tiếp phải reconcile pending
intent với broker trước khi tính action mới. Reject không được đánh dấu BE hoàn
tất.

Retcode busy/requote/timeout vẫn được phân loại retryable ngay cả khi response
ngoài mang status `unknown`. Pending action khôi phục sau crash luôn đi qua
`STALE` reconciliation, không được treo vô hạn ở trạng thái “đang chờ”.

## 5. Contract mutation MT5

`services/mt5_service.py` trả kết quả theo `OperationStatus`:
`CONFIRMED`, `PARTIAL`, `REJECTED` hoặc `UNKNOWN`. Trường compatibility
`success` chỉ là `true` với `CONFIRMED`.

### 5.1 Sửa SL/TP

`modify_position_sltp()` phải:

1. Re-query position theo ticket.
2. Lấy SL và TP broker hiện tại.
3. Giữ nguyên trường caller không yêu cầu sửa; SL-only request vẫn gửi TP hiện
   tại.
4. Normalize giá theo metadata broker; state machine chịu trách nhiệm tạo target
   hợp lệ với stop/freeze constraints.
5. Gửi request đầy đủ ticket và broker symbol.
6. Re-query position sau `order_send`.
7. Chỉ trả `confirmed` khi effective SL và TP cùng đạt postcondition.

Với automation, request còn mang optimistic precondition của snapshot
(account fingerprint, broker symbol, SL và TP đã quan sát). Nếu user/EA hoặc
account thay đổi trước lúc thực thi, MT5 boundary reject trước `order_send`; vòng
sau đọc broker truth rồi mới tính lại. Cơ chế này ngăn target trailing cũ kéo
lùi một SL mới được siết hoặc khôi phục TP cũ ngoài ý muốn.

Nếu request được broker nhận nhưng query hậu kiểm lỗi hoặc giá không phản ánh
request, kết quả là `unknown`, không phải thành công. Reject giữ nguyên phase
quản lý.

### 5.2 Đóng position

`close_position()` phải dùng quote phía đóng (BUY đóng tại Bid, SELL đóng tại
Ask), normalize volume và chọn filling policy từ capability/bitmask symbol.

- `confirmed`: fresh re-query xác nhận ticket không còn tồn tại.
- `partial`: ticket còn tồn tại với volume nhỏ hơn; trả `executed_volume` và
  `remaining_volume`, giữ tracking cho phần còn lại.
- `rejected`: broker reject và hậu kiểm không cho thấy tiến triển.
- `unknown`: `PLACED`/accepted nhưng position không đổi, hoặc không thể re-query.

Không xóa tracking chỉ dựa trên `DONE`, `PLACED` hay `DONE_PARTIAL`.

### 5.3 Correlation position sau entry

Không dùng order/deal ID như position ticket fallback mù. Reconciliation phải
lọc theo broker symbol, magic và comment/correlation trước; exact position ticket
chỉ thắng trong tập candidate đã tương quan. Entry và position ID dùng cho BE
phải lấy từ position broker đã xác minh.

### 5.4 Hủy và sửa pending order

`cancel_pending_order()` chỉ trả `confirmed` khi MT5 chấp nhận request và
fresh re-query xác nhận ticket đã rời active order book. Nếu ticket biến mất
nhưng broker không acknowledge, kết quả là `unknown` vì order có thể đã fill
hoặc expire.

`modify_pending_order()` hỗ trợ buy/sell limit, stop và stop-limit. Request phải:

- giữ các field caller không sửa, gồm SL, TP, stop-limit leg và expiration;
- normalize giá theo tick size/digits;
- kiểm tra stop/freeze constraints với fresh tick trước khi gửi;
- không thêm filling policy vào request `REMOVE`/`MODIFY`;
- re-query và so khớp entry, SL, TP, stop-limit, expiration và time type.

Thiếu tick/normalization metadata phải reject trước `order_send`. Retcode được
chấp nhận nhưng postcondition không khớp vẫn là `unknown`.

### 5.5 Manual và bulk actions

Các thao tác position/pending từ UI được xếp hàng bất đồng bộ qua service và
vẫn dùng postcondition ở trên:

- partial close normalize volume; kết quả `partial` giữ quản lý volume còn lại;
- sửa SL/TP thủ công, pause/resume protection;
- **Đóng tất cả** đóng băng đúng snapshot target tại lúc xác nhận và áp dụng
  scope `AMA`/`ALL` đã chọn;
- **Flatten tài khoản** đóng băng cả position và pending snapshot, hiển thị cảnh
  báo mạnh rằng phạm vi gồm cả lệnh manual/EA khác.

Mọi manual/bulk mutation yêu cầu snapshot fresh chứa đúng ticket, account
fingerprint và broker symbol. Kill switch được kiểm tra cả lúc xếp hàng lẫn ngay
trước khi callback thực thi, nên mutation còn nằm trong queue sẽ bị hủy.

Item xuất hiện sau dialog xác nhận không được tự động thêm vào bulk target.

## 6. Executor và Qt boundary

Boundary runtime bắt buộc có các thuộc tính sau:

- QTimer và mọi thay đổi QWidget chỉ chạy trên Qt main thread.
- Snapshot, tick và mutation MT5 chạy ngoài GUI thread qua một
  `OrderManagementService`/executor được sở hữu ở application scope.
- Scanner gửi request/domain event tới service; worker không giữ hoặc gọi
  `OrdersScreen`.
- UI chỉ subscribe signal/result bất biến như snapshot update, state change và
  operation failure.
- Mọi MT5 call dùng cùng serialization boundary. `MT5Service` hiện đã serialize
  operation theo instance bằng `RLock`; executor vẫn phải đảm bảo không block
  event loop và không tạo một đường MT5 thứ hai ngoài boundary.
- Shutdown phải ngừng timer, không nhận task mới, drain/cancel task đúng trật tự,
  persist rồi flush trước khi đóng MT5.

Boundary đã được triển khai như sau:

- `AppController` sở hữu singleton `OrderManagementService` và inject cùng
  instance vào Scanner/Orders UI.
- `MainWindow` start service sau khi dựng screen; `AppController.shutdown()`
  shutdown service trước khi disconnect MT5.
- Service dùng `ThreadPoolExecutor(max_workers=1)`; QTimer chỉ schedule poll.
- Scanner reconcile position broker rồi gọi `register_position()` trên service,
  không gọi QWidget.
- Orders UI render cache và subscribe `snapshot_updated`, `state_changed`,
  `health_changed`, `operation_completed` và `operation_failed`; runtime path
  không import/gọi native MetaTrader5 từ widget.
- Settings gọi `update_policy()` để áp dụng policy cho service đang chạy mà
  không cần restart.

Automated test xác nhận broker operation chạy khác calling thread; service cũng
có guard không xếp poll mới khi poll trước còn chạy. Đây là evidence cho
boundary trong code, nhưng forward demo với Qt event loop/reconnect thật vẫn là
release gate.

## 7. Persistence account-scoped

`OrderManagementStateStore` dùng schema
`ama.order-management-state`, `schema_version=2` và file mặc định
`be_trailing_state.json` trong app data.

- Document lưu broker/server/login cùng SHA-256 fingerprint.
- Load chỉ trả state khi fingerprint khớp account hiện tại.
- Save validate toàn bộ document, ghi file tạm, fsync và atomic replace.
- Generation trước được giữ ở file `.bak`.
- JSON/schema/fingerprint corrupt bị quarantine với suffix `.corrupt.*`; không
  bị hiểu thành state rỗng.
- Unsupported version, account mismatch, validation error và I/O error có status
  tường minh.
- Broker unavailable không được xóa state file.

Store đã được nối vào service runtime. Account được kích hoạt từ snapshot fresh;
state chỉ restore khi ticket, broker symbol, side và entry khớp position hiện
tại. Service persist khi đăng ký, đổi state và sau poll; shutdown persist/flush
trước khi AppController disconnect MT5. Snapshot unavailable chỉ đánh dấu stale
và giữ state.

## 8. Gate thực thi (live từ 15/08/2026)

OM luôn bật: feature flag `order_management_v2` đã bị gỡ khỏi model (16/08/2026),
nhất quán với việc gỡ các flag Scanner V4 trước đó. Cùng ngày `manage_scope` cũng
bị gỡ — chỉ còn một phạm vi duy nhất (ALL): **Đóng tất cả** luôn nhắm mọi vị thế
đang mở, không còn lọc theo magic/comment AMA. Các
field `stage`, `kill_switch`, `require_demo_account`, `production_approved`,
`canary_broker_symbol`, `canary_position_id`, `manage_scope` đã bị xóa khỏi
`OrderManagementSettings`; key thừa trên disk từ bản cũ được loader bỏ qua
(không còn hiệu lực).

Các gate dưới đây điều khiển **automation BE/Trailing**. Thao tác manual rõ ràng
từ Orders UI vẫn khả dụng sau dialog xác nhận.

Thứ tự gate bắt buộc:

1. `account.trade_allowed` phải là `true`; `false` hoặc không xác định được
   (`None`) đều fail-closed, không gửi mutation.
2. Scanner chỉ auto-register position đã reconcile với AMA correlation.
   **Đóng tất cả** nhắm mọi vị thế (phạm vi duy nhất ALL); explicit
   per-position manual action là opt-in riêng. **Flatten** luôn là toàn account
   và dùng cảnh báo mạnh, không phải fallback âm thầm nào.

Service enforce `trade_allowed` cho automation, và chặn mọi mutation (kể cả
manual) sau khi service shutdown. Automated test bao phủ trade-not-allowed
fail-closed (vẫn tính intent nhưng không gửi broker), live execution, REAL
account chạy trực tiếp, trade-not-allowed/unknown fail-closed, runtime policy
update không cần restart và shutdown block.

Lưu ý vận hành: không còn kill switch phần mềm. Dừng khẩn cấp = đóng lệnh ở
terminal broker hoặc ngắt kết nối MT5.

## 9. Observability tối thiểu

Mỗi vòng poll phải có heartbeat/freshness. Mỗi mutation cần correlation ID,
account fingerprint, position ID, broker symbol, reason, old/new SL, preserved
TP, retcode, operation status và thời điểm broker xác nhận. UI phải phân biệt
healthy, stale, disconnected, retryable và non-retryable.

Không được hiển thị “đang bảo vệ” chỉ vì có config trong persistence. Trạng thái
active cần heartbeat broker fresh và state không paused/stale/error. Service đã
phát health/state/snapshot signal và structured event cho registration,
snapshot unavailable, reconciliation, automatic SL, close, manual SL/TP và
pending mutation; UI hiển thị LIVE/BLOCKED/STALE dựa trên
`execution_allowed` và freshness của snapshot. Event mutation thật
(`SL_MODIFY_REQUESTED`, `BE_TRIGGERED`...) thay thế hoàn toàn
`SL_MODIFY_SHADOW` của chế độ cũ.

## 10. Mức độ triển khai và release blocker

| Hạng mục | Mức độ hiện tại |
|---|---|
| Snapshot typed, account trade mode, metadata broker | Có mã và unit test |
| Postcondition SL/TP và close/partial | Có mã và unit test fake MT5 |
| State machine thuần và invariant BE/Trailing | Có mã và unit test |
| Persistence v2 account-scoped/atomic/backup/quarantine | Có mã và unit test |
| Settings/feature flag | Có mã và test settings/UI |
| OrderManagementService, single executor và lifecycle application | Có mã và automated test |
| AppController–Scanner–Orders UI cache/signal boundary | Đã tích hợp; có targeted automated evidence |
| Runtime health/observability baseline | Đã tích hợp; cần forward-demo evidence |
| Pending cancel/modify, partial/manual và frozen bulk/flatten | Có mã và automated contract test |
| Targeted và full automated suite | Đã đạt: targeted 191 passed in 3.15s trên 17 file; full suite 2740 passed, 8 skipped, 17 xfailed, 5 warnings in 178.62s (179.5s wall) |
| Forward test broker demo qua nhiều phiên và reconnect | Không còn là gate bắt buộc: owner quyết định chạy thật trực tiếp từ 15/08/2026 |

Targeted automated test chứng minh contract với fake/in-memory dependency và
boundary trong process. Theo quyết định của owner (phần mềm cá nhân), tính năng
đã chuyển sang chạy thật ngày 15/08/2026 mà không qua giai đoạn forward-demo hay
canary; các invariant fail-closed trong contract này và `account.trade_allowed`
là lớp bảo vệ còn lại.
