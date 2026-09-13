# Tech Lead review — gate 40, lần 3

**Quyết định: APPROVED cho gate 40. R40-01 đến R40-07 đều CLOSED trong phạm vi chặng B.**

- Reviewer: Codex, Tech Lead do người dùng chỉ định.
- Thời điểm: 2026-09-10 23:16 Asia/Saigon.
- Phạm vi lượt này: bốn finding R40-01/02/03/05 còn mở sau review lần 2, regression liên quan và tính toàn vẹn hồ sơ. Giữ kết luận CLOSED của R40-04/06/07; không tuyên bố chạy lại toàn bộ kiểm chứng của các vòng trước.
- HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`; branch thực tế `main`, working tree chưa commit. Quyết định gắn với nội dung file được kiểm tra, không chỉ HEAD.
- Manifest trình lại mới nhất: **13/13 file khớp**, digest `ECCE9848C1A5339BB9F806726F6921DF2327507F3D5E57C55399623E5AEC5A1F`. Manifest lần 1 trong response là lịch sử, không dùng để kiểm bản hiện tại.
- Response SHA256: `3BB2D0D462C0C439083F0B0572E7DA1AC77E22A50994D2C04B93F400C4D24A55`.
- Báo cáo gate 40 gốc giữ SHA256 `7A7D996EE36AA1017B5D00B6CDC0B997B22B0B44FC180C392130A49554A9F329`; báo cáo lần 2 giữ SHA256 `39FF4BBECA0D0DDFC7C432EA0FDDC608B14A8C4741736ACED250915D2C6ABB52`.
- Toàn bộ 41 đường dẫn đầu vào liệt kê trong manifest của báo cáo lần 2, hash lại trên bản hiện tại, cho digest `A142F6A0F236ED1A1F53270BDA481DCDEB527B8E81373CECDADC9022A3DE0126`. Phương pháp: SHA256 uppercase + hai khoảng trắng + repo-relative path; sort path, join LF không newline cuối, SHA256 UTF-8. Báo cáo này không nằm trong aggregate.

## Kết luận từng finding

| Finding | Kết quả |
|---|---|
| R40-01 | CLOSED: valid OHLC/order, external width 5, causal ATR/tick buffer và eventful replay/restart acceptance |
| R40-02 | CLOSED: reversal tại/sau expiry bị chặn cả khi không truyền as_of |
| R40-03 | CLOSED: public production dùng lại internal/leg-count legacy; probe full payload khớp HEAD |
| R40-04 | Giữ CLOSED: dữ liệu sau cutoff không ảnh hưởng structure tại cutoff cũ |
| R40-05 | CLOSED: typed round-trip giữ provisional/width/scope, không promote fallback thành usable |
| R40-06 | Giữ CLOSED: interval canonical và ATR temporal bounds của snapshot |
| R40-07 | Giữ CLOSED: metadata numeric/string phân biệt trong cache key |

Không còn finding chặn gate trong bản sửa được trình lại.

## Bằng chứng kiểm tra mới

### R40-01 — evaluator và acceptance canonical

- Đọc `core/smc_structure_replay.py`: không tự sort/bỏ record sai; lọc eligible tại cutoff rồi gọi `require_valid_smc_candles`. External mặc định width 5; width 2 mang provisional và không usable. Buffer lấy từ ATR trước event cùng timeframe và tick metadata; static buffer chỉ là assertion phải khớp giá trị causal.
- Parse fixture v2 và chạy validator độc lập: **BUY 53 nến, SELL 62 nến, không lỗi OHLC**.
- Chạy evaluator với default width 5: mỗi side có **5 event**; BUY kết thúc bearish, SELL kết thúc bullish, khớp expected. Width 2 cho **0 event** ở cả hai side.
- Probe đảo thứ tự/duplicate bị `SmcCandleDataError`; record không phải Candle bị `ValueError`. Không silently sửa input.
- Test cold từng cutoff so event IDs cùng direction, source BOS, tracked continuation, protected ID/level; test future malformed OHLC giữ kết quả tại cutoff cũ.
- Task-39 restart dùng timeline có event/protected thực thay chuỗi tăng đơn điệu rỗng. Cache store/producer vẫn chưa tích hợp và không phải điều kiện bổ sung ở gate này.

### R40-02 — expiry không phụ thuộc optional cutoff

Đọc guard mới sau khi chọn reversal candle: nếu không truyền as_of, dùng chính close time để chặn `occurred >= expires_at`.

Probe độc lập BUY và SELL từ helper hiện có: BOS ngày 08/01, candidate ngày 10/01, reversal close ngày 18/01 sau deadline 17/01 04:00. Cả bốn cách gọi (hai side × có/không as_of) đều trả **confirmed=false, candidate_status=expired**. Các regression reclaim và terminal confirmed trước đó tiếp tục pass.

### R40-03 — production parity với baseline

- `_smc_for_timeframe` dùng `_legacy_detect_internal_structure` và `_legacy_count_trend_legs`; legacy external payload được giữ.
- Probe nạp module `HEAD:core/smc_context.py` vào bộ nhớ, so với working-tree module qua **public `build_smc_context`**. Dữ liệu OHLC hợp lệ gồm 200 candle/TF, sinh bằng `random.Random(40)`, timestamp cách nhau đúng D1/H4/H1 tương ứng; symbol EURUSD.
- **Toàn bộ public payload bằng HEAD** cho cả D1/H4/H1. Mỗi TF có 14 internal highs, nên kiểm chứng đi qua nhánh từng mất `time`/gắn sai timeframe, không chỉ test nến phẳng.
- Không sửa producer, scorer, entry hoặc risk trong lượt review. Đây là regression trên synthetic input, không phải live runtime rollout acceptance.

### R40-05 — bảo toàn provisional qua typed model

Probe `SmcSwing.from_dict(raw).to_dict()` trên external width-2 đã đủ right bars nhưng provisional cho kết quả:

```text
provisional=True
confirmed=True
usable=False
scope=external
pivot_width=2
```

Model giữ blocker độc lập với confirmed_at. Các test canonical confirmed bootstrap và unconfirmed payload đều pass; không cần chèn lại flag sau deserialize.

## Regression đã chạy

```powershell
$smcTests = @(rg --files tests -g 'test_smc*.py')
python -m pytest @smcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q
```

**573 passed in 6.10s** — kết quả mới của Tech Lead, không dùng số 5.94s của coder làm kết quả tự chạy. `git diff --check` không có whitespace error, chỉ cảnh báo LF/CRLF.

Không chạy toàn bộ repository test suite, UI, live broker, performance nghiệm thu hoặc dispatch giao dịch. Các kiểm tra tích hợp tiếp theo vẫn phải thực hiện đúng task/gate, không được suy ra từ kết quả unit/context seam ở đây.

## Quyền tiếp tục và giới hạn

1. **Gate 40 APPROVED** cho đúng bản code/hồ sơ được hash ở trên. Gate 16 vẫn APPROVED; các báo cáo CHANGES_REQUESTED cũ là lịch sử.
2. Coder cập nhật **progress và response** sang trạng thái bàn giao APPROVED, dẫn báo cáo này trước khi tiếp tục, để không còn hiển thị blocker cũ như trạng thái hiện tại. Nếu cập nhật manifest bàn giao, giữ nguyên digest lịch sử được duyệt trong báo cáo này.
3. Được triển khai **task 41–55** trên nhánh làm việc theo kế hoạch: zone/setup models, detectors, available_at, grouping và tests. **Dừng tại task 56 để Tech Lead review**; không làm task 57 trước khi gate 56 được APPROVED.
4. Không tự nối evaluator/detector mới vào Analyze/Scanner production, bỏ các gate tiếp theo hoặc bật auto-entry. Phê duyệt chặng B không phải phê duyệt rollout.
5. Thay đổi semantics/threshold đã duyệt phải trình lại phần chịu ảnh hưởng; không dùng APPROVED này cho nội dung code khác manifest mà chưa kiểm tra.

Lượt này chỉ tạo báo cáo review; không sửa runtime, fixture, test, progress, response hoặc báo cáo cũ, và không tự triển khai task 41.
