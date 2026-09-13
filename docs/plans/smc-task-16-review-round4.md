# Tech Lead review — task 16, lần 4

**Quyết định: CHANGES_REQUESTED. Còn một phần R16-08; chưa bắt đầu task 17.**

- Reviewer: Codex, Tech Lead do người dùng chỉ định.
- Thời điểm kiểm tra: 2026-09-10 18:12 Asia/Saigon.
- Runtime HEAD: `fb9ea527ee7ff0eb48c53875e24796260008e92c`; tracked/staged diff rỗng.
- Phạm vi: kiểm lại bốn finding còn mở của review lần 3, đọc đặc tả/fixture thực tế và kiểm tra phần liên quan. Đây là gate hồ sơ task 16, không phải nghiệm thu implementation/runtime.
- Xác minh manifest: đủ 14 file, không hash mismatch; aggregate `4A3EC676092F5858420012795955C7C9269E784D7B27FBCDB124DCABB631B978`.
- Response SHA256: `E7EAD7F8BFDC66E4594C5A070FD41499D323875C0B15AC2A465DDA933CF1DDBD`.
- Ba báo cáo review trước giữ nguyên SHA256 như hồ sơ bàn giao; round 3 là `72E9D38CA57E8C97C65810E1525A27CDC3B90F9FD5294253A1E7A9F9B628AFA3`.

## Kết quả

| Finding | Kết quả lần 4 |
|---|---|
| R16-01 | CLOSED ở mức đặc tả: tách ready time khỏi source-history anchor; filter fixture chọn đúng L1 |
| R16-02 | CLOSED ở mức đặc tả: invariant áp dụng từng candidate; selected ID/final raw được đổi theo confirmation rank |
| R16-03 | Giữ CLOSED: M15 không sửa quality |
| R16-04 | Giữ CLOSED: sweep owner theo claim time, stable ID chỉ tie cùng thời điểm |
| R16-05 | CLOSED ở mức đặc tả: P11 và planner thống nhất execution ATR H4→D1 |
| R16-06 | Giữ CLOSED: directional wick/close color đúng |
| R16-07 | Giữ CLOSED: D1 proximity/open/unreacted không cấp reaction bonus |
| R16-08 | PARTIALLY RESOLVED — P2: OB/FVG và endpoint S/D đã sửa; hai ví dụ S/D vẫn không suy ra được từ OHLC hợp lệ |
| R16-09 | Giữ CLOSED: watch-no-plan giữ selected IDs/quality/lifecycle |

Tổng: **8 finding đóng, 1 finding còn một phần**. Không yêu cầu thiết kế lại các phần đã đóng.

## Finding duy nhất còn mở

### R16-08 — [P2] Feature giả định trong hai ví dụ S/D vi phạm quan hệ OHLC

**Owner:** task 11; đồng bộ response/progress và manifest sau sửa.

**Vị trí:** `docs/plans/smc-bqlc-spec.md:286–287`; công thức feature tại dòng 89–92.

Dòng minimum gán ba normalized feature body/ATR, body/range và close-location cùng bằng `.80`, suy ra formation `.640`. Dòng trên minimum giữ chúng và chỉ đổi family feature để ra `.740`. Phép cộng Q/S đúng với các feature được gán, nhưng không tồn tại departure candle hợp lệ sinh ra đồng thời các feature này:

```text
body_range_score = .80
=> body/range = .50 + .80*(1.00-.50) = .90

close_score = .80
=> directional_close = .70 + .80*(.90-.70) = .86
```

BUY bullish có `open >= low`, nên `body/range <= (close-low)/range`. Hai giá trị `.90 > .86` vi phạm bất đẳng thức này: open bị đặt thấp hơn low `.04*range`. SELL mirror cho open cao hơn high `.04*range`, cũng không hợp lệ.

Ngoài ra, ngay cả khi bỏ qua lỗi close-location, dòng minimum vẫn không thể có width_score=1:

```text
avg_range=1, impulse_range=1.50
body/range=.90 => body=1.35
body_atr_score=.80 => body/ATR=.86 => ATR=1.56976744186
base_width=zone_width=.66 => width/ATR=.42044444444 > .35
=> width_score=.89162393162, không phải 1
=> geometry=.75455555556, không phải .825
```

**Tác động:** nếu chuyển hai dòng này thành raw-input golden test, scorer đúng công thức không thể đạt expected. Nếu test chỉ truyền sẵn normalized `.80`, test bỏ qua chính lỗi nối raw OHLC/ATR với feature mà review lần 3 yêu cầu kiểm chứng. Đây là phần bằng chứng của R16-08 chưa hoàn tất, không phải finding mới hoặc yêu cầu đổi detector.

**Các phần đã chấp nhận, không sửa lại:**

- OB original width bằng base width; tính lại đúng geometry/Q/S: `0/.540/7.980` và `.8775/.84550/10.11850`.
- FVG dùng inverse, ra geometry `.475`, Q `.685`, S `8.995`.
- S/D family formation endpoint `[1.50,3.00]`: minimum → 0, 2.25 → .50, 3.00 → 1. Chấp nhận endpoint này; không đổi detector minimum để cứu ví dụ.
- Bounds validity là gate; không tự cấp điểm Q.

## Bộ số tham khảo đã tính độc lập để sửa đúng một lần

Có thể thay hai ví dụ S/D bằng bộ input sau; đây là đề xuất dữ liệu minh họa, không phải thay đổi công thức hoặc runtime:

- Cùng base gốc `[99.34,100.00]`, width `.66`, `n=5`, compression limit `1.32`.
- `avg_range=1`, `formation_atr=2` là input thống kê đã có từ history trước departure; không tuyên bố đã tái tính chúng từ một candle.
- `B=.8`, `L=.2`, `C=.3`, `integrity=.8` là **giả định subtotal** để minh họa; không gọi đây là full raw-history-to-score test.
- BUY departure nằm ngoài base và đóng trên base high. SELL lấy mirror `price'=200-price`, hoán đổi high/low; base SELL thành `[100,100.66]`.

| Case | BUY O/H/L/C | SELL O/H/L/C | body/ATR score | body/range score | close score | family score | formation | geometry | Q | S |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Minimum range=1.50 | 100.09 / 101.50 / 100 / 101.29 | 99.91 / 100 / 98.50 / 98.71 | 3/7 | .60 | .80 | 0 | .460 | .825 | .635 | 8.645 |
| Trên minimum range=2.25 | 100.135 / 102.25 / 100 / 101.935 | 99.865 / 100 / 97.75 / 98.065 | 6/7 | .60 | .80 | .50 | .710 | .825 | .760 | 9.520 |

Cả hai có body/range=.80, directional close=.86; width/ATR=.33 cho width_score=1 và compression=.50. Các normalized feature và subtotal trên đã được tính bằng Decimal từ BUY OHLC; SELL là phép đối xứng cùng khoảng cách/tỷ lệ. Khi impulse range thay đổi với ATR giữ nguyên, body/ATR score cũng phải thay đổi; không giữ mọi feature khác cố định rồi gọi là cùng raw input.

Coder có thể dùng bộ số khác nếu chứng minh được cùng chuỗi input → feature → subtotal. Ghi rõ các subtotal giả định ở ví dụ OB/FVG nữa; không cần dựng runtime scorer hoặc lịch sử ATR đầy đủ ở lượt sửa hồ sơ này.

## Bằng chứng đóng ba finding còn lại

- **R16-01:** structure §10.2 dùng ready time chỉ làm gate, source history riêng. Phép lọc thực tế trên bootstrap_records trong fixture cho `[L0,L1]`, chọn latest `L1`; break 05/01 12:00 sau ready 05/01 00:00. Continuation dùng anchor BOS trước; SELL áp dụng mirror. Không còn loại source chỉ vì pivot trước ready time. Fixture là timeline contract, chưa phải causal runtime replay test.
- **R16-02:** lifecycle dòng 205 đã bỏ invariant giữ selected toàn cục; selection §12 minh họa B→A khi A đổi sang confirmed, quality mỗi candidate không đổi. Nullable parent link, ID độc lập và expiry/plan policy đã được chấp nhận ở vòng trước.
- **R16-05:** P11 dòng 129–131 tách formation ATR cho width/quality và execution ATR chung cho hard distance. Ví dụ formation ATR `.80`, width `.60`, H4 execution ATR `2`, distance `4` đạt cả width và distance (`.60<=.80`, `4<=6`). Giữ các quyết định planner đã chấp nhận ở review 3; runtime parity vẫn là kiểm chứng tương lai.

## Kiểm chứng và giới hạn

- `git status`, HEAD, tracked/staged diff: runtime không đổi so với baseline.
- SHA256 14 file và aggregate: PASS; ba báo cáo cũ không đổi.
- Parse ba JSON fixture bằng PowerShell: PASS.
- Bootstrap source predicate chạy trên fixture thực tế: PASS.
- Decimal probe OB/FVG: PASS; probe quan hệ OHLC/ATR của S/D hiện tại xác nhận finding; bộ số thay thế BUY tính được các giá trị trong bảng.
- Đọc lại các contract M15/no-penalty, D1 reaction và watch-no-plan liên quan; giữ quyết định CLOSED trước đó, không tuyên bố rerun toàn bộ kiểm chứng cũ.
- Không chạy lại suite 418 test. `418 passed in 3.41s` là baseline ở review đầu, không phải kết quả mới và không chứng minh contract chưa triển khai.
- Không chạy feature runtime mới, PIT/UI/replay/performance hoặc dispatch giao dịch. Không sửa runtime, specs, fixtures, progress hoặc báo cáo cũ trong lượt review này.

## Điều kiện trình lại

Chỉ sửa hai ví dụ S/D và diễn đạt mức bằng chứng/subtotal giả định của R16-08; đồng bộ response/progress cùng manifest. Giữ nguyên công thức/endpoints và tám finding đã đóng. Trình lại gate 16; chưa triển khai task 17. Lần kiểm tiếp theo tập trung đúng phần còn mở này và tính toàn vẹn của hồ sơ.
