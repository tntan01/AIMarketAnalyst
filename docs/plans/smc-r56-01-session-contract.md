# R56-01 — Contract nguồn FVG qua session closure

**Trạng thái: CONTRACT CHỐT BỞI TECH LEAD theo yêu cầu người dùng ngày 2026-09-11; IMPLEMENTATION PENDING / acceptance RED.**

Chốt contract không phải APPROVED gate56. Bảy finding đã CLOSED giữ nguyên; chỉ triển khai phần R56-01 này rồi trình lại Tech Lead. Không task57, không rollout production.

## 1. Quyết định và phạm vi

P5 trước đây chỉ ghi “reject gap chỉ do session boundary; giữ gap có displacement hợp lệ”, thiếu định nghĩa tính toán. Tài liệu này **bổ sung một quy ước kỹ thuật mới, công khai**, không giả vờ công thức bên dưới đã tồn tại trong spec cũ. Nó là nguồn quyết định hiện tại cho session-origin và thay các diễn giải mâu thuẫn về open equality/strict range trong các vòng review.

Không thay ngưỡng gap `max(2*tick, .10*formation_ATR)`, middle body/range `.50`, close-location BUY `.70` / SELL `.30`, direction, original bounds, setup source, available_at hay lifecycle. Không suy ra tick path/giá đã giao dịch từng mức liên tục từ OHLC. “Có bằng chứng displacement” dưới đây là nhãn vận hành dựa trên OHLC, không phải khẳng định nguyên nhân lịch sử hay hiệu quả giao dịch.

Bộ bàn giao:

- Golden cases: `tests/fixtures/smc_r56_01_session_acceptance.json`.
- Acceptance executable: `tests/test_smc_r56_01_session_acceptance.py`.
- Coder handoff/result: `docs/plans/smc-r56-01-coder-handoff.md`.

## 2. Quy tắc tính toán duy nhất

### 2.1 Input và geometry

Xét đúng ba candle `first, middle, third`, cùng symbol/timeframe, timestamp aware tăng nghiêm ngặt, OHLC finite hợp lệ. Chỉ đánh giá formation hoàn tất trên prefix đóng ở cutoff; helper geometry không tự fetch hoặc dùng clock hiện tại. Không sửa input sai, không chèn missing candles. Lịch phiên dùng calendar/helper đã có.

Gap gốc `G=[gL,gH]`, `gL < gH`:

- BUY: `[first.high, third.low]`.
- SELL: `[third.high, first.low]`.

Đoạn bằng chứng theo hướng từ middle, **không phụ thuộc vị trí middle.open so với range cũ**:

- BUY: `D=[middle.low, middle.close]`.
- SELL: `D=[middle.close, middle.high]`.

Chọn cực trị ngược hướng → close vì close là điểm cuối đã biết của candle; không giả định high xảy ra trước low hay reconstruct tick sequence. Middle vẫn phải qua body/range, direction và close-location ở bước quality riêng. Vì vậy dùng D không cho phép wick-only bypass quality.

### 2.2 Thứ tự quyết định

1. Dữ liệu sai hoặc không có gap dương: không đánh giá nguồn như một FVG hợp lệ; fail closed.
2. Calendar báo missing candle trong phiên (`unexpected_gap`): `invalid`, không promote dù D bao phủ G.
3. Calendar không đủ biết khoảng trống có phải nghỉ phiên (`unknown`): `unknown`, không promote dù D bao phủ G.
4. `continuous`: **giữ policy FVG cũ**, không thêm containment gate D/G cho chuỗi liên tục. Origin accepted; gap minimum/middle quality vẫn kiểm riêng.
5. Known `session_gap` (closure ở first→middle, middle→third, hoặc nhiều cặp nếu calendar đủ chứng minh): xét D/G bằng bảng sau. Không veto riêng vị trí closure hay reopen open jump.

| Điều kiện, theo thứ tự | status | accepted | reason |
|---|---|---:|---|
| `D.low <= gL` và `D.high >= gH` | `displacement` | true | `FVG_SESSION_DISPLACEMENT_CONFIRMED` |
| `min(D.high,gH) <= max(D.low,gL)` — giao nhau không có độ rộng dương | `session_only` | false | `FVG_SESSION_ONLY_GAP` |
| Còn lại — giao nhau dương nhưng không bao phủ toàn bộ | `unknown` | false | `FVG_SESSION_ORIGIN_AMBIGUOUS` |

`session_only` nghĩa vận hành: không có phần gap độ rộng dương được đoạn displacement D chứng thực trong chuỗi có closure; không khẳng định có tick-level causal proof. Partial không bị gắn nhãn session-only hoặc confirmed; cần dữ liệu chi tiết hơn nhưng bản này không fetch thêm, trả unknown.

**Boundary chốt:** containment dùng `<=`/`>=` inclusive; D bằng G đạt. Chỉ chạm tại một endpoint không đạt coverage. Không đưa open equality hay open strictly-inside-range trở lại thuật toán. Không crop original gap về phần D giao G để đạt điều kiện.

**Độ chính xác:** so sánh trên giá numeric đã validate của input; không thêm epsilon/tolerance hay round theo tick vào phép containment này. Equality của input đạt; giá lệch thật dù nhỏ không được silently biến thành equality. Các fixture boundary dùng số biểu diễn chính xác; mirror fixture qua Decimal để tránh tự tạo sai số float ở test. Gap minimum vẫn dùng tick/ATR theo P5 hiện tại, không đổi policy rounding của các thành phần khác.

### 2.3 Quality và cutoff là gate độc lập

Origin accepted **không đủ** để confirmed: minimum gap, middle direction/body/range/close-location và required tick/ATR đều phải đạt. Không có requirement BOS/sweep mới.

- Missing/invalid tick/ATR hoặc tiny gap: không candidate FVG đủ chuẩn, không thay bằng current/future ATR.
- Weak/wrong-direction/range-zero middle: không confirmed; có thể giữ raw candidate audit như interface cũ.
- `available_at = confirmed_at = close(third)`; trước close đó vẫn pending.
- Pending → đủ cutoff phải bằng cold confirmation; repeated confirmation idempotent; invalid/expired không phục hồi.
- Append nến tương lai không thay ID/bounds/source hoặc confirmation tại cutoff cũ.

## 3. Interface kiểm chứng và evidence

Thêm một helper thuần nhỏ ở `core/smc_context.py`, không framework/service mới:

```python
classify_fvg_session_origin(
    candles: Sequence[Candle],  # đúng ba candle; caller sở hữu cutoff
    *, timeframe: str, symbol: str,
) -> dict
```

Helper trả tối thiểu:

```text
status: continuous | displacement | session_only | unknown | invalid
accepted: bool  # chỉ origin; không thay quality/tick/ATR gates
reason_codes: list[str]
gap_bounds: {low, high} | None
```

Quy tắc phụ:

- Continuous: `status=continuous`, `accepted=true`, reason `FVG_SESSION_CONTINUOUS`.
- Calendar unknown: `status=unknown`, false, reason `SESSION_GAP_UNKNOWN`.
- Unexpected gap: `status=invalid`, false, reason `FVG_CANDLE_GAP_UNEXPECTED`.
- No positive gap: `status=invalid`, false, `gap_bounds=None`, reason `FVG_NO_GAP`.
- Wrong argument shape/timeframe hoặc invalid OHLC/order/timestamp: dùng ValueError/SmcCandleDataError theo validation có sẵn, không sort/sửa dữ liệu. Timeframe normalize theo helper hiện có.
- Helper không tính ATR/tick minimum hoặc middle quality; detector thực hiện các gate đó như trước. Tránh mỗi caller diễn giải lại nguồn gap bằng logic khác.
- Có thể thêm D/continuity cho audit, không được đổi meaning các field tối thiểu. Tests không bắt code layout/thuật toán nội bộ.

`detect_fvg_candidates` gọi helper cho formation; origin không accepted thì không trả nó trong danh sách candidate để confirmation. Kết quả unknown/rejected vẫn có thể được caller audit trực tiếp qua helper, không bị ép thành boolean không lý do.

Candidate mới lưu nguyên diagnostic vào `evidence.session_origin`; giữ qua `SmcZone` round-trip. Có thể duy trì `session_continuity` và `session_displacement_eligible` legacy để tương thích nhưng chúng không được tạo authority song song. `confirm_fvg_candidate` không được promote payload có `evidence.session_origin.accepted=false` chỉ vì legacy eligible=true; trả reason origin hiện hành. Không tự bypass contradiction bằng cách bỏ evidence hoặc dựng lại current-data result khác. Contract này không yêu cầu nâng cấp persisted records production cũ trước gate56.

Tách helper nhằm giải thích được `unknown/session_only` ngay cả khi detector không trả candidate. Đây là phần mở rộng interface được Tech Lead chốt trong lượt này; Coder không phải đoán một API hay reason mới.

## 4. Golden matrix — expected độc lập

Fixture có 14 case gốc BUY, mỗi case mirror SELL. Các input rows, gap bounds và expected status/reason được ghi tay; test không tính expected từ output implementation.

| Case ID | Expected origin | Confirmed sau third close? |
|---|---|---:|
| reopen_inside | displacement | Có |
| reopen_at_edge_old_false_negative | displacement | Có |
| reopen_outside_then_reenter | displacement | Có |
| round4_one_tick_reopen | displacement | Có |
| full_coverage_equal_endpoints | displacement | Có |
| closure_before_third_but_middle_covers_gap | displacement | Có |
| session_only_third_reopen | session_only | Không |
| session_only_middle_reopen | session_only | Không |
| session_only_touch_is_not_coverage | session_only | Không |
| partial_coverage_at_low | unknown | Không |
| partial_coverage_at_close | unknown | Không |
| continuous_keeps_existing_policy | continuous | Có |
| unknown_calendar | unknown | Không |
| unexpected_missing_candle | invalid | Không |

Matrix chính cố ý cho gap minimum và middle quality **đều đạt** để lỗi nguồn không bị gate khác che. Tests riêng kiểm missing tick/ATR, gap minimum dưới/bằng/trên, weak/wrong-direction/zero-range, cutoff, repeat, terminal, future identity và typed evidence.

## 5. Đính chính fixture cũ và quyền thay đổi expected

Negative cũ của task47 và task54 dùng reopen=first.high, nhưng middle low quay vào range và close vượt toàn bộ gap; theo contract này đó là **positive**, không phải session-only. Tech Lead đã thay hai negative bằng case gap do third reopen mà middle không chạm tới. Case cũ được giữ nguyên raw OHLC trong golden fixture với expected positive, không xóa regression để làm test xanh.

Coder không được sửa/skip/xfail golden suite hoặc gọi production helper để generate expected. Nếu phát hiện mâu thuẫn giữa công thức và matrix thì dừng, báo ID/giá trị cụ thể để Tech Lead quyết định trước implementation tiếp theo. Thay contract phải ghi decision mới và lý do; không thêm expected bất ngờ sau khi đã nhận bàn giao.

## 6. Tiêu chí giao và nghiệm thu

Contract + suite được giao ở trạng thái **RED có chủ ý**. Người dùng chỉ yêu cầu chốt contract/tests trong lượt này; implementation chưa được sửa. Contract đã chốt không đồng nghĩa đã chứng minh thuật toán sinh lời hoặc gate56 APPROVED.

Đóng R56-01 khi golden suite xanh không xfail/skip, regression không tái phát, fixture tích hợp đã duyệt vẫn đạt, evidence/ID/cutoff đúng; Tech Lead review diff và ghi APPROVED riêng. Không tự chuyển task57 chỉ vì pytest xanh.
