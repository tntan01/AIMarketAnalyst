# EE-C1 — Corpus 15 tháng có spread

> **Giao bởi:** Tech Lead · **Ngày:** 07/10/2026 · **Người làm:** Coder
> **Kế hoạch tổng:** [`../edge-eval-plan.md`](../edge-eval-plan.md) (đọc §2,
> §3 E1/E2/E3/E4/E9). Quy tắc chung cho Coder: giống
> [`../smc-demote-task-plan.md`](../smc-demote-task-plan.md) §0.2 (một task =
> một commit, dán output thật, không gửi lệnh MT5…). File này là nguồn chính;
> mâu thuẫn → **dừng và hỏi**.

## 1. Mục tiêu

Lấy lịch sử D1/H4/H1/M15 **kèm spread từng nến** của 31 symbol từ MT5 **một
lần**, lưu đóng băng; lập danh sách cutoff 15 tháng (3 cutoff/ngày); kiểm
không rò dữ liệu tương lai. Không chạy Scanner (đó là EE-C2).

## 2. Chuẩn bị

1. Trên `main`, `git status` sạch. Terminal MT5 mở và đăng nhập.
2. Đọc (không sửa):
   - `scripts/smc_demote_corpus.py` — **mẫu chính**: cấu trúc `fetch/plan/verify`,
     `_fetch_symbol`, `_atomic_write_gzip`, `load_symbol_data`, `windows_at`,
     `_plan_symbol_cutoffs`, `_run_verify`. Task này làm bản tương tự, khác ở
     mục 3.
   - `services/mt5_service.py`: `load_ohlcv_range` (dòng ~757–805: thời gian
     nến = `datetime.fromtimestamp(rates["time"], tz=timezone.utc)`).
   - `core/market_models.py`: `closed_candles_at_cutoff`, `candle_close_at`.

## 3. Việc cần làm

### 3.1 File mới `scripts/edge_eval_corpus.py`

Đầu file như `smc_demote_corpus.py`. **Import, không copy**:

```python
from smc_demote_corpus import WINDOW_BARS, _atomic_write_gzip, _atomic_write_text, _file_sha256, _safe_name
import smc_real_snapshots as _real_snapshots   # _candle_payload, _candle_from_payload, _live_min_rr
```

Hằng số:

```python
OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "edge_eval"
DATA_DIR = OUTPUT_DIR / "data"                  # KHÔNG commit
MANIFEST_PATH = OUTPUT_DIR / "corpus_manifest.json"
CUTOFFS_PATH = OUTPUT_DIR / "cutoffs.json"
TIMEFRAMES = ("D1", "H4", "H1", "M15")
FETCH_DAYS = {"D1": 1300, "H4": 650, "H1": 540, "M15": 480}   # lùi từ fetched_at
TAIL_BARS = {"H1": 96, "M15": 384}                             # E4: 4 ngày giao dịch
SPREAD_TIMEFRAMES = ("H1", "M15")
CUTOFF_HOURS_UTC = (4, 12, 20)                                 # E2: cả 3 giờ, mọi ngày
PERIOD_START = date(2025, 7, 1)                                # E1
```

### 3.2 `fetch`

Giống `smc_demote_corpus.py fetch` (connect → `BLOCKED` exit 2 nếu lỗi;
`fetched_at = datetime.now(timezone.utc)` chỉ ở lệnh này; `available_symbols`;
`resolve_symbol`; `symbol_data_quality` lấy `tick_size`/`tick_size_source`;
`load_ohlcv_range` từng TF; lọc `closed_candles_at_cutoff(..., fetched_at)`),
**thêm**:

1. `import MetaTrader5 as mt5`; `point = mt5.symbol_info(broker_symbol).point`
   (`None`/≤ 0 → symbol lỗi `point_unavailable`).
2. Với mỗi TF trong `SPREAD_TIMEFRAMES`: gọi thêm
   `rates = mt5.copy_rates_range(broker_symbol, tf_id, start, fetched_at)` với
   **cùng** `start`/`end` như `load_ohlcv_range` (`tf_id`:
   `mt5.TIMEFRAME_H1`/`mt5.TIMEFRAME_M15`), dựng
   `{int(r["time"]): int(r["spread"]) for r in rates}`, rồi gán spread cho
   **từng** nến đã lọc theo `int(candle.time.timestamp())` bằng hàm
   `attach_spreads(candles, spread_by_ts) -> list[int]`. Nến nào không có
   spread → raise `ValueError("spread_missing:<tf>:<iso time>")` → symbol lỗi
   (không điền số).
3. Payload thêm `"point": point` và `"spread": {"H1": [...], "M15": [...]}`
   (cùng độ dài, cùng thứ tự với `candles[tf]`).
4. Manifest mỗi symbol thêm `point`, `spread_points_median` cho H1 và M15
   (`statistics.median`). Manifest gốc thêm `period_start`, `tail_bars`,
   `cutoff_hours_utc`.

### 3.3 `load_symbol_data` và `windows_at` (EE-C2 sẽ import)

```python
def load_symbol_data(path: Path) -> dict: ...
    # như bản SD-C1, giữ thêm data["spread"] (list[int]) và data["point"]

def windows_at(data: dict, cutoff: datetime) -> tuple[dict, dict, dict]:
    """Trả (prefix, tail, tail_spread).
    prefix[tf]: closed_candles_at_cutoff(...), giữ WINDOW_BARS[tf] nến cuối (4 TF).
    tail[tf] (H1, M15): nến KHÔNG thuộc tập closed-at-cutoff đầy đủ, giữ TAIL_BARS[tf] nến đầu
                        (cách làm y như windows_at của smc_demote_corpus).
    tail_spread[tf]: spread (point) của đúng các nến trong tail[tf], cùng thứ tự.
    """
```

Cutoff naive → `ValueError`. Không gọi `now()`.

### 3.4 `plan`

Chỉ đọc file. Với mỗi symbol `ok`: duyệt mọi ngày `D` từ `PERIOD_START` đến
ngày của nến H1 cuối; với **mỗi** giờ trong `CUTOFF_HOURS_UTC`:
`cutoff = D lúc giờ:00 UTC`. Giữ nếu đủ cả ba (đếm lý do bỏ như SD-C1):

- `market_closed`: không có nến H1 trong `[cutoff − 4h, cutoff)`;
- `insufficient_history`: prefix thiếu `WINDOW_BARS` ở bất kỳ TF nào;
- `insufficient_tail`: tail H1 < 96 **hoặc** tail M15 < 384.

Ghi `CUTOFFS_PATH` như SD-C1 (`cutoffs` sắp theo (symbol, cutoff) +
`summary`: total, by_symbol, by_hour, by_month, rejected).

Gợi ý tốc độ (không bắt buộc): `plan` gọi `windows_at` ~44.000 lần; nếu quá
chậm (> 15 phút), được tối ưu **bên trong** `windows_at` (vd. `bisect` theo
thời gian đóng) miễn kết quả giống hệt và test mục 3.6 vẫn pass. Không đổi
logic lọc.

### 3.5 `verify`

Như SD-C1, với mọi cutoff: prefix đủ `WINDOW_BARS` và bằng
`closed_candles_at_cutoff(...)[-WINDOW_BARS:]`; mọi nến prefix đóng ≤ cutoff;
mọi nến tail có `time >= cutoff`; tail H1 = 96, M15 = 384;
`len(tail_spread[tf]) == len(tail[tf])` và mọi spread là int ≥ 0; hash file
khớp manifest. In `verify: N cutoffs, 0 problems` (exit 0) hoặc tối đa 20 lỗi
(exit 1).

### 3.6 `.gitignore`

Thêm đúng một dòng: `reports/scanner/edge_eval/data/`.

### 3.7 Test `tests/test_edge_eval_corpus.py`

Nến tổng hợp, không MT5, tối thiểu:

1. `windows_at`: prefix không có nến đóng sau cutoff; nến H1 mở đúng tại
   cutoff nằm trong tail; `tail_spread` đúng nến (dùng spread = chỉ số nến để
   kiểm).
2. Thêm nến tương lai không đổi prefix tại cùng cutoff.
3. Cutoff naive → `ValueError`.
4. `attach_spreads`: thiếu spread một nến → `ValueError` chứa `spread_missing`;
   đủ → list đúng thứ tự.

## 4. Lệnh nghiệm thu (dán output thật vào report)

```powershell
python -X utf8 scripts/edge_eval_corpus.py fetch
python -X utf8 scripts/edge_eval_corpus.py plan
python -X utf8 scripts/edge_eval_corpus.py verify
python -X utf8 -m pytest tests/test_edge_eval_corpus.py tests/test_smc_demote_corpus.py -q
git status --short     # edge_eval/data/ KHÔNG được xuất hiện
```

**Đạt khi:** `verify` 0 problems; test pass; `data/` không bị git thấy; tổng
cutoff khoảng **27.000–33.000** (ngoài khoảng: không sửa tham số, ghi lý do).

## 5. Không được làm

- Không sửa `core/`, `services/`, `controllers/`, `ui/`, `config/`, mọi
  `scripts/smc_*`, `reports/scanner/smc_demote/`, `reports/scanner/smc_real_snapshots/`.
- Không gọi hàm order nào của MT5; chỉ `copy_rates_range`, `symbol_info`.
- Không chạy Scanner/`derive_live_analysis`. Không đổi hằng số 3.1 để đủ số.
- Không bắt đầu EE-C2.

## 6. Commit và báo cáo

- Commit `main`: `feat(research): [EE-C1] corpus 15 tháng có spread cho đo edge`.
  Gồm script, test, `.gitignore`, `corpus_manifest.json`, `cutoffs.json`.
  **Không** commit `data/`.
- Viết `docs/plans/edge-eval-tasks/EE-C1-report.md` (mẫu §7 của
  `smc-demote-task-plan.md`, ghi hash commit code), commit riêng
  `docs(edge): [EE-C1] báo cáo`. Kèm: bảng symbol (status, số nến 4 TF, spread
  trung vị H1/M15, số cutoff); symbol bị loại + lý do; cutoff bị bỏ theo lý
  do; thời gian `fetch`/`plan`/`verify`; dung lượng `data/`.
- Sau đó **dừng**, chờ TL review.

## Rework

_(TL ghi yêu cầu sửa ở đây nếu có.)_
