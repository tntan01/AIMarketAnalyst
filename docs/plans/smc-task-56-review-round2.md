# Tech Lead review — gate 56, lần 2

**Quyết định: CHANGES_REQUESTED. Chưa được làm task 57.**

- Reviewer: Codex, Tech Lead theo yêu cầu người dùng.
- Thời điểm: 2026-09-11, khoảng 03:49 Asia/Saigon.
- Phạm vi: kiểm tra lại R56-01…R56-08 trên bản FIXES_READY, regression và hồ sơ acceptance. Không sửa implementation/tests/specs/progress; chỉ thêm báo cáo này.
- HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`, branch `main`, working tree chưa commit.
- Manifest trong `smc-task-56-response.md`: **7/7 file khớp SHA256**.
- Báo cáo lần 1 không đổi: SHA256 `A718DB310BECC4FFEC058A498621B2A86EDFE722EB3B5E51BE67CC8FB9184059`.

## 1. Kết luận từng finding

**5 CLOSED, 3 còn OPEN/PARTIAL.** Các vấn đề còn mở vẫn chặn gate; số test pass không thay thế acceptance từ dữ liệu và schema thực.

| Finding | Kết luận lần 2 |
|---|---|
| R56-01 — FVG confirmation | **PARTIAL / P1:** cold confirmation đã có, nhưng pending → confirmed không tiến triển; session policy vẫn reject blanket |
| R56-02 — OB validity/provenance | **OPEN / P1:** từ chối BOS canonical thật; departure yếu vẫn confirmed vì chỉ kiểm tra measurement status |
| R56-03 — S/D close-location | **CLOSED:** có directional threshold; probe BUY/SELL dưới/bằng/trên ngưỡng đạt expected |
| R56-04 — S/D duplicate base | **CLOSED:** chọn một base canonical/impulse, tie-break xác định; nested equal bounds không còn làm typed setup lỗi |
| R56-05 — Setup lineage | **PARTIAL / P1:** raw OB/FVG/S-D đã cùng setup; qua typed zone round-trip rồi grouping lại thành hai setup |
| R56-06 — Future history | **CLOSED:** availability lọc closed history trước assessment, giữ kết quả tại cutoff khi thêm future candles |
| R56-07 — Measurement evidence | **CLOSED:** adapter giữ measurement của cả ba family qua zone/setup; mất departure source được theo dõi riêng tại R56-05 |
| R56-08 — Detector retention | **CLOSED trong phạm vi detector:** budget M15 tăng thành 147; probe 15 phút thật giữ zone ở tuổi 79/80/81. Chưa phê duyệt expiry/lifecycle task 64 |

## 2. Các lỗi còn mở

### R56-01 — FVG pending bị khóa bởi reason từ cutoff trước

**Vị trí:** `core/smc_context.py:619`, `:645–660`.

Hàm mới giữ toàn bộ reason của input, chỉ bỏ `ZONE_CANDIDATE`, rồi yêu cầu `if not reasons` để xác nhận. Khi gọi sớm, output thêm `FVG_THIRD_CANDLE_NOT_CLOSED`. Đưa chính pending output này vào lượt kế tiếp sau third close thì reason cũ vẫn chặn promotion dù tất cả điều kiện hiện tại đã đạt.

Probe dùng actual candidate từ fixture gate 56, `formation_end_index=17`:

```python
early = confirm_fvg_candidate(raw, candles, timeframe='H1',
    as_of=candle_close_at(candles[16].time, 'H1'))
incremental = confirm_fvg_candidate(early, candles, timeframe='H1',
    as_of=candle_close_at(candles[17].time, 'H1'))
cold = confirm_fvg_candidate(raw, candles, timeframe='H1',
    as_of=candle_close_at(candles[17].time, 'H1'))
```

```text
incremental: candidate, ['FVG_THIRD_CANDLE_NOT_CLOSED']
cold:        confirmed
```

Candidate/confirmation là các seam tách riêng nên không thể dựa vào việc caller luôn bỏ state cũ và dựng raw candidate mới để làm đúng. Tương tự, `ZONE_CONFIRMED` không nên trở thành blocker nếu xử lý lại output đã confirmed. Phân biệt audit reason và điều kiện chặn hiện hành; terminal invalid/expired không được phục hồi ngoài policy.

**Phần policy chưa xử lý:** tại `core/smc_context.py:526`, mọi `session_gap` vẫn bị loại trước khi kiểm tra displacement. P5 quy định reject gap *chỉ do* session boundary, giữ gap có displacement hợp lệ. Probe H1 EUR/USD:

```text
2026-09-11 21:00 UTC  O/H/L/C = 101/102/99/100
2026-09-13 21:00 UTC  O/H/L/C = 100/106/99.8/105.5
2026-09-13 22:00 UTC  O/H/L/C = 105.5/107/103/106
tick=.1; ATR=5
```

Middle mở đúng close candle trước (không có price jump lúc mở phiên), body/range khoảng .887, close-location khoảng .919; gap [102,103] đạt minimum. Calendar trả `session_gap`, detector trả **0 candidate**. Đây chưa phân biệt session-only với displacement thật như yêu cầu lần 1. Nếu muốn reject tất cả session gaps phải trình thay đổi policy riêng, không tự thay semantics P5 bằng test hiện hữu.

**Đóng khi:** kiểm thử cold/incremental/idempotent confirmation cùng kết quả tại cùng cutoff, có BUY/SELL; waiting reason hết hiệu lực không chặn mãi. Bổ sung positive displacement qua closure, negative session-only và unknown metadata với expected theo P5.

### R56-02 — Không tương thích với BOS canonical và vẫn thiếu quality gate

#### A. BOS thật bị từ chối vì không có boolean ngoài schema

**Vị trí:** `core/smc_context.py:3234–3235`; đối chiếu `core/smc_models.py:674` và phần tạo BOS tại `core/smc_context.py:2736`.

Guard mới bắt buộc `raw_event.get('confirmed') is True`. Nhưng `detect_structure_bos` tạo event qua `SmcStructureEvent.to_dict()`, schema xuất `status='confirmed'` và `confirmed_at`, **không có boolean `confirmed`**. Vì vậy đường structure canonical đã duyệt không nối được vào OB confirmation mới.

Probe dùng gate40 BUY fixture, thay hai candle để tạo OB trước continuation break thực:

```text
index 23 O/H/L/C = 105.5/106/104/105  (base bearish)
index 24 O/H/L/C = 105/108/104.5/107  (departure bullish)
index 25 giữ nguyên = 105/115/105/113 (BOS phá continuation)
TF=H4; tick=.01; cutoff=close(index 25)
```

Chạy `replay_smc_structure` với default external width 5, causal ATR/tick buffer; chọn BOS đúng cutoff rồi truyền nguyên dict vào confirmation của actual OB departure index 24:

```text
OHLC validation errors: 0
event.status: confirmed
event.get('confirmed'): None
actual OB: candidate
control chỉ thêm {'confirmed': True}: confirmed
```

Control chỉ để cô lập nguyên nhân, **không phải yêu cầu sửa schema structure bằng cách thêm cờ tự tạo vào fixture**. Consumer cần đọc/validate đúng contract typed event. Test hiện tại dùng `_event()` tự gắn cờ nên bỏ lọt incompatibility này.

#### B. Measurement `status='ok'` không có nghĩa departure đủ chất lượng

**Vị trí:** `core/smc_context.py:3191–3200`.

`measure_departure` trả `ok` khi range/ATR đo được, không kiểm tra ngưỡng P3. Confirmation chưa dùng body/range, body/ATR hoặc directional close-location để quyết định đủ chuẩn.

Probe 15 candle warm-up `(100,100.5,99.5,100.1)`, rồi:

```text
base      = (100.1,101,99,100)
departure = (100,110,99.8,101.1)
next      = (101,112,100,111)
```

Actual detector có ATR hợp lệ, departure close vượt base. Với event mapping hợp lệ theo interface hiện tại ở next close:

```text
BUY:  body/range=.107843, directional close-location=.127451 -> confirmed
SELL mirror qua 100: cùng hai tỷ lệ                            -> confirmed
```

Cả hai đều dưới P3 `.50/.70`. Đây là kiểm thử quality guard độc lập bằng event mapping, không gọi event mapping ấy là bằng chứng BOS thực. Positive structure integration phải dùng evaluator như probe A.

**Đóng khi:** consumer tương thích canonical event; đầy đủ quality gate bắt buộc, finite/provenance hợp lệ, lifecycle/expiry tại cutoff theo schema thực. Giữ các guard IDs, timestamps và direction đã sửa. Không thêm sweep/FVG thành điều kiện bắt buộc. Regression phải dùng event từ evaluator, không chỉnh boolean hay measurement thủ công để positive test pass.

### R56-05 — Departure source bị mất qua typed zone, regroup tạo setup mới

**Vị trí:** field mapping `SmcZone` trong `core/smc_models.py`; fallback source tại `core/smc_context.py:3729–3733`.

FVG raw đã có `departure_source_id=middle.time`, đúng với OB/S-D. Tuy nhiên `SmcZone.from_dict(...).to_dict()` không giữ `departure_source_id`/`departure_source_time`. Grouping luôn tính lại setup ID và fallback về `departure_end`: FVG là third time, OB/S-D là middle time. Một setup lại bị tách sau typed round-trip.

Probe actual OB/FVG/S-D từ gate56 fixture:

```python
raw = [ob, fvg, sd]
restored = [SmcZone.from_dict(z).to_dict() for z in raw]
len(group_smc_zones_into_setups(raw))       # 1
len(group_smc_zones_into_setups(restored))  # 2
[z.get('departure_source_id') for z in restored]  # [None, None, None]
```

Existing `setup_id` còn trong model không cứu được vì `assign_setup_ids_to_zones` ghi đè nó bằng identity tính từ source thiếu. Sau rebuild/serialization, downstream có thể đếm hai setup từ cùng impulse và mất ổn định ID.

**Đóng khi:** typed zone bảo toàn canonical departure lineage và grouping không tái tạo identity khác do adapter mất field. Test raw → typed → serialized → restored → grouped, cùng cutoff và permutation: giữ setup ID/count, child IDs, original bounds, availability. Vẫn tách đúng khác source/direction; không sửa bằng overlap grouping.

## 3. Bằng chứng cho các finding đã đóng

- **R56-03:** đọc directional close-location guard; probe BUY/SELL mirror với base `(100,101,99,100.1)` ×3, departure `O=100,H=110,L=100,C=106.9/107/107.1`, avg range=2, ATR=10. Kết quả hai side đều candidate/confirmed/confirmed tương ứng `.69/.70/.71`; các gate khác đều đạt.
- **R56-04:** detector chọn theo `(base_range, consolidation_bars, base_start, zone_id)` trên cùng departure/direction. Regression nested 3/5/7/10 equal bounds tạo một child; `SmcSetup.from_zones` không còn duplicate-ID error.
- **R56-06:** `closed_history` được lọc theo close <= as_of rồi mới đánh giá coverage. Regression prefix 20 candle/full 70/future malformed OHLC giữ cùng coverage và usable tại cutoff cũ.
- **R56-07:** probe actual raw cả ba family qua `SmcZone` và `SmcSetup`: OB giữ departure measurement; FVG giữ gap/middle/session measurements; S/D giữ base measurement. Adapter cũng hỗ trợ departure measurement sau S/D confirmation. R56-05 vẫn riêng vì source identity không phải measurement.
- **R56-08:** dùng OHLC có actual BOS như §2A, đổi timestamps sang đúng M15, sau BOS append candle `(113,114,112,113)` không phá base. Ở age=79/80/81 có 105/106/107 candle, validation 0 lỗi; detector giữ cùng `zone_id=smcz-4ba6ccd6d9fdb1062290`, available_at `2026-09-07T06:30:00+00:00`. Để cô lập retention khỏi R56-02, confirmation control thêm boolean `confirmed=True` vào event canonical. Không coi control đó là end-to-end approval. Việc giữ record ở age=81 là đúng cho history; expiry/usable tại age=81 thuộc task lifecycle sau gate này.

## 4. Hồ sơ và tests cần sửa khi trình lại

### Fixture gate56 chưa chứng minh structure-to-zone pipeline

`tests/fixtures/smc_gate56_zone_pipeline.json` có 19 OHLC rows hợp lệ, nhưng không chứa event provenance như phần mô tả response khẳng định. Event trong tests do `_event()` tự dựng với chuỗi ID tùy ý. Chạy fixture bằng `replay_smc_structure(..., timeframe='H1', tick_size=.1)` cho **0 event**, không có BOS tại index 17.

Fixture có timeline index và history budget 69 nhưng chỉ 18 closed candle ở cutoff index 17; chưa có positive complete-history usable case. `test_r56_05...` chỉ group raw candidates, không chạy ba family qua confirmation → availability → typed serialization. Vì vậy chưa thể dùng fixture này để xác nhận detector không quá dễ hoặc reject gần hết zone.

Yêu cầu: một fixture/timeline tích hợp có structure event thật từ seam gate40, history đủ cutoff/lifetime, expected độc lập cho mỗi family và mỗi side; thể hiện open/close time, source event, confirmation/available_at, setup/child IDs. Không yêu cầu nối production.

### Test M15 hiện không kiểm tra đúng các boundary đã đặt tên

`tests/test_smc_gate56_review_regressions.py:230–260` dùng `_candles()` luôn tăng **1 giờ** (`:32`) nhưng gọi detector với M15. Chỉ tạo 102 candles nên `candles[:102]` và `candles[:103]` giống nhau. `as_of` luôn là close index 22, không phải cutoff cuối mỗi mốc L-1/L/L+1. Cần sửa để khóa thực sự regression retention đã được reviewer kiểm tra độc lập, không chỉ giữ tên test.

### Các phần hồ sơ đúng

- Header progress đã bỏ thông tin task 41 chưa bắt đầu, giữ gate56 CHANGES_REQUESTED và chờ review.
- Manifest 7/7 khớp, báo cáo cũ không bị sửa.
- Test task55 đã sửa candle append thành thời gian tương lai đúng thứ tự.
- Không thấy thay đổi gọi production builder sang detector mới; không suy ra rollout từ test pass.

## 5. Verification mới của reviewer

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
# 627 passed in 7.54s

$gateTests = @(rg --files tests -g '*task4[1-9].py' -g '*task5[0-5].py')
python -m pytest @gateTests tests/test_smc_gate56_review_regressions.py -q
# 54 passed in 1.25s

python -m py_compile core/smc_context.py core/smc_models.py
git diff --check
# Exit 0; Git chỉ cảnh báo LF/CRLF.
```

Các probe trong báo cáo chạy read-only bằng Python; không sửa expected/tests để hợp actual sai. Không tuyên bố chạy toàn repository, UI/live trading hoặc production acceptance.

## 6. Yêu cầu lần trình lại tiếp theo

1. Sửa R56-01, R56-02, R56-05 và bổ sung regression đúng schema/timeline; giữ CLOSED của năm finding còn lại và chạy regression tránh tái phát.
2. Thay positive OB mock bằng genuine canonical BOS trong integration fixture; sửa M15 timestamps, số candle và cutoff; thêm typed regroup và pending/cold parity.
3. Response map từng finding, báo command/count actual và manifest mới. Không sửa báo cáo lần 1 hoặc lần 2; progress ghi fixes ready chờ review, không tự APPROVED.
4. **Dừng gate56; chưa được task57 hoặc rollout production.**

## 7. SHA256 bản đã kiểm tra

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `2CE72588C47C10ED426343CAB2985A26B46DA4D0C1900587622F2D80D256399E` |
| `core/smc_models.py` | `B220981EE74D12809B1DFFD82C09979E4BBA74900EC0DD6E96A4B7881520BC4A` |
| `tests/test_smc_gate56_review_regressions.py` | `C2BB8288A0ED5ABEB19913AD6F977122039D1C65FBA19129DBC3A015F351F22C` |
| `tests/fixtures/smc_gate56_zone_pipeline.json` | `901CB4DF70C58C4533D6840AF0D4901CC3B7F6886D75875BBC44751DED1756F3` |
| `docs/plans/smc-task-56-response.md` | `847D5558097A6AC77AB270C6112652437352366E30AA3FEF120CD27545FFE76A` |

Các file còn lại của manifest Coder cũng đã kiểm tra khớp; quyết định gắn với working-tree content này, không chỉ HEAD.
