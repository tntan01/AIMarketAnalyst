# R56-01 — Bàn giao implementation sau khi chốt contract/tests

**Tech Lead, 2026-09-11. Trạng thái: READY_FOR_IMPLEMENTATION; acceptance RED có chủ ý. Gate56 vẫn CHANGES_REQUESTED.**

Người dùng yêu cầu hoàn thiện contract và acceptance tests trước, sau đó mới giao Coder sửa implementation. Tài liệu này bàn giao phần implementation cho **CODER2**, owner các bản sửa gate56 gần nhất. Không mở task57, không rollout production, không sửa lại bảy finding đã CLOSED.

## 1. Nguồn quyết định đã chốt

Đọc theo thứ tự:

1. [Contract R56-01](smc-r56-01-session-contract.md): nguồn quyết định hiện tại cho session-origin. Công thức D/G là quy ước kỹ thuật mới được Tech Lead bổ sung rõ ràng; các heuristic open-equality/strictly-inside-range trong phản hồi review cũ không còn là acceptance criteria.
2. [Golden fixture](../../tests/fixtures/smc_r56_01_session_acceptance.json): 14 trường hợp BUY, mirror SELL; expected ghi tay, không lấy từ implementation.
3. [Acceptance suite](../../tests/test_smc_r56_01_session_acceptance.py): 114 tests, gồm geometry, classification, public pipeline, evidence và lifecycle.
4. [Review gate56 lần 5](smc-task-56-review-round5.md): lịch sử finding còn mở, không thay đổi nội dung lịch sử.

## 2. Công việc implementation được giao

- Thêm helper thuần `classify_fvg_session_origin(candles, *, timeframe, symbol)` với input validation, status/reason/bounds và thứ tự quyết định đúng contract. Dùng calendar hiện có; không tạo lịch phiên hoặc service mới.
- Known closure: full D/G containment inclusive mới đủ displacement; giao nhau độ rộng bằng 0 là session-only; partial là unknown. Vị trí middle.open không phải veto. Continuous giữ policy cũ; unknown calendar và missing candle fail closed.
- Cho `detect_fvg_candidates` sử dụng một kết quả helper duy nhất, giữ tick/ATR/gap/middle gates độc lập. Không crop original bounds, không đổi ID/source/available_at.
- Lưu diagnostic tại `evidence.session_origin`, giữ qua typed round-trip. `confirm_fvg_candidate` không được dùng legacy eligible=true để override origin evidence rejected/unknown; giữ reason tương ứng.
- Bảo toàn cutoff/prefix, pending/cold parity, repeat, terminal và future-append parity. Không nới gate để làm tests xanh.

Phạm vi chính: `core/smc_context.py`; chỉ sửa adapter trong `core/smc_models.py` nếu thật sự cần để giữ evidence. Không refactor rộng, không đổi scoring/threshold/logic ngoài R56-01. Repo đang có thay đổi của nhiều lượt trước: giữ nguyên thay đổi không liên quan, không reset/checkout/commit toàn bộ worktree.

Coder có thể thêm regression tests riêng. **Không sửa/skip/xfail contract, golden fixture, acceptance suite hoặc hai negative fixture Tech Lead đã đính chính để làm xanh.** Nếu contract và fixture mâu thuẫn, báo case ID, input, công thức và expected cụ thể cho Tech Lead; không tự chọn một interpretation khác.

## 3. Baseline đã kiểm chứng trước bàn giao

Implementation chưa được Tech Lead sửa trong lượt chốt contract này. HEAD tham chiếu: `fb9ea527ee7ff0eb48c53875e24796260008e92c` trên `main`; vì worktree dirty, SHA256 bên dưới xác định baseline thực tế tốt hơn HEAD.

| Artifact | SHA256 trước implementation |
|---|---|
| `core/smc_context.py` | `4C8BA93AA51A50C897B479EBEF491C24F1FC2A9007B914EEDA42586899453972` |
| `core/smc_models.py` | `C8FBBD90AA10E7F99B61DE8DAEBB30B5019B9D3A9E98987EE27144C2D29045E5` |
| Contract R56-01 | `F04A0E6451801E04EA90E288543FD03B96CB82C715657992962A2FDB433D50BB` |
| Golden fixture | `698CF8A2557FFD829CEBF7316AE30D854C84BED605B17F5FF1C6220254D2BDD5` |
| Acceptance suite | `F1975050751F61A44CFE3B0936C19179A85DEECA08735D942986CFD8A253A5CA` |
| `tests/test_smc_fvg_session_task47.py` | `7B2995CB2ADAB20D10EE557CF844D3520D737587208FED625D2FE4767A246031` |
| `tests/test_smc_detector_task54.py` | `950A09776E6C3138D24B140952977667BF58B5DF0D95973B9379A482C06D9A5C` |

Kết quả thực chạy:

- Acceptance: **38 failed, 76 passed**. Trong 38 fail: 28 thiếu interface diagnostic mới; 6 lỗi detector ở 3 positive case × BUY/SELL (reopen tại edge, reopen ngoài range rồi reenter, D bằng G); 2 thiếu evidence; 2 legacy boolean override origin unknown. Không diễn giải 28 assertion interface mới thành 28 lỗi cũ độc lập.
- Regression ngoài acceptance mới: **632 passed**.
- Chạy gộp acceptance + regression: **38 failed, 708 passed**; đúng tổng baseline, không có collection error hay lỗi regression mới.
- Compile ba test files mới/sửa: passed. `git diff --check`: passed, chỉ cảnh báo LF/CRLF.
- Golden labels đã được đối chiếu độc lập bằng Decimal với công thức contract; các matrix cases đều qua middle quality/gap minimum hiện có, tránh lỗi nguồn bị gate khác che.

Tech Lead đã sửa đúng hai negative fixture sai ở task47/task54 thành session-only do third reopen; dữ liệu negative cũ được giữ thành golden positive `reopen_at_edge_old_false_negative`. Đây là sửa oracle có giải thích, không xóa regression. Review lịch sử không bị viết lại.

## 4. Lệnh tái lập và nghiệm thu

Chạy từ `D:/Projects/AIMarketAnalyst` bằng PowerShell:

```powershell
python -m pytest tests/test_smc_r56_01_session_acceptance.py -q

$smcRegressionTests = @(rg --files tests -g 'test_smc*.py' -g '!test_smc_r56_01_session_acceptance.py')
python -m pytest @smcRegressionTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q

git diff --check
```

Điều kiện trình lại: toàn bộ **114 acceptance tests** và ít nhất baseline **632 regression tests** pass, không skip/xfail; golden artifacts không đổi. Ghi đúng lệnh và kết quả thực tế, không chỉ ghi “đã fix”. Nếu thêm tests, giải thích số lượng tăng. Nếu môi trường không chạy được, báo blocker, không đánh dấu CLOSED.

Tạo `docs/plans/smc-r56-01-implementation-response.md` gồm:

1. Root cause và mapping từng yêu cầu contract → vị trí code → tests chứng minh.
2. Các file thay đổi trong lượt implementation, phân biệt với dirty changes có sẵn.
3. Lệnh/kết quả acceptance, regression, diff check; SHA256 contract/fixture/suite vẫn giữ nguyên.
4. Giải thích vì sao thuật toán không còn phụ thuộc reopen position; cách giữ evidence authority và không làm thay đổi continuous/lifecycle.
5. Trạng thái **WAITING_REVIEW**; báo ADMIN/Tech Lead, dừng tại gate56. Chỉ Tech Lead quyết định APPROVED sau review diff và chạy kiểm chứng.

Không cập nhật review cũ thành APPROVED, không tự đóng R56-01 chỉ vì pytest xanh. Nếu cập nhật progress/current response thì ghi implementation đã sửa, chờ review; không làm mất lịch sử CHANGES_REQUESTED.
