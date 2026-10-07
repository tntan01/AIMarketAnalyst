# SD-C1 — Lấy lịch sử nến MT5 và lập danh sách cutoff

> **Giao bởi:** Tech Lead · **Ngày:** 07/10/2026 · **Người làm:** Coder
> **Kế hoạch tổng:** [`../smc-demote-task-plan.md`](../smc-demote-task-plan.md)
> (chỉ cần đọc §0.2 "Quy tắc bắt buộc" và §2 Q1/Q2/Q8). File này là nguồn
> chính cho task; nếu thấy mâu thuẫn với plan → **dừng và hỏi**, không tự chọn.

## 1. Mục tiêu

Tạo bộ dữ liệu nến **đóng băng** cho nghiên cứu offline: lấy lịch sử D1/H4/H1/M15
của mọi symbol từ MT5 **một lần**, lưu ra file, rồi lập danh sách mốc thời gian
(cutoff) để task sau (SD-C2) chạy lại Scanner tại từng mốc. Task này **không**
chạy Scanner, không chấm điểm gì.

## 2. Chuẩn bị

1. Làm trực tiếp trên branch `main` (không tạo branch). Kiểm `git status` trước khi bắt đầu.
2. Terminal MT5 phải đang mở và đăng nhập (Owner đã xác nhận sẵn sàng).
3. Đọc trước (không sửa) các file sau — task này **dùng lại** code trong đó:
   - `scripts/smc_real_snapshots.py`: dòng 40–70 (import, hằng số), hàm
     `_candle_payload`, `_candle_from_payload`, `_digest`, `_live_min_rr`,
     `_load_window`, phần đầu `_run_collect` (cách gọi `MT5Service`).
   - `services/mt5_service.py`: `MT5Service.connect`, `available_symbols`,
     `resolve_symbol`, `symbol_data_quality`, `load_ohlcv_range`.
   - `core/market_models.py`: `closed_candles_at_cutoff(candles, timeframe, cutoff)`.
   - `config/constants.py`: `SUPPORTED_SYMBOLS` (31 symbol).

## 3. Việc cần làm

### 3.1 File mới `scripts/smc_demote_corpus.py`

Một script, 3 lệnh con: `fetch`, `plan`, `verify`. Đầu file làm giống
`scripts/smc_real_snapshots.py`: thêm `PROJECT_ROOT` vào `sys.path`. Được phép
`import smc_real_snapshots` (thêm `PROJECT_ROOT / "scripts"` vào `sys.path`) để
dùng lại `_candle_payload`, `_candle_from_payload`, `_digest`, `_live_min_rr`.
**Không** copy-paste logic lọc nến đóng; luôn gọi `closed_candles_at_cutoff`.

Hằng số (đặt ở đầu file):

```python
OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_demote"
DATA_DIR = OUTPUT_DIR / "data"            # KHÔNG commit (xem 3.3)
MANIFEST_PATH = OUTPUT_DIR / "corpus_manifest.json"
CUTOFFS_PATH = OUTPUT_DIR / "cutoffs.json"
TIMEFRAMES = ("D1", "H4", "H1", "M15")
FETCH_DAYS = {"D1": 1000, "H4": 400, "H1": 220, "M15": 120}   # lùi từ thời điểm fetch
WINDOW_BARS = {"D1": 500, "H4": 500, "H1": 500, "M15": 100}   # cửa sổ production
TAIL_BARS = {"H1": 48, "M15": 192}                            # nến sau cutoff
CUTOFF_HOURS_UTC = (4, 12, 20)
PERIOD_DAYS = 92                                              # ~3 tháng
```

### 3.2 Lệnh `fetch`

1. `service = MT5Service()`; `connect()` thất bại → in `BLOCKED: MT5 terminal
   is not available` và `exit 2`.
2. `fetched_at = datetime.now(timezone.utc)` — **chỉ** lệnh `fetch` được đọc
   đồng hồ; `plan`/`verify` không bao giờ gọi `now()`.
3. `available = service.available_symbols(market_watch_only=False)`.
4. Với mỗi `app_symbol` trong `SUPPORTED_SYMBOLS`:
   - `broker_symbol = service.resolve_symbol(app_symbol, available)`; không có
     → ghi lý do `symbol_not_found`, sang symbol kế.
   - `quality = service.symbol_data_quality(app_symbol, broker_symbol)` → lấy
     `tick_size`, `tick_size_source`.
   - Với mỗi timeframe: `service.load_ohlcv_range(broker_symbol, tf,
     fetched_at - timedelta(days=FETCH_DAYS[tf]), fetched_at)`; lỗi → ghi lý do
     `fetch_error:<tf>:<message>`, symbol đó coi như thiếu dữ liệu.
   - Lọc: `closed_candles_at_cutoff(candles, tf, fetched_at)` (bỏ nến đang hình
     thành).
   - Ghi `DATA_DIR / f"{safe_name}.json.gz"` (`safe_name` = `app_symbol` bỏ `/`,
     ví dụ `EURUSD`), nội dung JSON:
     ```json
     {"symbol": "EUR/USD", "broker_symbol": "...", "tick_size": 0.00001,
      "tick_size_source": "...", "fetched_at": "...",
      "candles": {"D1": [{"t":..., "o":..., "h":..., "l":..., "c":..., "v":...}], "H4": [...], "H1": [...], "M15": [...]}}
     ```
     (mỗi nến dùng `_candle_payload`). Ghi file kiểu atomic: ghi file tạm rồi
     `os.replace`.
5. Ghi `MANIFEST_PATH` (JSON, `indent=2`, `sort_keys=True`):
   - `fetched_at`, `min_rr` và `min_rr_status` (từ `_live_min_rr()`),
     `fetch_days` (= `FETCH_DAYS`);
   - `symbols`: mỗi symbol → `broker_symbol`, `status` (`ok` / lý do lỗi),
     số nến và thời gian nến đầu/cuối của từng timeframe, `sha256` của file
     dữ liệu (dùng `hashlib.sha256` trên bytes file `.json.gz`).
6. In bảng tóm tắt: symbol, status, số nến từng TF, thời gian chạy.

### 3.3 `.gitignore`

Thêm đúng một dòng: `reports/scanner/smc_demote/data/`.

### 3.4 Hàm dùng chung `windows_at` (SD-C2 sẽ import hàm này)

```python
def load_symbol_data(path: Path) -> dict: ...
    # đọc file .json.gz, trả dict có "candles" là {tf: list[Candle]} (dùng _candle_from_payload)

def windows_at(data: dict, cutoff: datetime) -> tuple[dict[str, list[Candle]], dict[str, list[Candle]]]:
    """Trả (prefix, tail).
    prefix[tf] = closed_candles_at_cutoff(data["candles"][tf], tf, cutoff), giữ WINDOW_BARS[tf] nến CUỐI.
    tail["H1"], tail["M15"] = các nến KHÔNG nằm trong tập closed-at-cutoff đầy đủ,
    giữ TAIL_BARS[tf] nến ĐẦU, theo đúng cách _load_window trong smc_real_snapshots.py làm.
    """
```

`cutoff` bắt buộc timezone-aware; naive → `ValueError`.

### 3.5 Lệnh `plan`

Chỉ đọc file trong `DATA_DIR` + manifest, không gọi MT5, không gọi `now()`.

Với mỗi symbol `status == "ok"`:
1. `last_day` = ngày (UTC) của nến H1 cuối cùng trong dữ liệu.
2. Duyệt mọi ngày `D` từ `last_day - PERIOD_DAYS` đến `last_day`:
   `hour = CUTOFF_HOURS_UTC[D.toordinal() % 3]`, `cutoff = D lúc hour:00 UTC`.
3. Giữ cutoff nếu **tất cả** đúng (nếu không, đếm theo lý do bỏ):
   - `market_closed`: không có nến H1 nào có `time` trong `[cutoff - 4h, cutoff)`;
   - `insufficient_history`: `windows_at` cho prefix thiếu số nến so với
     `WINDOW_BARS` ở bất kỳ TF nào;
   - `insufficient_tail`: tail H1 < 48 nến.
4. Ghi `CUTOFFS_PATH`: danh sách sắp xếp theo (symbol, cutoff), mỗi phần tử
   `{"symbol", "broker_symbol", "cutoff"}` (ISO, có `+00:00`); kèm khối
   `summary`: tổng số, theo symbol, theo giờ (4/12/20), theo tháng, và số bị bỏ
   theo từng lý do.

### 3.6 Lệnh `verify`

Đọc `CUTOFFS_PATH` + dữ liệu, với **mọi** cutoff gọi `windows_at` và kiểm:
- mọi nến prefix có thời điểm đóng ≤ cutoff (tính lại bằng
  `closed_candles_at_cutoff` cho chắc, so số lượng);
- mọi nến tail có `time ≥ cutoff`; tail H1 = 48, tail M15 > 0;
- prefix đủ `WINDOW_BARS`;
- hash file dữ liệu khớp manifest.

In `verify: N cutoffs, 0 problems` khi đạt (exit 0); có lỗi → liệt kê tối đa 20
lỗi đầu, `exit 1`.

### 3.7 Test `tests/test_smc_demote_corpus.py`

Dùng nến **tổng hợp** (không cần MT5), tối thiểu 3 test:
1. `windows_at` không trả nến prefix nào đóng sau cutoff; nến H1 mở đúng tại
   cutoff nằm trong tail, không nằm trong prefix.
2. Thêm nến tương lai vào dữ liệu không làm đổi prefix tại cùng cutoff.
3. `windows_at` với cutoff naive → `ValueError`.

## 4. Lệnh nghiệm thu (chạy đủ, dán output thật vào report)

```powershell
python -X utf8 scripts/smc_demote_corpus.py fetch
python -X utf8 scripts/smc_demote_corpus.py plan
python -X utf8 scripts/smc_demote_corpus.py verify
python -X utf8 -m pytest tests/test_smc_demote_corpus.py -q
git status --short     # data/ KHÔNG được xuất hiện
```

**Đạt khi:** `verify` 0 problems; test pass;
`git status` không có file trong `reports/scanner/smc_demote/data/`; tổng
cutoff khoảng 1.500–2.300 (nếu ngoài khoảng này: không sửa tham số, ghi rõ lý
do trong report).

## 5. Không được làm

- Không sửa bất kỳ file nào trong `core/`, `services/`, `controllers/`, `ui/`,
  `config/`, `scripts/smc_real_snapshots.py`, `reports/scanner/smc_real_snapshots/`.
- Không gửi lệnh giao dịch, không gọi hàm order nào của MT5.
- Không chạy Scanner/`derive_live_analysis` (đó là SD-C2).
- Không đổi các hằng số ở 3.1 để "cho đủ số"; thiếu thì báo cáo.
- Không bắt đầu SD-C2.

## 6. Commit và báo cáo

- Commit thẳng lên `main`, message dạng
  `feat(research): [SD-C1] lấy lịch sử MT5 và lập cutoff cho corpus SMC demote`.
  Commit gồm: script, test, `.gitignore`, `corpus_manifest.json`, `cutoffs.json`.
  **Không** commit `data/`.
- Sau commit code, viết `docs/plans/smc-demote-tasks/SD-C1-report.md` theo mẫu §7
  của plan (ghi hash commit code) rồi commit riêng file report:
  `docs(smc): [SD-C1] báo cáo`. Report gồm thêm:
  - bảng symbol: status, số nến D1/H4/H1/M15, số cutoff;
  - danh sách symbol bị loại và lý do;
  - số cutoff bị bỏ theo từng lý do;
  - thời gian chạy `fetch` và dung lượng thư mục `data/`.
- Sau đó **dừng**, chờ TL review.

## Rework

_(TL ghi yêu cầu sửa ở đây nếu có.)_
