# Runtime Status

Cập nhật trạng thái runtime: **17/08/2026 (Asia/Ho_Chi_Minh)**.

Tài liệu này ghi trạng thái cấu hình đang lưu trên máy hiện tại. Đây không
phải giá trị mặc định của mã nguồn và không thay thế contract trong
[`scanner-flow.md`](../scanner/scanner-flow.md).

> **Scanner là runtime hiện hành, chạy live từ 15/08/2026:** cutover hoàn tất
> ở Bước 12 (14/08/2026); Bước 13 nối RuntimeOrderPolicy live và gỡ bỏ toàn bộ
> rollout machinery (stage ladder, kill switch, release/canary readiness) cùng chế
> độ SHADOW theo quyết định của owner. Xem
> [`scanner-architecture.md`](../scanner/scanner-architecture.md).

## Order Management V2

Contract runtime **đang chạy live** từ 15/08/2026 theo quyết định của owner
(phần mềm cá nhân, không qua rollout), xem
[`order-management-contract.md`](../trading/order-management-contract.md). Các
contract snapshot MT5, postcondition position/pending, state machine,
persistence account-scoped và `OrderManagementService` single-executor đã được
triển khai cùng targeted automated test.

`AppController` sở hữu và shutdown service; `MainWindow` start service; Scanner
reconcile position broker rồi register vào service; Orders UI đọc cache và nhận
Qt signals thay vì gọi native MetaTrader5. Service load/persist/flush state theo
account, phát health/operation events và đưa broker I/O qua một executor tuần tự.
Pending cancel/modify, manual/partial close, scoped frozen close-all và frozen
flatten cũng đi qua boundary này.

Mặc định mã nguồn là phạm vi quản lý `AMA` (live, fail-safe) và OM hoạt động
vô điều kiện: feature flag `order_management_v2` đã bị gỡ khỏi model
(16/08/2026) để hệ thống luôn bật, nhất quán với việc gỡ các flag Scanner
trước đó. Stage ladder, kill switch, `require_demo_account`,
`production_approved` và canary đã bị xóa khỏi cả code lẫn settings; key thừa
trên disk bị loader bỏ qua. Gate thực thi hiện tại chỉ còn duy nhất
`account.trade_allowed` của broker (fail-closed khi `false`/không xác định).
Thao tác manual vẫn cần dialog xác nhận riêng. Settings cập nhật policy của
service đang chạy mà không cần restart.

Full suite tại thời điểm chuyển live: **3717 passed, 8 skipped, 16 xfailed**.
Sau khi nối 5 live producer (16/08/2026): **3775 passed, 8 skipped, 16 xfailed**.
Sau fix freshness tick-priority + scenario plan producer (16/08/2026):
**3809 passed, 8 skipped, 16 xfailed**.
Sau khi gỡ toàn bộ shadow subsystem (16/08/2026):
**3598 passed, 8 skipped, 16 xfailed** (số test giảm do xóa test shadow).
Sau khi gỡ feature flag `order_management_v2` (OM always-on, 16/08/2026):
**3595 passed, 8 skipped, 16 xfailed** (giảm 3 test: feature-flag settings/UI/service).
Sau khi gỡ `manage_scope` (chỉ còn phạm vi ALL) + gộp tab Quản lý lệnh thành lưới 2 cột:
**3594 passed, 8 skipped, 16 xfailed** (giảm 1 test scope combo).

## Sửa lỗi Journal nghiêm trọng (16/08/2026)

Rà soát phần Nhật ký so với thiết kế phát hiện 6 lỗi; đã sửa và thêm test
regression. Full suite: **3605 passed, 8 skipped, 16 xfailed**; smoke xanh;
`sends_real_order=False` giữ nguyên.

- **B1** `core/account_guard.py`: `calculate_loss_stats` đếm streak theo
  `reversed(trades)` trong khi `list_closed_trades_for_account_guard` đã trả
  newest-first → streak gần như luôn 0. Sửa: duyệt nhánh theo thứ tự mới nhất
  trước (khớp `_v4_consecutive_losses`); bỏ biến chết `loss_sequence`.
- **B2** Guard bỏ sót lệnh thua: lệnh MT5-sync thiếu SL bị `result_pct`/
  `result_r` wipe → 0, nhưng `result_amount` vẫn âm. Sửa: `_is_loss_trade` lấy
  `result_amount < 0` làm tín hiệu chính, fallback `result_pct`→`result_r`.
- **B3** `result_pct` là % giá, không phải % tài khoản → so với
  `max_daily_loss_pct` sai ngữ nghĩa. Sửa: `calculate_loss_stats`/`check_account_guard`
  nhận `account_balance` (tùy chọn); khi có balance + `result_amount`, daily/weekly
  = `sum(result_amount)/balance×100` (% tài khoản). Không có balance/amount thì giữ
  fallback legacy (test Phase-4 cũ vẫn xanh). `evaluate_portfolio_risk` đã truyền
  balance thật.
- **#7/B4** `services/journal_service.py`: `update_lifecycle` wipe
  `result_r/result_pct/realized_effective_rr` khi payload MT5 chỉ có
  actual_entry/exit mà thiếu SL. Sửa: không wipe với payload `synced_from ==
  "mt5_history"`. **Chưa làm:** ghép lệnh MT5 theo `candidate_id` (cột journal
  chưa có; cần migration + wire row_id từ scanner placement — ngoài phạm vi đợt này).
- **#8** `services/mt5_service.py`: `_closed_trades_from_deals` lấy entry/exit từ
  deal đầu/cuối → scale-in/partial close tính sai. Sửa: `_volume_weighted_average`
  bình quân giá theo volume cho entry_deals/exit_deals.
- **#5** `list_closed_trades_for_account_guard`: `select_cols` thiếu zone/scoring
  metadata → cohort `symbol_direction_zone` (cần `entry_zone_score` +
  `entry_zone_scoring_version`) không ánh xạ được. Sửa: bổ sung đủ cột zone,
  sub_zone, selected_zone_id, quality/relevance/setup score, scoring version,
  smc_scorer_version, scanner_scorer_version, scanner_feature_version,
  smc_score_breakdown_json. Test: `tests/test_account_guard_fixes.py` (B1/B2/B3).

## Rà soát "cả 3 blocker" → READY_NOW (17/08/2026)

Owner yêu cầu xử lý 3 nguyên nhân khiến mọi cặp `BLOCKED` trong scan live
(thứ 7 22:25, scan 28 cặp). Quyết định + kết quả tại từng mục:

1. **Scenario RR (`GATE_SCENARIO_RR_BLOCK` mọi cặp)** — owner chốt **"align: anchor
   at protective zone"**. Sửa `core/scanner_scenario_producers.py`: entry ghim tại cạnh
   vùng bảo vệ (BUY=`zone_low`, SELL=`zone_high`), risk = đúng buffer 1.0×ATR, TP vượt cạnh
   xa vùng. Trước đây entry market-anchor (close H1) + SL cột sâu ở cạnh vùng xa giá làm risk
   = (giá−vùng_đối_ứng)+ATR → RR 0.02–1.5 mọi cặp → cổng 2:1 không bao giờ đạt. Cập nhật test:
   `test_scanner_scenario_producers.py`, `test_scanner_release.py`. Full suite
   **3605 passed / 8 skipped / 16 xfailed**; smoke xanh; `sends_real_order=False` giữ nguyên.
2. **Spread threshold đủ 26 cặp** — owner chốt **"real-data probe script, không bịa"**.
   Viết `scripts/propose_spread_thresholds.py` (read-only): đọc spread points thật từ
   `MT5.symbol_info().spread` cho 31 symbol, in bảng + JSON `spread_threshold_by_symbol`
   đề xuất để owner duyệt; KHÔNG ghi config. `--multiple` để chấp nhận spread nới rộng.
   Đã sửa (17/08/2026): script cần gọi `svc.connect()` trước khi đọc status — `mt5_connection_status()`
   đọc `terminal_info()` không khởi tạo phiên IPC, nên probe cũ báo "MT5 not connected" giả dù terminal
   vẫn chạy. Chạy lại khi market mở để đọc spread phiên thật.
3. **Macro confidence 0.5 (0 headline)** — owner chốt **"data-freshness, không đụng gate"**.
   Xác nhận: transport + parse + cache merge đều lành mạnh; Google News RSS trả ~39 mục nhưng
   toàn bộ là tin cũ (mới nhất 2026-08-11), tất cả ngoài cửa sổ 24h → 0 headline trong window
   → coverage base/quote=0 → `macro_data_quality`=0.5. 5/6 source macro còn lại đều confidence
   1.0; chỉ coverage tin tức tiền tệ kéo chất lượng xuống. Không sửa code/gate; khi feed trả
   tin mới trong phiên tuần, coverage phục hồi.

## Trạng thái thực thi Scanner

| Thuộc tính | Giá trị hiện tại |
|---|---|
| Order policy | LIVE — `config/scanner_order_policy.json`, owner-accepted 2026-08-15; loader fail-closed, lỗi config phát `ORDER_POLICY_FAULT` và giữ `order_enabled=False` |
| Live producers (safety/account/portfolio/journal) | Đã nối đủ 5 producer live (16/08/2026): spread key chuẩn hóa cent, volatility ratio ATR thật, required margin lô tối thiểu broker-tính + free margin thật, đếm vị thế + exposure `margin÷balance`, drawdown journal 90 ngày. Candidate có thể đạt `READY_NOW` trên dữ liệu thật; thiếu dữ liệu vẫn fail-closed. Chi tiết §13.1 architecture doc |
| Scenario plan producer | 16/08/2026 nối (`core/scanner_scenario_producers.py`). 17/08/2026 RE-ALIGN (owner quyết định "anchor at protective zone"): entry ghim tại cạnh vùng bảo vệ mà SL buffer bám (BUY=`zone_low`, SELL=`zone_high`), SL = cạnh vùng ± 1.0×ATR (hệ số analysis_pipeline.py:1563, risk = đúng buffer), TP = zone đối diện vượt cạnh xa vùng bảo vệ (analysis_pipeline.py:1567-1572). Trước đó entry market-anchor (close H1) làm risk = (giá−vùng)+ATR → RR hệ thống ≪ 2:1 → `GATE_SCENARIO_RR_BLOCK` vĩnh viễn. KHÔNG nhánh ATR tổng hợp. Thiếu vùng/target → `None` → scenario gate fail-closed. Full suite 3605 passed / 8 skipped / 16 xfailed (17/08) |
| Data freshness (tick-priority) | 16/08/2026: tham chiếu tuổi feed ưu tiên tick broker (`symbol_data_quality` đọc `symbol_info_tick`), fallback `last_candle_time_utc` khi không có tick; SLA `max_candle_age_minutes=3` giữ nguyên giá trị, `observed.freshness_reference = "tick"\|"candle"`. Fix false-positive `SAFETY_DATA_STALE` ~12/15 phút do `time` nến M15 là thời điểm MỞ nến; cuối tuần tick già vẫn BLOCK đúng |
| Tài khoản cent | Broker symbol `EURUSDc` khớp ngưỡng qua chuẩn hóa key (`_spread_threshold_for`); không cần đổi config |
| Rollout stage ladder | Đã gỡ bỏ khỏi codebase (15/08/2026) |
| Shadow subsystems còn lại | 16/08/2026: gỡ toàn bộ theo quyết định owner — Bước 5 event-impact derate, Bước 6 AI Macro Verdict, Macro V2 diagnostics, backtest engine shadow trong release gate, và `ai_verdict` dimension của macro gate. Đường live vốn không tiêu thụ shadow nào nên quyết định live không đổi. Release gate bỏ thành phần engine shadow nên report version bump lên `backtest-phase7-release-report-v2` (báo cáo v1 đã lưu không còn hiệu lực) |
| Kill switch | Đã gỡ bỏ; dừng khẩn = đóng lệnh ở broker hoặc ngắt MT5 |
| SMC scorer | `smc-v2` (canonical duy nhất, không có mode để chọn) |
| Feature flags runtime | 16/08/2026: đã xóa `scanner_architecture_v2`, `auto_trade_v2` (không reader nào — Scanner/auto-trade là đường live vô điều kiện), `scanner_fast_tier2` (được gán nhưng không bao giờ branch) và `order_management_v2` (OM always-on, gate chỉ còn `account.trade_allowed`); flag còn hiệu lực: `scanner_fast_tier1`, `scanner_mt5_history_cache`, `scanner_core_result_early`. `vix_pair_aware_enabled=false` hiệu lực do settings cũ chưa có key; hai flag Backtest cũ không còn được runtime sử dụng. Key cũ còn sót trên disk bị loader bỏ qua và tự mất ở lần lưu kế tiếp |
| Risk limits 2 lớp (giữ nguyên) | `trading.max_consecutive_losses`/`max_concurrent_orders` KHÔNG trùng dư: chúng nuôi guard chain lúc ĐẶT LỆNH (`_portfolio_limits` → `evaluate_portfolio_risk` tại scanner_controller) và cấu hình Backtest, trong khi scan gate dùng `journal_max_consecutive_losses`/`portfolio_position_limit` của RuntimeOrderPolicy. Hai lớp ở hai thời điểm thực thi khác nhau; xóa lớp nào cũng chạm guard live hoặc backtest nên giữ cả hai |

`backtest_config_v2`/`backtest_engine_v2`, `scanner_architecture_v2`/
`auto_trade_v2`/`scanner_fast_tier2`, `sqlite_database_path`/`settings_storage`
và các key rollout cũ (`stage`, `kill_switch`, `scanner_rollout`...) có thể vẫn
còn trong file Settings được tạo bởi bản cũ. Loader hiện bỏ qua các key này và
lần lưu Settings tiếp theo sẽ không ghi lại; Strategy Router không phụ thuộc
vào chúng. Tương tự, `advanced.event_impact_derate_enabled`/
`advanced.macro_ai_verdict_enabled` (đã gỡ 16/08/2026) và
`macro.ai_conviction_threshold` trong `config/scanner_order_policy.json`
không còn reader; key thừa trên disk bị loader bỏ qua.

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

Từ 15/08/2026 không còn release/canary readiness gate nào chặn lệnh. Lệnh được
gửi khi RuntimeOrderPolicy `certified()` và toàn bộ execution guard chain đạt
(xem `scanner-flow.md` §11). Config order policy trên máy là bộ số
owner-accepted (threshold 40/35/5/2:1, safety, macro, portfolio 1 lệnh/0.3
exposure, journal 3 lệnh thua liên tiếp/0.1 drawdown).

## Ý nghĩa vận hành

Lệnh thật chỉ có thể được gửi khi tất cả điều kiện sau cùng đạt:

```text
Auto-entry được người dùng chủ động bật trong chế độ quét định kỳ
AND RuntimeOrderPolicy certified (order_enabled=true)
AND candidate READY_NOW/auto_trade_candidate
AND execution revalidation, news, account và portfolio đều đạt

Lệnh thủ công từ dialog cần candidate hợp lệ và đi qua cùng guard chain,
không có override riêng.
```

Không còn kill switch phần mềm. Dừng khẩn cấp: tắt feature flag
(áp dụng ngay, không cần restart), đóng lệnh ở terminal broker hoặc ngắt kết
nối MT5. Đây là lựa chọn có chủ đích của owner.

## Khôi phục cấu hình

Bản sao cấu hình trước thay đổi (thời điểm 24/07/2026) được lưu tại:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\settings.before-live-20260724-231015.json
```

Mã nguồn hiện mặc định live (OM always-on, feature flag đã gỡ 16/08/2026, không
stage ladder); settings trên máy này cũng đã được chuyển sang live ngày
15/08/2026.
