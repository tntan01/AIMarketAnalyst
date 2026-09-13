# Tech Lead review — task 16, lần 5

**Quyết định: APPROVED cho gate 16. R16-01 đến R16-09 đều CLOSED ở mức đặc tả.**

- Reviewer: Codex, Tech Lead do người dùng chỉ định.
- Thời điểm: 2026-09-10 18:29 Asia/Saigon.
- Phạm vi lượt này: phần R16-08 còn mở sau review lần 4, các tài liệu bàn giao liên quan và tính toàn vẹn manifest. Giữ kết luận đối với tám finding đã đóng; không tuyên bố review lại toàn bộ runtime.
- Runtime HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`; tracked/staged diff rỗng.
- Submission manifest: `F6C56A33AEC121E0F393B9CE3DB79B18BA70DEDC8879D51ABE82DD121B2A050B`; đủ 14 file, không hash mismatch.
- Response SHA256: `E802AAE6F7EAC83FA1B90AF8D77D668F5A00A97DC1114D740E0D029F52B3469D`.
- Báo cáo review lần 4 giữ nguyên SHA256: `81676D65CC616237C2E9A58B5EC8D1608C67864810EC36643DBF03E639B7467C`.

## R16-08 — CLOSED

Đã đọc công thức và bảng ví dụ hiện tại trong `docs/plans/smc-bqlc-spec.md` §4/§9; đối chiếu với response, acceptance dossier và implementation progress.

- Hai ví dụ S/D đã dùng OHLC hợp lệ, cùng `formation_atr=2`, `avg_range=1`, base/zone width `.66`, compression limit `1.32`.
- Body/range=.80 sinh normalized score=.60; directional close=.86 sinh score=.80. Không còn tổ hợp body/range=.90 lớn hơn directional close=.86 của vòng trước.
- Width/ATR=.33 cho width_score=1; compression=.50; geometry=.825.
- Khi impulse range tăng từ 1.50 lên 2.25, body/ATR score tăng từ 3/7 lên 6/7. Không còn giữ sai feature này cố định.
- Endpoint S/D `[1.50,3.00]` không đổi: minimum → 0, 2.25 → .50, 3.00 → 1.
- Formation/integrity giả định của OB/FVG và integrity giả định của S/D đã được ghi rõ. ATR/avg_range là input thống kê cho ví dụ, không phải bằng chứng đã dựng và chạy toàn bộ history runtime.

Probe độc lập đọc trực tiếp bốn chuỗi OHLC từ bảng Markdown, kiểm tra ordered OHLC/close color, rồi tính feature → formation → geometry → Q → S bằng Decimal:

| Case | Formation | Geometry | Q | S | Kết quả |
|---|---:|---:|---:|---:|---|
| BUY minimum | .460 | .825 | .635 | 8.645 | PASS |
| SELL minimum | .460 | .825 | .635 | 8.645 | PASS |
| BUY trên minimum | .710 | .825 | .760 | 9.520 | PASS |
| SELL trên minimum | .710 | .825 | .760 | 9.520 | PASS |

BUY/SELL parity và ba endpoint đều PASS. Expected trong spec, response, dossier và progress đã đồng bộ. Không còn finding chặn gate trong phần sửa được trình lại.

## Kiểm chứng hồ sơ

- Tính SHA256 từng file, sort đường dẫn rồi tính aggregate theo phương pháp đã công bố: 14/14 khớp.
- So với manifest lần 4, trong 14 file chỉ BQLC spec, acceptance dossier và implementation progress đổi hash; 11 file còn lại giữ nguyên. Response được hash riêng, ngoài aggregate.
- Parse cả ba fixture JSON: PASS; các fixture giữ nguyên hash so với lần 4.
- `git status`, `git rev-parse HEAD`, tracked/staged diff xác nhận runtime nền không đổi.
- Không chạy lại suite 418 test: `418 passed in 3.41s` là baseline của review đầu, không phải kết quả mới hoặc test expected-after-fix.
- Chưa kiểm chứng implementation mới, causal replay, parity Analyze/Scanner, PIT, UI, restart/cache, performance hay execution. Những mục này vẫn thuộc các task/gate tiếp theo.

## Quyền tiếp tục và giới hạn phê duyệt

1. Gate 16 được APPROVED cho đúng bộ hồ sơ có digest ở trên, cùng các quyết định thành phần đã chấp nhận trong các báo cáo trước. Coder có thể cập nhật progress task 16, dẫn báo cáo này làm bằng chứng.
2. Cho phép tiếp tục **task 17–39 của chặng B**, theo kế hoạch đã duyệt, trên nhánh làm việc; chưa thay producer production.
3. **Dừng tại task 40 để Tech Lead review** dữ liệu, nhân quả, protected swing và BOS/CHoCH. Không bắt đầu task 41 trước khi gate 40 được APPROVED.
4. Phê duyệt hồ sơ không phải phê duyệt runtime/production/auto-entry. Không bỏ qua các gate 40/56/72/100/116/128/144; thay đổi semantics hoặc tham số đã duyệt phải trình review phần chịu ảnh hưởng.

Lượt này chỉ tạo báo cáo review; không sửa runtime, specs, fixtures, progress hoặc báo cáo cũ, và không tự triển khai task 17.
