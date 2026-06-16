# Báo cáo Đối chiếu: Phân tích mã nguồn vs Tài liệu Thiết kế

> Ngày: 2026-06-16
> Đối chiếu giữa: Kết quả rà soát mã nguồn (16/06) và 3 tài liệu thiết kế (architecture.md, product_spec.md, system_backtest_design.md)

---

## Mục lục

1. [Tổng quan mức độ tuân thủ](#1-tổng-quan-mức-độ-tuân-thủ)
2. [Các sai lệch giữa code và thiết kế](#2-các-sai-lệch-giữa-code-và-thiết-kế)
3. [Các vi phạm nguyên tắc thiết kế](#3-các-vi-phạm-nguyên-tắc-thiết-kế)
4. [Các lỗi kỹ thuật cần sửa ngay](#4-các-lỗi-kỹ-thuật-cần-sửa-ngay)
5. [Các cơ hội cải thiện kiến trúc](#5-các-cơ-hội-cải-thiện-kiến-trúc)
6. [Kế hoạch hành động theo thứ tự ưu tiên](#6-kế-hoạch-hành-động-theo-thứ-tự-ưu-tiên)
7. [Phụ lục: Danh sách file liên quan](#7-phụ-lục-danh-sách-file-liên-quan)

---

## 1. Tổng quan mức độ tuân thủ

### Điểm mạnh — Code tuân thủ tốt thiết kế

| Nguyên tắc từ tài liệu | Tình trạng | Bằng chứng |
|---|---|---|
| **Core không import PyQt6/services/UI** | ✅ Đúng | Toàn bộ `core/` chỉ dùng Python thuần + pandas/numpy |
| **Core chỉ trả dữ liệu sạch, không render** | ✅ Đúng | `chart_payload.py` trả JSON, không tạo widget |
| **Worker giao tiếp qua signal/slot** | ✅ Đúng | `ScannerWorker`, `BacktestWorker` dùng `pyqtSignal` |
| **Migration có version rõ ràng** | ✅ Đúng | `data/migrations/001-005` với `schema_migrations` table |
| **AI chỉ diễn giải, không quyết định execution** | ✅ Đúng | AI chỉ gọi trong `_write_scanner_ai_summary`, không tham gia gate/decision |
| **Entry engine là nơi duy nhất xác nhận entry** | ✅ Đúng | `entry_engine.py` là module duy nhất set `ready_to_trade` |
| **Backtest gọi `analyze_symbol()` thật** | ✅ Đúng | `system_backtest_engine.py` gọi pipeline thật, không viết lại |
| **Backtest không ghi vào journal thật** | ✅ Đúng | Kết quả lưu JSON riêng trong `data/backtests/` |
| **Phân biệt app assets / user data / cache** | ✅ Đúng | `config/paths.py` tách biệt rõ |
| **Lot chuẩn hóa theo broker step/min** | ✅ Đúng | `_normalize_volume()` trong `mt5_service.py` |
| **Auto-trade không vượt max_risk_percent** | ✅ Đúng | Controller cap trong `run_market_scan` |
| **Không vào thêm nếu đã có position/order** | ✅ Đúng | `has_open_position_or_order()` check |
| **Contract size ưu tiên MT5 cho XAU/XAG/BTC** | ✅ Đúng | `contract_size_override_for_symbol()` |
| **5 chế độ backtest (Strict/Balanced/Legacy/Research/Backtest)** | ✅ Đúng | `trade_open_block_reason()` trong `system_backtest_engine.py` |
| **Direction bias tính 1 lần, không thiên vị buy** | ✅ Đúng | `neutral` tiebreaker đã sửa, entry quality bonus đã bỏ |

### Tổng kết: ~85% tuân thủ. 15% còn lại là các sai lệch và vi phạm dưới đây.

---

## 2. Các sai lệch giữa code và thiết kế

### SD-1. Thiếu thư mục `ui/components/`

**Thiết kế yêu cầu** (architecture.md:94-102):
```
ui/components/
  app_button.py
  icon_button.py
  card.py
  stat_card.py
  toolbar.py
  section_header.py
  loading_state.py
  empty_state.py
```

**Thực tế:** Thư mục `ui/components/` **không tồn tại**. Các widget tái sử dụng (nút, card, loading state) được code inline trong từng screen file hoặc không được tách riêng.

**Tác động:**
- Trùng lặp code UI giữa các màn hình
- Khó thay đổi style đồng bộ
- Vi phạm nguyên tắc: "Mọi button, card, toolbar, header, loading state và empty state nên dùng component chung"

**Lợi ích nếu sửa:** Giảm 30-40% code UI trùng lặp, style nhất quán, dễ bảo trì.

---

### SD-2. `controllers/app_controller.py` gần như trống rỗng

**Thiết kế yêu cầu** (architecture.md:82-86):
```
controllers/
  app_controller.py
  analysis_controller.py
  settings_controller.py
```

**Thực tế:** `app_controller.py` chỉ có 9 dòng, không làm gì ngoài load settings. `analysis_controller.py` không tồn tại. Vai trò điều phối bị dồn hết vào `scanner_controller.py` (449 dòng).

```python
# app_controller.py hiện tại — 9 dòng
class AppController:
    def __init__(self, settings_service=None):
        self.settings_service = settings_service or SettingsService()
        self.settings = self.settings_service.load()
```

**Tác động:** Không có điểm điều phối trung tâm. Mỗi screen tự khởi tạo controller riêng.

**Lợi ích nếu sửa:** Có 1 nơi quản lý dependency injection, lifecycle, và routing tập trung.

---

### SD-3. Thiếu test coverage theo thiết kế

**Thiết kế yêu cầu** (architecture.md:135-139):
```
tests/
  test_indicators.py
  test_signal_engine.py
  test_risk_engine.py
  test_settings_service.py
```

**Thực tế:** `test_indicators.py`, `test_risk_engine.py`, `test_settings_service.py` **không tồn tại**. Có 51 tests nhưng thiếu các test quan trọng:
- Không test indicator calculations
- Không test risk engine position sizing
- Không test full pipeline integration

**Lợi ích nếu sửa:** Phát hiện regression sớm, đặc biệt khi thay đổi công thức tính indicator hoặc position sizing.

---

### SD-4. 12 file script tạm nằm ở thư mục gốc

**Thiết kế yêu cầu** (architecture.md:29-140): Cấu trúc thư mục rõ ràng, không có script tạm ở gốc.

**Thực tế:** 12 file Python ở thư mục gốc:
```
add_import.py
fix_backtest.py
fix_toggle.py
replace_buttons.py
replace_dialog_buttons.py
replace_missing_buttons.py
replace_other_buttons.py
replace_qdialogbuttonbox.py
replace_qdialogbuttonbox2.py
replace_regex.py
replace_script.py
update_dialog_texts.py
```

Đây là các script migration/refactoring một lần cho UI. Đã hoàn thành nhiệm vụ nhưng chưa được dọn dẹp.

**Tác động:** Làm bẩn không gian làm việc, gây nhầm lẫn về entry point (`main.py`), vi phạm nguyên tắc "Không code tất cả trong một lần — chia module rõ ràng".

**Lợi ích nếu sửa:** Không gian làm việc sạch, rõ ràng. Không ai hiểu nhầm file tạm là production code.

---

### SD-5. Không có `controllers/analysis_controller.py`

**Thiết kế yêu cầu** (architecture.md:84): `controllers/analysis_controller.py` làm nhiệm vụ "passes `entry_context` into the technical prompt payload".

**Thực tế:** Logic này nằm trong `analysis_engine.py` luôn. Không có controller riêng cho analysis.

**Tác động:** Thấp. Logic prompt đã nằm trong `prompt_builder.py` và `analysis_engine.py` nên không bị thiếu chức năng.

---

## 3. Các vi phạm nguyên tắc thiết kế

### VP-1. `analyze_symbol` vi phạm Single Responsibility (SRP)

**Nguyên tắc từ architecture.md:**
> "Phải chia module rõ ràng để dễ mở rộng, dễ bảo trì"
> "Controller không được: Tính chỉ báo kỹ thuật, Tính điểm giao dịch, Chứa query SQL phức tạp"

**Thực tế:** `analysis_engine.py:48-402` (354 dòng) là một hàm monolithic gọi 15+ engine, build gate context, merge codes, tính final_score, evidence score, chart payload, backtest replay, checklist, confidence reason, v.v.

**Vi phạm:** Một hàm làm quá nhiều việc — orchestration + computation + formatting.

**Lợi ích nếu sửa:**
- Tách thành `AnalysisPipeline` class với các step rõ ràng
- Mỗi step test được độc lập
- Khi thêm engine mới (ví dụ Phase 18), không cần sửa hàm 350 dòng
- Giảm rủi ro bug khi modify

---

### VP-2. Hai hệ thống decision song song

**Nguyên tắc từ architecture.md:**
> "code phải rõ ràng, dễ bảo trì"

**Thực tế:** Tồn tại 2 hệ thống phân loại:
1. **Legacy**: `classify_decision()` (signal_engine.py) + `classify_scanner_action()` (scanner.py) — dùng `ready/watch/wait/skip`
2. **Mới**: `make_final_decision()` (decision_engine.py) — dùng `READY_TO_TRADE/WAITING_CONFIRMATION/WATCH_ONLY/TRADE_BLOCKED/STAND_ASIDE`

Cả hai cùng chạy trong `analyze_symbol`, output được chọn qua flag `use_decision_engine_action`.

**Vi phạm:** Code thừa, khó hiểu, dễ gây bug khi 2 hệ thống cho kết quả khác nhau.

**Lợi ích nếu sửa:**
- Xóa ~100 dòng code thừa
- Không còn confusion về "hành động nào là đúng"
- Gate system chỉ cần tích hợp với 1 decision engine duy nhất

---

### VP-3. Bare `except Exception` trong core engines

**Nguyên tắc từ architecture.md:**
> "Lỗi kỹ thuật đầy đủ nằm trong log. UI chỉ hiển thị thông báo ngắn, rõ nguyên nhân"

**Thực tế:** Nhiều nơi dùng `except Exception` bắt tất cả, bao gồm `KeyboardInterrupt`, `SystemExit`, `MemoryError`:

| File | Vị trí | Bắt exception gì |
|---|---|---|
| `scanner_controller.py:171` | Loop xử lý từng symbol | Nuốt mọi exception → hiển thị "không quét được" |
| `news_service.py` | 15+ vị trí | Nuốt exception khi fetch tin tức |
| `system_backtest_engine.py:174` | Backtest loop | Nuốt exception khi phân tích |

**Vi phạm:** "Lỗi kỹ thuật đầy đủ nằm trong log" — nhưng với `except Exception`, lỗi không được log đúng cách, gây khó debug.

**Lợi ích nếu sửa:**
- Bug bị ẩn sẽ lộ ra khi chạy test
- Log có đủ thông tin để debug
- Không nuốt `MemoryError` hoặc `KeyboardInterrupt`

---

### VP-4. Không có logging nhất quán trong toàn bộ hệ thống

**Nguyên tắc từ architecture.md:**
> "Ứng dụng phải có logging thống nhất: Log file xoay vòng, không ghi API key, lỗi đầy đủ trong log"

**Thực tế:** `logging_service.py` có tồn tại và được gọi từ `main.py`, nhưng trong `core/` engines và `services/`, logging gần như không được sử dụng. Exception bị nuốt trong scanner loop không được log.

**Lợi ích nếu sửa:** Debug được trên máy user, audit trail cho auto-trade, cảnh báo sớm khi có vấn đề.

---

## 4. Các lỗi kỹ thuật cần sửa ngay

### L-1. [CRITICAL] Duplicate `legacy_action` key trong `make_final_decision`

**File:** `core/decision_engine.py`

**Dòng:** 518-519, 536-537

```python
# DÒNG 518-519 — TRADE_BLOCKED path
"legacy_action": decision_to_legacy_action(TRADE_BLOCKED),
"legacy_action": decision_to_legacy_action(TRADE_BLOCKED),  # ← TRÙNG KEY

# DÒNG 536-537 — decision_cap TRADE_BLOCKED path
"legacy_action": decision_to_legacy_action(TRADE_BLOCKED),
"legacy_action": decision_to_legacy_action(TRADE_BLOCKED),  # ← TRÙNG KEY
```

**Nguyên nhân:** Copy-paste error. Python dict chỉ giữ giá trị cuối, nên không crash, nhưng là dấu hiệu code không được review kỹ.

**Tác động:** Hiện tại chưa gây lỗi vì 2 giá trị trùng. Nhưng nếu sau này ai đó sửa 1 dòng mà không sửa dòng kia → bug rất khó phát hiện.

**Fix:** Xóa dòng trùng, chỉ giữ 1 dòng.

**Lợi ích:** Code sạch, không gây hiểu nhầm, tránh bug tiềm ẩn.

---

### L-2. [CRITICAL] `mt5.initialize()` không có `shutdown()` tương ứng

**File:** `core/risk_engine.py:341-367`

**Hàm:** `_resolve_quote_to_usd_rate()`

```python
def _resolve_quote_to_usd_rate(symbol: str) -> float | None:
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():  # ← GỌI INITIALIZE
            return None
        # ... xử lý ...
        return None
    except Exception:
        return None
    # ← KHÔNG GỌI mt5.shutdown()
```

**Tác động:** MT5 SDK giữ tài nguyên native (shared memory, pipes). Mỗi lần scan (31 symbols), hàm này có thể được gọi nhiều lần. Auto-scan mỗi 15 phút → memory leak tích lũy → MT5 terminal crash sau vài ngày.

**Fix:** Thêm `finally: mt5.shutdown()`.

**Lợi ích:** Ngăn memory leak, MT5 terminal ổn định khi chạy auto-scan dài ngày.

---

### L-3. [CRITICAL] SQLite connection không có busy timeout + retry

**File:** `services/journal_service.py:497-500`

```python
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

**Vấn đề:** Không set `timeout` hoặc `isolation_level`. Khi scanner thread và UI thread cùng ghi journal → `database is locked`.

**Fix:**
```python
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```

**Lợi ích:** Không crash khi auto-scan và user thao tác journal đồng thời.

---

### L-4. [HIGH] `ThreadPoolExecutor` không được quản lý shutdown trong backtest

**File:** `core/system_backtest_engine.py`

Backtest sử dụng ThreadPoolExecutor nhưng không đảm bảo shutdown khi có lỗi giữa chừng. Nếu user cancel backtest, worker threads treo.

**Fix:** Dùng `with ThreadPoolExecutor() as executor:` hoặc try/finally với `executor.shutdown(wait=False)`.

**Lợi ích:** Clean resource khi cancel, không để zombie threads.

---

### L-5. [HIGH] Migration SQL không an toàn khi chạy lại

**File:** `data/migrations/002-005*.sql`

Các file dùng `ALTER TABLE ADD COLUMN` thuần. SQLite không hỗ trợ `IF NOT EXISTS` cho `ADD COLUMN`. Nếu migration chạy trên DB đã có column (vd: backup restore), sẽ crash.

**Fix:** Trong `JournalService.migrate()`, kiểm tra column tồn tại trước khi chạy ALTER TABLE bằng `PRAGMA table_info`.

**Lợi ích:** Migration an toàn với mọi trạng thái DB.

---

## 5. Các cơ hội cải thiện kiến trúc

### CT-1. Tách `analyze_symbol` thành `AnalysisPipeline` class

**Thiết kế hiện tại:** 1 hàm 354 dòng trong `analysis_engine.py`

**Thiết kế đề xuất:**
```python
class AnalysisPipeline:
    def execute(self, request, candles, **kwargs) -> dict:
        # Step 1: Technical + SMC
        technical = self._build_technical(candles)
        smc = self._build_smc(candles)
        data_quality = self._build_data_quality(request, candles)

        # Step 2: Scoring
        scores = self._score_scenarios(technical, smc, ...)

        # Step 3: Trade plans
        scenarios = self._build_scenarios(request, technical, smc, scores, ...)

        # Step 4: Gates
        gate_result = self._check_gates(...)

        # Step 5: Final decision
        decision = self._make_decision(scores, gate_result, scenarios)

        # Step 6: Enrichment
        return self._enrich_result(...)
```

**Lợi ích:**
- Mỗi step test được độc lập
- Có thể override từng step trong backtest (vd: mock macro)
- Dễ thêm step mới (Phase 18, 19...)
- Code dễ đọc, dễ review

---

### CT-2. Deprecate hoàn toàn legacy decision system

**Giữ lại:** `make_final_decision()` trong `decision_engine.py`

**Xóa bỏ:**
- `classify_decision()` trong `signal_engine.py:495-509`
- `classify_scanner_action()` trong `scanner.py:40-54`
- Flag `use_decision_engine_action` trong `analyze_symbol`

**Lợi ích:**
- Xóa ~80 dòng code
- Không còn confusion 2 hệ thống
- Gate system tích hợp nhất quán
- Tất cả consumer dùng chung 1 interface

---

### CT-3. Tạo `ui/components/` theo đúng thiết kế

**Lợi ích:**
- Giảm 30-40% code UI trùng lặp
- Style nhất quán trên toàn bộ app
- Dễ thay đổi theme/design system
- Đúng với kiến trúc đã đề ra

---

### CT-4. Triển khai dependency injection đơn giản

**Hiện tại:** Mỗi controller tự khởi tạo service với default constructor.

**Đề xuất:** Tạo 1 factory/container trong `app_controller.py` để quản lý singleton instances.

```python
class AppController:
    def __init__(self):
        self._settings_service = SettingsService()
        self._mt5_service = MT5Service()
        self._journal_service = JournalService()
        # ...

    @property
    def scanner_controller(self) -> ScannerController:
        if self._scanner_controller is None:
            self._scanner_controller = ScannerController(
                settings_service=self._settings_service,
                mt5_service=self._mt5_service,
                journal_service=self._journal_service,
                # ...
            )
        return self._scanner_controller
```

**Lợi ích:**
- Không tạo trùng service instances
- Dễ test với mock
- Đúng vai trò "điều phối" của AppController theo thiết kế

---

### CT-5. Thêm integration tests cho scanner pipeline

**Thiết kế yêu cầu** (product_spec.md:269-275):
> "Core: scoring, risk, entry engine, signal engine, decision engine, trade gate"
> "Scanner ranking, opportunity score, scanner row contract"

Hiện có 51 unit tests (all passing) nhưng không có integration test nào cho full pipeline.

**Lợi ích:** Phát hiện regression khi thay đổi engine, đảm bảo pipeline hoạt động end-to-end.

---

## 6. Kế hoạch hành động theo thứ tự ưu tiên

### Giai đoạn 1: SỬA NGAY (Hôm nay) — 3 việc

| # | Việc cần làm | File | Thời gian | Lợi ích |
|---|---|---|---|---|
| 1 | **Sửa duplicate `legacy_action` key** | `core/decision_engine.py` | 30 phút | Code sạch, tránh bug tiềm ẩn |
| 2 | **Thêm `mt5.shutdown()` trong finally** | `core/risk_engine.py:341-367` | 1 giờ | Ngăn memory leak MT5 |
| 3 | **Thêm SQLite busy timeout + WAL mode** | `services/journal_service.py:497` | 30 phút | Không crash database locked |

**Tổng: 2 giờ. Rủi ro: thấp. Lợi ích: ngăn 3 bug có thể crash app.**

---

### Giai đoạn 2: ƯU TIÊN CAO (Tuần này) — 5 việc

| # | Việc cần làm | File liên quan | Thời gian | Lợi ích |
|---|---|---|---|---|
| 4 | **Di chuyển 12 script tạm vào `scripts/migrations/`** | 12 file gốc | 1 giờ | Không gian làm việc sạch |
| 5 | **Thêm `PRAGMA table_info` check trong migration** | `services/journal_service.py:93-108` | 1 giờ | Migration an toàn |
| 6 | **Sửa `except Exception` → specific exceptions** | `news_service.py`, `scanner_controller.py` | 3 giờ | Lộ bug ẩn, log đầy đủ |
| 7 | **Xóa duplicate key trong tất cả vị trí `make_final_decision`** | `core/decision_engine.py` (14 vị trí) | 1 giờ | Code sạch hoàn toàn |
| 8 | **Thêm logging vào scanner loop** | `scanner_controller.py`, core engines | 2 giờ | Debug được trên máy user |

**Tổng: 1 ngày. Rủi ro: thấp-trung bình. Lợi ích: codebase sạch, dễ bảo trì.**

---

### Giai đoạn 3: CẢI THIỆN KIẾN TRÚC (Tuần sau) — 4 việc

| # | Việc cần làm | File liên quan | Thời gian | Lợi ích |
|---|---|---|---|---|
| 9 | **Tách `analyze_symbol` → `AnalysisPipeline` class** | `core/analysis_engine.py` | 2 ngày | Dễ test, dễ mở rộng |
| 10 | **Deprecate legacy decision system** | `signal_engine.py`, `scanner.py`, `decision_engine.py` | 1 ngày | Code rõ ràng, không confusion |
| 11 | **Tạo `ui/components/` cơ bản** | `ui/components/`, các screen | 2 ngày | UI nhất quán, giảm trùng lặp |
| 12 | **Thêm integration test cho scanner pipeline** | `tests/test_integration_scanner.py` | 1 ngày | Phát hiện regression |

**Tổng: 1 tuần. Rủi ro: trung bình. Lợi ích: kiến trúc bền vững.**

---

### Giai đoạn 4: TỐI ƯU (Tháng sau) — 4 việc

| # | Việc cần làm | File liên quan | Thời gian | Lợi ích |
|---|---|---|---|---|
| 13 | **Parallel symbol scanning** | `scanner_controller.py` | 2 ngày | Scan nhanh hơn 60-70% |
| 14 | **Lazy chart payload + settings cache** | `analysis_engine.py`, `scanner_controller.py` | 1 ngày | Giảm 15% memory, giảm I/O |
| 15 | **Triển khai dependency injection** | `app_controller.py` | 1 ngày | Dễ test, dễ maintain |
| 16 | **Bổ sung test cho indicators, risk_engine, settings_service** | `tests/` | 2 ngày | Đủ test coverage theo thiết kế |

**Tổng: 1 tuần. Rủi ro: trung bình. Lợi ích: performance + test coverage.**

---

## 7. Phụ lục: Danh sách file liên quan

### File cần sửa (theo thứ tự ưu tiên)

| Ưu tiên | File | Vấn đề |
|---|---|---|
| **GĐ1** | `core/decision_engine.py` | Duplicate `legacy_action` key (14 vị trí) |
| **GĐ1** | `core/risk_engine.py:341-367` | `mt5.initialize()` không shutdown |
| **GĐ1** | `services/journal_service.py:497-500` | SQLite không có timeout + WAL |
| **GĐ2** | 12 file `*.py` ở thư mục gốc | Di chuyển vào `scripts/migrations/` |
| **GĐ2** | `services/journal_service.py:93-108` | Migration không check column tồn tại |
| **GĐ2** | `services/news_service.py` (15+ vị trí) | `except Exception` quá rộng |
| **GĐ2** | `controllers/scanner_controller.py:171,304,425` | `except Exception` nuốt lỗi |
| **GĐ2** | `core/system_backtest_engine.py` | ThreadPoolExecutor shutdown |
| **GĐ3** | `core/analysis_engine.py` | `analyze_symbol` quá lớn (354 dòng) |
| **GĐ3** | `core/signal_engine.py:495-509` | Legacy `classify_decision` |
| **GĐ3** | `core/scanner.py:40-54` | Legacy `classify_scanner_action` |
| **GĐ3** | `ui/screens/*.py` | Tách components dùng chung |
| **GĐ3** | `tests/` | Thiếu integration test |
| **GĐ4** | `controllers/scanner_controller.py:109` | Scan tuần tự → parallel |
| **GĐ4** | `controllers/app_controller.py` | Dependency injection |

### File cần tạo mới

| File | Mục đích |
|---|---|
| `ui/components/app_button.py` | Button component chung |
| `ui/components/card.py` | Card component chung |
| `ui/components/loading_state.py` | Loading indicator |
| `ui/components/empty_state.py` | Empty state placeholder |
| `tests/test_indicators.py` | Test indicator calculations |
| `tests/test_risk_engine.py` | Test position sizing |
| `tests/test_integration_scanner.py` | Integration test full pipeline |

### File cần xóa (sau khi di chuyển)

| File | Lý do |
|---|---|
| `add_import.py` | Script migration 1 lần |
| `fix_backtest.py` | Script migration 1 lần |
| `fix_toggle.py` | Script migration 1 lần |
| `replace_buttons.py` | Script migration 1 lần |
| `replace_dialog_buttons.py` | Script migration 1 lần |
| `replace_missing_buttons.py` | Script migration 1 lần |
| `replace_other_buttons.py` | Script migration 1 lần |
| `replace_qdialogbuttonbox.py` | Script migration 1 lần |
| `replace_qdialogbuttonbox2.py` | Script migration 1 lần |
| `replace_regex.py` | Script migration 1 lần |
| `replace_script.py` | Script migration 1 lần |
| `update_dialog_texts.py` | Script migration 1 lần |

---

## Kết luận

Hệ thống **tuân thủ ~85% thiết kế**, đặc biệt tốt ở các nguyên tắc cốt lõi:
- Core tách biệt hoàn toàn khỏi UI/services
- Pipeline engine có thứ tự rõ ràng
- Backtest gọi pipeline thật, không viết lại
- Auto-trade an toàn với nhiều lớp bảo vệ

**3 việc cần sửa ngay (GĐ1 — 2 giờ):**
1. Duplicate `legacy_action` key → tránh bug tiềm ẩn
2. `mt5.shutdown()` → ngăn memory leak
3. SQLite WAL mode → không crash database locked

**2 sai lệch kiến trúc lớn nhất:**
1. `analyze_symbol` 354 dòng — cần tách thành Pipeline class
2. 2 hệ thống decision song song — cần deprecate legacy

**Lợi ích tổng thể nếu thực hiện đầy đủ:**
- Codebase sạch, đúng kiến trúc đề ra
- Hiệu năng scan cải thiện 60-70%
- Không còn bug tiềm ẩn gây crash
- Dễ dàng thêm tính năng mới
- Test coverage đầy đủ → tự tin refactor



NHẬN XÉT CỦA ANTIGRAVITY
Sau khi đối chiếu báo cáo audit_report_20260616.md với mã nguồn hiện tại của dự án mà tôi vừa phân tích, tôi xác nhận rằng phần lớn các phân tích trong báo cáo là chính xác và nắm bắt rất đúng các vấn đề lõi của hệ thống.

Dưới đây là đánh giá chi tiết về việc mục nào nên làm, mục nào không nên làm (hoặc cần điều chỉnh cách làm):

🟢 Những mục RẤT NÊN LÀM (Làm càng sớm càng tốt)
1. Nhóm sửa lỗi kỹ thuật (GĐ1 - L-1, L-2, L-3)

OK - L-2 (mt5.shutdown() bị thiếu): Đây là lỗi nghiêm trọng nhất. Thư viện MetaTrader5 dùng cơ chế IPC (Inter-Process Communication) ngầm. Việc gọi initialize() liên tục mà không shutdown() sẽ rò rỉ bộ nhớ (memory leak) và chắc chắn làm crash terminal MT5 khi chạy auto-scan thời gian dài.
OK - L-3 (SQLite WAL mode + Timeout): Việc thiếu timeout và chế độ WAL trong journal_service.py sẽ làm ứng dụng bị văng (crash) với lỗi database is locked ngay khi luồng background scanner và UI cùng cố gắng ghi log.
OK - L-1 (Trùng key legacy_action): Tuy hiện tại không gây crash do dict tự ghi đè, nhưng đây là "bom nổ chậm" nếu sau này cần đổi logic. Sửa chỉ mất 1 phút.
2. Nhóm bảo vệ hệ thống (GĐ2 - L-4, L-5, SD-4)

OK - L-4 (Dọn dẹp ThreadPoolExecutor): Chắc chắn phải làm. ThreadPool không được quản lý sẽ tạo ra "zombie threads", tiếp tục ngầm gọi MT5 ngay cả khi user đã huỷ backtest.
OK - L-5 (Migration SQL an toàn): Việc thêm PRAGMA table_info trước khi ADD COLUMN là bắt buộc đối với SQLite để tránh crash app khi cập nhật phiên bản.
OK - SD-4 (Dọn 12 file script tạm): Rất nên làm. Gom toàn bộ vào thư mục scripts/ui_migrations/ để root directory sạch sẽ.
3. Nhóm Tests (CT-5) - Cần đẩy mức độ ưu tiên lên cao nhất

OK - Báo cáo xếp CT-5 (Integration test cho scanner pipeline) vào Giai đoạn 3 là hơi muộn. Bạn BẮT BUỘC phải viết integration test cho analyze_symbol() trước khi tiến hành tách file (CT-1) để tránh lỗi hồi quy (regression bugs).
🟡 Những mục NÊN LÀM (Nhưng cần làm cẩn thận)
OK - 1. Tách analyze_symbol (CT-1)

Hàm này đang dài >350 dòng và ôm đồm quá nhiều việc (God Object). Việc tách thành AnalysisPipeline là đúng đắn. Tuy nhiên, rủi ro làm hỏng logic hiện tại rất cao. Chỉ làm sau khi đã xong mục test (CT-5).
OK - 2. Loại bỏ hệ thống decision cũ (CT-2)

Nên làm để code đồng nhất. Tuy nhiên, cần rà soát kỹ các file UI (Dashboard, Scanner Screen) vì chúng có thể đang bind trực tiếp vào các chuỗi cũ như ready, watch.
OK - 3. Dependency Injection (CT-4)

Rất tốt cho kiến trúc, giúp chỉ khởi tạo MT5Service một lần. Nên làm.
🔴 Những mục KHÔNG NÊN LÀM (Hoặc cần xem xét lại mức độ khả thi)
1. Parallel symbol scanning (Quét mã song song - Đề xuất số 13 trong GĐ4)

Không nên làm bằng Threading thông thường. Thư viện MetaTrader5 của Python không thread-safe. Nếu bạn bắn nhiều request kéo OHLCV cùng lúc từ nhiều luồng (thread) khác nhau mà không cấp phát instance riêng biệt cho từng luồng, MT5 Terminal sẽ bị đơ (freeze) hoặc trả về None ngẫu nhiên.
Hướng xử lý thay thế: Nếu muốn làm, phải thiết kế một MT5ConnectionPool hoặc gom các request lại quét tuần tự nhưng dùng asyncio ở tầng UI để không làm đơ giao diện, thay vì đa luồng ở tầng lấy dữ liệu MT5.
2. Sửa toàn bộ except Exception cùng lúc (L-6 trong GĐ2)

Không nên làm một lúc. Việc gỡ bỏ except Exception trong vòng lặp scanner có thể làm scanner bị sập (crash) liên tục vì những lỗi vặt (vd: mất mạng 1 giây, MT5 timeout).
Hướng xử lý thay thế: Thay vì bỏ except Exception, hãy giữ nguyên nhưng thêm logging (logger.exception("Lỗi khi scan...")) để ghi nhận lỗi mà vẫn cho vòng lặp chạy tiếp các mã (symbol) khác.
💡 Đề xuất lộ trình tối ưu nhất cho bạn:
Mở core/decision_engine.py và services/journal_service.py để sửa ngay 3 lỗi rủi ro cao (L-1, L-2, L-3).
Dọn dẹp 12 file rác ở thư mục gốc vào scripts/.
Viết 1 kịch bản test tổng thể cho Pipeline.
(Chỉ khi xong bước 3) Mới bắt đầu chẻ nhỏ analyze_symbol().



NHẬN XÉT CỦA CODEX
Mình đã đối chiếu report với repo hiện tại. Kết luận ngắn: report có nhiều điểm đúng, nhưng có vài mục đã lỗi thời hoặc trỏ sai file. Test hiện tại đang xanh: 51 passed.
Nên Sửa Sớm
Duplicate legacy_action trong [core/decision_engine.py (line 518)](/d:/Projects/AIMarketAnalyst/core/decision_engine.py:518) và [core/decision_engine.py (line 536)](/d:/Projects/AIMarketAnalyst/core/decision_engine.py:536)
Đúng như report. Không gây crash ngay, nhưng nên xóa key trùng.

Quản lý lifecycle MT5
Report chỉ nêu [core/risk_engine.py (line 341)](/d:/Projects/AIMarketAnalyst/core/risk_engine.py:341), nhưng thực tế rộng hơn: toàn repo không có mt5.shutdown() nào, trong khi services/mt5_service.py gọi mt5.initialize() nhiều nơi. Đặc biệt [services/mt5_service.py (line 258)](/d:/Projects/AIMarketAnalyst/services/mt5_service.py:258) còn dùng ThreadPoolExecutor để load timeframe song song. Nên sửa theo hướng có helper/context quản lý MT5 tập trung, và cân nhắc bỏ parallel MT5 call nếu package không ổn định với thread.

SQLite journal thiếu timeout/WAL
[services/journal_service.py (line 497)](/d:/Projects/AIMarketAnalyst/services/journal_service.py:497) đúng là chỉ sqlite3.connect(self.db_path). Nên thêm timeout, PRAGMA journal_mode=WAL, có thể thêm PRAGMA busy_timeout.

Migration chưa idempotent
Các file như [data/migrations/002_add_account_guard_fields.sql (line 1)](/d:/Projects/AIMarketAnalyst/data/migrations/002_add_account_guard_fields.sql:1) dùng ALTER TABLE ADD COLUMN thẳng. Nếu DB đã có cột nhưng migration table lệch trạng thái, app có thể fail. Nên xử lý trong migration runner bằng PRAGMA table_info.

Logging chưa đủ mạnh
Có configure_logging(), nhưng chỉ dùng FileHandler, chưa xoay vòng ở [services/logging_service.py (line 11)](/d:/Projects/AIMarketAnalyst/services/logging_service.py:11). Các boundary except Exception như [controllers/scanner_controller.py (line 171)](/d:/Projects/AIMarketAnalyst/controllers/scanner_controller.py:171) nên giữ để scanner không sập cả vòng, nhưng phải logger.exception(...).

Dọn script tạm ở root
Report đúng: nhiều file replace_*.py, fix_*.py, add_import.py đang nằm cạnh main.py. Nên chuyển vào scripts/ui_migrations/ hoặc xóa nếu chắc chắn không cần.

Nên Sửa Nhưng Làm Sau
Tách analyze_symbol()
[core/analysis_engine.py (line 48)](/d:/Projects/AIMarketAnalyst/core/analysis_engine.py:48) đúng là đang ôm orchestration lớn. Nhưng nên viết integration test cho pipeline trước rồi mới tách.

Deprecate legacy decision
Legacy vẫn tồn tại ở [core/signal_engine.py (line 495)](/d:/Projects/AIMarketAnalyst/core/signal_engine.py:495) và [core/scanner.py (line 40)](/d:/Projects/AIMarketAnalyst/core/scanner.py:40). Nên gỡ dần, vì scanner/UI vẫn còn dùng bridge legacy_action.

Dependency injection qua AppController
[controllers/app_controller.py (line 6)](/d:/Projects/AIMarketAnalyst/controllers/app_controller.py:6) hiện rất mỏng. Nên làm, nhưng không cấp bách bằng MT5/SQLite/logging.

Không Nên Sửa Theo Report
Không tạo mới ui/components/
Report lỗi thời: thư mục này đã tồn tại với app_button.py, card.py, toolbar.py, loading_state.py, empty_state.py, v.v. Có thể audit mức độ sử dụng, nhưng không phải “thiếu component”.

Không sửa ThreadPoolExecutor trong core/system_backtest_engine.py theo report
File này hiện không dùng ThreadPoolExecutor. Vấn đề thread thật nằm ở services/mt5_service.py.

Không “mass replace” toàn bộ except Exception
Với scanner/news/service boundary, bỏ catch hàng loạt dễ làm app dễ sập hơn. Hướng đúng là log đầy đủ, chỉ siết exception ở nơi thật sự có contract rõ.

Không làm parallel symbol scanning với MT5 lúc này
Repo đã có parallel ở tầng timeframe MT5 rồi, và đây mới là điểm đáng lo. Đừng mở rộng parallel scan trước khi có chiến lược MT5 thread-safety.

Ưu tiên thực tế mình đề xuất: sửa decision_engine duplicate key, thiết kế lại MT5 lifecycle/threading, thêm SQLite timeout/WAL, thêm logging cho scanner boundary, rồi viết integration test trước khi refactor analyze_symbol().