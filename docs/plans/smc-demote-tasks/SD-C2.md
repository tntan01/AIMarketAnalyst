# SD-C2 — Replay corpus và gắn nhãn outcome

> **Giao bởi:** Tech Lead · **Ngày:** 07/10/2026 · **Người làm:** Coder
> **Kế hoạch tổng:** [`../smc-demote-task-plan.md`](../smc-demote-task-plan.md)
> (chỉ cần đọc §0.2 "Quy tắc bắt buộc" và §2 Q3/Q8). File này là nguồn chính
> cho task; nếu thấy mâu thuẫn với plan → **dừng và hỏi**, không tự chọn.

## 1. Mục tiêu

Chạy lại Scanner (đường live thật) tại **từng cutoff** trong
`reports/scanner/smc_demote/cutoffs.json` (2010 cutoff, do SD-C1 tạo), ghi điểm
từng side, rồi gắn nhãn kết quả tương lai cho từng side. Task này **không**
phân tích thống kê (đó là SD-C3).

## 2. Chuẩn bị

1. Làm trực tiếp trên `main`. Kiểm `git status` sạch trước khi bắt đầu.
2. Dữ liệu SD-C1 phải có sẵn: chạy
   `python -X utf8 scripts/smc_demote_corpus.py verify` → phải in
   `verify: 2010 cutoffs, 0 problems`. Không đạt → **dừng, báo TL**. **Không**
   chạy lại `fetch` (sẽ đổi dữ liệu đóng băng).
3. Đọc trước (không sửa):
   - `scripts/smc_demote_corpus.py`: `DATA_DIR`, `MANIFEST_PATH`,
     `CUTOFFS_PATH`, `TAIL_BARS`, `load_symbol_data`, `windows_at`.
   - `scripts/smc_replay_parity.py`: `_candles`, `_live`,
     `decision_fingerprint`, `_live_side_fields`, `CORPUS_PATH`.
   - `core/scanner_live_producers.py`: `derive_live_analysis` (dòng ~282–396).
   - `core/scanner_scenario_producers.py`: `plans_from_canonical_selection`.
   - `core/smc_scoring_result.py`: class `SmcSideSelection` (field `state`,
     `quality_raw`, `quality_score`, `b`, `q`, `l`, `c`, `zone_low`,
     `zone_high`, `plan_available`, `readiness`).
   - `core/indicators.py`: `atr`.

## 3. Việc cần làm

### 3.1 File mới `scripts/smc_demote_replay.py`

Đầu file giống `scripts/smc_demote_corpus.py` (thêm `PROJECT_ROOT` và
`PROJECT_ROOT / "scripts"` vào `sys.path`). **Import**, không copy:

```python
from smc_demote_corpus import (CUTOFFS_PATH, DATA_DIR, MANIFEST_PATH, OUTPUT_DIR,
                               TAIL_BARS, load_symbol_data, windows_at)
import smc_replay_parity as _parity
from core.indicators import atr
from core.scanner_live_producers import derive_live_analysis
from core.scanner_scenario_producers import plans_from_canonical_selection
from core.smc_snapshot_cache import smc_rule_versions
```

Hằng số:

```python
ROWS_PATH = DATA_DIR / "replay_rows.jsonl"        # KHÔNG commit (data/ đã ignore)
ERRORS_PATH = DATA_DIR / "replay_errors.jsonl"    # KHÔNG commit
SUMMARY_PATH = OUTPUT_DIR / "replay_summary.json" # commit
PARITY_PATH = OUTPUT_DIR / "replay_parity_c2.json" # commit
TRIAL_PATH = OUTPUT_DIR / "replay_trial.json"     # commit
SIDES = ("buy", "sell")
FWD_HOURS = (8, 24)
ATR_PERIOD = 14
```

Ba lệnh con: `parity`, `run`, `summary` (mục 3.4–3.6).

### 3.2 Hàm lõi `live_analysis_at(data, cutoff, min_rr)` và `analyze_cutoff(data, cutoff, min_rr) -> dict`

`live_analysis_at` trả `(analysis, prefix, tail)`; `analyze_cutoff` gọi nó rồi
dựng row. Cả `parity` lẫn `run` đều đi qua hai hàm này.

1. `prefix, tail = windows_at(data, cutoff)`.
2. Gọi `derive_live_analysis` **giống hệt** `_parity._live`:
   ```python
   analysis = derive_live_analysis(
       prefix["D1"], prefix["H4"], prefix["H1"],
       symbol=data["symbol"], captured_at=cutoff, news_in_3h=False,
       m15_candles=prefix["M15"], m15_as_of=cutoff,
       tick_size=data["tick_size"], tick_size_source=data["tick_size_source"],
       min_rr=min_rr,
   )
   ```
   (`min_rr` lấy từ `corpus_manifest.json`, khóa `min_rr`.) Bước 1–2 là
   `live_analysis_at`; các bước sau thuộc `analyze_cutoff`.
3. `ref_close = prefix["H1"][-1].close`;
   `atr_h1 = atr([c.high ...], [c.low ...], [c.close ...], ATR_PERIOD)[-1]`
   trên `prefix["H1"]`. `atr_h1` là `None` hoặc ≤ 0 → raise
   `ValueError("atr_h1_unavailable")` (fail-closed, **không** thay số khác).
4. `plans = plans_from_canonical_selection(analysis["canonical_smc"])`.
5. Trả về dict (đây chính là một dòng của `replay_rows.jsonl`):
   ```text
   symbol, broker_symbol, cutoff (ISO +00:00), regime (analysis["regime"]),
   ref_close, atr_h1,
   sides: { "buy": {...}, "sell": {...} }
   ```
   Mỗi side:
   ```text
   trend, momentum, location, smc_raw   ← analysis["raws"].per_side[side].trend/.momentum/.location/.smc
   smc_state, quality_raw, quality_score, b, q, l, c, zone_low, zone_high, plan_available
                                         ← analysis["canonical_smc"].side(side).selection (giữ None nếu None)
   readiness_status, smc_readiness_state ← (selection.readiness or {}).get("status") / .get("smc_state")
   entry, stop_loss, take_profit         ← plans[side] (None nếu plans[side] là None)
   labels                                ← mục 3.3
   ```
   `selection` là `None` → mọi field SMC của side đó là `None`.
   (Đường đã kiểm: một snapshot EUR/USD mất ~1 giây trên máy dev.)

### 3.3 Hàm gắn nhãn `label_side(side, plan, ref_close, atr_h1, cutoff, tail) -> dict`

**Chỉ** nhận `tail` (nến sau cutoff) + `ref_close`/`atr_h1`; không nhận
`prefix`. Đầu hàm: nếu có nến nào trong `tail["H1"]` hoặc `tail["M15"]` có
`time < cutoff` → `raise ValueError("tail_before_cutoff")`.

`d = +1` nếu `side == "buy"`, `-1` nếu `"sell"`.

**(a) Outcome phụ — mọi side (kể cả không có plan):**

- `fwd_8h_atr  = (tail["H1"][7].close  - ref_close) * d / atr_h1`
- `fwd_24h_atr = (tail["H1"][23].close - ref_close) * d / atr_h1`
- Tail H1 ngắn hơn số cần → field đó `None` (không bịa).

**(b) Outcome chính — chỉ side có plan** (`plan` khác `None`); không có plan →
`tp_sl = None`, các field (b) khác `None`.

Plan `entry`/`stop_loss`/`take_profit` = E/S/T. Kiểm hình học trước: BUY cần
`S < E < T`, SELL cần `T < E < S`; sai → `tp_sl = "plan_invalid"`, dừng.
`risk = abs(E - S)`.

Duyệt `tail["M15"]` theo thứ tự thời gian (tối đa 192 nến):

1. **Khớp lệnh (entry là lệnh limit tại mép zone):** nến đầu tiên `i` có
   BUY `low <= E` / SELL `high >= E`. Không có → `tp_sl = "not_filled"`.
   Giá khớp luôn coi là `E` (kể cả khi nến mở đã vượt E — ghi giới hạn này
   trong report).
2. Từ nến `i` trở đi, với mỗi nến `j`:
   - `sl_hit` = BUY `low <= S` / SELL `high >= S`;
   - `tp_hit` = BUY `high >= T` / SELL `low <= T`;
   - **Tại nến khớp `j == i`: bỏ qua `tp_hit`** (không biết TP in trước hay
     sau lúc khớp), chỉ xét `sl_hit`;
   - `sl_hit` (kể cả cùng nến với `tp_hit`) → `"sl_first"` (STOP_FIRST);
     chỉ `tp_hit` → `"tp_first"`; dừng ở nến đầu tiên có kết quả.
3. Hết tail chưa chạm → `"unresolved"`.

Ghi thêm: `fill_bar` (= i hoặc `None`), `resolve_bar` (j hoặc `None`),
`mfe_r`, `mae_r` — tính trên các nến từ `i` đến `resolve_bar` (bao gồm), hoặc
đến hết tail nếu `unresolved`:
BUY `mfe_r = (max(high) - E)/risk`, `mae_r = (E - min(low))/risk`;
SELL `mfe_r = (E - min(low))/risk`, `mae_r = (max(high) - E)/risk`.
`not_filled`/`plan_invalid` → `mfe_r = mae_r = None`.

Không tính spread/chi phí (Q9).

### 3.4 Lệnh `parity`

Kiểm `analyze_cutoff` gọi đường live đúng như công cụ parity đã có. **Không**
so với file `reports/scanner/smc_real_snapshots/replay_parity.json` (file đó
tạo 17/09, trước khi producer SMC đổi ngày 04/10 — đã lỗi thời).

Với **mỗi** row trong `_parity.CORPUS_PATH` (58 row), `cutoff =
datetime.fromisoformat(row["as_of"])`, `fp = lambda a:
_parity._live_side_fields(_parity.decision_fingerprint(a["smc_evaluation"]))`:

1. **Kỳ vọng** (công cụ cũ, code hiện tại):
   `prefix = {tf: _parity._candles(row, tf, bars=500, tail=False) for tf in ("D1","H4","H1","M15")}`;
   `expected = fp(_parity._live(prefix, row))`.
2. **Đường SD-C2:** dựng
   ```python
   data = {"symbol": row["symbol"], "broker_symbol": row.get("broker_symbol"),
           "tick_size": row["tick_size"], "tick_size_source": row["tick_size_source"],
           "candles": {tf: _parity._candles(row, tf, bars=500, tail=True)
                       for tf in ("D1", "H4", "H1", "M15")}}
   ```
   (cửa sổ 500/100 nến của row + future tail nối sau), gọi
   `analysis, _, _ = live_analysis_at(data, cutoff, row.get("min_rr"))`,
   `got = fp(analysis)`.
3. **So 1:** `got == expected` (dict 2 side × 7 field).
4. **So 2 (kiểm field row đọc từ `canonical_smc`):** `row_c2 =
   analyze_cutoff(data, cutoff, row.get("min_rr"))`; với mỗi side phải có
   `row_c2 smc_state == got state`, `quality_raw == got quality_raw`,
   `plan_available == got plan_available`, `readiness_status == got
   readiness_status`, `smc_readiness_state == got smc_state`.

Một row là mismatch nếu So 1 hoặc So 2 sai; ghi rõ field nào, giá trị hai bên.

Ghi `PARITY_PATH`: `{"rows": 58, "matched": n, "mismatches": [...tối đa toàn bộ...], "rule_versions": smc_rule_versions()}`.
In `parity: 58 rows, N mismatches`. 0 mismatch → exit 0, ngược lại exit 1.

**Kiểm thêm (chỉ báo cáo, không làm fail):** với mỗi row cũ mà
`load_symbol_data` của cùng symbol trong `DATA_DIR` cho `windows_at` đủ
500/500/500/100 nến tại `row["as_of"]`: so `time/open/high/low/close` của
prefix đóng băng với prefix của row (từng TF). Ghi vào `PARITY_PATH` khóa
`frozen_vs_corpus`: số row so được, số row khớp hoàn toàn, danh sách lệch
(symbol, as_of, tf, số nến lệch).

### 3.5 Lệnh `run`

Tùy chọn: `--symbols EUR/USD,GBP/USD` · `--from 2026-08-01` · `--to 2026-08-31`
(theo ngày UTC của cutoff, bao gồm hai đầu) · `--workers N` (mặc định 1) ·
`--limit N` · `--redo` · `--trial`.

1. Đọc `CUTOFFS_PATH`, lọc theo tùy chọn.
2. **Chạy tiếp:** đọc `ROWS_PATH` (nếu có), lấy tập khóa `symbol@cutoff` đã
   có → bỏ qua các cutoff đó. Dòng cuối file hỏng JSON (do bị ngắt giữa chừng)
   → bỏ qua dòng đó và in cảnh báo; dòng hỏng **không phải dòng cuối** → dừng,
   exit 1. Lỗi cũ trong `ERRORS_PATH` **không** bị bỏ qua (chạy lại).
3. `--redo`: trước khi chạy, ghi lại `ROWS_PATH` (atomic: file tạm +
   `os.replace`) bỏ các dòng khớp bộ lọc, để chúng được tính lại.
4. Song song bằng `concurrent.futures.ProcessPoolExecutor(max_workers=N)`.
   Hàm worker ở cấp module (Windows dùng spawn), nhận `(symbol, cutoff_iso,
   min_rr)`, giữ cache `load_symbol_data` theo symbol trong biến global của
   process. Submit theo thứ tự (symbol, cutoff). Main guard
   `if __name__ == "__main__":` bắt buộc.
5. Worker bắt **mọi** exception của một cutoff, trả
   `{"symbol","cutoff","error_type","message"}`; main ghi vào `ERRORS_PATH`,
   **không** dừng lô. Thành công → main append một dòng JSON vào `ROWS_PATH`
   rồi `flush()` ngay. Worker trả thêm `elapsed_s` và `peak_rss_mb` (hàm ở mục
   3.7).
6. In tiến độ mỗi 50 snapshot: số xong / tổng, lỗi, tốc độ, ETA.
7. `--trial`: ghi thêm `TRIAL_PATH`: số snapshot, `elapsed` tổng,
   giây/snapshot (trung bình, p95), `peak_rss_mb` lớn nhất, số worker, và
   **ước tính** thời gian cả lô 2010 snapshot với 1/4/8 worker.

JSON dùng `ensure_ascii=False, sort_keys=True`; số thực ghi nguyên (không
làm tròn).

### 3.6 Lệnh `summary`

Đọc `ROWS_PATH` + `ERRORS_PATH` + `CUTOFFS_PATH`, ghi `SUMMARY_PATH`:
`cutoffs_total`, `rows`, `errors`, `error_rate`, `missing` (cutoff chưa có row
cũng chưa có lỗi), lỗi theo `error_type`, số row theo regime, theo mỗi side:
đếm `smc_state`, đếm `tp_sl` (`tp_first/sl_first/unresolved/not_filled/
plan_invalid/None`), `rule_versions` (`smc_rule_versions()`), `rows_sha256`
(sha256 bytes của `ROWS_PATH`). In bảng tóm tắt.

### 3.7 Đo RAM (không có `psutil` trên máy dev — dùng nguyên đoạn này)

```python
import ctypes
from ctypes import wintypes

class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

def _peak_rss_mb() -> float | None:
    if sys.platform != "win32":
        return None
    kernel32 = ctypes.WinDLL("kernel32"); psapi = ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    pmc = _PMC(); pmc.cb = ctypes.sizeof(_PMC)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        return None
    return round(pmc.PeakWorkingSetSize / 2**20, 1)
```

### 3.8 Test `tests/test_smc_demote_replay.py`

Nến **tổng hợp**, không MT5, không gọi `derive_live_analysis`. Tối thiểu:

1. `label_side` với `tail` có một nến `time < cutoff` → `ValueError`.
2. BUY: nến M15 sau khi khớp chạm cả SL và TP cùng nến → `"sl_first"`.
3. BUY: nến khớp (`i`) chạm TP nhưng không chạm SL, các nến sau không chạm gì
   → `"unresolved"` (TP ở nến khớp bị bỏ qua).
4. SELL: không nến nào có `high >= E` → `"not_filled"`, `mfe_r is None`.
5. SELL: khớp rồi chạm TP → `"tp_first"`, `mfe_r`/`mae_r` đúng số tính tay.
6. `fwd_8h_atr`/`fwd_24h_atr` đọc đúng `tail["H1"][7]` và `[23]`, đổi dấu
   theo side.
7. Plan sai hình học (BUY với `S >= E`) → `"plan_invalid"`.
8. Đọc `ROWS_PATH` (dùng `tmp_path`): dòng cuối hỏng bị bỏ qua; dòng giữa hỏng
   → lỗi.

## 4. Thứ tự chạy và lệnh nghiệm thu (chạy đủ, dán output thật vào report)

```powershell
python -X utf8 scripts/smc_demote_corpus.py verify
python -X utf8 -m pytest tests/test_smc_demote_replay.py tests/test_smc_demote_corpus.py -q
python -X utf8 scripts/smc_demote_replay.py parity
python -X utf8 scripts/smc_demote_replay.py run --symbols EUR/USD --from 2026-08-01 --to 2026-08-31 --workers 1 --trial
# đọc replay_trial.json, chọn N (≤ 12; máy dev 16 core) → ghi lý do chọn N vào report
python -X utf8 scripts/smc_demote_replay.py run --workers N
python -X utf8 scripts/smc_demote_replay.py run --workers N   # chạy lần 2: phải báo 0 snapshot mới (chạy tiếp đúng)
python -X utf8 scripts/smc_demote_replay.py summary
git status --short     # data/ KHÔNG được xuất hiện
```

Lô bị ngắt giữa chừng → chạy lại đúng lệnh `run`, không xóa `ROWS_PATH`.

**Đạt khi:**

- `parity`: 58 rows, **0 mismatches**. Có mismatch → **dừng, không chạy cả
  lô**, báo TL kèm `PARITY_PATH`.
- Test pass.
- `summary`: `missing = 0`; `error_rate ≤ 2%`. Trên 2% → không sửa core,
  không lọc bớt; liệt kê lỗi theo `error_type` + 3 ví dụ trong report rồi dừng.
- Lần `run` thứ hai không chạy lại snapshot nào.
- `git status` không có file trong `reports/scanner/smc_demote/data/`.

## 5. Không được làm

- Không sửa file nào trong `core/`, `services/`, `controllers/`, `ui/`,
  `config/`, `scripts/smc_real_snapshots.py`, `scripts/smc_replay_parity.py`,
  `scripts/smc_demote_corpus.py`, `reports/scanner/smc_real_snapshots/`,
  `reports/scanner/smc_demote/cutoffs.json`, `corpus_manifest.json`.
- Không chạy `smc_demote_corpus.py fetch`; không gọi MT5.
- Không tự viết lại logic lọc nến đóng hay cắt cửa sổ — dùng `windows_at`.
- Không tính điểm TechnicalScore, AUC, hit-rate… (đó là SD-C3).
- Không dùng `context_cache_root` hay cache kết quả SMC nào khác.
- Không bắt đầu SD-C3.

## 6. Commit và báo cáo

- Commit thẳng lên `main`, message
  `feat(research): [SD-C2] replay corpus và gắn nhãn outcome SMC demote`.
  Gồm: `scripts/smc_demote_replay.py`, `tests/test_smc_demote_replay.py`,
  `replay_parity_c2.json`, `replay_trial.json`, `replay_summary.json`.
  **Không** commit `data/`.
- Sau commit code, viết `docs/plans/smc-demote-tasks/SD-C2-report.md` theo mẫu
  §7 của plan (ghi hash commit code), commit riêng:
  `docs(smc): [SD-C2] báo cáo`. Report gồm thêm:
  - kết quả `parity` và khối `frozen_vs_corpus`;
  - số liệu chạy thử (giây/snapshot, RAM), N đã chọn và lý do, tổng thời gian
    cả lô;
  - bảng `summary`: rows, lỗi theo loại, regime, `smc_state` và `tp_sl` theo
    side;
  - giới hạn: giá khớp luôn là E, bỏ TP ở nến khớp, không spread.
- Sau đó **dừng**, chờ TL review.

## Rework

_(TL ghi yêu cầu sửa ở đây nếu có.)_
