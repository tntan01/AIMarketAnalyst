# Tech Lead review — gate 40, lần 2

**Quyết định: CHANGES_REQUESTED. Chưa bắt đầu task 41.**

- Reviewer: Codex, Tech Lead do người dùng chỉ định.
- Thời điểm: 2026-09-10 22:42 Asia/Saigon.
- Phạm vi: kiểm lại R40-01…07 trên code/fixture thực tế, các acceptance test mới và đường public production liên quan. Gate 16 vẫn APPROVED.
- HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`, branch `main`, working tree chưa commit.
- Manifest response 12/12 file khớp; aggregate `F5D9C3D3843E728654C6644AFEE66EC90B6B6B69AF5B7F5C9031A170BDB79008`.
- Response SHA256: `20468A481D1BDC8324EE97A7029FCC3D1F535BAD22E4F68FA5C7F59CE7502960`.
- SHA256 báo cáo gate 40 gốc: `7A7D996EE36AA1017B5D00B6CDC0B997B22B0B44FC180C392130A49554A9F329`. Không chỉnh sửa báo cáo này.
- Manifest đầy đủ đầu vào review lần này: 41 file, digest `226FE3369B1527E2250507AE491082BD45AFA8700E0969680B377D4F4673A2D4`, xem cuối báo cáo.

## Kết quả

| Finding | Lần 2 |
|---|---|
| R40-01 | PARTIAL — P1: đã có chronological replay/refresh continuation, nhưng acceptance dùng OHLC sai và policy pivot không được duyệt |
| R40-02 | PARTIAL — P1: reclaim/expiry có as_of và terminal confirmed đã sửa; bỏ as_of vẫn confirmed ngoài lifetime |
| R40-03 | PARTIAL — P1: external/structure mới đã tách khỏi builder; internal detector mới vẫn chạy trong production |
| R40-04 | CLOSED cho lỗi dữ liệu sau cutoff làm đổi structure tại cutoff cũ |
| R40-05 | PARTIAL — P2: canonical confirmed payload đã đọc được; round-trip vẫn làm mất provisional/usable gate |
| R40-06 | CLOSED: snapshot reject future ATR, ATR sau eligible close và interval sai |
| R40-07 | CLOSED: cache phân biệt metadata numeric/string và giữ order invariant |

**3 finding đóng, 4 còn một phần.** Không yêu cầu làm lại phần đã đóng.

## Test đã chạy

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
```

**571 passed in 4.84s** — kết quả mới của Tech Lead, khác kết quả 5.00s coder ghi trong response. `git diff --check` không có whitespace error, chỉ cảnh báo LF/CRLF. Không chạy toàn bộ repository suite, UI, broker/live hoặc dispatch giao dịch.

## Phần còn phải sửa

### R40-01 — [P1] Replay acceptance chưa chứng minh contract được duyệt

**Vị trí:** `core/smc_structure_replay.py:34–35,52–59`; `tests/fixtures/smc_gate40_structure_replay.json:6,14–18`. **Task:** 18–19, 25–31, 36–39.

Chấp nhận hướng tách pure evaluator và replay theo từng close. Tuy nhiên:

1. Fixture được gọi “actual OHLC hợp lệ” có **7 nến sai OHLC ở mỗi side**, index zero-based `[8,9,10,11,13,14,16]`. Ví dụ BUY index 8 có O=100, L=104; index 14 có L=104 lớn hơn cả O=100 và C=103.5. Chính `validate_smc_candles` của repository báo `SMC_OHLC_INVALID`. Evaluator không gọi validator và vẫn phát **5 event** cho mỗi timeline.
2. Evaluator tự sort input và silently bỏ item không phải Candle. Probe đảo ngược thứ tự fixture cho cùng events thay vì reject timestamp order sai. Contract task 19 yêu cầu không tự chữa/reorder dữ liệu hỏng; đây chưa phải acceptance đường dữ liệu → structure.
3. Fixture dùng `pivot_width=1`; evaluator default `pivot_width=2` nhưng gọi external detector không có provisional flag. Contract đã duyệt là external width=5; fallback width=2 chỉ observation, không phát BOS/CHoCH/protected confirmed. Chạy fixture với width=5 cho **0 event / unknown**, nên expected hiện tại không chứng minh chuỗi external canonical. Default `break_buffer=1.0` cũng là con số giá tuyệt đối, không phải policy `max(2*tick, .10*ATR_event)`.

**Yêu cầu đóng:**

- Validate dữ liệu eligible trước detector, trả lỗi/reason cho OHLC/order/duplicate/type invalid; giữ dữ liệu sau cutoff không ảnh hưởng kết quả cũ. Không sort để che order sai.
- Viết fixture BUY/SELL OHLC hợp lệ có đủ context/warm-up và pivots external width=5, đủ first BOS → continuation BOS → candidate → confirmed/reclaim/expiry.
- Width nhỏ chỉ được dùng ở unit test thuật toán có nhãn rõ, không thay acceptance canonical; fallback width=2 phải không tạo confirmed event.
- Acceptance dùng buffer được suy ra từ ATR causal và tick metadata, hoặc input policy tường minh đã được tính/kiểm chứng theo cùng công thức; không coi default 1.0 là chuẩn cho mọi symbol.
- Test cold từng cutoff so state/events/protected/source thực. Task-39 hiện dùng chuỗi giá tăng tuyến tính, nên structure events rỗng; thêm restart case có event/protected khác null để phép so không chỉ đúng trên unknown/rỗng.

Không yêu cầu production integration/cache store. Các helper state-transition unit test nhỏ có thể giữ lại, nhưng không dùng chúng để chứng minh gate canonical đã đạt.

### R40-02 — [P1] Expiry guard bị bỏ qua khi không truyền as_of

**Vị trí:** `core/smc_context.py:1490–1494` và phần chọn break candle cuối của `confirm_choch_candidate`. **Task:** 34–37.

Guard mới chỉ chạy khi `cutoff is not None`, trong khi API vẫn cho `as_of=None`. Các candle có close time xác định đầy đủ nhưng nhánh này không dùng chúng để chặn confirmation quá hạn.

Probe dùng `bullish_swings/candle/swing` trong `tests/test_smc_bos.py`:

- BOS H1 ngày 08/01; bearish candidate ngày 10/01, expires_at=**17/01 04:00**.
- Thêm H3=105 pivot/confirmed 11/12 và L3=97 pivot/confirmed 12/13.
- Gọi confirm với candle ngày **18/01 08:00**, close 95.9 (close_at=12:00), buffer=1.
- `as_of="2026-01-18T12:00:00Z"` → false/expired, đúng.
- Cùng input, bỏ as_of → **true/confirmed**, vẫn sai như finding gốc.

**Yêu cầu đóng:** so thời điểm reversal thực với deadline kể cả không có as_of; hoặc bắt buộc cutoff tại API và reject lời gọi thiếu. Không được để optional argument mở đường bỏ qua lifetime. Bổ sung BUY/SELL tại/sau expiry với cả hai cách gọi; giữ những test reclaim và terminal confirmed đã đạt.

### R40-03 — [P1] Internal swing detector mới vẫn được gọi từ production

**Vị trí:** `core/smc_context.py:248–249,2278–2284,2307–2311`. **Task:** giới hạn chặng B.

Builder đã quay về legacy external `swing_points` và không còn output `structure_bos`; phần này đúng. Nhưng `_smc_for_timeframe` vẫn gọi `_detect_internal_structure` đã được sửa sang `internal_swing_points` mới. Call không truyền symbol/timeframe, nên default **H4** còn bị gắn vào internal swing của H1/D1; legacy key `time` vẫn mất ở internal payload.

Probe so module HEAD với working tree qua public `build_smc_context`, 200 nến H1 OHLC hợp lệ từ random.Random(40):

- H1 internal high cũ có `time=2026-01-01T12:00:00+00:00`.
- Bản mới cùng điểm có `time=None`, `timeframe=H4`, confirmed_at=18:00 (width2 H1 đúng phải close=15:00).
- Public output khác baseline. Đây là runtime behavior/provenance change, không chỉ thêm seam độc lập.

Test production mới chỉ dùng 20 nến phẳng và assert highs rỗng/không có structure_bos; không đi qua nhánh internal có swing nên bỏ sót lỗi. `_count_trend_legs` cũng vẫn dùng bản sửa; phải kiểm parity helper này thay vì coi legacy route đã hoàn toàn khôi phục.

**Yêu cầu đóng:** giữ production internal detector/payload và helper semantics như baseline, tách detector mới cho pure evaluator; không chỉ truyền timeframe vào đường mới rồi coi đã giữ production. Thêm regression có external/internal swing thật, so đầy đủ key/provenance/downstream với baseline cho H1/H4/D1. Không bật rollout trước gate.

### R40-05 — [P2] Typed round-trip nâng provisional swing thành usable

**Vị trí:** `core/smc_models.py:417–430,492–521`. **Task:** 21, 25–31.

Việc xuất `confirmed` đã sửa trường hợp canonical confirmed bình thường. Tuy nhiên model chưa mang provisional/width/scope contract, và `from_dict` bỏ `provisional`/`usable` từ detector input. Sau serialize, usable chỉ suy ra từ timestamp.

Probe:

```python
raw = {
    "swing_id": "L1", "symbol": "EURUSD", "timeframe": "H4",
    "kind": "low", "level": 100,
    "pivot_time": "2026-01-01T00:00:00Z",
    "confirmed_at": "2026-01-02T00:00:00Z",
    "provisional": True, "usable": False, "pivot_width": 2,
}
result = SmcSwing.from_dict(raw).to_dict()
# result.get("provisional") == None
# result["usable"] == True; result["confirmed"] == True
```

Fallback đủ right bars không đồng nghĩa external canonical usable. Payload sau round-trip mất blocker mà initialize/BOS/protected dựa vào, có thể phát confirmed event từ provisional.

**Yêu cầu đóng:** giữ provenance/gate trong canonical model hoặc reject provisional ở adapter chỉ nhận canonical; không silent promote. Test confirmed canonical, unconfirmed, provisional fallback và internal/external qua detector → typed/deserialize → initialize/BOS/protected. Không chèn flag thủ công sau round-trip.

## Các finding đã đóng

- **R40-04:** evaluator cắt input tại as_of trước xử lý mỗi prefix. Probe trên OHLC hợp lệ, width5, giữ cutoff cũ rồi thêm future volatility H=10000/L=-10000 hoặc future OHLC malformed đều cho result giống prefix. Đóng lỗi future-input leak của review gốc; không đồng nghĩa đã duyệt policy/validation acceptance còn ở R40-01.
- **R40-06:** snapshot kiểm interval theo TF, ATR reference <= as_of và <= last eligible close. Các test reject và round-trip bốn TF đạt. Không mở rộng yêu cầu event-context ngoài task hiện tại.
- **R40-07:** typed numeric wrapper phân biệt numeric/string; probe nested 5 vs "5" cũng cho key khác. Metadata order-only test đạt. Không yêu cầu triển khai cache store.

## Điều kiện trình lại

Sửa R40-01/02/03/05 còn mở, giữ số finding gốc. Trình valid canonical fixtures, regression production có internal swings và negative tests như trên; chạy lại suite 571-test cùng tests mới. Cập nhật response/progress cho đúng kết quả và manifest; không tự ghi APPROVED, không sửa báo cáo cũ. Chỉ tiếp tục task 41 khi Tech Lead duyệt gate 40.

Lượt review này chỉ tạo báo cáo; không sửa code, fixture, tests, progress hoặc response của coder.

## Manifest đầu vào

Hợp các file trong manifest review gốc và response mới, thêm response; sort repo-relative path. Mỗi dòng SHA256 uppercase + hai khoảng trắng + path; join LF không newline cuối, SHA256 UTF-8 cho digest `226FE3369B1527E2250507AE491082BD45AFA8700E0969680B377D4F4673A2D4`. Các dependency tracked khác neo theo HEAD.

```text
9142B298173BF209B150421D2A38FA03CC58F9CF5A0DFC3C08ED3F0299507F54  core/market_models.py
EC14C60C6BCABF8045207F2993362EF255D99DF484C10022FE123E2E509247C9  core/smc_context.py
5B3FD1F9665C339CE0F809AFA2DA9C707B80FF9D4C542CAB10C7D783A1436639  core/smc_history.py
0CED5C6BBA138E4C142341CED629F4AC95AD6D7909B44C25E38D7CBD6CF2485F  core/smc_models.py
75D2A7ACA9AC0EBAB3C2CF794E0B2FE93FC80740DAA3DF7F060FAA2D8ECC2483  core/smc_snapshot_cache.py
07FEA9FB18462D1F2A3E65EFEB54972EB26395694BAADAC3185166EE3D516550  core/smc_structure_replay.py
C966D8307A28C8E61A20A1E93830E2778CABB5BBC01A4DBE42D47E56A0398682  docs/plans/smc-data-spec.md
088A567411443FB121D6D99C35D2CDDA91AEDF2FD10F3AC5006AC836A6782125  docs/plans/smc-implementation-plan.md
BA0F6B6B47F3247DE5FB30B16423675D489ECD3FEB0BAB1C1512359A41E77A66  docs/plans/smc-implementation-progress.md
C4A3C1C7785010E3DD6E82D3312C61689D0D3A0D3B9218415EA53E1826A11FC1  docs/plans/smc-parameter-table.md
FCFED4E61B0D4C1C831469953179D7363BA285D77C62028EF7B17A7731D7EBA2  docs/plans/smc-scoring-upgrade-plan.md
20C66269A3D4C1D827E070DA4FEB8D87A631D0729189EF5E98ACCB6DF99AA27C  docs/plans/smc-structure-spec.md
20468A481D1BDC8324EE97A7029FCC3D1F535BAD22E4F68FA5C7F59CE7502960  docs/plans/smc-task-40-response.md
6D9BF9B5E36228EF13985C29CF6885A447C700E927A2D62728763B4B38F07261  tests/fixtures/smc_d1_proximity_only.json
7F334CF3BFB9EC39A4114A8AD18CBD522F54A6B53898786A70B26BA1951A477D  tests/fixtures/smc_data_boundaries.json
68466CB160688F9A0C2ED710C540E56B621FE30A044F9C6F0F6ECEDFECE132C7  tests/fixtures/smc_gate40_structure_replay.json
1253E04657D1A90E0DC6447202B5B3B87D41988755E7E66DBE39ABC18F3B23ED  tests/fixtures/smc_m15_stale_rejection.json
1C556136F1B1AEF48230233654CB119B6C9F7870D6626289A839DFA94955DA17  tests/fixtures/smc_protected_swing_differs_from_latest.json
EC4B8B8D7AB8C4E83869B24D5955ABA9E724D1AB287BFE132EAC5B4B9FA9894B  tests/fixtures/smc_snapshot_cache_task38.json
BDD0E9B66B638C5F30EEF0C4BF8CECFCBCB4CEA16D6B9C54F0E818B6FB136367  tests/fixtures/smc_snapshot_cache_task39.json
03C10FEF6E4C3C873FC6F265292C92BC457269CFD04EE9A3801A5ADAE1A846C3  tests/fixtures/smc_structure_task36.json
AADEA22AA43568DDC0EFE0F431747C6955CF5A405DD5012656C2A52696D2BACD  tests/fixtures/smc_structure_task37.json
2EDB5EB07804B5B746F644152A1EE51026518DDA182C7D4000BAEE03058C249A  tests/test_smc_atr_reference.py
3C7BDDAAEFD63398B720FFDD17AF41B7E2DA3F727372ED7F8F307A8D67C493DD  tests/test_smc_bos.py
188AEF98E3D9F13F24F4E1487D90E34D1ADBEF68231C642940A85491FB7496D9  tests/test_smc_context.py
0D0A294E0B4A67CFD91C64FEEF00EE1AED372475E412E4CDE6875F8F17FBCA91  tests/test_smc_data_boundaries.py
E5A9BA0CE7D393FCB673D298B079278A0C87E2637DC4617DD4E17C5B17AA02BB  tests/test_smc_data_cutoff.py
F1F5F635C97F49C60C35C5064D60BC20BEA362A9ECCAF051D0290ED045B21DB5  tests/test_smc_data_validation.py
987CF16CF0284E961228EAAB937A862FC3D97F7044538F899B9CD3B907F0A6B2  tests/test_smc_external_pivots.py
94333C8A79978ADD999450907B95E34209A2BDCE67EAEE845A01FE9BCB3A4A59  tests/test_smc_gate40_review.py
F2348231F6D256123A8D535E3958EDD1B00EB0983E36EB2283E14A2792081F73  tests/test_smc_history.py
92222F251A088E29B731E28F1DADF00FC3C519FCE8FB4E7CA55595C1BC3312E2  tests/test_smc_internal_pivots.py
86B77CC15A4966C6496437897D31293A5775A9C17B1832539F7399E3F226CDCB  tests/test_smc_snapshot_cache_task38.py
908717E7AA5053367AD90D9A5CCA90BBE3FD6185735F6CF5805F3F48E300FBE6  tests/test_smc_snapshot_cache_task39.py
9F6D4DBFB4B0979115822B5B50E18D466CF7AECD6DE18C5AC04ED6F1F06B9443  tests/test_smc_snapshot_models.py
B963F576C453D271BAEB9A0303AEE63D8FE7DC3B6C54DF6BE96E4EFA506F6E18  tests/test_smc_structure_event_models.py
B846D9EDEDEC9B003EF5E0DF46D033F5429E489C5C31493493290B100F0DBBCF  tests/test_smc_structure_state.py
1D6FC0B3CF8446EDD1D789E790A0229ED4DF95AFD903B5BEF9A3AA936BEA9B8D  tests/test_smc_structure_task36.py
8B0EF2F0D75BF19ECB1A51CE37D848DCDA25E2C4AB5A5FFA84DE451E1AAFE60E  tests/test_smc_structure_task37.py
1FDA6F3B8D53AE418E80BDA2753F0940B33B1C76389123282092A61E6CF15A8D  tests/test_smc_swing_models.py
0A85E9F770CB453C8D46D5A7B55C503ACBECD957694EC70A5B84307A79589A70  tests/test_smc_swing_ordering.py
```

