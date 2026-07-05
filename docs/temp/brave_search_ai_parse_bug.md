# Brave Search & AI Parse — Kiểm tra & Bug Report

> Ngày kiểm tra: 2026-07-05
> Mục đích: Xác minh Brave Search + AI parse actual values hoạt động trong Dashboard "Tin tức & Sự kiện"

---

## 1. Cấu hình

| Mục | Giá trị |
|-----|--------|
| `brave_api_key` | `BSAOVJa-...` (đã lưu trong `settings.json` → `advanced.brave_api_key`) |
| `fred_api_key` | `300a8bf8...` (đã lưu, hoạt động) |
| AI provider | DeepSeek (deepseek-v4-pro) |

---

## 2. Brave Search API — Hoạt động

Gọi trực tiếp `_brave_search()`:

```
Query: "US Nonfarm Payrolls June 2026 actual"
→ 10 results trả về thành công
→ Tìm thấy actual: 57,000 jobs, unemployment 4.2%
```

**Kết luận:** API key hợp lệ, Brave Search trả về dữ liệu đúng.

---

## 3. BUG #1: `lookup_actuals_batch()` không bao giờ chạy — 100% event bị chặn

### Điều tra (2026-07-05)

Chạy trace từng event qua từng filter của `lookup_actuals_batch()`:

```
now (UTC) = 2026-07-05T16:07:46
from_date  = now - 7 days = 2026-06-28
to_date    = now + 7 days = 2026-07-12

Raw events from calendar_events_window: 74 events
  Past (< now):    0
  Future (>= now): 74
  Earliest event:  2026-07-06T01:00Z

Filter chain trong lookup_actuals_batch:
  Filter 1 (type != "event"):          -39
  Filter 2 (da co actual):             -0
  Filter 3 (khong co time_utc):        -0
  Filter 4 (parse time loi):           -0
  Filter 5 (future event >= now):      -74  ← TẤT CẢ BỊ CHẶN TẠI ĐÂY
  -----------------------------------------
  PASSED (se duoc Brave Search):        0
```

### Nguyên nhân gốc

**Dòng code:** [forex_factory_client.py:246](services/forex_factory_client.py#L246) — `_fetch_json_events()` gọi URL:

```
https://nfs.faireconomy.media/ff_calendar_thisweek.json
```

Forex Factory API `thisweek.json` **chỉ trả về events trong tương lai** (chưa diễn ra). Các event đã qua trong tuần hiện tại bị API loại bỏ khỏi response.

Bằng chứng:
- Raw `thisweek.json`: 74 events — **0 quá khứ**
- `lastweek.json` URL: **HTTP 404** — không tồn tại
- Disk cache (in-memory): 158 events — **0 quá khứ**
- `calendar_cache.json` file trên disk: **không tồn tại** (cache chưa từng được persist)

**Hệ quả:** `lookup_actuals_batch()` tại [news_service.py:1361](services/news_service.py#L1361) luôn gặp `ev_time >= now` → `continue` → **Brave Search không bao giờ được gọi**.

### Phạm vi ảnh hưởng

| Chức năng | Mức độ |
|-----------|--------|
| Dashboard "Tin tức & Sự kiện" — actual lookup | **Vô hiệu hóa hoàn toàn** |
| `lookup_actuals_batch()` | Không thể hoạt động nếu không có event quá khứ |
| `lookup_actual_single()` | Không ảnh hưởng (gọi thủ công từ UI) |
| `_brave_search()` | API hoạt động nhưng không có input |
| `_parse_with_ai()` (BUG #2 bên dưới) | Không được trigger do BUG #1 chặn trước |

### Phương án sửa

#### Phương án A: Persistent cache tích lũy dần (KHUYẾN NGHỊ)

**Mô tả:** Khi app chạy auto-scan định kỳ, `thisweek.json` dần chứa event đã qua. Persist cache ra file (`calendar_cache.json`) với logic merge (không overwrite), giữ event trong 7 ngày. Event quá khứ được tích lũy qua các lần chạy → `lookup_actuals_batch` có input.

**Ưu:** Không thêm dependency. Tận dụng cơ chế cache có sẵn. Đơn giản.
**Nhược:** Cần app chạy liên tục để tích lũy. Lần đầu vẫn không có event quá khứ. Cache cần cơ chế TTL.

#### Phương án B: Fetch thêm nguồn dữ liệu lịch sử

**Mô tả:** Thêm nguồn calendar có hỗ trợ date range quá khứ (Financial Modeling Prep, Trading Economics). Gọi khi `from_date < now`.

**Ưu:** Có ngay event quá khứ + actual values.
**Nhược:** Thêm dependency bên ngoài. Có thể cần API key trả phí.

#### Phương án C: Mở rộng Brave Search cho event sắp diễn ra

**Mô tả:** Bỏ giới hạn `ev_time >= now`, thay bằng `ev_time >= now - timedelta(hours=24)` để lookup cả event sắp diễn ra. Dùng Brave tìm forecast/expectation thay vì actual.

**Ưu:** Không cần thay đổi data source.
**Nhược:** Thay đổi mục đích từ "actual" → "forecast". Cần điều chỉnh prompt AI.

---

## 4. BUG #2: `_parse_with_ai()` — AI response không được parse đúng

### Mô tả

Khi test với event giả lập đã qua:

```python
past_event = {
    'type': 'event',
    'currency': 'USD',
    'title': 'ISM Manufacturing PMI',
    'time_utc': '2026-07-01T14:00:00Z',
    'forecast': '49.5',
    'previous': '48.7',
    'actual': '',
}
svc.lookup_actuals_batch([past_event])
```

### Kết quả

| Bước | Kết quả |
|------|---------|
| Brave Search | 10 kết quả, có chứa actual value |
| `_parse_with_ai()` (AI) | Trả về **toàn bộ reasoning text** thay vì chỉ con số |
| `_parse_fallback_regex()` | **Không được gọi** — vì AI không raise exception, response không rỗng, không phải "NONE" |
| `past_event["actual"]` | Nguyên đoạn văn bản reasoning (~500 ký tự) — **SAI** |

### Nguyên nhân

DeepSeek model trả về thinking/reasoning tokens trước answer. Code hiện tại không:
- Strip phần thinking khỏi response
- Kiểm tra độ dài response (nếu > 20 ký tự → có thể không phải số)
- Fallback về regex khi AI response không giống numeric value

### Vị trí code

[news_service.py:1294](services/news_service.py#L1294) — `_parse_with_ai()`

```python
def _parse_with_ai(self, text, event_name, forecast, previous):
    ...
    result = ai.analyze(prompt, max_tokens=100).strip()
    if not result or result.upper() == "NONE":
        return ""
    return result  # ← BUG: trả về toàn bộ reasoning nếu AI model output thinking
```

### Hướng sửa đề xuất

1. Nếu `len(result) > 20` → coi như AI không trả về số → fallback regex
2. Hoặc: strip dòng cuối cùng của response (answer thường nằm cuối)
3. Hoặc: luôn chạy `_parse_fallback_regex()` trên raw search text như 1 tầng fallback bổ sung

---

## 5. Cache

- Cache lưu tại `%APPDATA%/ai-market-analyst/cache/actual_cache.json`
- Key format: `USD|ISM Manufacturing PMI|2026-07-01`
- Cache đã bị ghi giá trị sai (AI reasoning text) — cần xóa để test lại sau khi fix

---

## 6. Tổng kết

| # | Bug | Mức độ | Nguyên nhân gốc | Khuyến nghị |
|---|-----|--------|-----------------|-------------|
| **1** | `lookup_actuals_batch()` không bao giờ chạy | **Nặng** | FF API `thisweek.json` chỉ trả event tương lai, cache không persist | Phương án A: persistent cache tích lũy |
| **2** | `_parse_with_ai()` trả về reasoning thay vì số | **Trung bình** | DeepSeek model output thinking tokens, code không strip/lọc | Fallback regex nếu `len(result) > 20` |

**Thứ tự sửa:** BUG #1 trước (mở đường dữ liệu) → BUG #2 sau (parse đúng dữ liệu).
