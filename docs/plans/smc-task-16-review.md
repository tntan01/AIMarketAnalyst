# Tech Lead review — SMC task 16

**Quyết định: CHANGES_REQUESTED. Chưa được bắt đầu task 17.**

- Reviewer: Codex, vai trò Tech Lead do người dùng chỉ định.
- Thời điểm đánh giá: 2026-09-10 14:43 (Asia/Saigon).
- Revision runtime: `fb9ea527ee7ff0eb48c53875e24796260008e92c`, branch `main`.
- Phạm vi: hồ sơ task 1–15 trình tại gate 16, gồm 13 tài liệu `docs/plans/smc-*.md` có trước báo cáo này và ba fixture task 4/5. Các file này đang untracked; HEAD riêng lẻ không định danh được hồ sơ review.
- Digest hồ sơ: `69f954f4a84c23a55c259d13e2dbc2dd8085342651a8d9bdabe52108cb428a93`. Cách tính: sắp absolute paths trên máy review; mỗi dòng là SHA256 file viết hoa, một dấu cách, repository-relative path dùng `/`; nối các dòng bằng LF, không newline cuối; SHA256 UTF-8 của chuỗi đó. Không bao gồm báo cáo này.
- Chưa có thay đổi tracked/runtime trong gói trình. Đây là review đặc tả trước implementation; findings bên dưới không khẳng định thuật toán mới đã được chạy.

## Bằng chứng đã kiểm tra

Đã đọc hai kế hoạch gốc, toàn bộ đặc tả dữ liệu/structure/parameter/zone/lifecycle/BQLC/readiness/selection/compatibility, progress, acceptance dossier và ba fixture. Đã đối chiếu caller của scorer cùng các seam thực tế trong `scanner_scenario_producers`, `risk_engine`, `entry_engine` và M15 evaluator.

Chạy lại đúng bộ baseline 22 module ghi ở task 3:

```text
python -m pytest tests/test_smc_canonical_golden.py tests/test_smc_composition.py tests/test_smc_consumer_phase6.py tests/test_smc_context.py tests/test_smc_directional_confluence.py tests/test_smc_domain_models.py tests/test_smc_m15_confirmation.py tests/test_smc_phase7_validation.py tests/test_smc_prefilter.py tests/test_smc_scorer.py tests/test_smc_scoring_phase0.py tests/test_smc_scoring_result.py tests/test_smc_sweep_linking.py tests/test_smc_zone_ai_review.py tests/test_smc_zone_audit_cache.py tests/test_smc_zone_lifecycle.py tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
```

Kết quả review: **418 passed in 3.41s**. Baseline coder báo 418 pass được xác nhận lại.

Probe độc lập trên runtime hiện tại tái hiện cả ba ca:

- M15: 48 candle, rejection cũ vẫn trả `confirmed=True`, `reaction=True`, `penalty=0`.
- D1 proximity-only: bonus `(2, ["D1_ZONE_REACTION_BONUS"])`.
- Protected-swing fixture: `structure=mixed`, `bos=False`, `choch=False`, `choch_confirmed=False`.

Các kết quả này xác nhận baseline/probe, chưa xác nhận expected contract mới. Không chạy giao dịch hoặc sửa runtime.

## Findings phải giải quyết trước khi duyệt gate 16

### R16-01 — [P1] State machine chưa định nghĩa đủ để xác nhận reversal và chọn protected swing

**Owner:** task 7, đồng bộ task 8/11 và fixture task 5.

**Vị trí:** `smc-structure-spec.md:35–48, 53–64`; `smc-parameter-table.md:32`.

Theo §4, bearish BOS chỉ được phát trong bearish state. Nhưng §5 giữ trend bullish khi mở bearish CHoCH candidate, rồi yêu cầu một bearish BOS mới để chuyển sang bearish. Chưa có rule cho continuation level/state tạm của candidate để phát BOS xác nhận đó. Triển khai nguyên văn có thể khiến reversal không bao giờ confirmed; triển khai bằng ngoại lệ tự chọn lại thay đổi semantics chưa được duyệt.

Protected low được mô tả là swing “làm điểm xuất phát hợp lệ của impulse”, nhưng chưa có phép chọn khi nhiều confirmed lows nằm trước BOS: interval nào được xét, chọn low cuối hay extreme, và swing phải confirmed trước thời điểm nào. Ví dụ gán sẵn `L1` chưa giải quyết việc detector tự tìm `L1`. External fallback width 2 cũng chưa quy định khi nào được chuyển về width 5 và có được tính lại lịch sử hay không.

**Yêu cầu sửa:** bổ sung thuật toán chọn continuation/protected source, candidate-local reversal levels, phép so LH/HL với level nào, thứ tự pivot confirmation/break/reclaim/expiry. Chốt external width/fallback sao cho không thay lịch sử event đã confirmed khi thêm nến.

**Kiểm tra lại:** timeline BUY và SELL có nhiều swing đủ điều kiện trước BOS; break protected → pivot mới confirmed → BOS reversal; reclaim/timeout; điểm chuyển fallback. Mỗi bước ghi state, tracked/protected IDs, `confirmed_at`, event expected; prefix và batch tại cùng cutoff phải có cùng kết quả. Ở gate này cần expected cụ thể trong hồ sơ, runtime tests thuộc chặng B.

### R16-02 — [P1] Chưa nối được M15 confirmation với visit/lifecycle của vùng H4/H1

**Owner:** task 10/12, đồng bộ task 6/8/9.

**Vị trí:** `smc-lifecycle-spec.md:65–71, 89–97, 149`; `smc-readiness-spec.md:29, 50–52, 70–71`.

Lifecycle chỉ exit khi toàn candle không còn overlap vùng mở rộng, dùng ATR cùng timeframe; open visit không được reacted. Readiness lại chặn mọi open/completed-unreacted visit trước khi xét M15. Chưa ghi rõ visit dùng timeframe nào cho zone H4/H1 và M15 trigger tham chiếu visit đó ra sao.

Ví dụ H4 zone đã available: M15 chạm rồi micro break + displacement đóng ra ngoài vùng, nhưng H4 candle đang forming hoặc H4 candle vừa đóng vẫn có wick overlap. Nếu visit theo H4, nó còn open và bị chặn bất kể M15; nếu coder dựng visit theo M15 để vượt điều kiện này thì dwell/integrity Q có thể đổi khi thêm/thiếu M15. Cả hai cách diễn giải đều chưa được contract phân xử. Mốc expiry “12 bar kể từ visit/trigger anchor” còn cho nhiều kết quả khác nhau khi visit kéo dài.

**Yêu cầu sửa:** chốt owner/timeframe của quality lifecycle và entry visit, quan hệ ID giữa chúng, điều kiện cho M15 xác nhận trong visit đang mở, cùng anchor chính xác cho lookback/follow-through/expiry/max-run. Giữ invariant cùng child setup thay M15 không đổi B/Q/L/C; không tự thêm yêu cầu H4 reaction trước mọi entry.

**Kiểm tra lại:** BUY/SELL timeline H4 chưa đóng nhưng M15 đã đủ confirmation; H4 wick overlap nhưng M15 đã thoát; visit kéo dài hơn 12 M15 bar rồi có trigger mới; thiếu M15; visit mới hủy trigger cũ. Ghi quality, visit ID, readiness và expiry expected cho từng cutoff.

### R16-03 — [P1] Expected mới vẫn giữ M15 penalty trái với công thức đích

**Owner:** task 4/8, đồng bộ task 11/14/15 và progress.

**Vị trí:** `smc-parameter-table.md:25, 120`; `tests/fixtures/smc_m15_stale_rejection.json:364–367`.

Bảng P1 cho phép “quality downgrade” khi thiếu M15; P10 và fixture `expected_after_fix` yêu cầu `penalty=2` khi không confirmed/hết hạn. Trong khi thiết kế gốc §9 và BQLC/readiness spec yêu cầu bỏ M15 penalty khỏi raw. Nếu task 79 khóa expected này hoặc task 96 tiếp tục chiếu penalty, lỗi cap/phạt cũ sẽ quay lại dưới contract mới.

**Yêu cầu sửa:** expected sau sửa phải ghi waiting/not-confirmed cùng quality không đổi. Bỏ penalty khỏi contract mới, hoặc nếu cần field legacy thì khóa rõ chỉ dùng đọc lịch sử, không được tiêu thụ vào score/projection hiện hành. Đồng bộ bảng, fixture, progress và acceptance dossier.

**Kiểm tra lại:** cùng selected child và core snapshot, thay M15 giữa confirmed/missing/stale/expired phải giữ nguyên B/Q/L/C, S và projected SMC raw; chỉ confirmation/readiness thay đổi. Fixture phải phân biệt expected hiện tại với expected mới.

### R16-04 — [P1] Bảng tham số và công thức đưa ra kết quả khác nhau cho cùng input

**Owner:** task 8/10/11.

**Vị trí:** `smc-parameter-table.md:83–85, 95–96`; `smc-bqlc-spec.md:124–125, 144–153`.

Những mâu thuẫn có thể tính trực tiếp:

- H4 zone age=4, lifetime=30: P7 cho age factor `0.80`; BQLC cho `1 - 0.75*4/30 = 0.90`.
- Dwell=1: P7 ghi không phạt; BQLC `inverse(1,0,5)=0.80`, đã giảm integrity. P7 còn dùng đơn vị “điểm”, BQLC dùng feature `[0,1]` mà không map giữa hai cách tính.
- Sweep reclaim sau 2–3 candle: P8 chỉ cho 1 candle; BQLC vẫn chấm reclaim `0.50`.
- P8 ghi consumed link không tái dùng cho zone khác; BQLC cho mọi child cùng setup tham chiếu và giữ contribution. Giữ one-to-one từ code cũ sẽ làm sibling phụ thuộc thứ tự duyệt.

**Yêu cầu sửa:** chốt một công thức/boundary cho từng rule và dẫn tham chiếu từ các tài liệu còn lại. Giải quyết rõ đơn vị dwell, age interpolation, reclaim window và consumption theo pool/event/setup/child. Không coi việc “không có TBD” là đã khóa được contract khi các bảng khác nhau.

**Kiểm tra lại:** bảng số tính tay tại dwell 0/1/5/6, age 3/4/8/9/lifetime/lifetime+1, reclaim 1/2/3/4; hai child cùng setup dùng cùng sweep, đảo thứ tự và scan lại không đổi contribution.

### R16-05 — [P1] Shared planner mới có interface, chưa chốt quy tắc của hai đường chạy hiện có

**Owner:** task 13, đồng bộ task 2/8/12/14.

**Vị trí:** `smc-selection-spec.md:99–133, 195–217`; `smc-parameter-table.md:130`.

Inventory đã ghi Analyze và Scanner có hai planner, nhưng spec chưa chọn cách thống nhất công thức thực tế. `core/scanner_scenario_producers.py:115–170` dùng current H4/D1 ATR, BUY entry ở original low, SL=low−1 ATR và TP từ technical opposite zone. `core/risk_engine.py:720, 850–923` có execution sub-zone, swing/zone SL buffers, risk floors và các nhánh TP riêng. Khẳng định “cùng pure coordinator” không tự làm hai plan này giống nhau.

P11 còn đổi width eligibility sang formation ATR cùng TF trong khi Scanner hiện dùng current H4/D1 ATR, nhưng chưa tách phép đo quality khỏi execution geometry cần giữ. Với width=1.2, H1 formation ATR=1 và current H4 ATR=2, hai rule cho reject/pass khác nhau. Ngoài ra chưa có ma trận cho technical fallback độc lập như phụ lục S yêu cầu; chỉ nói không bypass chưa xác định trường hợp nào được giữ.

**Yêu cầu sửa:** lập mapping concrete cho entry/refinement, protective SL, TP, ATR nguồn, distance/width, min-RR/risk floor và fallback của cả hai route; chỉ rõ owner giữ rule nào và thay đổi hành vi nào cần duyệt. Tách pure geometry/plan khỏi gate tài khoản. Nếu cache chứa final selected plan, ghi đủ technical price/levels/execution-policy inputs ảnh hưởng plan vào identity hoặc quy định lớp đó không được cache cùng evaluation.

**Kiểm tra lại:** ví dụ số BUY/SELL với cùng snapshot/policy qua Analyze, Scanner và replay; ghi exact entry/SL/TP/ATR/RR, candidate trace và selected IDs. Bao gồm H1/H4 ATR khác nhau, TP thiếu, candidate đầu không plan, min-RR thay đổi, no-SMC technical fallback và SMC invalidation cấm fallback.

### R16-06 — [P2] Tham số rejection M15 được chép sai đại lượng từ code

**Owner:** task 8, đồng bộ task 12 và acceptance cases task 15.

**Vị trí:** `smc-parameter-table.md:119`; đối chiếu `core/smc_m15_confirmation.py:169–177`.

P10 gọi `0.80` là body/range và `0.25` là range-location. Runtime thực tế kiểm tra directional wick `>= max(0.80*body, 0.25*candle_range)`, đồng thời close đúng màu. Hai đại lượng này không tương đương. Probe với O=100, C=100.4, H=100.5, L=99.4 được hàm rejection hiện tại nhận dù body/range chỉ `0.363636`.

**Yêu cầu sửa:** ghi phương trình rejection đầy đủ cho BUY và SELL, phép so sánh ở biên, wick/body/range nào được dùng, và cách nối follow-through. Nếu muốn thay detector rejection, trình bày là thay quy tắc; không ghi là tái sử dụng nguyên contract hiện có.

**Kiểm tra lại:** wick đúng/bằng/dưới threshold, doji/range=0, close sai hướng; mirror BUY/SELL; rejection phải gắn visit và follow-through để không quay lại stale-confirmation.

### R16-07 — [P2] C vẫn thưởng D1 visit chưa có reaction

**Owner:** task 11, đồng bộ task 10 và D1 acceptance task 15.

**Vị trí:** `smc-bqlc-spec.md:162`.

`independent_htf_reaction_score=0.50` khi visit đã exit nhưng chưa có full reaction. Lifecycle gọi trường hợp này `completed_unreacted`; kế hoạch gốc chỉ cho phản ứng HTF độc lập đủ hiệu lực làm evidence, không thưởng chạm/visit đơn thuần. Một exit không có follow-through vẫn nhận `2 * 0.25 * 0.50 = 0.25` điểm S. Đây là một biến thể của vấn đề D1 evidence chưa đủ mà vẫn nhận bonus.

**Yêu cầu sửa:** reaction feature bằng 0 khi chưa đạt reaction contract. Nếu muốn chấm partial reaction, phải định nghĩa event có bằng chứng riêng và trình thay đổi thiết kế; không dùng trạng thái exit làm chứng cứ đủ.

**Kiểm tra lại:** proximity-only, open, completed_unreacted, completed_reacted, expired reaction; giữ các component khác cố định để nhìn rõ contribution C; có BUY/SELL và cờ legacy/canonical trái nhau.

### R16-08 — [P2] Q tái đưa điểm mặc định cho dữ liệu hợp lệ

**Owner:** task 11.

**Vị trí:** `smc-bqlc-spec.md:110–115`; đối chiếu `smc-scoring-upgrade-plan.md:144, 154`.

OB/S-D nhận `bounds_integrity_score=1` chỉ vì bounds ordered/finite. Đây là điều kiện validate bắt buộc, không phải mức chất lượng hình học. Mọi candidate hợp lệ của hai family tự nhận `7 * 0.20 * 0.35 = 0.49` điểm S, kể cả width score bằng 0 tại 1 ATR. Điều này đưa lại loại điểm mặc định mà thiết kế yêu cầu bỏ và tạo chênh lệch family do schema hợp lệ.

**Yêu cầu sửa:** đưa ordered/finite vào hard validation; phần geometry có trọng số phải đo đặc tính hình học có ý nghĩa và quy tắc theo family. Chốt lại công thức/ví dụ số sau thay đổi, không chỉ đổi tên feature.

**Kiểm tra lại:** bounds invalid luôn reject; bounds valid không tự sinh contribution; ví dụ hình học yếu/tốt của OB/S-D/FVG có expected tính tay và không dùng helper production làm expected.

### R16-09 — [P2] Selected IDs cho watch-no-plan đang có hai contract đối nghịch

**Owner:** task 13/14, đồng bộ task 12.

**Vị trí:** `smc-selection-spec.md:162, 184, 194`.

Coordinator và đoạn giải thích yêu cầu giữ selected watch zone với quality/lifecycle khi không có plan. Nhưng bảng canonical result lại yêu cầu `selected_setup_id/selected_zone_id=null` cho no-plan. Nếu finalizer làm theo bảng, consumer không còn biết quality/lifecycle thuộc vùng nào và có thể nhầm với no-zone; nếu làm theo loop, validator viết từ bảng sẽ reject result.

**Yêu cầu sửa:** confirmed watch còn hợp lệ giữ selected IDs/quality/lifecycle; chỉ plan/reference null và `plan_available=false`. Tách rõ no-zone và candidate chưa confirmed. Đồng bộ field presence/nullability trên selection, readiness, compatibility.

**Kiểm tra lại:** round-trip ba payload độc lập: valid selected có plan; valid selected watch nhưng TP/min-RR không tạo plan; đủ core nhưng no valid setup. Kiểm tra IDs, raw/null, plan, status và UI text expected.

## Quyết định và phạm vi sửa tiếp theo

Task 16 nhận **CHANGES_REQUESTED**, gồm 5 finding P1 và 4 finding P2. Coder sửa hồ sơ ở các task gốc nêu trên, cập nhật fixture/progress theo quyết định mới rồi trình lại gate 16. Cần ghi rõ revision hoặc digest của hồ sơ đã sửa và đáp án cho từng finding. Chưa triển khai task 17 hoặc thuật toán chặng sau.

Baseline/inventory, việc giữ runtime chưa đổi và phân biệt dữ liệu synthetic với dữ liệu thật là các phần đã có bằng chứng. Corpus MT5, UI, replay và performance được ghi pending cho chặng sau; việc chúng chưa chạy không phải finding chặn riêng ở gate 16. Không yêu cầu chạy một backtest lớn để xử lý review này.

Ở lần review lại, yêu cầu là đặc tả nhất quán với ví dụ và expected có thể triển khai; chưa yêu cầu thực hiện trước các runtime tests thuộc task 17 trở đi. Findings về semantics phải được giải quyết trong hồ sơ, không để coder tự chọn một trong nhiều cách hiểu lúc viết code.
