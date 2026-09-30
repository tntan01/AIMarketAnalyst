# Plan — Độ bền kết quả nhận định AI (ca "Nhận định AI — độ bền kết quả")

> **Trạng thái: MỞ — lập 30/09/2026.** Owner duyệt **phạm vi A+B+C** và **chi phí
> kiểm chứng** (chạy thật ~11-13 lời gọi AI ở bước nghiệm thu) ngày 30/09/2026.
> Không còn quyết định mở; ca này **không** đụng khóa policy nào (A/B/C không
> thêm/đổi khóa chính sách, không đổi luật "retry một lần" của contract §9.1
> bước 5 — chỉ đổi *nội dung* lần retry).
>
> Tài liệu thẩm quyền: `docs/news/news-architecture.md` (§9.1 bước 3/5, §11a —
> `prompt_hash`; sửa đổi **đợt 7**) + `docs/ui/screen_design.md` mục News Screen
> (dòng "Lý do lỗi" của tổng kết batch). Lệch tài liệu ↔ code = defect phải đóng.
> **Bài học D3 (bắt buộc): plan này được commit ngay khi mở ca** — không đợi
> đóng ca. Hoàn tất ca → xóa plan (D3), lịch sử Git.

---

## 1. Bối cảnh và bằng chứng

Sau khi sửa lỗi ngân sách token (commit `4cfa1bd`…`887fb81` chưa gồm; phần sửa
`AI_TREND_MAX_TOKENS` nằm trong working tree), lượt "Nhận định tất cả" **11 phạm
vi** đã từ **2 đủ / 9 lỗi** lên **9 đủ / 2 lỗi** (ảnh Owner 30/09/2026). Hai
phạm vi còn lỗi báo cùng một câu: `"AI không trả về JSON hợp lệ."` — tức thất
bại ở **tầng parse**, không phải tầng mạng.

Điều tra 30/09/2026 (6 lời gọi thật trên **bản sao** `news.db` trong temp, cùng
prompt thật của từng phạm vi):

| Lần gọi | `finish_reason` | Phản hồi | Parser |
|---|---|---|---|
| EUR #1 | `stop` | JSON có `#` lẫn trong mảng: `"evidence_item_ids": [378, #3289, #2744, …]` | ❌ `InvalidJson` (chết ở ký tự `#`) |
| EUR #2 | `stop` | JSON trần | ✅ ok |
| EUR #3 | **`length`** | **rỗng** — reasoning 26.306 ký tự, đốt hết 8.000 token | ❌ `InvalidResponse` |
| XAU #1-3 | `stop` | JSON trần | ✅ ok ×3 |

Số đo ngân sách output (đã dùng để chốt hằng số hiện hành): ca nặng nhất (USD,
prompt 29.017 ký tự) cần **5.931** token output, trong đó 5.114 là reasoning;
EUR cần 5.248 (4.562 reasoning).

## 2. Nguyên nhân gốc

1. **Ký hiệu `#` của prompt bị model bắt chước vào JSON (gốc chính).** Prompt in
   mỗi dòng dữ kiện là `- [event #75] …` / `- [news #139] …`
   (`core/trend_prompt_builder.py` d.209-216), schema yêu cầu
   `evidence_item_ids` là **mảng số nguyên**, và mẫu schema lại là một chuỗi
   **không phải số** (`"ids printed above"` — d.225-228, d.351). Chỉ dẫn hiện
   tại (d.170-171) **không** nói "không kèm `#`". Parser cố tình chỉ nhận JSON
   trần (`core/trend_verdict_parser.py` d.229-238) nên **một ký tự `#` là mất cả
   phạm vi**.
2. **Độ dài suy luận biến thiên cực mạnh ⇒ có lần hết ngân sách, `content`
   rỗng.** Cùng prompt EUR: có lần reasoning 4.183 ký tự, có lần **26.306 ký
   tự** (gấp 6 lần) → chạm trần 8.000 token, `content` = 0 ký tự. Retry hiện tại
   (`controllers/news_controller.py` `analyze_trend`) **gửi lại y nguyên cùng
   ngân sách** ⇒ gần như chắc chắn hỏng lại, chỉ tốn thêm một lời gọi.
3. **Chẩn đoán mờ.** Mọi loại thất bại (`InvalidJson`, `InvalidResponse`,
   `MissingHorizon`, `InvalidEnumValue`, …) đều hiển thị chung `PARSE_FAIL_TEXT`
   ⇒ người dùng (và lần điều tra sau) không phân biệt được "JSON hỏng", "hết
   ngân sách" hay "sai cấu trúc verdict".

## 3. Phạm vi

**Trong:** `core/trend_prompt_builder.py`, `services/ai/provider_adapter.py`
(+ hai adapter chat-completion dùng chung helper này),
`controllers/news_controller.py`, `ui/screens/news_screen.py` (chỉ dòng "Lý do
lỗi" đã có), tests họ `tests/test_news_*` + `tests/test_fix_streaming.py`,
tài liệu đồng bộ (`news-architecture.md`, `screen_design.md`).

**Ngoài (cấm đụng):** khóa policy (`config/news_policy.json`), `core/news_models.py`,
`core/trend_verdict_parser.py` (**parser hợp đồng nguyên trạng** — không nới
lỏng, không "unwrap"), `services/news_service.py`, `forex_factory_client.py`,
`interest_rate_service.py`, code vĩ mô/Scanner/Dashboard/alert; verdict AI vẫn
advisory-only (§9.2).

## 4. Ràng buộc bất biến

1. `core/` thuần ASCII, không import services/Qt; `services/` không công thức;
   không chuỗi hiển thị trong `core/`/`services/` (L3) — nhãn tiếng Việt của lô C
   nằm ở `controllers/` (khuôn `PARSE_FAIL_TEXT`/`NO_AI_CONFIG_TEXT` đã có).
2. **`prompt_hash` chỉ đổi đúng MỘT lần trong ca** (lô A — lần 3 tính từ đầu
   miền; lần 1 đợt 5, lần 2 đợt 6). B/C cấm đụng khung prompt.
3. Giữ đúng **một lần retry** cho mỗi lượt phân tích (§9.1 bước 5): B chỉ đổi
   *nội dung* lần retry (sửa lỗi / nâng ngân sách), không thêm lượt thứ hai.
4. Parser không đổi: vẫn từ chối JSON không hợp lệ và JSON sai hợp đồng; "không
   lưu verdict rác" giữ nguyên.
5. Mỗi lô: họ test news + nhóm AI xanh mới sang lô kế; **1 commit/lô**
   (`A (ca "Nhận định AI — độ bền kết quả"): …`).
6. Bước 0 mỗi lô: rà `git status` — commit lô chỉ chứa hunk của lô.

## 5. Lô

### Lô A — Bịt gốc ký hiệu id (prompt)

**Neo:** §9.1 bước 3 (khung prompt), §11a (`prompt_hash` provenance).

**Sản phẩm:**
1. `_EVENT_LINE_TEMPLATE` / `_NEWS_LINE_TEMPLATE`: bỏ `#` khỏi nhãn id
   (`- [event 75] …`, `- [news 139] …`).
2. Mẫu schema: `evidence_item_ids` lấy ví dụ **số** (vd `12, 34`) thay cho chuỗi
   `ids printed above`.
3. Chỉ dẫn tường minh: id trong `evidence_item_ids` là **số nguyên trần** —
   không kèm `#`, không bọc nháy, không trang trí.

**DoD:** mọi test prompt xanh với hash mới; `prompt_hash` mới được ghi vào
contract (§9.1 bước 3 + mục sửa đổi **đợt 7**); test ghim: prompt không còn
chuỗi `#` trong nhãn dòng; prompt USD/EUR vẫn độc lập dữ liệu (hash ổn định).

### Lô B — Retry sửa lỗi + ngân sách thích ứng

**Neo:** §9.1 bước 5 (retry một lần theo tín hiệu `retryable`).

**Sản phẩm:**
1. `services/ai/provider_adapter.py`: thêm **lỗi có kiểu** cho ca "model hết
   ngân sách output" (`finish_reason=length` / không còn nội dung) — hai adapter
   chat-completion (OpenAI-Compatible, DeepSeek) raise lỗi này thay vì
   `RuntimeError` chung; các lý do rỗng khác giữ nguyên.
2. `controllers/news_controller.py`: một lần retry **khác nội dung theo loại lỗi**:
   - lỗi parse mức tài liệu (`InvalidJson`/`InvalidResponse`) → lần 2 gửi lại
     kèm **chỉ dẫn sửa** ngắn (yêu cầu JSON trần, id số nguyên trần, kèm
     `detail` của parser);
   - lỗi hết ngân sách → lần 2 **nâng ngân sách** (×2, có trần).
   `prompt_hash`/`input_snapshot` vẫn lấy từ prompt gốc (provenance không đổi).

**DoD:** test controller: (a) lỗi parse → lần gọi thứ hai mang chỉ dẫn sửa và
lần gọi thứ ba KHÔNG tồn tại; (b) lỗi hết ngân sách → lần hai mang ngân sách
lớn hơn; (c) hai lần đều hỏng → `ok=False`, không ghi verdict nào; (d) thành
công ở lần hai → ghi đủ 3 verdict, `prompt_hash` = hash của prompt GỐC.

### Lô C — Lỗi tự nói lý do

**Neo:** §9.1 bước 5/7; screen_design (dòng "Lý do lỗi" của tổng kết batch).

**Sản phẩm:**
1. `TrendAnalysisResult` thêm trường **có kiểu** `error_type` (mã lỗi máy đọc:
   `InvalidJson`, `InvalidResponse`, `OutputBudget`, `Provider`, `NoConfig`, …).
2. Controller map `error_type` → **thông báo chính xác theo loại** (thay vì một
   câu `PARSE_FAIL_TEXT` cho mọi ca): "AI không trả về JSON hợp lệ." /
   "AI trả về verdict sai cấu trúc." / "AI hết ngân sách suy luận trước khi trả
   lời." — UI hiển thị nguyên văn nên dòng "Lý do lỗi" tự nói đúng loại, **không
   thêm từ điển nhãn mới** (một khái niệm một từ, D6).

**DoD:** test controller (map loại lỗi → câu chữ) + test dialog (dòng "Lý do
lỗi" hiện đúng câu theo loại); mọi chuỗi mới nằm ở `controllers/`.

## 6. Nghiệm thu (Owner đã duyệt chi phí)

1. Battery họ tin tức + nhóm AI/dialog/prompt; battery toàn repo đối chiếu ngoại
   lệ đã biết (họ `test_step3_fred` + collection error `test_smc_gate72`).
2. **Lượt thật "Nhận định tất cả" 11 phạm vi** trên bản sao `news.db` (không
   chạm `%APPDATA%`): kỳ vọng **11/11 ok**, 33 dòng verdict, không phạm vi lỗi —
   ~11-13 lời gọi AI.
3. `prompt_hash` mới ghim trong test + ghi trong contract; đồng bộ
   `news-architecture.md` (§9.1 bước 3/5, sửa đổi đợt 7) và `screen_design.md`.
4. Build `.exe` + smoke theo thông lệ ca (nếu phạm vi chạm asset đóng gói — ca
   này không thêm asset).

## 7. Rủi ro và vòng đời

- **Rủi ro 1:** đổi nhãn id có thể làm model trích id kém hơn → đo bằng lượt
  thật ở nghiệm thu; nếu verdict trích dẫn sai, parser từ chối (không lưu rác) —
  phát hiện được ngay.
- **Rủi ro 2:** chi phí token của retry sửa lỗi (prompt lớn hơn) — chỉ xảy ra ở
  lượt hỏng, tối đa 1 lần/phạm vi.
- **Vòng đời:** hoàn tất ca → xóa plan này (D3) + cập nhật contract; lịch sử Git
  giữ mốc.
