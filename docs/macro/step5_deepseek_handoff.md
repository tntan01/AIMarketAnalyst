# Bước 5 — AI Event Impact Assessment: Tài liệu bàn giao DeepSeek

**Ngày tạo**: 2026-08-07
**Trạng thái**: Đã chốt thiết kế (D1–D7), chưa implement
**Cách dùng**: Chạy tuần tự 5 prompt ở Phần 2, mỗi prompt một lần, `pytest` xanh toàn bộ rồi mới commit và chuyển prompt kế tiếp. Không gộp, không nhảy bước.

---

## PHẦN 1 — MÔ TẢ VẤN ĐỀ (dán vào đầu mỗi prompt)

```
## NGỮ CẢNH DỰ ÁN

Dự án: AIMarketAnalyst tại D:\Projects\AIMarketAnalyst — Python 3.11, desktop app
scan tín hiệu forex (PyQt + MT5). Hệ thống chấm điểm vĩ mô (macro score 0-30)
và tính macro_confidence (0.0-1.0) để điều tiết trọng số điểm macro trong điểm
tổng hợp.

## VẤN ĐỀ CẦN GIẢI QUYẾT (BƯỚC 5 — AI EVENT IMPACT ASSESSMENT)

Hệ thống phòng thủ sự kiện kinh tế hiện có 3 lớp nhưng chỉ phủ gần:
- Blackout ±30 phút ở tầng execution (fail-closed).
- news_in_3h → regime "news_sensitive" (core/technical_context.py:142).
- Bước 3: sự kiện high-impact cách 0.5-4 giờ liên quan cặp tiền →
  macro_confidence_in *= 0.8 + reason code MACRO_HIGH_IMPACT_EVENT_NEARBY
  (core/analysis_pipeline.py, khối thêm ở commit e304003).

LỖ HỔNG: ngoài 4 giờ trở ra hệ thống không biết gì. Một setup có thể nhận
điểm vĩ mô cao dù 20 giờ nữa chạy qua FOMC/NFP/CPI — điểm cao là điểm giả.

GIẢI PHÁP: module mới dùng AI đánh giá trước mỗi sự kiện high-impact trong
cửa sổ 4-48 giờ, trả lời 3 câu hỏi: mức nguy hiểm (magnitude), thị trường đã
price-in chưa (priced_in), cửa sổ rủi ro dài bao nhiêu giờ (risk_window).
Kết quả CHỈ dùng để phòng thủ: hạ macro_confidence + cảnh báo, KHÔNG bao giờ
cộng điểm, KHÔNG tạo bias hướng (giữ bất biến Phase 15C.1 của hệ thống).

## CÁC QUYẾT ĐỊNH THIẾT KẾ ĐÃ CHỐT (bắt buộc tuân thủ, không bàn lại)

D1. Cửa sổ: Bước 5 chỉ kích hoạt khi 4 < hours_until ≤ 48. Bước 3 giữ nguyên
    0.5 < h ≤ 4.0. Đúng mốc 4.0 thuộc về Bước 3.
D2. Derate nhân vào _macro_confidence_in trong core/analysis_pipeline.py
    (pattern Bước 3), KHÔNG đi qua macro_data_quality của NewsService.
D3. Derate ĐỐI XỨNG (1 scalar cho cả buy và sell). Trường expected_direction
    không chạm điểm số — chỉ dùng cho cảnh báo và journal.
D4. Floor: macro_confidence không xuống dưới 0.15, áp MỘT lần ở cuối chuỗi nhân.
D5. Mỗi sự kiện chỉ derate 1 lần theo cửa sổ; mỗi cặp tối đa 1 event bị derate
    mỗi scan — chọn event có hệ số derate thấp nhất, tie thì chọn event gần hơn.
D6. Fail-closed: AI lỗi/không có AI/JSON hỏng/AI confidence < 0.5 → assessment
    fallback {magnitude: "medium", priced_in: "unknown"} → hệ số 0.85. Không
    bao giờ ném exception ra khỏi preload.
D7. Cache theo EVENT (1 assessment phục vụ mọi cặp chứa currency đó):
    - Key: sha1(time_utc | currency | tên_event_chuẩn_hóa) + AI fingerprint.
    - TTL nhóm trường tĩnh (magnitude, expected_direction, risk_window_hours):
      min(thời_gian_đến_event, 24h).
    - TTL riêng của trường priced_in: 6 giờ.
    - Negative cache (AI hỏng): 30 phút.
    - Tối đa 2 lời gọi AI mỗi cycle; event chưa đến lượt nhận fallback 0.85.

## BẢNG DECISION TABLE (AI → hệ số derate)

Hệ số = 1 − penalty(magnitude) × thừa_số(priced_in)
  penalty: high=0.30, medium=0.15, low=0.05
  thừa_số: not_priced_in=1.0, partial=0.6, priced_in=0.3, unknown=1.0

Kết quả cụ thể:
  high:   not_priced_in=0.70  partial=0.82  priced_in=0.91   unknown=0.70
  medium: not_priced_in=0.85  partial=0.91  priced_in=0.955  unknown=0.85
  low:    not_priced_in=0.95  partial=0.97  priced_in=0.985  unknown=0.95

Điều kiện kích hoạt derate: 4 < hours_until ≤ min(48, risk_window_hours)
VÀ currency của sự kiện thuộc cặp đang phân tích.
Backstop: hours_until ≤ 24 mà magnitude=high thì hệ số không được lớn hơn 0.85.
Confidence gate: AI confidence < 0.5 → coi như unknown (hệ số 0.70 nếu high,
0.85 nếu medium/low).

## SCHEMA JSON MÀ AI PHẢI TRẢ VỀ

{
  "magnitude": "low" | "medium" | "high",
  "priced_in": "priced_in" | "partial" | "not_priced_in" | "unknown",
  "expected_direction": "currency_up" | "currency_down" | "two_way" | "unknown",
  "risk_window_hours": <số từ 1 đến 24>,
  "confidence": <số từ 0 đến 1>,
  "evidence": ["căn cứ ngắn 1", "căn cứ ngắn 2"]
}

Quy tắc validate:
- Sai enum ở magnitude/priced_in/expected_direction → loại (None).
- risk_window_hours không phải số, là bool, hoặc ngoài 1-24 → loại.
- confidence là bool hoặc ngoài 0-1 → loại.
- evidence không phải list[str] → loại.
- evidence rỗng mà priced_in ≠ "unknown" → KHÔNG loại, nhưng hạ priced_in
  xuống "unknown".
- Phải trích được JSON kể cả khi response bị bọc trong markdown fence hoặc
  có rác bao quanh (tìm từ "{" đầu đến "}" cuối).

## QUY ƯỚC CODE CỦA DỰ ÁN (bắt buộc)

- Comment và docstring bằng tiếng Việt.
- Pattern parser JSON nghiêm ngặt: tham khảo _parse_ai_stance_json tại
  services/news_service.py:1728.
- Pattern cache: tham khảo _stance_cache tại services/news_service.py:130
  và _ai_fingerprint tại services/news_service.py:166.
- Pattern test AI: tham khảo tests/test_step4_ai_stance.py (mock AI là object
  có method analyze(prompt, max_tokens=...) trả string).
- Giao diện AI service: ai_service.analyze(prompt, max_tokens=300) — đồng bộ,
  có thể ném exception.
- KHÔNG sửa file ngoài danh sách cho phép của từng bước. KHÔNG "cải tiến",
  KHÔNG refactor code có sẵn. KHÔNG làm phần của bước sau.
```

---

## PHẦN 2 — 5 PROMPT THỰC HIỆN TUẦN TỰ

### PROMPT 1/5 — Module thuần logic (chưa nối runtime)

```
Nhiệm vụ: tạo module logic thuần cho Bước 5 (AI Event Impact Assessment) và
test đầy đủ. CHƯA nối vào runtime — không import module này từ bất kỳ file
nào khác, không sửa bất kỳ file nào đang tồn tại.

[ĐỌC NGỮ CẢNH DỰ ÁN Ở PHẦN 1]

### File được phép tạo (chỉ 2 file này):
1. services/event_impact_assessor.py
2. tests/test_step5_event_impact.py

### Nội dung services/event_impact_assessor.py:

1. Dataclass EventImpactAssessment với các trường:
   event_key (str), currency (str), event_name (str), time_utc (str),
   hours_until (float), magnitude ("low"|"medium"|"high"),
   priced_in ("priced_in"|"partial"|"not_priced_in"|"unknown"),
   expected_direction ("currency_up"|"currency_down"|"two_way"|"unknown"),
   risk_window_hours (float), ai_confidence (float|None),
   evidence (list[str]), source ("ai"|"fallback"), applied_derate (float|None).

2. Hàm make_event_key(event: dict) -> str:
   chuẩn hóa tên event (lowercase, gộp khoảng trắng liên tiếp),
   trả sha1 của chuỗi "time_utc|currency|tên_chuẩn_hóa" (hex digest).
   Input là event dict có sẵn của dự án với các trường: currency, event,
   impact, time_utc, hours_until, forecast, previous, actual
   (xem services/forex_factory_client.py:343-355).

3. Hàm build_event_prompt(event, stance_info, headlines) -> str:
   prompt tiếng Việt yêu cầu AI trả lời DUY NHẤT một JSON đúng schema trong
   ngữ cảnh, không thêm văn bản. Input đưa vào prompt:
   - Sự kiện: tên, currency, time_utc, hours_until, impact, forecast, previous.
   - Stance của currency: dict {stance, strength, confidence, source} — ghi rõ
     "không có dữ liệu stance" nếu None/rỗng.
   - Tối đa 8 headlines, mỗi dòng gạch đầu dòng; ghi rõ "không có headline"
     nếu rỗng.
   Nhấn mạnh trong prompt: evidence phải dựa trên forecast/previous/headlines
   được cung cấp, không được bịa; nếu không đủ căn cứ phán đoán price-in thì
   trả priced_in = "unknown".

4. Hàm parse_ai_event_json(response) -> dict|None:
   validate theo đúng QUY TẮC VALIDATE trong ngữ cảnh. Trả dict đã chuẩn hóa
   hoặc None.

5. Hàm derate_factor(assessment, hours_until) -> float:
   trả hệ số theo DECISION TABLE trong ngữ cảnh, kèm đủ điều kiện:
   - hours_until ≤ 4 hoặc > 48 → trả 1.0.
   - hours_until > risk_window_hours của assessment → trả 1.0.
   - ai_confidence < 0.5 → xử lý priced_in như "unknown".
   - Backstop: hours_until ≤ 24 và magnitude == "high" → kết quả không vượt 0.85.
   - Không bao giờ trả dưới 0.15 hoặc trên 1.0.

6. Hàm select_dominant_assessment(assessments, pair_base, pair_quote)
   -> assessment|None:
   chỉ giữ assessment có currency thuộc (base, quote) và thỏa điều kiện kích
   hoạt (4 < hours_until ≤ 48, hours_until ≤ risk_window_hours); chọn cái có
   derate_factor nhỏ nhất; tie → chọn hours_until nhỏ hơn; không có → None.

7. Class EventImpactAssessmentCache:
   lưu dict {cache_key → (assessment, timestamp)}; cache_key gồm event key +
   ai_fingerprint (tham khảo _ai_fingerprint tại services/news_service.py:166 —
   copy logic tương đương, không import NewsService).
   - get(event_key, fingerprint, now): trả assessment nếu nhóm trường tĩnh còn
     hạn (TTL = min(thời_gian_đến_event, 24h)) — tính từ hours_until; nếu chỉ
     priced_in hết hạn 6h thì trả assessment kèm cờ "priced_in_stale" = True.
   - put(event_key, fingerprint, assessment, now).
   - Entry quá hạn bị loại bỏ khi get.

8. Class EventImpactAssessor:
   __init__(self, cache=None): giữ cache (mặc định tạo mới).
   Method assess_upcoming_events(self, events, ai_service, stance_lookup,
   headlines_by_currency, *, now=None, max_ai_calls=2) -> list[EventImpactAssessment]:
   - Chỉ nhận event có impact high (kiểm tra chuỗi impact chứa "high"/"red",
     tham khảo calendar_helpers._is_high_impact) và 4 < hours_until ≤ 48.
   - Sắp theo hours_until tăng dần.
   - Event đã có cache hợp lệ → dùng cache (gọi lại AI nếu priced_in_stale và
     còn quota).
   - Tối đa max_ai_calls lời gọi AI; mỗi lời gọi: build_event_prompt →
     ai_service.analyze(prompt, max_tokens=300) → parse_ai_event_json →
     assessment source="ai". Mọi exception/None → assessment fallback:
     magnitude="medium", priced_in="unknown", expected_direction="unknown",
     risk_window_hours=24.0, ai_confidence=None, evidence=[], source="fallback".
   - Event chưa đến lượt gọi AI → cũng nhận assessment fallback như trên.
   - Mọi assessment đều được put vào cache. Toàn bộ method bọc try/except —
     lỗi bất ngờ trả về danh sách fallback cho toàn bộ event đầu vào hợp lệ,
     không bao giờ ném exception.
   - stance_lookup: callable(currency) -> dict|None.
   - headlines_by_currency: dict {currency: list[str]}.

### Nội dung tests/test_step5_event_impact.py:

Mock AI là class FakeAI có analyze(prompt, max_tokens=...) trả string dựng sẵn,
đếm số lần gọi; có chế độ ném exception/giả lập timeout. Viết các nhóm test:

A. Parser (≥9 case): JSON hợp lệ đầy đủ; magnitude sai enum; priced_in sai enum;
   risk_window_hours ngoài 1-24; risk_window_hours là bool; confidence là bool;
   confidence ngoài 0-1; evidence không phải list; JSON bọc markdown fence;
   response rỗng/không phải str → None; evidence rỗng + priced_in="priced_in"
   → giữ các trường khác nhưng priced_in thành "unknown".
B. Decision table (≥11 case): đủ 9 ô bảng trong ngữ cảnh (kiểm tra giá trị số
   gần đúng 3 chữ số); hours_until=4.0 → 1.0; hours_until=48.5 → 1.0;
   hours_until > risk_window_hours → 1.0; backstop hours=20 + high +
   priced_in → ≤ 0.85; ai_confidence=0.3 + high + priced_in → ra giá trị nhánh
   unknown (0.70).
C. Cache (≥6 case): hit trong TTL không cần gọi lại; hết TTL trường tĩnh →
   cần đánh giá lại; hết TTL priced_in 6h → cờ priced_in_stale True; negative
   entry tồn tại sau lỗi; fingerprint AI khác → miss; 2 event cùng tên khác
   giờ → 2 key khác nhau.
D. Orchestrator (≥6 case): 4 event + max_ai_calls=2 → đúng 2 lời gọi AI, 2
   event còn lại là fallback source="fallback" hệ số 0.85; FakeAI ném exception
   → không exception lọt ra, toàn fallback; ai_service=None → toàn fallback;
   lọc đúng cửa sổ (loại h=3.9, h=49, impact không high); currency không thuộc
   cặp bị loại ở select_dominant_assessment; tie-break chọn event gần hơn.

### Định nghĩa hoàn thành:
- pytest tests/test_step5_event_impact.py xanh toàn bộ.
- Không file nào khác trong dự án bị thay đổi (kiểm tra bằng git status).
```

### PROMPT 2/5 — Nối dây shadow (tính + ghi journal, CHƯA derate)

> **BỔ SUNG SAU REVIEW PROMPT 1 (2026-08-07)**: Trường `hours_until` trong event
> dict của ForexFactory được tính TẠI THỜI ĐIỂM FETCH và được cache tới 24 giờ
> (`forex_factory_client.py:342-350`, `CALENDAR_CACHE_MAX_AGE`) — nó có thể cũ
> tối đa ~24h. Bước 3 tránh vấn đề này bằng cách tự tính lại từ `time_utc`
> (`_hours_until_high_impact` trong analysis_pipeline.py). Vì vậy trong bước
> này, TRƯỚC KHI gọi `assess_upcoming_events`, phải tính lại `hours_until` cho
> từng event từ `time_utc` so với `datetime.now(UTC)` (dùng
> `calendar_helpers.parse_event_time`), và loại event có `time_utc` không parse
> được hoặc đã trôi qua. KHÔNG được tin field `hours_until` có sẵn trong event.
> Yêu cầu này áp dụng cho cả dữ liệu đẩy vào `data_quality_flags`.

```
Nhiệm vụ: nối module EventImpactAssessor (đã có ở services/event_impact_assessor.py,
đã test xanh) vào luồng chạy thật ở chế độ SHADOW: hệ thống tính assessment và
ghi journal + đưa vào kết quả phân tích, nhưng TUYỆT ĐỐI chưa nhân derate vào
macro_confidence. Điểm số sau bước này phải giống hệt trước khi nối.

[ĐỌC NGỮ CẢNH DỰ ÁN Ở PHẦN 1]

### File được phép sửa (chỉ 3):
1. services/news_service.py
2. core/analysis_pipeline.py
3. tests/test_step5_shadow_wiring.py (tạo mới)

### 1. services/news_service.py
- Trong NewsService.__init__ (khoảng dòng 128): tạo instance
  self._event_assessor = EventImpactAssessor() (import từ
  services.event_impact_assessor).
- Trong preload_macro_contexts (khoảng dòng 1059): sau khi đã có snapshot
  (self._get_global_macro_snapshot), gọi đánh giá sự kiện — đọc lịch và
  headlines từ snapshot đang có (xem MacroGlobalSnapshot và
  _refresh_global_macro_snapshot tại news_service.py:664 để biết cách lấy
  calendar events và global headlines), stance_lookup đọc từ self._stance_cache
  đang có (không gọi AI lại cho stance), headlines_by_currency xây từ headlines
  của snapshot. Bọc toàn bộ trong try/except riêng — mọi lỗi chỉ log/emit,
  KHÔNG được làm hỏng preload. Thêm counter observability
  "ai_event_assessment_calls" nếu có performance_tracker (pattern
  safe_performance_call như trong _ai_currency_stance).
- Trong data_quality_flags (khoảng dòng 375): thêm vào dict trả về field mới
  "upcoming_event_assessments" — danh sách dict (chuyển dataclass sang dict)
  chỉ gồm assessment có currency thuộc base/quote của symbol; lấy từ cache của
  assessor, không gọi AI trong method này. Field cũ giữ nguyên không đổi.

### 2. core/analysis_pipeline.py
- Trong bước xử lý macro (cùng khu vực khối derate Bước 3 thêm ở commit
  e304003): đọc self._data_quality.get("upcoming_event_assessments", []), dùng
  select_dominant_assessment với base/quote của self._request.symbol, lưu kết
  quả (payload dict của assessment chọn + trường hours_until) vào biến instance
  self._macro_event_ahead_assessment (mặc định None), khởi tạo
  self._macro_event_ahead_reason_code = None.
- Ở nơi lắp ráp kết quả cuối (khu vực gắn reason_codes, khoảng dòng 1366):
  KHÔNG thêm reason code mới (chưa bật), chỉ cần đảm bảo payload assessment
  xuất hiện trong result["macro"]["event_assessments"] (list rỗng nếu không có).
- KHÔNG nhân _macro_confidence_in. KHÔNG đụng khối derate Bước 3.

### 3. Journal + observability
- Mỗi assessment mới do AI tạo ra (source="ai") được append một dòng JSON vào
  data/event_assessment_journal.jsonl (thư mục data ở gốc dự án, cùng nơi
  data/shadow_records.jsonl — kiểm tra .gitignore; nếu chưa có dòng ignore cho
  file này thì thêm vào .gitignore). Trường trong dòng JSON: timestamp_utc,
  event_key, currency, event_name, time_utc, hours_until, magnitude, priced_in,
  expected_direction, risk_window_hours, ai_confidence, evidence, source.
  Ghi file phải try/except, lỗi ghi file không được ảnh hưởng luồng chính.

### 4. tests/test_step5_shadow_wiring.py (mock toàn bộ, không network)
- preload với assessor/AI lỗi → preload hoàn tất bình thường, không exception.
- data_quality_flags trả field mới lọc đúng currency của cặp; field cũ
  (next_high_impact_event, news_in_3h, high_impact_event_within_30m,
  resume_after) không đổi.
- Pipeline với data_quality có assessments → result["macro"]["event_assessments"]
  có payload; macro_confidence KHÔNG đổi so với khi không có assessments
  (so sánh điểm số cuối cùng).
- Pipeline với data_quality không có field (fixture cũ) → không crash.

### Định nghĩa hoàn thành:
- pytest xanh toàn bộ (cả bộ test cũ).
- Chạy thử 1 scan thật: điểm số mọi symbol giống hệt trước khi nối; journal
  có dòng mới sau scan.
```

### PROMPT 3/5 — Công cụ kiểm chứng (record / label / report)

> **BỔ SUNG SAU REVIEW PROMPT 2 (2026-08-07) — BẮT BUỘC SỬA TRƯỚC KHI LÀM
> PROMPT 3** (chỉ sửa services/news_service.py + tests/test_step5_shadow_wiring.py):
>
> **Lỗi 1 — vi phạm chính bổ sung của review Prompt 1 (dòng 239-248 ở trên):
> `hours_until` KHÔNG được tính lại từ `time_utc`.**
> `_preload_event_impact_assessments` (news_service.py:426) đang truyền thẳng
> events từ `snapshot.calendar_payload["events"]` vào `assess_upcoming_events`.
> Chuỗi dữ liệu thật: `_fetch_global_calendar_payload` ưu tiên đọc cache
> (news_service.py:669-676) → `_cached_calendar_events`
> (forex_factory_client.py:796-813) trả dòng event với `hours_until` tính TẠI
> LÚC FETCH, cache sống tới 24h (`CALENDAR_CACHE_MAX_AGE`). Hậu quả: event có
> thể mang `hours_until` cũ tối đa ~24h — (a) sự kiện ĐÃ DIỄN RA vẫn lọt cửa
> sổ 4-48h (vd fetch cách đây 20h thấy h=6 → sự kiện đã qua 14h nhưng module
> vẫn tưởng còn 6h), (b) backstop 24h, so sánh risk_window, static TTL
> `min(h,24h)` đều chạy trên số cũ, (c) `replace(assessment, hours_until=...)`
> trong assess_upcoming_events (event_impact_assessor.py:557-559) chỉ copy lại
> chính con số cũ đó nên module KHÔNG thể tự sửa. Cách sửa: trong
> `_preload_event_impact_assessments`, TRƯỚC KHI gọi `assess_upcoming_events`,
> duyệt từng event, parse `time_utc` bằng `calendar_helpers.parse_event_time`
> (pattern có sẵn trong CÙNG file: `_event_time` dùng cho
> next_high_impact_event ở news_service.py:401-406), tính lại
> `hours_until = (event_time - now_utc).total_seconds()/3600`, LOẠI event có
> `time_utc` không parse được hoặc đã trôi qua (hours_until ≤ 0), và truyền
> bản copy dict mới (không mutate snapshot gốc).
>
> **Lỗi 2 — `_upcoming_event_assessments_for_symbol` đọc thẳng dict private
> `cache._entries` (news_service.py:553-563).** Ba vấn đề: (a) bỏ qua lọc TTL
> — entry quá hạn vẫn nằm trong `_entries` cho tới khi `cache.get` xóa, đọc
> thẳng sẽ trả về assessment hết hạn; (b) trả `hours_until` TẠI LÚC PUT (không
> bao giờ được refresh) nên dù sửa Lỗi 1, chu kỳ sau đọc lại vẫn ra số cũ;
> (c) phụ thuộc vào internals — module đổi cấu trúc cache là method này âm thầm trả
> list rỗng. Docstring nói "entry quá hạn sẽ tự bị loại ở pipeline (4 <
> hours_until ≤ 48)" KHÔNG phải lưới an toàn: pipeline lọc theo chính con số
> hours_until trong payload — con số đang cũ. Cách sửa: trong
> `_preload_event_impact_assessments`, lưu kết quả `assess_upcoming_events`
> vào `self._last_event_assessments` (kèm thời điểm preload);
> `_upcoming_event_assessments_for_symbol` đọc từ attribute đó thay vì
> `cache._entries`. KHÔNG đọc bất kỳ attribute bắt đầu bằng `_` nào của
> EventImpactAssessor/Cache.
>
> **Lỗi 3 (phụ, sửa luôn thể):** counter `ai_event_assessment_calls` đang tăng
> 1 lần mỗi preload bất kể có bao nhiêu lời gọi AI thật
> (news_service.py:455-459) — lệch pattern `ai_stance_calls` của Bước 4 (tăng
> theo từng lời gọi AI). Chỉ increment khi lời gọi AI thực sự diễn ra, hoặc
> đổi tên counter thành `ai_event_assessment_cycles` cho đúng ngữ nghĩa.
>
> **Định nghĩa hoàn thành của phần bổ sung này:**
> - pytest xanh toàn bộ.
> - Test mới: preload nhận event có `hours_until` field trong cửa sổ (vd 10.0)
>   nhưng `time_utc` ĐÃ QUA → event đó không xuất hiện trong
>   `data_quality_flags["upcoming_event_assessments"]` và không ghi journal.
> - Test mới: preload nhận event `time_utc` hợp lệ tương lai nhưng field
>   `hours_until` sai (vd 99.0) → assessment trong data_quality_flags có
>   `hours_until` tính lại đúng từ `time_utc`.
> - news_service.py không còn đọc attribute private (`_entries`) của cache.

```
Nhiệm vụ: tạo công cụ kiểm chứng chất lượng dự đoán priced_in của Bước 5,
pattern record/label/report của scripts/validate_macro_v2.py (đọc file đó trước
để theo đúng convention).

[ĐỌC NGỮ CẢNH DỰ ÁN Ở PHẦN 1]

### File được phép tạo: scripts/validate_event_assessment.py

### Chức năng:
1. record: không cần làm lại — journal đã được ghi bởi NewsService ở bước
   trước (data/event_assessment_journal.jsonl). Script chỉ đọc.
2. label: CLI con "label" — liệt kê các assessment trong journal mà time_utc
   ĐÃ QUA (sự kiện đã diễn ra), theo thứ tự thời gian; với mỗi sự kiện hiển
   thị: tên, currency, giờ diễn ra, dự đoán priced_in + expected_direction +
   evidence; hỏi người dùng nhập nhãn thực tế:
   - Thị trường có biến động mạnh quanh sự kiện không? (yes/no)
   - Giá chạy có đúng expected_direction không? (yes/no/không rõ)
   - Đánh giá chủ quan: sự kiện đã được price-in trước đó? (yes/partial/no)
   Nhãn lưu vào data/event_assessment_labels.jsonl (append theo event_key,
   không trùng).
3. report: CLI con "report" — đọc journal + labels, in bảng tổng hợp:
   - Số sự kiện đã label / tổng số sự kiện đã diễn ra.
   - Ma trận trùng khớp: dự đoán priced_in vs nhãn price-in thực
     (đếm theo 3x3: priced_in/partial/not_priced_in).
   - Tỉ lệ expected_direction đúng hướng.
   - Liệt kê các sự kiện dự đoán sai rõ ràng để xem lại evidence.

### Quy ước:
- Script chạy standalone: python scripts/validate_event_assessment.py label|report.
- Không import từ UI; chỉ đọc file jsonl và chuẩn library (+ argparse).
- File label jsonl thêm vào .gitignore nếu cần.

### Định nghĩa hoàn thành:
- Script chạy không lỗi trên journal rỗng (báo "chưa có dữ liệu").
- Với dữ liệu mẫu tự tạo trong test/thử tay: label lưu được, report in đúng
  ma trận đếm.
```

### PROMPT 4/5 — Bật derate + reason code + integration test

```
Nhiệm vụ: bật chức năng phòng thủ của Bước 5: nhân derate vào
macro_confidence, thêm reason code, sau một cờ settings để tắt nhanh. Mặc định
cờ TẮT cho đến khi được bật thủ công.

[ĐỌC NGỮ CẢNH DỰ ÁN Ở PHẦN 1]

### File được phép sửa/tạo:
1. services/settings_service.py + config/settings.py (hoặc nơi định nghĩa
   settings hiện hành — tìm pattern thêm field mới vào nhóm advanced settings)
2. core/analysis_pipeline.py
3. core/reason_codes.py
4. tests/test_analysis_pipeline_integration.py (mở rộng)

### 1. Settings flag
- Thêm flag bool event_impact_derate_enabled, mặc định False, vào nhóm advanced
  settings theo đúng pattern các flag hiện có.

### 2. core/reason_codes.py
- Thêm hằng số MACRO_HIGH_IMPACT_EVENT_AHEAD (đặt cạnh nhóm MACRO_* hiện có,
  khoảng dòng 61) và message tĩnh trong REASON_CODE_MESSAGES:
  "Có sự kiện vĩ mô tác động mạnh trong 4-48 giờ tới, giảm mức tin cậy vĩ mô."

### 3. core/analysis_pipeline.py
Chỉ chạy khi flag bật (đọc từ settings; tìm cách pipeline hiện tại đọc settings
— nếu pipeline không có sẵn access thì truyền qua data_quality từ controller
là phương án dự phòng, ưu tiên cách ít xâm lấn nhất).
- Tại khối macro, ĐẶT SAU khối derate Bước 3 (khối commit e304003), KHÔNG sửa
  khối đó:
  + Nếu flag bật và self._macro_event_ahead_assessment khác None
    (đã gắn ở Bước 2-shadow):
      factor = derate_factor(assessment, hours_until)
      nếu factor < 1.0:
          self._macro_confidence_in *= factor
          self._macro_event_ahead_reason_code = MACRO_HIGH_IMPACT_EVENT_AHEAD
  + CUỐI chuỗi nhân confidence trong method (sau cả derate thiếu dữ liệu,
    Bước 3, và Bước 5): áp floor —
    self._macro_confidence_in = max(self._macro_confidence_in, 0.15)
    (floor áp cả khi flag tắt — đây là chốt an toàn chung).
- Nơi lắp reason_codes cuối pipeline (khu vực dòng 1366): append
  self._macro_event_ahead_reason_code nếu khác None, đúng cách Bước 3 append
  _macro_event_reason_code.
- Trong payload result["macro"]["event_assessments"]: bổ sung trường
  applied_derate = factor thực tế đã nhân (None nếu không derate).

### 4. Mở rộng tests/test_analysis_pipeline_integration.py (theo pattern test
Bước 3 sẵn có trong file) — tối thiểu 8 case:
  1. Event 6h, currency khớp cặp, magnitude=high + priced_in=not_priced_in
     → confidence nhân đúng 0.70 và reason code xuất hiện.
  2. Event 3h → chỉ derate Bước 3 (0.8) chạy, không có code Bước 5, không
     nhân đôi.
  3. Event 30h nhưng currency KHÔNG thuộc cặp → không derate.
  4. Event 60h → không derate.
  5. Hai event trong cửa sổ (6h medium/partial và 20h high/not_priced_in)
     → chỉ 1 derate của event nghiêm trọng nhất (high → 0.70).
  6. Chồng worst-case: thiếu toàn bộ dữ liệu correlation (0.4) × Bước 3 (0.8)
     × Bước 5 (0.70) → kết quả bị chặn tại floor 0.15.
  7. Flag TẮT → kết quả bit-identical với trước khi có tính năng (so sánh
     toàn bộ dict điểm).
  8. data_quality không có field assessments (fixture cũ) → không crash,
     không derate.

### Định nghĩa hoàn thành:
- pytest xanh toàn bộ.
- Flag tắt: mọi kết quả phân tích không đổi.
- Flag bật: chỉ confidence/reason code/payload thay đổi theo đúng 8 case.
```

### PROMPT 5/5 — UI + tài liệu

```
Nhiệm vụ: hiển thị cảnh báo sự kiện trong UI và cập nhật tài liệu kiến trúc.

[ĐỌC NGỮ CẢNH DỰ ÁN Ở PHẦN 1]

### File được phép sửa:
1. ui/screens/scanner_detail_screen.py
2. docs/macro/macro_score_architecture.md
3. .gitignore (chỉ nếu cần cho các file jsonl đã thêm trước đó)

### 1. UI — card Vĩ mô
- Trong _dialog_card_macro (scanner_detail_screen.py khoảng dòng 448): nếu
  result["macro"]["event_assessments"] có assessment với applied_derate khác
  None, thêm MỘT dòng cảnh báo dưới thông tin hiện có, định dạng:
  "⚠ {tên_event} ({currency}) trong {hours_until:.1f}h — mức {magnitude},
   {priced_in tiếng Việt: 'đã price-in'/'price-in một phần'/'chưa price-in'/
   'không rõ price-in'}"
- Không có assessment áp dụng → không hiển thị gì thêm.
- Không thay đổi layout/màu sắc hiện có; dòng mới dùng style cảnh báo đang có
  trong màn hình (tìm pattern hiển thị warning hiện dùng).
- Dữ liệu thiếu/không đúng kiểu → im lặng bỏ qua, không crash UI.

### 2. docs/macro/macro_score_architecture.md
- Thêm dòng vào bảng Phase Changelog đầu file, format như các dòng Phase 15:
  ngày hiện tại | "Bước 5: AI Event Impact Assessment — derate macro_confidence
  cho sự kiện high-impact trong 4-48h (shadow → active)" | tác động.
- Thêm mục mới mô tả: luồng dữ liệu (preload → assessor → data_quality_flags
  → pipeline), schema JSON của AI, decision table đầy đủ, quy tắc cache 2 tầng
  TTL, fail-safe 0.85, floor 0.15, reason code mới, và ranh giới với Bước 3
  (Bước 3 giữ 0.5-4h, Bước 5 từ >4h).

### Định nghĩa hoàn thành:
- Mở màn hình chi tiết với data mẫu có/không có assessment đều render đúng.
- Docs nhất quán với code đã implement ở 4 prompt trước.
- pytest vẫn xanh (không test UI thì đảm bảo không phá import).
```

---

## PHẦN 3 — QUY TRÌNH CHẠY & KỶ LUẬT

```
1. Chạy Prompt 1 → pytest tests/test_step5_event_impact.py xanh → commit:
   "Bước 5: module AI Event Impact — parser, decision table, cache, test"
2. Chạy Prompt 2 → TOÀN BỘ pytest xanh + scan thử điểm không đổi → commit:
   "Bước 5: nối dây shadow — assessment ghi journal, chưa derate"
3. Chạy Prompt 3 → commit: "Bước 5: công cụ kiểm chứng priced_in (record/label/report)"
   → CHỜ ≥5 sự kiện high-impact thật, đọc report trước khi chạy Prompt 4.
4. Chạy Prompt 4 → TOÀN BỘ pytest xanh, flag tắt bit-identical → commit:
   "Bước 5: bật derate 4-48h sau cờ settings, floor 0.15, reason code mới"
5. Chạy Prompt 5 → commit: "Bước 5: cảnh báo sự kiện trong card Vĩ mô + tài liệu"

Kỷ luật:
- Mỗi prompt xong phải git diff soát lại — chỉ được đụng đúng danh sách file
  của prompt đó; thấy sửa lan man là revert phần ngoài phạm vi.
- Prompt 3 xong BẮT BUỘC chờ dữ liệu sự kiện thật và đọc report trước khi
  chạy Prompt 4 (bật derate). Nếu report cho thấy priced_in đoán tệ: chỉnh
  prompt AI ở module (Prompt 1), không thay đổi decision table.
- Không gộp nhiều prompt vào một lần chạy. Không để model tự "cải tiến"
  code có sẵn ngoài phạm vi từng bước.
```

---

## PHỤ LỤC — NGUỒN GỐC CÁC QUYẾT ĐỊNH

| Quyết định | Căn cứ từ code |
|---|---|
| Cửa sổ 4–48h, ranh giới 4.0 thuộc Bước 3 | Bước 3 đang dùng `0.5 < h <= 4.0` (`analysis_pipeline.py`, commit e304003) |
| Derate trong pipeline, không qua quality | `macro_confidence` bị nhân tiếp `freshness_multiplier` ở controller (`scanner_controller.py:2482, 2648`) → nhân kép nếu đặt trong quality |
| Đối xứng | `macro_confidence` là scalar chung 2 phía; Phase 15B discard surplus (`signal_engine.py:127-133`); 15C.1 cấm directional bias từ calendar |
| Floor 0.15 | `macro_cap` = 15–20 tùy regime (`signal_engine.py:28-34`) → floor 0.15 giữ weight 2–3, "gần im tiếng nhưng chưa xóa" |
| 1 event/scan, nghiêm trọng nhất thắng | Tránh sụp confidence khi chồng nhiều event trong tuần lễ tin |
| Fallback 0.85 | Tương đương mức phạt Bước 3 (0.8) — "chưa biết gì" thì phạt vừa phải; preload re-raise exception sẽ chết scan (`scanner_controller.py:489-501`) |
| Cache key = bộ ba event | ForexFactory không có stable ID; code đang dedup bằng `(time_utc, currency, event)` (`forex_factory_client.py:179`) |
| TTL priced_in 6h | Trường duy nhất thay đổi khi sự kiện đến gần; Bước 4 cache fallback 24h là điểm yếu không lặp lại |
| Cap 2 lời gọi/cycle | Timeout adapter 30–120s (`services/ai/providers/*`); preload chạy background song song MT5 setup |
