# Tech Lead review — gate 56, lần 1

**Quyết định: CHANGES_REQUESTED. Chưa được làm task 57.**

- Reviewer: Codex, Tech Lead theo yêu cầu người dùng.
- Thời điểm: 2026-09-11, khoảng 03:22 Asia/Saigon.
- Phạm vi: phần triển khai task 41–55, đối chiếu hai kế hoạch SMC, zone spec, parameter table và acceptance dossier. Task 56 là mốc Tech Lead review, không tự hoàn tất bằng việc Coder đánh dấu các task trước đó DONE.
- HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`; branch `main`; implementation và hồ sơ còn trong working tree, nhiều file untracked.
- Không sửa implementation, tests của Coder, progress, specs hay các báo cáo cũ trong lượt này. Chỉ thêm báo cáo review này.
- Giữ nguyên quyết định gate 16/gate 40 đã APPROVED. Không yêu cầu rollout production hoặc triển khai lifecycle task 57–65 để giải quyết các lỗi detector dưới đây.

## 1. Kết luận

Có **8 finding cần sửa: 4 P1 và 4 P2**. Bộ test hiện tại pass nhưng chưa đủ chứng minh acceptance của gate 56: positive FVG không có đường confirmed, OB thiếu guard, cùng impulse bị tách setup, và availability dùng future history.

| ID | Mức | Vấn đề | Task liên quan |
|---|---|---|---|
| R56-01 | P1 | FVG đủ chuẩn vẫn luôn candidate, không có confirmed/available_at | 45–47, 52, 54 |
| R56-02 | P1 | OB promote dù thiếu dữ liệu bắt buộc hoặc event không hợp lệ/không causal | 43–44, 54 |
| R56-03 | P2 | S/D bỏ qua close-location bắt buộc | 42, 49, 54 |
| R56-04 | P2 | S/D trả nhiều base cùng impulse, có thể trùng zone_id và làm typed setup lỗi | 48, 50–51, 55 |
| R56-05 | P1 | OB/FVG thực tế cùng impulse bị gán hai setup khác nhau | 45, 50, 55 |
| R56-06 | P1 | Availability dùng cả nến sau as_of để quyết định đủ history | 52 |
| R56-07 | P2 | Evidence của detector mất khi qua model zone/setup | 41, 51 |
| R56-08 | P2 | Window 80 nến làm mất OB M15 còn trong lifetime khi rebuild | 53, 55 |

## 2. Findings và điều kiện đóng

### R56-01 — FVG hợp lệ không bao giờ được xác nhận

**Vị trí:** `core/smc_context.py:470`, đặc biệt `:557–568`.

`detect_fvg_candidates` đo gap, session continuity và middle quality, nhưng mọi kết quả đều có `lifecycle_status=candidate`, `confirmed_at=None`, `available_at=None`. Tìm trong `core` không có bước confirmation FVG mới hoặc consumer của `middle_quality_eligible` thực hiện việc promote. `apply_zone_availability` tiếp tục giữ chúng ở waiting confirmation. Legacy `detect_fvg` không phải đường hoàn tất contract mới.

Probe ba H1 candle hợp lệ, symbol EUR/USD, bắt đầu 2026-09-07 00:00 UTC; mỗi dòng là `(open, high, low, close)`:

```text
00:00  (101,   102, 99,   100)
01:00  (100,   106, 99.8, 105.5)
02:00  (105.5, 107, 103,  106)
tick=.1; ATR_before_event=5
gap=[102,103]; middle_quality_eligible=True
actual: lifecycle_status=candidate, available_at=None
expected: confirmed tại 03:00 UTC, available_at=03:00 UTC
```

Zone spec §4 xác nhận FVG ngay tại close nến thứ ba nếu đủ điều kiện, không chờ BOS/sweep. Đây là bỏ toàn bộ positive FVG ở đường mới, không chỉ thiếu tối ưu detector.

**Đóng khi:** có đường thuần candidate → family confirmation → availability dùng được, kiểm tra cutoff và đủ toàn bộ gate. Test BUY/SELL cần assert trạng thái/timestamp thực, không chỉ `direction` hoặc output của measurement helper. Giữ tiny/weak/wrong-direction/unknown-session không confirmed. Đối chiếu thêm P5: policy phân biệt session-only gap với displacement hợp lệ, không mặc định mọi chuỗi qua giờ nghỉ đều là cùng một trường hợp.

### R56-02 — Confirmation OB không kiểm tra đủ validity và causal provenance

**Vị trí:** `core/smc_context.py:3036`, đặc biệt `:3083–3121` và `:3141–3153`.

Confirmation chỉ tìm dict có nhãn BOS/cùng direction/confirmed_at và association gần index. Nó không chặn measurement thiếu ATR, thiếu event/broken-level ID, event đã invalidated; nhánh có index không đối chiếu timestamp với departure close. Nhánh không index dùng tối đa `3*24*60` phút khi có candles, không phải ba bar của source timeframe; khi không có candles còn không có upper bound thời gian.

Dùng OB từ fixture R56-01 (base index 0, departure index 1, measurement báo ATR unavailable), cung cấp BOS bullish index 2, confirmed tại 03:00 UTC:

| Biến thể probe độc lập | Actual |
|---|---|
| Có event_id/broken_level_id nhưng formation ATR thiếu | `confirmed`, body_atr vẫn `None` |
| Event thêm `invalidated=True`, `invalidated_at=03:00`, as_of=03:00 | Vẫn `confirmed` |
| Index vẫn 2 nhưng occurred_at/confirmed_at backdate về 00:00 | `confirmed`, available_at=00:00, trước departure |
| Bỏ event_id và broken_level_id | `confirmed`, confirmation_event_id chuỗi rỗng |
| Bỏ occurred_index; occurred_at 24 giờ sau departure H1; truyền candles | Vẫn `confirmed`, dù quá cửa sổ ba bar |

Zone spec §1/§3 yêu cầu missing required data fail closed, event IDs, close time causal và không nâng lại từ event reclaim/invalidated. Những dict bị lỗi không được tự coi như event đã qua typed boundary; hàm đang công khai nhận mapping và tự làm một phần validation.

**Đóng khi:** dùng/validate provenance chuẩn của structure event, timestamp/index/source-TF nhất quán, association theo đúng bar đóng của timeframe; chặn missing required data và terminal event tại cutoff. Áp các quality gate bắt buộc từ P3 hoặc giữ unavailable trước khi promote; không thêm sweep/FVG thành điều kiện bắt buộc. Có tests valid warm-up + genuine event, missing IDs/ATR, invalidated/reclaimed, mismatch timestamp/index, timestamp-only late event và BUY/SELL. Xác định rõ boundary event close bằng departure close theo contract, không thay bằng so sánh open time.

### R56-03 — S/D bỏ qua close-location

**Vị trí:** `core/smc_context.py:3448–3467`.

`measure_departure` đã tính close-location nhưng confirmation chỉ kiểm tra close ngoài base, body/range, body/ATR và efficiency. Zone spec §5 và P3 còn yêu cầu BUY close-location >= .70 / SELL <= .30.

Probe H1 dùng base:

```text
(100,   100.4, 99.8, 100.1)
(100.1, 100.5, 99.9, 100.2)
(100.2, 100.3, 99.9, 100)
departure=(100, 103, 100, 101.8)
average_range_before_departure={3: .6}; ATR_before_event=2
```

BUY có body/range=.60, body/ATR=.90, efficiency=5, close-location=.60 và close > base high. **Actual confirmed**, dù close-location không đạt. Mirror qua giá 100 bằng `(200-O, 200-L, 200-H, 200-C)` cho SELL close-location=.40, cũng **confirmed**.

**Đóng khi:** áp directional close-location trong confirmation, reason rõ; test dưới/bằng/trên ngưỡng ở cả hai chiều với các điều kiện khác đều đạt. Không dùng wick-only case đang fail body/range để thay thế test riêng cho close-location.

### R56-04 — Không chọn/deduplicate base S/D trên cùng impulse

**Vị trí:** `core/smc_context.py:3291–3370`; lỗi lộ ra khi gọi `SmcSetup.from_zones`.

P6 yêu cầu chọn base hẹp nhất trên cùng impulse. Detector hiện append tất cả các base 3/5/7/10 đạt compression. ID dùng cùng thời gian base cuối và bounds, nên nested bases cùng bounds có ID trùng, trong khi typed setup bắt child ID unique.

Probe H1: 10 candle `(100,100.5,99.5,100.1)` rồi departure `(100,103,100,102.8)`; `average_range_before_departure={10:1}`, ATR=2:

```text
candidates tại departure index 10: 4
unique zone_id: 1
confirmation: ['confirmed', 'confirmed', 'confirmed', 'confirmed']
SmcSetup.from_zones(confirmed, ...):
ValueError: SMC setup child_zone_ids must be unique
```

**Đóng khi:** chọn base canonical theo policy hẹp nhất với tie-break ổn định, deduplicate trước tạo child; vẫn giữ audit evidence của các lựa chọn nếu cần. Test nested equal/different bounds, permutation và add-prefix; chạy qua detector → confirmation → typed setup, không chỉ mock danh sách child có ID khác nhau.

### R56-05 — FVG dùng third candle làm setup source, khác OB của cùng impulse

**Vị trí:** `core/smc_context.py:522–539`, `:3530–3553`.

FVG tạo setup từ `third.time`, OB tạo setup từ departure candle ngay sau base — chính middle candle của FVG. Grouping chỉ hash source string bằng nhau; không có bước resolve nguồn displacement chung. Với ba candle R56-01:

```text
OB departure source  = 2026-09-07T01:00:00+00:00
FVG departure source = 2026-09-07T02:00:00+00:00
group_smc_zones_into_setups([OB, FVG], symbol='EUR/USD', timeframe='H1')
actual setup count = 2
expected = 1, vì cùng bullish impulse ở middle candle
```

Không được sửa bằng cách gộp mọi zone gần nhau hoặc overlap. Cần tách source impulse ổn định khỏi thời điểm pattern FVG hoàn tất/available_at. Hiện tests task 50/55 tự gán `departure_end='event-1'` cho mọi family nên không kiểm chứng association thực.

**Đóng khi:** detector/association cung cấp lineage chung thực sự; integration fixture OB/FVG/S-D cùng impulse chỉ một setup, khác impulse hoặc direction vẫn riêng. FVG chưa đóng nến thứ ba không xuất hiện ở cutoff sớm; thêm child sau này không đổi ID/bounds/available_at của child cũ.

### R56-06 — Future candles làm availability tại cutoff cũ thay đổi

**Vị trí:** `core/smc_context.py:3631–3668`.

Hàm nhận `as_of` nhưng truyền toàn bộ `candles` vào `assess_smc_history`. Helper history yêu cầu caller đã lọc closed candles; availability hiện không làm bước đó. Nó chỉ dùng cutoff để so `available_at`.

Probe tái sử dụng `_candles`/`_zone` trong `tests/test_smc_zone_availability_task52.py`:

```python
c = _candles(70)
z = _zone(c, origin_index=10, available_index=15)
cutoff = candle_close_at(c[19].time, 'H1')
# apply_zone_availability([z], history, timeframe='H1',
#                         symbol='EUR/USD', as_of=cutoff)
```

| History truyền vào, cùng zone và cutoff | raw_count | usable |
|---|---:|---|
| `c[:20]` | 20 | False |
| `c` gồm thêm 50 nến tương lai | 70 | True |

Đây là look-ahead tại helper mới, không quy kết toàn bộ production/backtest. Future candle đã bù warm-up/lifetime chưa có tại cutoff.

**Đóng khi:** lọc/validate closed prefix tại boundary nhận as_of, hoặc enforce một input snapshot đã freeze và từ chối dữ liệu ngoài cutoff. Positive/negative prefix test phải bất biến khi nối future valid/invalid candles. Không silently dùng full array để báo complete history.

### R56-07 — Mất formation evidence ở typed round-trip

**Vị trí:** `core/smc_models.py:1015`, `:1388`; output detector trong `core/smc_context.py:3029`, `:564–567`, `:3361`.

Các detector lưu `departure_measurement`, `base_measurement`, `gap_measurement`, `middle_measurement`, `session_continuity` ở top level. `SmcZone.from_dict` và `SmcSetup.from_zones` chỉ đọc khóa `evidence`. Không có adapter nối hai schema.

Probe OB thực từ R56-01:

```text
raw departure_measurement tồn tại: True
SmcZone.from_dict(raw, ...).to_dict()['evidence']: None
departure_measurement còn trong serialized zone: False
SmcSetup.from_zones([raw], ...).children[0].evidence: None
```

Evidence hình thành/nguồn ATR cần cho downstream quality và audit không còn, trái điều kiện task 51 giữ evidence riêng từng child. Tests hiện truyền sẵn `evidence` nên không phát hiện mismatch producer/model.

**Đóng khi:** thống nhất schema evidence hoặc adapter canonical có nguồn; round-trip actual OB/FVG/S-D giữ đầy đủ measurement, references, IDs và reasons. Thêm kiểm tra typed children qua serialization; không lấy ATR/current candles để tái dựng evidence đã mất.

### R56-08 — Detector history vẫn cắt 80 bar, mất OB M15 chưa hết lifetime

**Vị trí:** `core/smc_context.py:2954`; FVG cũng dùng window cố định tại `:483`.

Tách top-K output là đúng, nhưng `retain_zone_history_candidates` chỉ sao chép những candidate detector còn trả về. OB vẫn bỏ mọi departure ngoài 80 bar cuối, trong khi M15 lifetime 80 được tính từ available_at, chưa kể độ trễ confirmation. Cold rebuild vì thế có thể mất zone còn hiệu lực dù input đủ history.

Probe M15, timestamp liên tục mỗi 15 phút từ 2026-09-07 00:00 UTC:

```text
20 candle (100,101,99,100)
base       (101,102,99,100)       # index 20
departure  (100,106,99.8,105.5)   # index 21
các candle tiếp (105,106,104,105), không phá base

detect_order_block_candidates(c[:101], ...): 1 candidate
detect_order_block_candidates(c[:102], ...): 0 candidate
```

Khi thêm candle index 101, departure mới cách 80 bar và nếu BOS xác nhận ở index 22 thì tuổi tính từ confirmation còn dưới 80. P7 quy định chỉ stale khi `age > lifetime`. Việc candidate mất khỏi detector không phải expiry hợp lệ và không được hàm retention phía sau khôi phục.

**Đóng khi:** history window có định nghĩa theo lifetime + formation/confirmation/warm-up context, đủ cold replay; output top-K tách biệt. Test M15 tại L-1/L/L+1, có BOS/available_at thực, cold rebuild so incremental, đủ input history và không invalidation. Không yêu cầu triển khai toàn bộ lifecycle trước gate này, nhưng detector phải cung cấp đủ nguồn cho task tiếp theo.

## 3. Test và hồ sơ acceptance

### Đã chạy

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
# 619 passed in 9.17s

$gateTests = @(rg --files tests -g '*task4[1-9].py' -g '*task5[0-5].py')
python -m pytest @gateTests -q
# 46 passed in 1.16s

git diff --check
# Exit 0; chỉ cảnh báo LF/CRLF của Git, không whitespace error.
```

Ngoài pytest đã chạy các Python probe read-only được mô tả ở từng finding. Đây là quan sát actual/expected độc lập; không ghi chúng thành test khẳng định hành vi sai là chuẩn. Chưa chạy toàn bộ test repository, live trading, UI/chart hay production rollout acceptance.

### Những thiếu sót cần khắc phục trong lần trình lại

- Task 54 chủ yếu kiểm tra candidate direction/measurement và vài negative; chưa khóa positive confirmed → available → grouped typed child end-to-end cho cả ba family, cả BUY/SELL.
- Test identity tại `tests/test_smc_zone_identity_task55.py:34` và `:54` gọi lại `_candles` cho candle append, nên timestamp reset về ngày/giờ đầu thay vì nến tương lai. Sửa fixture thành chuỗi hợp lệ rồi mới kiểm tra prefix invariance; validation không được bỏ qua lỗi order/duplicate để test xanh.
- Task 56 yêu cầu fixture và chart/timeline. Hiện progress dừng ở task 55 chờ review; chưa thấy hồ sơ gate 56 riêng trình raw OHLC, event/zone/setup timeline và expected độc lập. Cần bổ sung timeline tái lập được với open/close time, formation/departure, confirmation, available_at, cutoff, zone_id/setup_id và history budget. Không cần nối production để trình fixture này.
- Header progress còn nói task 41 chưa bắt đầu trong khi bảng đã DONE tới 55. Coder cần đồng bộ trạng thái bàn giao thành gate 56 CHANGES_REQUESTED theo báo cáo này; giữ lịch sử gate 16/40, không sửa báo cáo review cũ.

## 4. Yêu cầu trình lại

1. Sửa R56-01…R56-08 trong phạm vi detector/model/availability/grouping hiện tại, không tự đổi công thức hay nới threshold trong spec để hợp code.
2. Thêm regression từng finding và một fixture tích hợp có input OHLC hợp lệ, event provenance từ structure seam đã duyệt, cả BUY/SELL. Khóa boundary cutoff, family confirmation, identity và typed evidence; có timeline cho Tech Lead kiểm tra.
3. Chạy lại 46 tests chặng này sau khi mở rộng và bộ regression 619-test command ở trên; báo actual test count/command, không chỉ câu “all pass”.
4. Thêm response mapping từng ID → files/tests/evidence, manifest/hash bản sửa và đồng bộ progress. Không tự đặt APPROVED.
5. Dừng tại gate 56, chờ Tech Lead review lại. **Không triển khai task 57 hoặc rollout production.**

## 5. Dấu vân tay nguồn đã review

SHA256 trên nội dung working tree tại lượt kiểm tra; HEAD một mình không đại diện bản code này.

| File | SHA256 |
|---|---|
| `core/smc_context.py` | `8D779A124843C16EA54B5F732EB98ADEA55E7D0F0E58A4E32B93ACE192C8E3CF` |
| `core/smc_models.py` | `3E6162071393ABF6B149233A1A8921A98B51B9BD2FF63D5374FF1E187AB533BD` |
| `core/smc_history.py` | `5B3FD1F9665C339CE0F809AFA2DA9C707B80FF9D4C542CAB10C7D783A1436639` |
| `docs/plans/smc-zone-spec.md` | `C609A6E50A7B3FB865F5FE0AF0BF6137F2EA424EA4D060CB7F07EB0B6C34D766` |
| `docs/plans/smc-parameter-table.md` | `C4A3C1C7785010E3DD6E82D3312C61689D0D3A0D3B9218415EA53E1826A11FC1` |
| `docs/plans/smc-implementation-progress.md` | `E360BFF23A08BB788316E157367A9905FD8C0E92D7DCE216532D16EC520F2F20` |
