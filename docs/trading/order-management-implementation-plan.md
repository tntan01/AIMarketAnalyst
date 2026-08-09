# Kế hoạch nâng cấp tính năng quản lý lệnh

- Ngày lập kế hoạch: 09/08/2026
- Trạng thái: implementation và automated release gate đã đạt; forward-demo
  broker/reconnect release gate chưa đạt
- Báo cáo đầu vào: [`order-management-review.md`](order-management-review.md)
- Runtime contract: [`order-management-contract.md`](order-management-contract.md)
- Phạm vi: Orders, BE/Trailing Stop, đóng vị thế, lệnh chờ, tích hợp Scanner và MT5

## Trạng thái thực hiện

Cập nhật ngày **09/08/2026**. Ký hiệu: `[x]` là phạm vi code đã triển khai và có
targeted automated test; `[~]` là implementation đã có nhưng evidence phát hành
chưa đủ; `[ ]` là chưa triển khai/kiểm chứng. Automated test không đồng nghĩa đã
đạt release gate broker.

| Giai đoạn | Trạng thái | Evidence hiện có | Phần còn lại |
|---|---|---|---|
| 0 — Regression | `[x]` | Test trực tiếp production broker contract, state machine, persistence, service/executor, pending và settings/UI; full suite cuối xanh | Broker/forward evidence được theo dõi riêng ở release gate |
| 1 — Snapshot MT5 | `[x]` | Typed position/pending/tick snapshot phân biệt `AVAILABLE`/`UNAVAILABLE`, mang account/trade mode/metadata; Orders UI dùng cache service | Cần xác nhận reconnect trên broker demo |
| 2 — SL/TP và close | `[x]` | Fake-MT5 test cho giữ TP, normalize, stop/freeze, re-query postcondition, filling mode, partial/unknown close; UI xếp hàng async | Cần forward demo với broker thật |
| 3 — State machine/service | `[x]` | State machine thuần cùng `OrderManagementService`, single executor, confirmation, bounded retry và shutdown lifecycle | Cần soak/reconnect evidence |
| 4 — Scanner/threading | `[x]` | Scanner reconcile alias/correlation rồi register service; AppController DI, MainWindow start, Orders cache/signals; broker operation được test off caller thread | Cần quan sát Qt/MT5 thật qua forward demo |
| 5 — Persistence | `[x]` | Store schema v2 account-scoped, atomic/backup/quarantine; service load/reconcile/persist và AppController shutdown flush | Cần restart/reconnect demo evidence |
| 6 — Observability/UI health | `[x]` | Service phát snapshot/state/health/operation signals và structured protection/manual/pending events; UI hiển thị HEALTHY/STALE/ERROR, account/stage, kết quả async | Đối soát audit/heartbeat với broker thật thuộc release validation |
| 7 — Pending/manual/bulk | `[x]` | Cancel/modify mọi pending type có postcondition; manual SL/TP, pause/resume, partial close; close-all scoped/frozen và flatten frozen | Cần thao tác thử trên broker demo |
| 8 — Rollout/release | `[~]` | Feature/stage/account/CANARY/PRODUCTION automation gates, kill switch toàn bộ mutation và runtime `update_policy` đã có automated test; targeted và full suite đều xanh | Forward demo qua nhiều phiên/reconnect vẫn là release blocker |

### Evidence kiểm thử đã ghi nhận

- Targeted final suite ngày 09/08/2026 gồm 17 file test liên quan: **191 passed
  in 3.15s**.
- Full suite cuối ngày 09/08/2026: **2740 passed, 8 skipped, 17 xfailed,
  5 warnings in 178.62s (179.5s wall)**. Full-suite gate đã đạt cho worktree tích
  hợp hiện tại.
- Baseline trước thay đổi đã ghi nhận: **2615 passed, 8 skipped, 17 xfailed**.
  Đây là mốc so sánh lịch sử, không phải full-suite evidence cho worktree hiện
  tại.
- Automated service test xác nhận broker operation chạy ngoài calling thread;
  chưa có evidence Qt + MT5 thật đầu-cuối.
- Chưa có forward-test trên broker demo qua nhiều phiên thị trường và reconnect
  MT5. Đây vẫn là **release blocker**; tài liệu không tuyên bố live-safe hoặc GA.

## Mục tiêu

Thay engine quản lý lệnh hiện tại bằng một lớp quản lý độc lập, lấy trạng thái broker làm nguồn dữ liệu chuẩn và không thay đổi state nội bộ trước khi xác minh thao tác đã thực sự thành công.

Sau khi hoàn thành, hệ thống phải bảo đảm:

- Lỗi kết nối không bị hiểu thành tài khoản không có vị thế.
- SL không bao giờ bị dời lùi.
- TP không thay đổi ngoài ý muốn khi cập nhật SL.
- BE/Trailing chỉ chuyển state sau khi broker xác nhận.
- Scanner, Orders UI và MT5 không vi phạm Qt thread affinity.
- State không bị dùng nhầm giữa các tài khoản.
- Người dùng nhận biết được protection đang healthy, stale hay lỗi.

## Tổng quan giai đoạn

| Giai đoạn | Nội dung | Ưu tiên |
|---|---|---|
| 0 | Đóng băng rủi ro và tạo test tái hiện lỗi | P0 |
| 1 | Chuẩn hóa contract dữ liệu MT5 | P0 |
| 2 | Sửa thao tác SL/TP và đóng vị thế | P0 |
| 3 | Tách BE/Trailing khỏi UI thành state machine | P0 |
| 4 | Sửa tích hợp Scanner, symbol và threading | P0 |
| 5 | Làm lại persistence và account identity | P1 |
| 6 | Observability và trạng thái UI | P1 |
| 7 | Hoàn thiện pending/manual actions | P2 |
| 8 | Shadow/demo rollout và release gate | Bắt buộc |

Ước lượng cho một lập trình viên: **10–15 ngày làm việc**, chưa bao gồm thời gian forward-test trên broker demo.

## Giai đoạn 0 — Khóa hành vi hiện tại bằng regression test

### Mục tiêu

Tái hiện được các lỗi P0 bằng test gọi production code trước khi sửa, tránh sửa xong nhưng không có bằng chứng chống tái phát.

### Test file dự kiến

- `tests/test_order_management_state_machine.py`
- `tests/test_order_management_mt5_contract.py`
- `tests/test_order_management_persistence.py`
- `tests/test_order_management_threading.py`
- `tests/test_order_management_ui.py`

### Trường hợp bắt buộc

1. Giá chưa đạt 1R không được gửi yêu cầu trailing.
2. Broker reject BE phải giữ `be_done=False` hoặc state tương đương.
3. BUY phải dùng Bid, SELL phải dùng Ask.
4. Sửa SL phải giữ nguyên TP.
5. `positions_get() is None` không được xóa tracking.
6. Close reject phải giữ tracking.
7. `DONE_PARTIAL` phải giữ tracking cho volume còn lại.
8. App symbol `EUR/USD` phải resolve thành broker symbol `EURUSDm`.
9. SL broker chặt hơn cache không bao giờ bị kéo lùi.
10. Worker thread không được thao tác trực tiếp QWidget hoặc QTimer của UI.
11. Account khác có ticket trùng không được nhận state cũ.
12. Pending order không được hiểu nhầm là đã bị hủy khi chỉ đóng positions.

### Điều kiện hoàn thành

- Tất cả lỗi hiện tại được tái hiện bằng test đỏ trước khi sửa.
- Test gọi production method/service với fake MT5, không sao chép thuật toán sang helper riêng.
- Lưu kết quả baseline hiện tại: `2615 passed, 8 skipped, 17 xfailed`.

## Giai đoạn 1 — Chuẩn hóa contract dữ liệu broker

### Mục tiêu

Phân biệt rõ “không có vị thế” với “không lấy được dữ liệu”.

### Model đề xuất

```python
class SnapshotStatus(Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


@dataclass
class AccountIdentity:
    broker: str
    server: str
    login: int


@dataclass
class PositionsSnapshot:
    status: SnapshotStatus
    account: AccountIdentity | None
    positions: list[BrokerPosition]
    observed_at_utc: datetime
    error_code: int | None
    message: str
```

### Công việc

- Thêm `MT5Service.positions_snapshot()` và `pending_orders_snapshot()`.
- Không dùng `[]` để biểu diễn lỗi hoặc trạng thái unavailable.
- Bổ sung vào position:

  - `magic`;
  - broker symbol;
  - position ticket/identifier;
  - `digits`, `point`, `trade_tick_size`;
  - stop/freeze level;
  - account identity.

- Giữ API cũ tạm thời cho consumer khác; Orders V2 chỉ dùng snapshot mới.
- Chỉ cleanup tracking khi snapshot là `AVAILABLE` và position được xác nhận không tồn tại.
- Khi snapshot là `UNAVAILABLE`:

  - giữ nguyên tracking;
  - đánh dấu state stale;
  - không phát sinh thao tác broker mới;
  - hiển thị cảnh báo.

### File dự kiến

- `services/mt5_service.py`
- `services/order_management_models.py` — mới
- `tests/test_order_management_mt5_contract.py`

### Điều kiện hoàn thành

- Mất kết nối không làm mất config.
- UI phân biệt được “0 vị thế” và “không lấy được dữ liệu”.
- Snapshot luôn mang account identity khi broker khả dụng.

## Giai đoạn 2 — Sửa contract SL/TP và đóng vị thế

### 2.1 Sửa SL/TP

`modify_position_sltp()` phải thực hiện theo thứ tự:

1. Re-query position hiện tại.
2. Lấy cả SL và TP hiện hữu.
3. Nếu caller chỉ sửa SL, giữ nguyên TP.
4. Normalize giá theo `trade_tick_size` và `digits`.
5. Kiểm tra optimistic precondition account, broker symbol, SL và TP từ snapshot;
   nếu đã đổi thì reject trước `order_send`.
6. Kiểm tra stop level và freeze level.
7. Gửi request có đủ `action`, `symbol`, `position`, `sl` và `tp`.
8. Trả về `retcode`, `last_error`, request ID và giá broker xác nhận.
9. Re-query position sau request.
10. Chỉ báo thành công khi postcondition được xác minh.

Kết quả đề xuất:

```python
@dataclass
class PositionModifyResult:
    status: Literal["confirmed", "rejected", "unknown"]
    position_id: int
    requested_sl: float
    effective_sl: float | None
    effective_tp: float | None
    retcode: int | None
    message: str
```

### 2.2 Sửa close position

- Không coi `PLACED` là vị thế đã đóng hoàn tất.
- `DONE_PARTIAL` phải trả remaining volume.
- Sau `order_send`, re-query position ticket.
- Chỉ trả trạng thái `closed` khi position được xác nhận không còn tồn tại.
- Chọn filling policy đúng từ bitmask broker; không hard-code IOC.
- Tracking chỉ bị xóa khi trạng thái là `closed`.
- Với partial close, cập nhật volume và tiếp tục quản lý SL.

### Điều kiện hoàn thành

- Không thay đổi TP ngoài ý muốn.
- Không báo đóng thành công khi position còn mở.
- Broker reject không làm thay đổi state quản lý.
- Test exact request payload qua cho BUY, SELL và nhiều loại symbol.

## Giai đoạn 3 — Tách BE/Trailing thành service và state machine

### Mục tiêu

Loại bỏ logic giao dịch khỏi `OrdersScreen` để có thể kiểm thử độc lập và không phụ thuộc vòng đời widget.

### Thành phần mới

- `services/order_management_service.py`
- `core/order_management_state_machine.py`
- `services/order_management_models.py`

### State đề xuất

```text
UNMANAGED
    ↓ enable
WAITING_BE
    ↓ broker xác nhận SL tại BE
BE_ACTIVE
    ↓ bắt đầu trailing
TRAIL_WIDE
    ↓ profit >= 2R
TRAIL_TIGHT

Bất kỳ state nào:
    → PAUSED
    → STALE
    → ERROR_RETRYABLE
    → CLOSED
```

Không dùng một boolean `be_done` đơn lẻ để mô tả toàn bộ vòng đời.

### Luồng mỗi tick

1. Lấy snapshot position mới nhất.
2. Xác minh account, ticket, symbol và side.
3. Dùng giá có thể đóng:

   - BUY → Bid;
   - SELL → Ask.

4. Luôn coi broker SL/TP là nguồn chuẩn.
5. Tính mức SL mong muốn.
6. Áp các invariant:

   - `WAITING_BE` không được trailing;
   - BUY: SL mới không nhỏ hơn SL broker hiện tại;
   - SELL: SL mới không lớn hơn SL broker hiện tại;
   - TP không đổi;
   - giá phải hợp lệ theo tick size và broker constraints.

7. Gửi request.
8. Re-query broker.
9. Chỉ chuyển state khi postcondition được xác nhận.
10. Lưu state và phát event.

### Retry policy

- Lỗi kết nối: chuyển `STALE`, không thay state giao dịch.
- Broker busy/requote: retry với backoff.
- Pending intent khôi phục sau crash: bắt buộc `STALE` reconcile trước khi retry.
- Invalid stops: không retry liên tục; phát cảnh báo cấu hình.
- Position không tồn tại: xác minh bằng snapshot fresh trước khi chuyển `CLOSED`.
- Giới hạn retry để tránh spam `order_send`.

### ATR policy

- Dùng candle H1 đã đóng, không lấy forming candle làm nguồn duy nhất.
- Refresh ATR theo bar timestamp thay vì cố định suốt đời vị thế.
- Nếu ATR unavailable:

  - không âm thầm chuyển sang fixed pip;
  - chuyển state cảnh báo hoặc dùng fallback được người dùng cấu hình rõ.

### Điều kiện hoàn thành

- State machine unit-test được mà không cần PyQt.
- UI đóng/mở không làm mất state khi ứng dụng vẫn chạy.
- Không có đường code nào dời SL lùi.
- Không chuyển state trước khi broker xác nhận.

## Giai đoạn 4 — Sửa tích hợp Scanner và threading

### Broker symbol và position correlation

Sau khi đặt lệnh:

1. Dùng `broker_symbol` từ execution result.
2. Re-query positions theo broker symbol.
3. Xác minh position bằng:

   - position ticket;
   - magic;
   - correlation comment;
   - side;
   - volume;
   - thời gian mở.

4. Trả về `position_id` đã xác minh, không lấy `order_id/deal_id` làm fallback mù.
5. Dùng actual fill/open price từ position broker làm entry của BE.

### Qt threading

- Scanner Worker không gọi `OrdersScreen` trực tiếp.
- Scanner phát event/signal `position_opened`.
- `OrderManagementService` nhận request qua queued connection.
- Orders Screen chỉ subscribe các signal:

  - `snapshot_updated`;
  - `position_state_changed`;
  - `operation_failed`.

- Mọi thay đổi QWidget thực hiện ở main thread.
- Mọi MT5 I/O đi qua cùng một service boundary và lock/executor.
- Không còn direct `import MetaTrader5` trong Orders Screen.

### Điều kiện hoàn thành

- Test `EUR/USD → EURUSDm` qua.
- Không có Qt warning về timer/thread.
- Scanner không làm UI gọi MT5 đồng thời ngoài serialization boundary.
- Auto-tracking được đăng ký ngay cả khi tab Orders chưa mở.

## Giai đoạn 5 — Làm lại persistence và lifecycle

### Schema đề xuất

```json
{
  "schema_version": 2,
  "account": {
    "broker": "...",
    "server": "...",
    "login": 123456
  },
  "updated_at_utc": "...",
  "positions": {
    "12345": {
      "broker_symbol": "EURUSDm",
      "side": "buy",
      "entry_price": 1.1,
      "initial_sl": 1.098,
      "broker_sl": 1.1002,
      "broker_tp": 1.105,
      "state": "TRAIL_WIDE",
      "extreme_price": 1.103,
      "last_confirmed_at_utc": "..."
    }
  }
}
```

### Công việc

- Load persistence trước khi bắt đầu timer.
- So khớp account fingerprint trước khi sử dụng state.
- Xác minh symbol, side và entry trước khi attach state vào ticket.
- Broker state luôn thắng cached `current_sl`.
- Ghi file atomic bằng temp file rồi replace.
- Giữ backup của state gần nhất.
- Validate schema; file corrupt phải được cách ly và cảnh báo.
- Persist sau mọi state transition và successful SL modification.
- Flush state trong `AppController.shutdown()`.
- Không xóa file khi broker đang unavailable.

### Điều kiện hoàn thành

- Đổi account không dùng nhầm state.
- Crash giữa lúc save không làm mất toàn bộ file.
- Restart sau khi trailing đã chạy không nới SL.
- Corrupt state tạo cảnh báo rõ ràng thay vì `except: pass`.

## Giai đoạn 6 — Observability và trạng thái UI

### Event cần ghi

- `ORDER_MANAGEMENT_ENABLED`
- `BE_TRIGGERED`
- `SL_MODIFY_REQUESTED`
- `SL_MODIFY_CONFIRMED`
- `SL_MODIFY_REJECTED`
- `TRAIL_MODE_CHANGED`
- `POSITION_CLOSE_REQUESTED`
- `POSITION_CLOSE_PARTIAL`
- `POSITION_CLOSE_CONFIRMED`
- `BROKER_SNAPSHOT_UNAVAILABLE`
- `STATE_RECONCILIATION_FAILED`

Mỗi event chứa account fingerprint, position ID, broker symbol, correlation ID, old/new SL, TP và retcode; không ghi thông tin nhạy cảm không cần thiết.

### UI cần bổ sung

- Connection state: healthy/stale/disconnected.
- Account login/server và live/demo.
- Last broker refresh.
- Last successful SL update.
- Số lỗi/retry gần nhất.
- Trạng thái thực:

  - Chờ BE;
  - Đang gửi BE;
  - BE đã xác nhận;
  - Trail Wide/Tight;
  - Tạm dừng;
  - Stale;
  - Lỗi broker.

- Không đếm config là “active” nếu không có broker heartbeat.
- Hiển thị rõ automation phụ thuộc ứng dụng và MT5 terminal đang chạy.

### Điều kiện hoàn thành

Người dùng có thể trả lời ngay trên UI:

1. Vị thế nào đang được quản lý?
2. SL cuối cùng broker xác nhận là bao nhiêu và lúc nào?
3. Nếu protection không hoạt động, nguyên nhân là gì?

## Giai đoạn 7 — Hoàn thiện nghiệp vụ quản lý lệnh

### Pending orders

Bổ sung service và UI cho:

- hủy pending order;
- sửa entry, SL, TP và expiration;
- hiển thị đúng buy/sell limit, stop và stop-limit;
- hiển thị ticket, setup time và magic/comment;
- xác minh postcondition sau cancel/modify.

### Position actions

- Partial close với volume được normalize theo broker step.
- Sửa SL/TP thủ công.
- Pause/resume trailing.
- Reconcile sau khi người dùng sửa SL ngoài MT5.
- Filter theo symbol, strategy, magic và AMA/manual.

### Bulk actions

Tách hai hành động:

- **Đóng tất cả vị thế**: chỉ đóng snapshot position được hiển thị trong dialog xác nhận.
- **Flatten tài khoản**: đóng positions và hủy pending orders, dùng xác nhận mạnh hơn.

Danh sách target phải được đóng băng tại thời điểm xác nhận; position mở mới trong lúc dialog hiển thị không được tự động đưa vào bulk action.

### Điều kiện hoàn thành

- Không có bulk action với phạm vi mơ hồ.
- Lệnh manual/EA khác không bị ảnh hưởng nếu người dùng chọn phạm vi AMA.
- Cancel/modify/close đều có postcondition verification.

## Giai đoạn 8 — Rollout và release gate

### Feature flag

Thêm `order_management_v2` và triển khai theo thứ tự:

1. **Shadow mode**: tính desired SL nhưng không gửi broker.
2. **Demo mode**: cho phép gửi trên tài khoản demo.
3. **Canary**: giới hạn một symbol/một position.
4. **Live opt-in**: người dùng chủ động bật sau cảnh báo.
5. **General availability**: chỉ khi đủ evidence.

Không rollback về engine cũ nếu phát hiện lỗi; fallback an toàn là read-only/manual management.

### Release gate bắt buộc

- 0 lần SL bị dời lùi.
- 0 lần TP thay đổi ngoài ý muốn.
- 0 tracking state bị xóa do snapshot unavailable.
- 0 thao tác QWidget từ worker thread.
- 0 orphan position sau close partial/reject.
- Alias broker được test tối thiểu với slash và suffix.
- Persistence được test qua restart, corrupt file và đổi account.
- [x] Targeted suite và full suite đều xanh: targeted **191 passed in 3.15s
  (17 file)**; full suite **2740 passed, 8 skipped, 17 xfailed, 5 warnings in
  178.62s (179.5s wall)**.
- [ ] Forward demo chạy ổn định qua nhiều phiên thị trường và reconnect MT5.

### Tài liệu cần cập nhật

- `docs/trading/order-management-review.md`
- Tạo runtime contract `docs/trading/order-management-contract.md`
- `docs/architecture/architecture.md`
- `docs/ui/screen_design.md`
- `docs/guides/USER_GUIDE.md`
- `docs/architecture/runtime-status.md`

## Thứ tự triển khai khuyến nghị

Bắt đầu bằng **Giai đoạn 0 → 4** trong một nhánh riêng. Chỉ sau khi toàn bộ P0 có test xanh mới tiếp tục persistence/UI và các tính năng P2.

Không nên vừa sửa state machine vừa bổ sung pending/partial close trong cùng thay đổi đầu tiên, vì phạm vi kiểm chứng sẽ quá rộng. Mỗi giai đoạn cần có test, tài liệu và bằng chứng broker/demo tương ứng trước khi chuyển sang giai đoạn tiếp theo.
