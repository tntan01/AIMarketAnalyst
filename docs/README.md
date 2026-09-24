# Tài liệu dự án AI Market Analyst

Cập nhật cấu trúc: **20/09/2026** — đợt đơn giản hóa cây tài liệu: chỉ giữ tài
liệu mô tả kiến trúc, tính năng và contract; toàn bộ biên bản review/response,
plan đã hoàn tất được loại khỏi cây (lịch sử truy qua Git).

Khi tài liệu và code khác nhau, thứ tự ưu tiên (theo quy tắc V2 trong
[Quy tắc kiến trúc](architecture/architecture-rules.md)):

1. Ý định Owner trong tài liệu chính — **tính quy định**: code phải theo.
2. Code/test đang chạy — phản ánh hiện trạng.
3. Mâu thuẫn giữa hai nguồn = **defect phải đóng** (sửa code theo tài liệu,
   hoặc Owner sửa tài liệu theo ý định mới), không phải trạng thái chấp nhận.

## Lối đọc nhanh

| Nhu cầu | Bắt đầu từ |
|---|---|
| **Quy tắc kiến trúc (kim chỉ nam mọi thiết kế/sửa chữa)** | `architecture/architecture-rules.md` |
| Hiểu sản phẩm | `product/product_spec.md` |
| Hiểu kiến trúc tổng thể | `architecture/architecture.md` |
| Cài đặt và sử dụng | `guides/installation_guide.md`, `guides/USER_GUIDE.md` |
| Scanner runtime contract | `scanner/scanner-architecture.md` — live từ 15/08/2026 |
| Luồng Scanner lịch sử | `scanner/scanner-flow.md` — tham khảo (pre-cutover) |
| Chấm điểm Scanner | `scanner/scanner-architecture.md` §3; `scanner/technical-scoring-architecture.md` giữ nội dung legacy có nhãn |
| Macro scoring hiện hành | `macro/macro_score_architecture.md` |
| Contract dữ liệu Tin tức (DB, producer, repository, AI nhận định xu hướng) | `news/news-architecture.md` — ban hành 20/09/2026; lộ trình §16 (hoàn tất 23/09/2026, READY-FOR-CONNECT) |
| Vận hành/re-validate VIX theo pair | `macro/macro_score_architecture.md`, mục Bước 7 |
| Contract SMC (B/Q/L/C, zone, lifecycle…) | `plans/smc-*-spec.md`, `plans/smc-parameter-table.md` |
| Quản lý lệnh / R:R | `trading/order-management-contract.md`, `trading/rr_anchor_semantics.md` |
| Thiết kế UI và baseline kiểm thử | `ui/screen_design.md`, `ui/style-guide.md` |

## Cấu trúc thư mục

| Thư mục | Nội dung |
|---|---|
| `product/` | Đặc tả sản phẩm và hành vi cấp cao. |
| `architecture/` | Kiến trúc tổng thể, trạng thái runtime. |
| `guides/` | Hướng dẫn cài đặt, sử dụng và vận hành. |
| `scanner/` | Runtime contract và kiến trúc đích Scanner. |
| `trading/` | Quản lý lệnh, R:R và contract liên quan giao dịch. |
| `macro/` | Macro runtime, economic calendar và VIX pair sensitivity. |
| `news/` | Tầng dữ liệu tin tức: database nguồn chân lý, bộ sản xuất, kho truy cập, contract AI nhận định xu hướng (advisory-only). |
| `journal/` | Phân tích tính năng journal. |
| `plans/` | Plan của công việc **đang mở** + spec/contract SMC còn hiệu lực (được code và test tham chiếu). |
| `ui/` | Thiết kế màn hình, style guide, fixture audit/baseline UI. |

## Tài liệu hiện hành quan trọng

- `architecture/architecture-rules.md`: **luật kiến trúc ban hành 20/09/2026** —
  nguồn chân lý duy nhất + một điểm thay đổi duy nhất, phân lớp, tài liệu song
  hành, quyền Owner và nguyên tắc không phiên bản; kèm danh mục thay đổi mẫu,
  sổ nợ kiến trúc và án lệ tốt. Mọi task thiết kế/sửa chữa phải tuân thủ.
- `scanner/scanner-architecture.md`: runtime contract hiện hành của Scanner
  (live từ 15/08/2026): TechnicalScore chỉ gồm Trend/Momentum/Location/SMC, Risk
  và Macro là gate, order policy owner-accepted.
- `scanner/scanner-features-spec.md`: đặc tả tính năng; §0.1 là nguồn đặc tả
  thuật toán/default config của Location runtime.
- `macro/macro_score_architecture.md`: contract chấm điểm macro hiện hành.
- `news/news-architecture.md`: **contract tầng dữ liệu Tin tức ban hành
  20/09/2026, sửa đổi đợt 3 24/09/2026** (Owner duyệt) — database tin tức là
  nguồn chân lý duy nhất; bên ghi (RSS/FRED tự động định kỳ, nhập tay, **dán
  mã nguồn trang ForexFactory** — kênh duy nhất của lịch kinh tế + actual,
  không thu tự động FF) chỉ ghi, bên tiêu thụ chỉ đọc qua
  `NewsRepository`; AI nhận định xu hướng là advisory-only, không tham gia bất
  cứ quy trình nào; ca "đập đi – xây mới" là ngoại lệ B6 đã ghi E3 trong
  `architecture/architecture-rules.md`. Đặc tả hiển thị Dashboard và mapping
  chấm điểm vĩ mô sẽ cập nhật vào tài liệu miền tương ứng sau khi phần Tin
  tức triển khai xong.
- `architecture/runtime-status.md`: trạng thái settings/thực thi thực tế.
- `ui/style-guide.md`: quy tắc UI sau chuẩn hóa style/density.
- `plans/smc-bqlc-spec.md`, `plans/smc-readiness-spec.md`,
  `plans/smc-parameter-table.md`, `plans/smc-r56-01-session-contract.md`:
  được `core/smc_quality.py`, `core/smc_readiness.py`,
  `scripts/smc_performance.py` và tests tham chiếu trực tiếp — không xóa/di
  chuyển khi chưa sửa code tương ứng.

## Bằng chứng kiểm thử UI (fixture, không phải tài liệu đọc)

- `ui/style/`: baseline, lock và allowlist cho style audit.
- `ui/density/`: baseline và lock cho density audit.
- `ui/reports/`: report responsive/dark-surface máy đọc được.
- `ui/baseline/`: ảnh baseline visual QA và manifest.

Các file này đang được `tools/` và `tests/` dùng để khóa regression UI
(`capture_ui_style_baseline.py`, `ui_dark_surface_audit.py`,
`test_dark_theme_surface_phase5.py`…). Không xóa.

## Quy tắc cập nhật

- **Mọi thiết kế/sửa chữa code phải tuân thủ `architecture/architecture-rules.md`**
  (nguồn chân lý duy nhất, một điểm thay đổi duy nhất, tài liệu trước code,
  không tên phiên bản cho tính năng). Vi phạm mới phải được duyệt ngoại lệ bằng
  văn bản và ghi vào sổ nợ kiến trúc của tài liệu đó.
- **Ngôn ngữ tài liệu (D6 trong `architecture/architecture-rules.md`):** tên
  tệp/thư mục bằng tiếng Anh không dấu; nội dung viết bằng tiếng Việt có dấu;
  thuật ngữ tiếng Anh dịch tối đa, chỉ giữ mã định danh code, tên công cụ và
  thuật ngữ không dịch được (chú giải tiếng Anh trong ngoặc ở lần đầu).
- Thay đổi hành vi Scanner: cập nhật tối thiểu `scanner/scanner-flow.md`, tài
  liệu kỹ thuật liên quan và test; mỗi bước Scanner phải được phân tích vào
  `scanner/scanner-architecture.md` trước khi sửa code.
- Thay đổi macro scoring: cập nhật `macro/macro_score_architecture.md`.
- Thay đổi tầng dữ liệu tin tức (schema, bộ sản xuất, repository, chính sách,
  contract AI nhận định): cập nhật `news/news-architecture.md`.
- Thay đổi UI contract: cập nhật `ui/style-guide.md` và lock/report nếu cần.
- Thay đổi phân quyền quét/auto-trade: cập nhật `guides/USER_GUIDE.md`.
- Tài liệu quy trình (review từng vòng, response, handoff) không đưa vào cây
  `docs/` — trao đổi qua session/commit message, bằng chứng nằm trong `tests/`.
- Vòng đời plan trong `docs/plans/`: mỗi công việc đang mở có **một** file
  `<tên>-plan.md` tự mang mục Trạng thái ở header; khi hoàn tất thì xóa plan
  (lịch sử trong Git) và sáp nhập contract còn hiệu lực vào tài liệu kiến trúc
  đích danh (`scanner/`, `macro/`, `trading/`…). Spec bị code tham chiếu chỉ
  xóa/dời cùng lúc sửa code.
