# BÁO CÁO ĐIỀU TRA: CHỨC NĂNG NHẬT KÝ PHÂN TÍCH (JOURNAL)

## Tổng quan kiến trúc

```
ui/screens/journal_screen.py        (2107 dòng) — Màn hình danh sách + Performance tab
ui/screens/journal_detail_screen.py  (935 dòng) — Màn hình chi tiết 1 bản ghi
controllers/journal_controller.py    (103 dòng) — Controller mỏng
services/journal_service.py          (581 dòng) — Persistence + Business Logic
services/journal_models.py           ( 94 dòng) — Data classes
services/journal_converters.py       (534 dòng) — Converter functions + Analytics
core/journal_feedback_engine.py      (146 dòng) — Phản hồi từ journal cho Scanner
data/migrations/                     (5 file SQL)
```

---

## 1. TRÙNG LẶP CODE

### 1a. `format_time` và `format_short_time` giống hệt nhau
**File:** [journal_screen.py:2049-2066](../ui/screens/journal_screen.py#L2049-L2066)

Cả 2 hàm có code y hệt — copy-paste rõ ràng:
```python
def format_time(value: str) -> str:
    ...
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    return parsed.strftime("%d/%m/%Y %H:%M")
```
Xóa `format_short_time`, chỉ giữ lại `format_time`.

### 1b. Logic xác định win/loss/breakeven từ `result_amount` bị lặp 2 nơi
**File:** [journal_service.py:390](../services/journal_service.py#L390) và [journal_converters.py:216](../services/journal_converters.py#L216)

```python
result = "win" if amount and amount > 0 else "loss" if amount and amount < 0 else "breakeven"
```
Cùng một dòng code xuất hiện ở cả `_mt5_trade_update_payload` và `journal_entry_from_mt5_trade`. Nên extract thành hàm `_result_label(amount)` trong `journal_converters.py`.

### 1c. Tính midpoint của entry zone bị lặp
**File:** [journal_converters.py:43-51](../services/journal_converters.py#L43-L51) và [journal_detail_screen.py:661](../ui/screens/journal_detail_screen.py#L661)

Converters có `_parse_entry_from_zone()` tính `(lo+hi)/2`. Detail screen tự tính lại `float(entry_zone_list[0] + entry_zone_list[1]) / 2`. Nên export `_parse_entry_from_zone` và dùng lại.

### 1d. `_safe_float` chỉ là wrapper không cần thiết
**File:** [journal_converters.py:17-19](../services/journal_converters.py#L17-L19)

```python
def _safe_float(value: object) -> float | None:
    return optional_float(value)
```
Không thêm giá trị gì so với `optional_float` từ `core.safe_types`. Nên dùng trực tiếp `optional_float` ở mọi nơi và xóa `_safe_float`.

### 1e. Logic tính performance metrics (win_rate, expectancy, profit_factor) bị lặp 3 nơi
- [journal_converters.py:412-455](../services/journal_converters.py#L412-L455) — `build_performance_summary`
- [journal_screen.py:1020-1061](../ui/screens/journal_screen.py#L1020-L1061) — `_update_filtered_stats_bar`
- [journal_screen.py:1507-1633](../ui/screens/journal_screen.py#L1507-L1633) — `_refresh_performance`

Mỗi nơi tự tính win_rate, expectancy, profit_factor từ danh sách entries/closed trades. Nếu công thức thay đổi phải sửa 3 nơi. Nên để UI chỉ hiển thị kết quả từ `build_performance_summary`, không tự tính lại.

### 1f. `tags_from_json` thực chất chỉ là alias của `normalize_tag_list`
**File:** [journal_converters.py:354-356](../services/journal_converters.py#L354-L356)

```python
def tags_from_json(value: object) -> list[str]:
    return normalize_tag_list(value)
```
Tên hàm gây hiểu nhầm (nghĩ rằng nó chỉ parse JSON), nhưng thực tế nó xử lý mọi định dạng giống `normalize_tag_list`. Có thể xóa và dùng thẳng `normalize_tag_list`.

### 1g. `journal_service.py` re-export chồng chéo
**File:** [journal_service.py:32-66](../services/journal_service.py#L32-L66)

Vừa có `__all__` list dài (lines 35-57), vừa có `from services.journal_converters import ...` (lines 60-66). Các UI import từ `services.journal_service` thay vì từ `services.journal_converters` — tạo coupling không cần thiết. Ví dụ trong `journal_detail_screen.py:832`:
```python
from services.journal_service import tags_from_json
```
Đáng lẽ nên import trực tiếp từ `services.journal_converters`.

---

## 2. THIẾT KẾ KHÔNG HỢP LÝ

### 2a. `JournalController` là lớp trung gian không cần thiết
**File:** [controllers/journal_controller.py](../controllers/journal_controller.py) (103 dòng)

Hầu hết method chỉ delegate thẳng sang `JournalService`:
- `list_entries` → `self.journal_service.list_entries`
- `get_entry` → `self.journal_service.get_entry`
- `symbols` → `self.journal_service.symbols`
- `update_note` → `self.journal_service.update_note`
- v.v...

Chỉ có `sync_mt5_history` và `export_entry_json` là có logic riêng. Những logic này có thể chuyển vào `JournalService`. Việc duy trì controller làm tăng số file phải bảo trì mà không thêm giá trị kiến trúc.

**Đề xuất:** Hợp nhất controller vào service, hoặc chuyển `export_entry_json` vào service và giữ controller chỉ cho orchestration MT5 sync.

### 2b. `journal_converters.py` import thừa
**File:** [journal_converters.py:12](../services/journal_converters.py#L12)

```python
from config.paths import PROJECT_ROOT, journal_db_path
```
Cả `PROJECT_ROOT` và `journal_db_path` đều không được dùng trong file này.

### 2c. Hằng số SQLite nằm trong models
**File:** [journal_models.py:11-12](../services/journal_models.py#L11-L12)

```python
SQLITE_TIMEOUT_SECONDS = 15
SQLITE_BUSY_TIMEOUT_MS = SQLITE_TIMEOUT_SECONDS * 1000
```
Đây là hằng số database connection, không phải data model. Nên chuyển vào `journal_service.py`.

### 2d. `_UPDATE_WHITELIST` hard-code danh sách field
**File:** [journal_service.py:229-238](../services/journal_service.py#L229-L238)

Mỗi khi thêm field mới vào `JournalEntry`, phải cập nhật thủ công whitelist này. Có thể tự động sinh từ `JournalEntry.__dataclass_fields__` (trừ `id`, `timestamp_utc`, `saved_at_utc`).

### 2e. `_safe_execute_migration` fragile với regex
**File:** [journal_service.py:114-118](../services/journal_service.py#L114-L118)

Regex `r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)"` không handle được column constraint (VD: `ADD COLUMN x TEXT DEFAULT 'abc'`). Nếu migration có ALTER TABLE trên nhiều bảng khác nhau, `PRAGMA table_info` chỉ được fetch 1 lần cho bảng đầu tiên → sai cho bảng thứ hai.

### 2f. `_apply_filters` gọi `_refresh_performance` mỗi lần filter thay đổi
**File:** [journal_screen.py:1445-1470](../ui/screens/journal_screen.py#L1445-L1470)

Mỗi lần user đổi filter (kể cả gõ từng ký tự trong ô tìm kiếm), `_refresh_performance()` được gọi → query `list_closed_trades_for_account_guard(limit=1000)` tốn kém. Performance tab nên tự refresh khi user chuyển sang tab đó, không phải mỗi lần filter ở tab Nhật ký thay đổi.

### 2g. `JournalEntry` có 2 field regime gây nhầm lẫn
- `market_regime` — từ phân tích AI (migration 001)
- `regime` — từ Phase 17 execution (migration 003)

Trong [journal_detail_screen.py:628](../ui/screens/journal_detail_screen.py#L628), `_analysis_html_parts` dùng `entry.market_regime`, nhưng `_load_lifecycle_form` không dùng field nào trong 2 field này cho hiển thị. Các nơi khác (filter, group performance) dùng `regime` (Phase 17). Rất dễ nhầm field nào đang được dùng.

### 2h. `_analysis_html_parts` quá dài (~160 dòng)
**File:** [journal_detail_screen.py:596-755](../ui/screens/journal_detail_screen.py#L596-L755)

Method này vừa render HTML, vừa tính R:R bar, vừa parse JSON, vừa mapping text. Vi phạm Single Responsibility. Nên tách thành các helper riêng: `_render_decision_html`, `_render_plan_html`, `_render_rr_bar`.

### 2i. `NotePopup` có bug tiềm ẩn với `WA_DeleteOnClose`
**File:** [journal_screen.py:491-553](../ui/screens/journal_screen.py#L491-L553)

`NotePopup` dùng `WA_DeleteOnClose` → khi user click ra ngoài, popup tự xóa. Nhưng `NotePopup._instance` vẫn trỏ đến object đã bị hủy. Lần sau gọi `show_at`, `cls._instance.close()` sẽ crash hoặc no-op trên object rác.

Cần ghi đè `closeEvent` để set `_instance = None`.

### 2j. `list_closed_trades_for_account_guard` có tham số `limit` nhưng khi lọc theo symbol thì không giới hạn thực sự
**File:** [journal_service.py:527-533](../services/journal_service.py#L527-L533)

Khi `symbol` được truyền, LIMIT vẫn được áp dụng với giá trị `limit` (mặc định 500). Nhưng trong `closed_trades_by_symbol` của controller, `limit=10000` được truyền. Cách dùng không nhất quán — khi cần toàn bộ lệnh của một symbol, nên dùng `LIMIT -1` (không giới hạn) hoặc bỏ LIMIT hẳn.

### 2k. `MODE_TEXT` được khai báo nhưng không dùng
**File:** [journal_screen.py:368](../ui/screens/journal_screen.py#L368)

```python
MODE_TEXT: dict[str, str] = {}
```
Dictionary rỗng, không được populate ở đâu, không được dùng ở đâu.

---

## 3. ĐỀ XUẤT CẢI THIỆN (theo thứ tự ưu tiên)

| Ưu tiên | Vấn đề | Đề xuất |
|---------|--------|---------|
| **Cao** | 1e — Performance metrics tính 3 nơi | Chỉ để `build_performance_summary` tính; UI chỉ hiển thị |
| **Cao** | 2i — Bug NotePopup dangling pointer | Thêm `closeEvent` set `_instance = None` |
| **Cao** | 2g — 2 field regime gây nhầm lẫn | Đổi tên `regime` → `execution_regime` hoặc gộp làm một |
| **Cao** | 1a — `format_time` và `format_short_time` giống hệt | Xóa `format_short_time` |
| **TB** | 2d — Whitelist hard-code | Tự động sinh từ `JournalEntry.__dataclass_fields__` |
| **TB** | 2f — Performance refresh quá nhiều | Chỉ refresh performance khi user vào tab Performance |
| **TB** | 1b, 1d — Hàm helper trùng lặp | Extract `_result_label()`, xóa `_safe_float` wrapper |
| **TB** | 2a — Controller mỏng không cần thiết | Hợp nhất controller → service hoặc xóa controller |
| **TB** | 2e — Regex migration fragile | Dùng SQL parser library hoặc ít nhất handle column constraints |
| **Thấp** | 2b — Import thừa | Xóa import không dùng trong `journal_converters.py` |
| **Thấp** | 2c — Hằng số sai chỗ | Chuyển SQLite constants vào `journal_service.py` |
| **Thấp** | 1g — Re-export chồng chéo | UI import trực tiếp từ `journal_converters` |
| **Thấp** | 2h — Method quá dài | Tách `_analysis_html_parts` thành các helper nhỏ |

---

## 4. TÓM TẮT

Code Journal về tổng thể **có cấu trúc tốt** — tách biệt rõ models / converters / service / UI. Migration có cơ chế an toàn khi chạy lại. Tuy nhiên, sau nhiều phase phát triển (Phase 7 Account Guard, Phase 17 Execution, MT5 Sync, Advanced Filters, Quick Filters), code bắt đầu có dấu hiệu **trùng lặp và leaky abstraction**:

- **3 nơi tự tính performance metrics** là vấn đề lớn nhất về bảo trì
- **2 field `market_regime` / `regime`** dễ gây bug khi không biết field nào đang dùng
- **Controller gần như rỗng** — cân nhắc giữ hay bỏ
- **1 bug tiềm ẩn** với NotePopup singleton pattern
