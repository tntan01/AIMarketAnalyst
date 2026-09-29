# Plan — Độ sâu dữ liệu theo chân trời (đợt 6)

> **Trạng thái: MỞ — lập 29/09/2026.** Owner đã chốt toàn bộ quyết định A1–E2
> (contract `docs/news/news-architecture.md` §13 đợt 6, 29/09/2026 — không còn
> quyết định mở). Tài liệu thẩm quyền duy nhất: `docs/news/news-architecture.md`
> **đợt 6** (§6.6, §7, §8, §9.1, §9.3 khoản 6, §11a, §11b, §13, §14, §16) +
> `docs/ui/screen_design.md` mục News Screen (bổ sung đợt 6 — PLANNED) +
> `docs/guides/USER_GUIDE.md` mục 7.1. Lệch tài liệu ↔ code = defect phải đóng.
> **Bài học đợt 5 (bắt buộc): file plan này được commit ngay trong lô đầu tiên
> của ca (C1)** — không đợi đóng ca. Hoàn tất ca → xóa plan (D3), lịch sử Git.

---

## 1. Bối cảnh và tóm tắt ca

Ca đợt 5 đã đóng (commit `1ae81e4`→`d5a108c`): 11 tài sản, batch, dialog 3 tab,
khối Market context. Vấn đề phát hiện sau khi chạy thật: **cửa sổ dữ kiện 7 ngày
duy nhất** khiến verdict trung/dài hạn thiếu bằng chứng (không có CPI/lộ trình
lãi suất/lịch sử phát biểu trong prompt). Ca đợt 6 sửa đúng gốc:

1. **Cửa sổ dữ kiện phân tầng theo chân trời** (§7 `ai_horizon_windows`:
   short 7 / mid 42 / long 180 ngày; long cap `ai_long_window_max_rows`=50).
2. **Context mở rộng:** rate path 6 tháng + yield delta 3 tháng/6 tháng
   (§8 `rate_paths`, §4.7 đợt 6).
3. **Độ sâu nguồn:** producer lợi suất ghi toàn bộ lịch sử lấy được mỗi round
   (FRED `limit=130`, Yahoo `range=1y` — bãi quy tắc "1 dòng/kỳ hạn/round").
4. **Khung prompt v2:** render `status` sự kiện + chỉ dẫn đối chiếu độ phủ
   bằng chứng với chân trời — `prompt_hash` đổi **lần 2** (provenance).
5. **Panel "độ phủ theo chân trời"** trong dialog + khuyến nghị dán dữ liệu
   định kỳ trong USER_GUIDE.

## 2. Phạm vi

**Trong:** `core/news_policy.py`, `core/trend_prompt_builder.py`,
`core/yield_context.py`, `core/rate_trend.py`, `config/news_policy.json`,
`services/news_producers/bond_yield_producer.py`,
`services/news_repository.py`, `controllers/news_controller.py`,
`ui/screens/news_screen.py`, tests họ `tests/test_news_*`, tài liệu đồng bộ.

**Ngoài (cấm đụng):** `services/news_service.py`,
`forex_factory_client.py`, `interest_rate_service.py`,
`market_data_service.py` (chỉ đọc tham khảo), code vĩ mô/Scanner/Dashboard/
alert; verdict AI vẫn advisory-only (§9.2); hai ca đấu nối (a)/(b).

## 3. Ràng buộc bất biến toàn cuộc

Kế thừa toàn bộ đợt 5 (plan đợt 5 mục 3 — xem Git lịch sử `d5a108c`), nổi bật:

1. **2 bất biến C4 giữ tuyệt đối:** context **không tính floor**
   (`ai_min_items` vẫn chỉ đếm events+items **cửa sổ short**); context
   **không được dẫn chứng** vào `evidence_item_ids` — parser hợp đồng
   nguyên trạng, test parser không sửa.
2. **`prompt_hash` chỉ được đổi đúng 1 lần trong ca** (lô C3, lần 2 tính từ
   đầu miền) — C4/C5 cấm đụng khung nữa.
3. `core/` thuần ASCII, không import services/Qt; `services/` không công
   thức; C3 typed; không chuỗi hiển thị trong core/services (L3).
4. Mọi số vận hành = khóa policy (R4/S4); không hard-code.
5. **Bước 0 mỗi lô:** rà `git status` — working tree còn nhóm (b) của luồng
   khác (`trend_verdict_parser.py`, `ui/icons.py`, unstaged
   `news_screen.py`/tests/`screen_design.md`...) — **commit lô chỉ chứa
   hunk của lô**; đan xen không tách được → hỏi techlead (khuôn Bước 0 đợt 5).
6. Mỗi lô: họ test news xanh nguyên trạng mới sang lô kế; 1 commit/lô
   (`C1 (ca "Độ sâu dữ liệu theo chân trời"): …`).

---

## 4. Lô C1 — Policy + cửa sổ phân tầng + hàm chọn dòng

**Neo:** §7 (khóa mới), §9.1 bước 2, §11a (hàm chọn dòng), §13 đợt 6 (A1–A3).

### Sản phẩm

1. **`config/news_policy.json` + `core/news_policy.py`:**
   - Khóa `ai_horizon_windows`: object lồng đúng 3 khóa `short`/`mid`/`long`,
     mỗi khóa `{days: int > 0}` (khuôn validate `ai_horizons` hiện hành);
     giá trị **short 7 / mid 42 / long 180** (provenance: "Owner chốt đợt 6
     29/09/2026 — mid 42 ngày chứa ≥1 chu kỳ CPI; long 180 phủ horizon
     1–6 tháng").
   - Khóa `ai_long_window_max_rows`: positive int = **50**.
   - `MANDATORY_KEYS`/`NewsPolicy`/`from_dict` mở rộng; thiếu/sai kiểu →
     typed error (B4, khuôn hiện hành).
2. **`core/trend_prompt_builder.py` — hàm thuần MỚI (chưa đổi chữ ký
   `build_trend_prompt` — việc đó thuộc C3):**
   - `HorizonWindowSet` (typed, từ policy) + `select_rows_for_windows(events,
     items, windows, long_max_rows)` → bộ rows từng cửa sổ theo quy tắc §9.1
     bước 2: short = tất cả; mid = events `impact` high/medium + items
     `kind=statement`; long = events `impact=high` **có actual** + items
     `kind=statement`, **cap `long_max_rows`** (ưu tiên impact cao trước, rồi
     gần đây trước — deterministic, không phụ thuộc thứ tự nhập vào).
   - Thuần, ASCII; đăng ký §11a (quy tắc chọn dòng dữ kiện).
3. **`controllers/news_controller.py`:** `AiScopePreview` thêm đếm phủ theo
   cửa sổ (`short_rows`/`mid_rows`/`long_rows: int` — dùng
   `select_rows_for_windows` trên dữ liệu đọc qua `events_in_range`/
   `items_in_range` **từng khoảng cửa sổ**; vẫn KHÔNG gọi AI; preview không
   đổi hành vi floor).

### Kiểm thử

- Policy: đủ/thiếu khóa, `days` sai kiểu/≤0, 3 cửa sổ thiếu 1 → raise; JSON
  fixture mọi test cập nhật.
- `select_rows_for_windows`: mid bỏ event low + headline; long bỏ event
  medium, bỏ event high **không actual**; cap 50 chọn đúng thứ tự ưu tiên
  (impact trước, gần đây trước); deterministic (xáo trộn input → cùng kết
  quả).
- Preview: đếm đúng từng cửa sổ (fake repo); floor vẫn trên short.

### DoD

Họ test news xanh; **commit C1 gồm file plan này** (bài học đợt 5); chưa có
hành vi prompt mới (hàm chọn chưa được builder dùng).

---

## 5. Lô C2 — Độ sâu nguồn + dẫn xuất 3m/6m + rate path

**Neo:** §6.6 (độ sâu lịch sử), §4.7 (delta 3m/6m), §8 (`rate_paths`), §11b.

### Sản phẩm

1. **`services/news_producers/bond_yield_producer.py`:** FRED `limit=130`
   (tham số request), Yahoo `range=1y`; converter `_fred_observations`/
   `_yahoo_observations` ghi **mọi bản ghi hợp lệ** theo ngày (bãi "chỉ dòng
   mới nhất" — giữ dedupe trong round `_dedupe` + UNIQUE giữa các round);
   `items_written` = số dòng thực ghi. Docstring ghi lý do (§6.6 đợt 6).
2. **`core/yield_context.py`:** `YieldContext` thêm `delta_3m_2y`/
   `delta_6m_2y`/`delta_3m_10y`/`delta_6m_10y`/`delta_3m_spread`/
   `delta_6m_spread`/`delta_3m_real`/`delta_6m_real` (hoặc gom
   `deltas_3m`/`deltas_6m` có kiểu — coder chọn hình gọn, C3 typed) — quy
   tắc: thiếu quan sát tham chiếu trước mốc → `None` (B4); cùng chủ sở hữu.
3. **`core/rate_trend.py`:** `derive_rate_path(observations, now, months=6)
   → RatePath` (dataclass: `rate_now`, `rate_then`, `change`; thiếu quan sát
   ~6 tháng trước → `change=None`). Danh tính M5 đăng ký §11b.
4. **`services/news_repository.py`:** `rate_paths(currencies) →
   list[RatePathSnapshot]` (khuôn `CurrencyRateTrend` — gọi
   `derive_rate_path`, không tự tính); `latest_bond_yields` context tự mang
   thêm delta 3m/6m (cùng `derive_yield_context`).

### Kiểm thử

- Producer: 1 round FRED limit=130 → ghi ~130 dòng/kỳ hạn; round lặp không
  nhân bản (UNIQUE); Yahoo range 1y converter bóc nhiều ngày; run status
  đúng.
- `yield_context`: delta 3m/6m đủ/thiếu quan sát mốc; biên tháng.
- `rate_trend.derive_rate_path`: đủ/thiếu; sai lệch mốc ±vài ngày lấy quan
  sát gần mốc nhất.
- Repo: `rate_paths` trả typed snapshot; thiếu → `None`/list rỗng đúng B4.

### DoD

Round thật (nếu có key) ghi lịch sử ~6 tháng trong 1 lượt; họ test xanh.

---

## 6. Lô C3 — Khung prompt v2 (hash đổi lần 2)

**Neo:** §9.1 bước 3 (khối v2), §13 đợt 6 (C1–C4), §11a.

### Sản phẩm

1. **`core/trend_prompt_builder.py`:**
   - `build_trend_prompt` nhận **bộ rows theo cửa sổ** (thay `events`/`items`
     đơn — keyword-only; cập nhật test ghim chữ ký có chủ đích) + hàm chọn
     của C1 áp bên trong hoặc nhận kết quả đã chọn (chọn cách một đường đọc
     chung cho preview/analysis — khuôn `_ai_context_and_outcome` đợt 5).
   - Render **3 section data** theo cửa sổ (`Data (short window, 7 days)`,
     `Data (mid window, 42 days)`, `Data (long window, 180 days, top 50)`)
     — mỗi dòng sự kiện **thêm `status`** (released/stale — từ
     `CalendarEvent.status`).
   - `MarketContext` thêm `rate_path` (Protocol/mô hình thuần — không import
     services) + yield delta 3m/6m (từ `YieldContext` mở rộng).
   - Chỉ dẫn khung: AI **đối chiếu độ phủ bằng chứng với chân trời** — dữ
     kiện phủ N ngày < chân trời → hạ confidence hoặc `insufficient_data`.
   - `_skeleton` v2 → **`prompt_hash` đổi đúng 1 lần** — ghim giá trị mới
     (thay pin `d261c7cc…`); mọi test hash cập nhật.
   - **3 bất biến giữ nguyên (mỗi cái 1 test):** floor trên cửa sổ short
     (chỉ đếm events+items); `evidence_item_ids` chỉ id rows in prompt
     (context không id); `snapshot` đúng §4.5.
2. **`controllers/news_controller.py`:** `_ai_rows`/`_ai_context_and_outcome`
   đọc theo 3 cửa sổ (chọn qua hàm C1) + context (rate_paths, delta 3m/6m)
   truyền vào builder; preview đồng bộ counts/context.
3. **KHÔNG sửa** parser + test parser (nguyên trạng, ghi rõ trong báo cáo).

### Kiểm thử

- Builder: 3 section render đúng; dòng event có `status`; chỉ dẫn độ phủ có
  mặt trong text; 3 bất biến; hash v2 ổn định + độc lập dữ liệu; đủ/thiếu
  từng cửa sổ; call site cũ cập nhật (controller + test dialog).
- Controller: scope currency/pair/XAU đọc đúng 3 cửa sổ; context đủ bộ.

### DoD

Hash v2 ghim; parser nguyên trạng xanh; prompt thật (debug) có 3 section +
status + rate path.

---

## 7. Lô C4 — Panel độ phủ dialog + đồng bộ hiển thị

**Neo:** §9.3 khoản 6; `screen_design.md` bổ sung đợt 6 (PLANNED); §13 đợt 6
(D1).

### Sản phẩm

1. **`ui/screens/news_screen.py` — tab Chi tiết:**
   - **Panel "độ phủ theo chân trời"** (1 dòng/nhóm dòng dưới dòng đếm cửa sổ
     tin): số dòng từng cửa sổ (short/mid/long + ghi chú cap 50) — lấy từ
     preview (C1), UI không tự tính, **không gọi AI**;
   - **Dòng ngữ cảnh mở rộng:** thêm rate path 6 tháng + delta 3m/6m
     (format khuôn hiện tại, thiếu → "—");
   - Nhãn mới vào từ điển hiển thị của file (khuôn đợt 5).
2. **`docs/ui/screen_design.md`:** bổ sung đợt 6 PLANNED → **IMPLEMENTED**
   (sau khi lô xanh — cùng commit lô).

### Kiểm thử

- Dialog: panel hiển thị đúng số dòng từng cửa sổ (fake preview); mở tab
  không gọi AI; dòng ngữ cảnh có/không rate path/delta 3m/6m; các test
  dialog hiện hành giữ nguyên hành vi cốt (batch, bias, deep-dive).

### DoD

Dialog đúng `screen_design.md` đợt 6; họ test xanh; smoke màn news xanh.

---

## 8. Lô C5 — Nghiệm thu + E2 + đồng bộ + đóng ca

**Neo:** §14, §16, §9.2; khuôn nghiệm thu lô B5 đợt 5.

### Việc

1. Cổng E2: chạy nguyên trạng (không mô-đul scoring/gate/alert mới);
   import-linter + ASCII-literal phủ module mở rộng (`rate_trend` mở rộng đã
   thuộc cổng) — bổ sung nếu có file core mới (không dự kiến).
2. Battery + 3 smoke + build `.exe` + boot bản đóng gói **trên cây commit
   thuần** (worktree — khuôn B5): migration không đổi, schedule 3 timer,
   không run FF lạ.
3. Kiểm thử thật (nếu key FRED + AI): 1 round `refresh_bond_yields()` ghi
   ~130 dòng/kỳ hạn; 1 lượt "Nhận định tất cả" — **ghi rõ DB nào** (bài học
   review B5); kiểm prompt thật có 3 section + status + rate path.
4. Đồng bộ tài liệu: `news-architecture.md` §16 (ghi chú hoàn tất đợt 6);
   `architecture.md`/`runtime-status.md`/`product_spec.md`;
   `USER_GUIDE.md` (đã ghi từ trước — rà lại); `README.md` gỡ đăng ký plan;
   **xóa plan** (D3 — sau khi Owner duyệt).
5. Commit C5 sạch (khuôn Bước 0); bàn giao nhóm (b) cho Owner.

### DoD (đóng ca)

Battery + smoke + build + boot xanh; E2 xanh; tài liệu đồng bộ; Owner duyệt;
xóa plan; tuyên bố đóng ca đợt 6.

---

## 9. Lệ thuộc và rủi ro

| # | Mục | Ghi chú |
|---|---|---|
| 1 | Thứ tự lô bắt buộc | C1 → C2 → C3 → C4 → C5 (C3 cần policy + hàm chọn C1 và context C2) |
| 2 | `prompt_hash` đổi đúng 1 lần | Chỉ lô C3; C4/C5 cấm đụng khung |
| 3 | Floor trên cửa sổ short | Bất biến — không mở rộng floor sang cửa sổ dài (tránh gọi AI khi chỉ có lịch sử cũ) |
| 4 | Prompt dài hơn | 3 section + ~50 dòng long — theo dõi giới hạn token provider khi nghiệm thu C3 (nếu vượt: báo techlead, không tự cắt) |
| 5 | Producer ghi nhiều dòng | `items_written` lớn (~400/round đầu) — đúng thiết kế, không phải lỗi; kiểm ingest_runs hiển thị đúng |
| 6 | Working tree dơ nhóm (b) | Khuôn Bước 0 đợt 5 — không cuốn hunk ngoài ca |
| 7 | Danh sách 11 tài sản / `_USD_PRICED_ASSETS` | Tái dùng từ đợt 5 — không khai báo trùng |
