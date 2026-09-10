# Location scoring: vấn đề, thiết kế nâng cấp và plan cho CODER

Ngày cập nhật: **2026-09-09**  
Trạng thái: **ĐỀ XUẤT — CHƯA TRIỂN KHAI**  
Phạm vi: Location trong TechnicalSignalScore của Scanner.

> **Yêu cầu người dùng:** đây là phần mềm cá nhân, thiết kế phải gọn và dễ bảo
> trì; không cần backtest nhiều. Tài liệu đã được rút gọn theo yêu cầu này.
> Mục tiêu của bản đầu là sửa các lỗi logic đã xác minh, giữ chương trình hoạt
> động nhất quán và giải thích được điểm. Không cần chứng minh lợi nhuận bằng
> một hệ thống nghiên cứu trước khi hoàn thành nâng cấp.

## 0. CODER cần đọc gì và làm đến đâu?

1. Đọc §1–3 để hiểu công thức hiện tại và các lỗi cần sửa.
2. Thực hiện thiết kế bản đầu tại §4–8.
3. Dùng bộ kiểm thử ngắn tại §9 và kiểm tra thực tế tại §10.
4. Làm theo 32 work item ở §11, mỗi bước có đầu ra kiểm tra được.
5. Hoàn tất theo checklist §12. Các mục §13 để sau, không chặn bản đầu.

**Điểm dừng bắt buộc theo yêu cầu người dùng:** sau task **8, 14, 21, 28 và
32**, CODER phải dừng, báo kết quả và hỏi Tech Lead/người dùng xác nhận.
Chưa được xác nhận thì không làm nhóm tiếp theo. Chi tiết tại §11.2.

Tài liệu thay thế kế hoạch trước có 82 work item, 54 tình huống bắt buộc và
nhiều bước đánh giá mô hình. Mô tả lỗi vẫn giữ; phần hạ tầng và điều kiện hoàn
thành được thu hẹp. Thay đổi này chỉ sửa tài liệu, chưa sửa runtime.

Các thuật ngữ:

- **Anchor:** vùng hỗ trợ cho BUY hoặc kháng cự cho SELL dùng làm mốc vị trí.
- **Obstacle:** vùng đối diện cản hướng giao dịch.
- **Canonical:** dữ liệu chính thức mà các phần của ứng dụng cùng đọc.
- **Raw:** điểm Location 0–25 trước quy đổi theo trọng số regime.
- **Cutoff:** thời điểm dữ liệu đã đóng được phép dùng để đánh giá.

## 1. Mã nguồn và luồng đang chạy

| File/hàm | Vai trò |
|---|---|
| [technical_context.py](../../core/technical_context.py), build_technical_snapshot | Tạo giá tham chiếu, ATR và vùng swing |
| [smc_context.py](../../core/smc_context.py), swing_points | Xác định swing với lookback=2 |
| [technical_context.py](../../core/technical_context.py), build_zones | Tạo support_zones/resistance_zones đơn giản |
| [scanner_features.py](../../core/scanner_features.py), location_quality_score_v4 | Chấm Location hiện tại |
| [scanner_features.py](../../core/scanner_features.py), derive_technical_raws | Tạo raw cho BUY/SELL |
| [scanner_live_producers.py](../../core/scanner_live_producers.py), derive_live_analysis | Ghép technical, canonical SMC, raw và regime |
| [scanner_release.py](../../core/scanner_release.py), run_pair_from_live | Tạo scenario, snapshot và chạy composition |
| [scanner_scenario_producers.py](../../core/scanner_scenario_producers.py) | Tạo entry/SL/TP từ vùng SMC hoặc technical fallback |
| [technical_signal_scorer.py](../../core/technical_signal_scorer.py) | Quy đổi raw vào TechnicalSignalScore |
| [scanner_composition.py](../../core/scanner_composition.py) | Chọn hướng và chạy các gate |
| [scanner_v4_models.py](../../core/scanner_v4_models.py) | Kiểm tra cấu trúc và phiên bản dữ liệu canonical |
| [scanner_snapshot.py](../../core/scanner_snapshot.py) | Lưu/đọc snapshot |
| [scanner_ui_adapter.py](../../core/scanner_ui_adapter.py) | Chuyển dữ liệu chính thức sang UI |

Luồng hiện tại:

~~~text
Nến D1/H4/H1 đã đóng
  -> technical context + canonical SMC
  -> raw Trend/Momentum/Location/SMC của BUY và SELL
  -> scenario entry/SL/TP
  -> snapshot -> composition -> candidate -> execution
~~~

Hai điểm không được bỏ qua:

1. Vùng trong technical_context còn được SMC và scenario sử dụng. Sửa trực tiếp
   build_zones có thể làm đổi các phần ngoài Location.
2. Entry được tạo sau raw. Bản đầu tiếp tục chấm Location theo H1 close, không
   đưa entry hoặc selected_side vào raw scorer và tạo vòng phụ thuộc.

Không suy ra module không chạy chỉ vì còn docstring “target-only/not wired”;
phải theo caller thực tế.

### 1.1 Ảnh hưởng dự kiến sau khi hoàn tất

Đây là tác động thiết kế, **chưa phải kết quả triển khai hoặc hiệu quả giao dịch
đã đo được**. Thay Location có thể làm thay đổi quyết định downstream dù giữ
nguyên trọng số và ngưỡng:

| Phần chương trình | Ảnh hưởng cần kiểm tra |
|---|---|
| Raw Location | Vùng sai phía/hết hiệu lực không còn làm anchor; xung đột có thể ra 0; điểm có thể tăng hoặc giảm |
| TechnicalSignalScore | Contribution Location đổi theo weight regime hiện có; ba thành phần còn lại giữ logic |
| SetupScore | Có thể đổi qua input Technical; công thức blend giữ nguyên |
| BUY/SELL | Có thể đổi selected side vì composition so sánh Technical hai side |
| Scenario | Cùng input/cùng side giữ cách tạo entry/SL/TP; plan được chọn cuối có thể khác khi side đổi |
| Candidate/ranking/execution | Trạng thái, thứ hạng và cơ hội đủ điều kiện có thể khác; gate/threshold hiện có vẫn áp dụng |
| UI | Thêm giải thích điểm, vùng, khoảng cách và unavailable; không đổi nghĩa cột khoảng cách tới entry |
| Journal/snapshot | Lưu detail nhỏ theo cơ chế hiện có; giữ nguyên điểm/version của lịch sử |
| Lệnh đang mở | Feature này không tự đóng vị thế hoặc sửa SL/TP; quản lý lệnh hiện có giữ nguyên |
| Tài nguyên | Thêm tính toán trên cửa sổ H4 có giới hạn; đo vài scan để xác nhận mức tăng thời gian, không cam kết “không chậm” trước khi đo |

Không kết luận nâng cấp sẽ luôn giảm số lệnh, tăng win rate hay lợi nhuận.
Mục tiêu nghiệm thu là logic đúng thiết kế, dữ liệu nhất quán và người dùng
hiểu được lý do điểm. Không thêm gate mới để bù một case chưa đạt kỳ vọng.

## 2. Công thức hiện tại

### 2.1 Dữ liệu đầu vào

- Giá: h1[-1].close, không phải bid/ask ngay trước đặt lệnh.
- ATR: atr_h4 hoặc atr_d1 hoặc 0.0.
- Hỗ trợ lấy từ 6 swing low H4 gần nhất; kháng cự từ 6 swing high gần nhất.
- Nửa độ rộng: max(ATR H4 mới nhất × 0.15, 0.0001).
- Biên: level ± nửa độ rộng.
- confluence_count đếm các swing cùng loại gần nhau trong 10 swing cuối.
- nearest_zone chọn khoảng cách tới interval gần nhất, không kiểm tra đúng phía
  hay trạng thái đã phá vỡ. Bằng khoảng cách thì xét strength.

### 2.2 Điểm nền, lấy điều kiện đúng đầu tiên

| Thứ tự | BUY | SELL | Điểm |
|---|---|---|---:|
| 1 | Trong hỗ trợ | Trong kháng cự | 15 |
| 2 | Cách hỗ trợ ≤0.5 ATR | Cách kháng cự ≤0.5 ATR | 10 |
| 3 | Trong kháng cự | Trong hỗ trợ | 0 |
| 4 | Còn lại | Còn lại | 3 |

Điểm cộng/trừ lấy trên hỗ trợ gần nhất của BUY hoặc kháng cự gần nhất của SELL:

- test_count≥3: −5; từ 5 trở lên trừ thêm 3.
- confluence_count≥3: +5.
- is_round_number=true: +3.
- Kẹp tổng vào 0–25.

Producer hiện không cấp test_count/is_round_number, nên hai nhánh đó không
hoạt động trong luồng dựng vùng hiện tại. Raw thực tế tối đa là 20. Ngay cả
input tự cung cấp đủ field thì các hạng dương chỉ cộng tới 23, không đạt 25.

### 2.3 Quy đổi vào điểm kỹ thuật

~~~text
Location contribution = raw × trọng số Location / 25
~~~

| Regime | Trọng số | Tối đa hiện tại với raw=20 |
|---|---:|---:|
| Có xu hướng | 20 | 16 |
| Đi ngang | 40 | 32 |
| Biến động mạnh | 40 | 32 |
| Chưa xác định | 25 | 20 |

Giữ cơ chế Fraction/normalization hiện có trong technical_signal_scorer.

## 3. Vấn đề và cách xử lý trong bản đầu

| ID | Vấn đề đã xác minh | Tác động | Xử lý |
|---|---|---|---|
| L01 | Không kiểm tra lifecycle; hỗ trợ cũ có thể nằm phía trên giá | BUY vẫn được điểm gần hỗ trợ dù sai phía | Loại sai phía; kiểm tra close phá vùng |
| L02 | Nhánh thuận xét trước nhánh xung đột | Trong cả hỗ trợ và kháng cự vẫn được 15 | Obstacle chứa giá được xét trước |
| L03 | Bonus vẫn cộng từ vùng xa | BUY trong kháng cự vẫn có thể được cộng 5 | Bỏ bonus; score chỉ theo anchor hợp lệ và khoảng cách |
| L04 | Trần khai báo 25 nhưng live tối đa 20 | Trọng số thực tế không đúng kỳ vọng | Công thức mới có thể đạt 0 và 25; không chỉ đổi mẫu số |
| L05 | Ngưỡng 0.5 ATR làm điểm nhảy 10 xuống 3 | Giá dịch rất nhỏ làm mất nhiều điểm | Hàm khoảng cách liên tục trước rounding |
| L06 | Confluence chỉ là số swing gần nhau; vùng trùng chưa gộp | Số lượng swing bị hiểu thành chất lượng | Không cộng confluence; loại duplicate chính xác; merge cụm để sau |
| L07 | Không đo khoảng trống tới cản phía trước | Điểm cao dù giá sắp gặp vùng đối diện | Thêm clearance theo hướng và ATR |
| L08 | H1 close khác entry dự kiến | UI có thể gây hiểu lầm về entry | Ghi rõ giá tham chiếu; giữ entry/R:R gate hiện có |
| L09 | Không có vùng vẫn được 3 | Trộn không có bằng chứng thuận với thiếu dữ liệu | Không anchor hợp lệ -> 0; dữ liệu lỗi -> unavailable |
| L10 | Mọi vùng cũ dùng ATR mới nhất | Biên vùng thay đổi chỉ vì ATR mới | Dùng ATR tại xác nhận swing, cố định biên |
| L11 | Floor 0.0001 cố định, chỉ nhìn 6 swing | Không phù hợp mọi đơn vị giá; mất vùng liên quan | ATR/tick metadata nếu có; lookback nến có giới hạn |
| L12 | Test chủ yếu khóa parity công thức cũ | Pass test chưa chứng minh đã sửa lỗi | Kiểm thử counterexample và các invariant chính |

### 3.1 Sáu trường hợp đã tái hiện

Dùng ATR_H4=1; input vùng thủ công, không phải dữ liệu giao dịch thực tế.

| Case | Input | Raw BUY hiện tại |
|---|---|---:|
| OLD-01 | price=99.8; support=[100,101] | 10 |
| OLD-02 | price=100; support=[99,101]; resistance=[99.5,100.5] | 15 |
| OLD-03 | price=110; support=[99,100], confluence=3; resistance=[109,111] | 5 |
| OLD-04 | price=100; không có vùng | 3 |
| OLD-05 | price=100.5; support=[99,100] | 10 |
| OLD-06 | price=100.5001; support=[99,100] | 3 |

OLD-01 chứng minh hàm chấp nhận vùng sai phía. Input tối thiểu không đủ để nói
breakout đã được xác nhận; chính việc thiếu thông tin đó cần sửa.

Ở OLD-05/06, mất 7 raw tương đương mất 11.2 điểm kỹ thuật khi trọng số=40.

Có thể dùng fixture sau để khóa baseline cũ ở test, không cần broker:

~~~python
from core.scanner_features import location_quality_score_v4

def zone(low, high, confluence=1):
    return {"low": low, "high": high, "confluence_count": confluence}

def score(price, supports, resistances):
    return location_quality_score_v4("buy", {
        "price": price, "atr_h4": 1.0, "atr_d1": 2.0,
        "support_zones": supports, "resistance_zones": resistances,
    })

assert score(99.8, [zone(100, 101)], []) == 10
assert score(100, [zone(99, 101)], [zone(99.5, 100.5)]) == 15
assert score(110, [zone(99, 100, 3)], [zone(109, 111)]) == 5
assert score(100, [], []) == 3
assert score(100.5, [zone(99, 100)], []) == 10
assert score(100.5001, [zone(99, 100)], []) == 3
~~~

## 4. Thiết kế gọn cho bản đầu

### 4.1 Tổ chức mã

Ưu tiên một module mới **core/location_engine.py** chứa các dataclass nhỏ và
hàm thuần cho vùng, lựa chọn và score. Chỉ tách thành hai file nếu đọc/bảo trì
khó; không mặc định tạo năm module, repository, event bus hoặc service mới.

Public interface đề xuất:

~~~text
build_location_context(closed_h4, reference_price, cutoff, config, tick_size=None)
    -> LocationContext

score_location(side, context)
    -> LocationResult
~~~

Context dựng một lần cho BUY/SELL. Không cần cache riêng khi chưa có bằng chứng
nút thắt hiệu năng. Bản đầu dựng lại từ cửa sổ nến có giới hạn, không lưu
lifecycle vào database hoặc quản lý revision cha/con.

Giữ nguyên support_zones/resistance_zones dùng chung. Location dùng danh sách
vùng riêng để không làm đổi SMC/scenario ngoài ý muốn.

### 4.2 Cấu hình đơn giản

Một cấu hình nhỏ, khai báo mặc định có tên rõ ràng; dùng file/settings hiện có
nếu cần chỉnh. Không xây màn hình tối ưu tham số hoặc vòng đời research/validated.

| Tham số đề xuất ban đầu | Giá trị | Ghi chú |
|---|---:|---|
| swing_lookback | 2 | Như cách nhận swing hiện tại |
| history_h4_bars | 240 | Số nến mong muốn; giữ minimum history của pipeline |
| zone_half_width_atr | 0.15 | Tính tại xác nhận swing |
| zone_max_width_atr | 1.0 | Loại vùng quá rộng sau làm tròn tick |
| invalidation_close_count | 2 | Hai close H4 liên tiếp xác nhận phá vùng |
| invalidation_buffer_atr | 0.10 | Buffer dùng ATR tại xác nhận vùng |
| zone_max_age_h4_bars | 120 | Tuổi vùng theo số nến đóng |
| proximity_zero_at_atr | 1.0 | Xa tới mức này thì điểm proximity bằng 0 |
| clearance_full_at_atr | 1.0 | Đủ khoảng trống để C=1 |
| unknown_clearance_factor | 0.5 | Không thấy obstacle không đồng nghĩa không có cản |

Đây là giá trị khởi đầu minh bạch để triển khai và xem thử, chưa phải tham số
được chứng minh tối ưu. Có thể dùng sau kiểm thử logic và kiểm tra mẫu ở §10;
không cần backtest lợi nhuận mới được hoàn thành bản đầu.

Thiếu file cấu hình tùy chọn -> dùng bộ mặc định này có version. Nếu đã có
cấu hình nhưng sai kiểu/NaN/ngoài miền -> báo lỗi, không âm thầm dùng giá trị khác.
Không tự đổi trọng số regime hay ngưỡng vào lệnh để bù phân phối điểm mới.

### 4.3 Dữ liệu tối thiểu

LocationZone chỉ cần:

~~~text
id, role, low, high
formed_at, confirmed_at, formation_atr
status: ACTIVE | SUSPECT | INVALIDATED | EXPIRED
~~~

- ID dựa trên role + thời gian swing, không dùng index rolling window.
- Cập nhật trạng thái trong lần dựng context; không cần history/revision database.
- Duplicate chính xác cùng nguồn/ID chỉ giữ một.
- Các vùng gần nhau chưa cần merge; không cộng thưởng theo số lượng vùng.

LocationResult chỉ cần:

~~~text
raw: int | null
status, reason_codes
reference_price, reference_closed_at
anchor: id, low, high, status hoặc null
obstacle: id, low, high, status hoặc null
distance_atr, clearance_atr hoặc null
proximity_factor, clearance_factor
model_version, config_used
~~~

Có thể dùng dataclass và serialize thành một dictionary nhỏ. Không tạo hai
hệ thống fingerprint, hệ thống replay hoặc lưu toàn bộ nến trong kết quả.

## 5. Quy tắc dựng vùng và lifecycle

### 5.1 Dữ liệu theo thời điểm

- Chỉ dùng nến đóng trước hoặc đúng cutoff; lọc cutoff trước rồi mới cắt 240 nến.
- Adapter phải xác định đúng Candle.time là open time hay close time theo dữ
  liệu broker. Không tự coi nến đang hình thành là đã đóng.
- Swing i với lookback=2 chỉ khả dụng sau khi nến i+2 đóng.
- Tính ATR(14) tại thời điểm xác nhận swing, dùng prefix nến tại thời điểm đó.
- Nếu chưa có ATR hợp lệ ở confirmation, bỏ swing đó; không thay bằng ATR cuối.
- Nến sai OHLC, timestamp trùng/sai hoặc ATR hiện tại không hợp lệ -> unavailable
  theo contract adapter hiện có, không fabricate số.
- Đủ minimum hiện có nhưng thiếu 240 nến vẫn có thể tính; ghi số nến thực xét.

### 5.2 Biên vùng cố định

~~~text
half_width = zone_half_width_atr * ATR_at_confirmation
low = swing_level - half_width
high = swing_level + half_width
~~~

Nếu có tick_size hợp lệ thì low làm tròn xuống, high làm tròn lên và bảo đảm
ít nhất một tick. Không có tick_size thì dùng giá liên tục theo ATR; không
thay bằng floor 0.0001 cho mọi tài sản.

Kiểm tra max width bằng ATR_at_confirmation. Biên không nở/co vì ATR mới.
ATR hiện tại chỉ dùng chuẩn hóa khoảng cách khi chấm điểm.

### 5.3 Theo dõi phá vùng

Support:

~~~text
break_line = low - invalidation_buffer_atr * formation_atr
~~~

Resistance:

~~~text
break_line = high + invalidation_buffer_atr * formation_atr
~~~

Duyệt các H4 close từ thời điểm xác nhận vùng tới cutoff:

1. Close xuyên break_line theo hướng bất lợi -> tăng breach streak.
2. Chưa đủ số close yêu cầu -> SUSPECT.
3. Đủ số close liên tiếp -> INVALIDATED.
4. Close không xuyên -> reset streak; SUSPECT trở lại ACTIVE.
5. INVALIDATED không tự hồi sinh; phải có swing/vùng mới.
6. Wick xuyên mà close không xuyên không tính breach.
7. Quá số nến tuổi tối đa -> EXPIRED.

Chỉ ACTIVE làm anchor. ACTIVE/SUSPECT có thể làm obstacle; không coi vùng cản
đã biến mất chỉ vì một close. INVALIDATED/EXPIRED không được dùng.

Ngay cả chưa invalidated, support nằm hoàn toàn phía trên giá BUY cũng không
được làm anchor. Kiểm tra đúng phía độc lập với xác nhận phá vỡ.

Không tự đổi vai trò support/resistance và không quản lý merge revision trong
bản đầu. Hạn chế này phải được giữ rõ khi review, không âm thầm làm thêm.

## 6. Chọn vùng và chấm điểm

### 6.1 Chọn anchor

BUY: support ACTIVE, reference_price ≥ low.  
SELL: resistance ACTIVE, reference_price ≤ high.

Giá có thể nằm trong vùng hoặc phía thuận của vùng. Các vùng chưa xác nhận,
hết hạn, sai phía hoặc quá rộng bị loại.

Trong tập hợp lệ, chọn theo khoảng cách tới interval, rồi độ rộng nhỏ hơn,
thời điểm xác nhận mới hơn, cuối cùng ID để kết quả ổn định. Không chọn theo
score tối đa, số swing hay điểm SMC.

### 6.2 Chọn obstacle

BUY: resistance ACTIVE/SUSPECT chứa giá hoặc nằm phía trên giá.  
SELL: support ACTIVE/SUSPECT chứa giá hoặc nằm phía dưới giá.

- Nếu bất kỳ obstacle hợp lệ nào chứa giá: CONFLICT, raw=0.
- Nếu không, chọn obstacle phía trước gần nhất, tính khoảng cách tới mép.
- Vùng hoàn toàn phía sau hướng giao dịch không được dùng làm obstacle.
- Không có obstacle trong cửa sổ dữ liệu: ghi limited context; không coi
  clearance là vô hạn.

### 6.3 Công thức đề xuất

~~~text
A = ATR H4 hiện tại, hữu hạn và >0
d = khoảng cách tới anchor / A
g = khoảng trống tới obstacle / A

P = clamp(1 - d / proximity_zero_at_atr, 0, 1)
C = clamp(g / clearance_full_at_atr, 0, 1)    nếu có obstacle
C = unknown_clearance_factor                 nếu không thấy obstacle

raw_exact = 25 * P * C
raw = ROUND_HALF_UP(raw_exact), kẹp 0..25
~~~

Các trường hợp xử lý trước công thức:

| Tình huống | Kết quả |
|---|---|
| Dữ liệu/cấu hình không hợp lệ | UNAVAILABLE, raw=null |
| Obstacle chứa giá | CONFLICT, raw=0 |
| Dữ liệu hợp lệ nhưng không có anchor | NO_VALID_ANCHOR, raw=0 |
| Anchor xa ít nhất proximity_zero_at_atr | raw=0, ANCHOR_TOO_FAR |

Không có base=3, confluence bonus, round-number bonus hoặc test_count penalty.
Không đọc macro, SL/TP hay R:R trong hàm score.

Ví dụ với cấu hình khởi đầu:

| Vị trí | P | C | Raw sau làm tròn |
|---|---:|---:|---:|
| Trong anchor, obstacle cách ít nhất 1 ATR | 1 | 1 | 25 |
| Cách anchor 0.5 ATR, obstacle đủ xa | 0.5 | 1 | 13 |
| Trong anchor, obstacle cách 0.2 ATR | 1 | 0.2 | 5 |
| Trong anchor, không thấy obstacle | 1 | 0.5 | 13 |
| Anchor cách ít nhất 1 ATR | 0 | bất kỳ | 0 |

Raw nguyên vẫn có bước làm tròn 1 điểm. Mục tiêu là bỏ bước nhảy 7 điểm vì
0.0001 ATR ở công thức cũ, không tuyên bố integer score hoàn toàn liên tục.

Giữ raw_max=25 và trọng số regime hiện tại. Đây là mô hình vị trí theo swing,
chưa phải mô hình chuyên biệt cho mọi chiến lược breakout hoặc limit entry.

## 7. Giai đoạn F: tích hợp canonical tối thiểu

### 7.1 Mục tiêu

Tính Location một lần rồi truyền cùng kết quả tới bộ chấm điểm, snapshot và UI.
Không xây thêm nền tảng quản lý dữ liệu chỉ cho một thành phần điểm.

Bốn việc cần làm:

1. Gắn LocationResult vào kết quả feature của từng phía; raw hợp lệ vẫn là int.
2. Truyền một location_detail nhỏ tới snapshot/detail chính thức.
3. Ghi model_version và cấu hình thực dùng để phân biệt lịch sử cũ/mới.
4. Xử lý unavailable rõ ràng và hiển thị đúng dữ liệu đã tính.

### 7.2 Dùng cấu trúc hiện có

- technical_raws hiện chỉ có trend/momentum/location. Không nhét các field
  giải thích vào dictionary strict này.
- Dùng trường detail/provenance được contract cho phép; nếu chưa có slot phù
  hợp thì thêm một location_detail có schema rõ ràng, cập nhật parser/serializer
  ở đúng các lớp đi qua. Không dùng field không hợp lệ để né validator.
- Full snapshot giữ detail nhỏ; compact row chỉ cần điểm/status/reasons hoặc
  reference tới detail.
- Dùng cơ chế snapshot hash hiện có nếu canonical input cần bổ sung identity.
  Không tạo score_fingerprint và location_input_fingerprint riêng.
- Chỉ tăng version/schema thật sự bị đổi; không bump toàn bộ hệ thống hoặc
  sửa version SMC khi SMC không thay đổi.

### 7.3 Thiếu dữ liệu

LocationResult.raw=null không được truyền vào SideSnapshot hiện đang đòi int.
Adapter chuyển thành TechnicalRawDerivationError có reason; controller sử dụng
luồng unavailable hiện có. Không thay null bằng 0/3 để tiếp tục chấm điểm.

Không có anchor trong dữ liệu hợp lệ là raw=0 và vẫn có kết quả đánh giá.
Đây khác với việc không tính được do thiếu ATR hoặc dữ liệu lỗi.

### 7.4 Lịch sử và cache

- Dữ liệu cũ vẫn giữ điểm/version cũ. Chỉ cần đọc/hiển thị được hoặc báo phiên
  bản không được hỗ trợ; không cần tái chạy công thức cũ.
- Không bắt buộc migration database mới. Dùng snapshot/JSON detail hiện có;
  chỉ thêm migration nếu cấu trúc lưu hiện tại thực sự không đáp ứng.
- Không viết lại journal cũ bằng điểm mới.
- Bản đầu không thêm cache riêng. Nếu existing cache bao kết quả feature,
  bổ sung version/config vào key hoặc làm hết hiệu lực khi đổi cấu hình.
- Không nối scorer mới vào live cho tới bước chuyển đổi cuối; khi chuyển chỉ
  có một công thức Location hoạt động.

## 8. Giao diện và ranh giới entry

Card Location chỉ cần:

~~~text
Location: 13/25 — đóng góp kỹ thuật: 20.8/40
Tham chiếu: giá đóng cửa H1 [thời gian]
Vùng hỗ trợ: [low, high], còn hiệu lực
Khoảng cách: 0.50 ATR H4
Vùng cản phía trước: cách 1.20 ATR
Lý do: còn cách vùng hỗ trợ
~~~

- UI đọc raw/contribution/detail, không tự tính lại công thức.
- raw=0 hiển thị 0; raw=null hiển thị “Không đủ dữ liệu”.
- Không thấy obstacle -> “Chưa thấy vùng cản trong dữ liệu đã xét”.
- Không gọi độ gần hỗ trợ là xác suất thắng.
- Model version/config có thể nằm ở phần chi tiết mở rộng, không làm rối card.
- Không bắt buộc vẽ lớp vùng mới lên biểu đồ.

Bản đầu giữ nguyên scenario/entry/R:R/execution gates hiện có. H1 Location
không xác nhận riêng entry limit ở giá khác. Hiển thị rõ reference để tránh
hiểu nhầm; chưa xây Entry Location Check, gate mới hoặc revalidation framework.
Nếu phát hiện lỗi độc lập trong execution, ghi task riêng thay vì mở scope.

## 9. Kiểm thử cần thiết, không phải backtest lợi nhuận

Đây là bộ kiểm tra code ngắn, chạy tự động. Nhiều hàng có thể gộp thành một
pytest parametrized test; không bắt buộc tạo 20 file hay 20 lớp test.

| ID | Case | Expected |
|---|---|---|
| T01 | BUY dưới support / SELL trên resistance | Không chọn anchor sai phía |
| T02 | Giá nằm trong cả hai loại vùng | CONFLICT, raw=0 |
| T03 | Anchor xa có nhiều swing, giá trong obstacle | raw=0; không bonus cứu điểm |
| T04 | Không có vùng nhưng dữ liệu hợp lệ | NO_VALID_ANCHOR, raw=0 |
| T05 | ATR lỗi/0/NaN, OHLC hoặc config sai | unavailable/typed error, không default điểm |
| T06 | Khoảng cách 0.5000 và 0.5001 ATR | raw_exact gần nhau, raw lệch tối đa 1 |
| T07 | Anchor xa dần, các điều kiện khác cố định | Score không tăng |
| T08 | Obstacle gần dần, các điều kiện khác cố định | Score không tăng |
| T09 | Trong anchor, obstacle đủ xa; raw_exact=x.5 | Đạt 25 và ROUND_HALF_UP đúng |
| T10 | Không quan sát được obstacle | C=unknown factor, có lý do limited context |
| T11 | Wick, một close, hai close và phục hồi | Lifecycle/streak đúng; không hồi sinh invalidated |
| T12 | Vùng chưa xác nhận hoặc hết hạn | Không làm anchor; trạng thái hợp lệ |
| T13 | Append nến tương lai, giữ cùng cutoff | Không đổi assessment quá khứ |
| T14 | ATR thay đổi sau xác nhận swing | Biên vùng cũ không đổi |
| T15 | Đảo thứ tự vùng/duplicate ID/phản chiếu BUY-SELL | Deterministic, không cộng điểm do duplicate, đối xứng |
| T16 | Raw 0/13/25 ở các regime | Đúng raw×weight/25 |
| T17 | Chỉ nâng Location, cùng fixture | Trend/Momentum/canonical SMC giữ nguyên |
| T18 | Lưu và đọc Location detail/version; dữ liệu cũ | Không mất field; không relabel dữ liệu cũ |
| T19 | UI với raw=0 và raw=null | Hiển thị khác nhau, không tự tính score |
| T20 | Live caller và error path | Chỉ một scorer; unavailable không biến thành candidate hợp lệ |

T13 chỉ chạy trên dữ liệu prefix/cutoff hợp lệ, lọc cutoff trước khi cắt cửa sổ.
T15 phản chiếu giá quanh một hằng số và đảo role, không phải phép nghịch đảo
cặp FX 1/price vì ATR và tick sẽ biến đổi phi tuyến.

Baseline đã chạy khi rà soát tài liệu lần đầu:

~~~powershell
python -m pytest tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py -q --disable-warnings
~~~

Kết quả **132 passed** trước khi sửa. Các test này khóa hiện trạng, không phải
bằng chứng công thức mới tốt hơn. Khi implementation thay đổi, giữ parity
Trend/Momentum và thay contract Location có version, không chỉ sửa expected
để che counterexample.

Chạy thêm test của các file tích hợp thực sự sửa, chẳng hạn:

~~~powershell
python -m pytest tests/test_scanner_live_producers.py tests/test_scanner_release.py tests/test_scanner_composition.py tests/test_scanner_snapshot.py tests/test_scanner_ui_adapter.py -q
~~~

Không cần chạy toàn bộ suite sau từng bước. Full suite chỉ chạy một lần cuối
nếu quy tắc repo yêu cầu hoặc thay đổi ảnh hưởng đủ rộng; chạy lại khi có lỗi
hay thay đổi mới. Không bỏ kiểm thử parser/normalization chỉ vì muốn ít backtest:
đây là kiểm tra tính đúng đắn của phần mềm.

## 10. Kiểm tra thực tế ngắn

Sau khi các test cần thiết đạt, chọn khoảng **5–10 ví dụ biểu đồ** từ một vài
symbol đang dùng. Đây là số mẫu tiện kiểm tra bằng mắt, không phải ngưỡng thống
kê hoặc bằng chứng lợi nhuận.

Nên có: gần hỗ trợ, trong kháng cự, vùng bị phá, vùng chồng lấn, giá xa vùng,
không có vùng phù hợp. Với mỗi ví dụ kiểm tra:

- Vùng chọn có đúng phía và còn hiệu lực không?
- Khoảng cách/clearance và lý do có khớp biểu đồ không?
- Raw/contribution có đúng công thức không?
- Điểm thay đổi có làm candidate vượt ngưỡng ngoài dự kiến không?

Dùng dữ liệu hoặc export sẵn có. Không bắt buộc viết evaluator, tạo dataset mới,
chia train/validation/holdout, quét tham số, chạy Monte Carlo hoặc mô phỏng P&L.
Một bảng Markdown ngắn “case / kết quả / ghi chú” là đủ; không cần hệ thống báo cáo.

Có thể chạy thử Scanner khi auto-trade tắt hoặc dùng demo để kiểm tra hiển thị
và quyết định. Không có thời hạn bắt buộc nhiều ngày hay yêu cầu số lệnh tối thiểu.
Không âm thầm đổi cấu hình giao dịch của người dùng khi kiểm tra.

Nếu test logic và kiểm tra mẫu đạt, có thể hoàn thành bản sửa. Theo dõi kết quả
sử dụng tiếp bằng journal hiện có; chỉ phân tích sâu hơn khi có vấn đề cụ thể.
Không dùng việc ít backtest làm cơ sở tuyên bố đã tăng lợi nhuận.

## 11. Plan 32 bước nhỏ cho CODER

Mỗi bước có thể là một phần nhỏ của commit; không bắt buộc 32 PR, 32 báo cáo
hay quy trình phê duyệt riêng. Các bước prepare chưa phát hành thay đổi runtime.

Task **1–32** là số thứ tự chính để giao việc và báo tiến độ. Giữ ID A01–H04
trong ngoặc để tra phụ thuộc và các ghi chú cũ; ID này không tạo task bổ sung.
Mỗi task vẫn có hướng dẫn chi tiết tương ứng tại §11.1.

**Cập nhật trạng thái:** CODER cập nhật trực tiếp cột **Trạng thái** của từng
task trong các bảng dưới: **Chưa thực hiện** → **Đang thực hiện** → **Hoàn thành**.
Chỉ ghi **Hoàn thành** khi đã đáp ứng điều kiện của task và ghi bằng chứng
kiểm tra theo §11.2; nếu bị chặn, ghi **Bị chặn — [lý do]**.
Riêng task **8, 14, 21, 28 và 32**, khi CODER làm xong thì ghi **Chờ review**;
chỉ đổi thành **Hoàn thành** sau khi có xác nhận cho mốc R1–R5 tương ứng.
Task 32 chỉ hoàn thành khi checklist §12 đạt và R5 được xác nhận.

### Giai đoạn A — Xác nhận lỗi và ranh giới

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi | Trạng thái |
|---:|---|---|---|---|---|
| 1 | A01 | Kiểm tra caller Location và consumer vùng dùng chung | — | Biết chính xác file cần sửa; bảo toàn thay đổi người dùng | Hoàn thành |
| 2 | A02 | Chạy baseline tests liên quan | A01 | Ghi command và kết quả ngắn | Hoàn thành |
| 3 | A03 | Thêm fixture sáu case OLD-01..06 | A02 | Tái hiện đúng công thức cũ | Hoàn thành |
| 4 | A04 | Xác minh nến H4 đóng/cutoff và ghi target vào architecture | A01 | Quy ước thời gian rõ; docs chưa tuyên bố đã live | Hoàn thành |

### Giai đoạn B — Mô hình tối thiểu

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi | Trạng thái |
|---:|---|---|---|---|---|
| 5 | B01 | Tạo location_engine.py, cấu hình mặc định có version | A04 | Không service/database mới | Hoàn thành |
| 6 | B02 | Validate cấu hình và input thiết yếu | B01 | T05 đạt; default khác với fallback che config lỗi | Hoàn thành |
| 7 | B03 | Tạo LocationZone/Context/Result nhỏ | B02 | Field đủ cho tính điểm và giải thích | Hoàn thành |
| 8 | B04 | Viết serialize detail và reason codes cần dùng | B03 | Null/0/status/version có ý nghĩa rõ; **DỪNG và hỏi tại R1, chờ xác nhận** | Hoàn thành |

### Giai đoạn C — Dựng vùng đúng

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi | Trạng thái |
|---:|---|---|---|---|---|
| 9 | C01 | Lọc closed candles theo cutoff, giới hạn history | B03,A04 | Không dùng nến tương lai | Hoàn thành |
| 10 | C02 | Tạo swing ID/confirmed_at | C01 | Không dùng index làm ID; swing có đủ xác nhận | Hoàn thành |
| 11 | C03 | Dựng biên bằng ATR tại confirmation, tick nếu có | C02 | T14 đạt; max width được kiểm tra | Hoàn thành |
| 12 | C04 | Viết breach streak BUY/SELL và expiry | C03 | T11,T12 đạt | Hoàn thành |
| 13 | C05 | Dedup chính xác và sắp xếp ổn định | C04 | Không merge/revision framework; duplicate không tăng điểm | Hoàn thành |
| 14 | C06 | Kiểm tra causal và context dùng chung hai phía | C05 | T13 đạt; context dựng một lần; **R2 đã được Tech Lead duyệt** | Hoàn thành |

### Giai đoạn D — Chấm Location

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi | Trạng thái |
|---:|---|---|---|---|---|
| 15 | D01 | Chọn anchor đúng phía/trạng thái | C06 | T01,T04 đạt | Hoàn thành |
| 16 | D02 | Chọn obstacle và xử lý conflict trước | D01 | T02,T03 đạt | Hoàn thành |
| 17 | D03 | Viết P,C,raw và rounding | D02 | T06–T10,T16 đạt | Hoàn thành |
| 18 | D04 | Hoàn thiện reason/detail/unavailable | D03,B04 | Không tạo điểm giả; raw0 khác null | Hoàn thành |
| 19 | D05 | Chạy invariants và regression của engine | D04 | T01–T16 liên quan đạt; không đọc SMC score/macro/R:R | Hoàn thành |

### Giai đoạn E — Xem thử ngắn, không xây backtest

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi | Trạng thái |
|---:|---|---|---|---|---|
| 20 | E01 | Chọn 5–10 case biểu đồ/export sẵn có và xem kết quả mới | D05 | Kiểm tra các tình huống §10, không cần evaluator riêng | Hoàn thành |
| 21 | E02 | Ghi ghi chú ngắn, sửa lỗi nếu có | E01 | Kết quả hợp lý về logic; không yêu cầu report lợi nhuận; **DỪNG và hỏi tại R3, chờ xác nhận** | Hoàn thành |

### Giai đoạn F — Tích hợp canonical gọn

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi | Trạng thái |
|---:|---|---|---|---|---|
| 22 | F01 | Gắn raw và một LocationResult/detail nhỏ vào feature output | D04 | Một nguồn kết quả, raw hợp lệ vẫn int | Hoàn thành |
| 23 | F02 | Truyền detail qua snapshot chính thức và reader | F01 | T18 đạt; không thêm key lạ vào technical_raws | Hoàn thành |
| 24 | F03 | Ghi version/config, cập nhật existing hash/cache nếu cần | F02 | Nhận diện dữ liệu cũ/mới; không hệ thống fingerprint mới | Hoàn thành |
| 25 | F04 | Nối typed unavailable vào luồng lỗi hiện có | F01 | T20 error path đạt; không null leak hoặc default điểm | Hoàn thành |

### Giai đoạn G — Giao diện và hồi quy

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi | Trạng thái |
|---:|---|---|---|---|---|
| 26 | G01 | UI đọc raw/contribution/detail, hiển thị reference H1 rõ | F02,F04 | T19 đạt; không tự tính score | Hoàn thành |
| 27 | G02 | Kiểm tra SMC/Trend/Momentum/scenario không đổi ngoài scope | G01 | T17 và existing tests liên quan đạt | Hoàn thành |
| 28 | G03 | Kiểm tra card trên giao diện hẹp/rộng, dark/light | G01 | Không overflow; không thêm overlay/màn hình mới; **DỪNG và hỏi tại R4, chờ xác nhận** | Hoàn thành |

### Giai đoạn H — Chuyển công thức và hoàn tất

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi | Trạng thái |
|---:|---|---|---|---|---|
| 29 | H01 | Nối duy nhất engine mới vào runtime, bỏ call cũ | E02,F03,F04,G02 | Không dual/shadow scoring; version đúng công thức | Hoàn thành |
| 30 | H02 | Chạy targeted integration tests và smoke check | H01,G03 | T01–T20 thuộc phạm vi đạt; kiểm tra không gửi lệnh thật | Hoàn thành |
| 31 | H03 | Cập nhật docs và checkpoint code/config để có thể quay lại | H02 | Không rewrite journal; không đổi threshold ngoài yêu cầu | Hoàn thành |
| 32 | H04 | Bàn giao kết quả, giới hạn và các mục để sau | H03 | Checklist §12 đạt; không đợi backtest lợi nhuận; **DỪNG và hỏi tại R5, chờ xác nhận** | Hoàn thành |

E xem được output engine độc lập trước integration. Sau H01 chạy smoke trên
đường live mới để bảo đảm wiring thực sự đúng; không coi unit test thay thế
cho kiểm tra tích hợp.

### 11.1 Hướng dẫn thực hiện từng bước

Các bảng trên là danh sách công việc; phần dưới là hướng dẫn thực thi cho
đúng 32 ID đó, không bổ sung một dự án hay giai đoạn nghiên cứu mới.

Quy tắc chung:

- Mỗi bước đọc lại file thực tế trước khi sửa. Tên file/hàm là điểm bắt đầu,
  không phải danh sách file bắt buộc phải thay đổi.
- Chỉ sửa các lớp mà dữ liệu thật sự đi qua; không refactor cả hệ thống vì một
  field mới.
- Dùng một file tests/test_location_engine.py cho các test domain; thêm test
  tích hợp vào file hiện có. Không cần một module hoặc bộ test riêng cho mỗi ID.
- Các bước F/G có thể chuẩn bị bằng fixture gọi engine mới trực tiếp. H01 mới
  đổi caller live; không thêm cờ chạy hai scorer để thử.
- Lỗi thuộc bước nào thì sửa và chạy lại test liên quan bước đó. Không cần
  lặp lại toàn bộ quy trình từ A01.
- Ghi kết quả vào cùng checklist/ghi chú triển khai, khoảng một dòng mỗi bước
  là đủ. Test chưa chạy phải ghi chưa chạy, không suy ra từ đọc code.

#### Task 1 (A01) — Kiểm tra caller Location và consumer vùng dùng chung

**File bắt đầu:** scanner_features.py, technical_context.py,
scanner_live_producers.py, scanner_release.py, smc_scorer.py và
scanner_scenario_producers.py trong core.

**Thực hiện:**

1. Xem git status để biết thay đổi đã có; không reset, checkout đè hoặc xóa
   file của người dùng.
2. Tìm caller của location_quality_score_v4, derive_technical_raws,
   build_technical_snapshot và build_zones bằng rg.
3. Tìm nơi đọc support_zones/resistance_zones; ghi vùng nào dùng cho Location,
   vùng nào dùng cho SMC/scenario.
4. Tìm đường UI canonical đang hiển thị technical breakdown. Không chọn một
   hàm legacy chỉ vì tên có chữ location.

**Đầu ra/kiểm tra:** một ghi chú ngắn về đường đi caller và phạm vi thay đổi.
Phải xác nhận engine mới sẽ không mutate các danh sách vùng dùng chung.

#### Task 2 (A02) — Chạy baseline tests liên quan

**File bắt đầu:** tests/test_scanner_features.py,
tests/test_technical_signal_scorer.py, tests/test_scanner_scenario_producers.py.

**Thực hiện:**

1. Chạy lệnh baseline tại §9 trước sửa công thức.
2. Ghi số test đạt/lỗi và command. Số 132 trong tài liệu là kết quả lịch sử,
   không phải số bắt buộc ở mọi commit về sau.
3. Nếu có test lỗi sẵn, ghi rõ đó là baseline failure; kiểm tra có liên quan
   Location hay không trước khi tiếp tục.

**Đầu ra/kiểm tra:** có baseline để phân biệt regression do bản sửa.
Không sửa expected, skip test hoặc đổi ngưỡng để baseline “xanh”.

#### Task 3 (A03) — Thêm fixture sáu lỗi cũ

**File bắt đầu:** tests/test_scanner_features.py hoặc nhóm fixture nhỏ trong
tests/test_location_engine.py.

**Thực hiện:**

1. Tạo helper zone và input theo §3.1, đặt tên case OLD-01 đến OLD-06.
2. Xác nhận kết quả cũ 10,15,5,3,10,3 đúng trên hàm hiện tại.
3. Giữ input/expected baseline có nhãn legacy. Sau H01, chúng có thể là dữ
   liệu tham chiếu lịch sử; không cần duy trì callable scorer cũ trong runtime.
4. Tạo test mới riêng cho hành vi sửa, dùng cùng geometry khi phù hợp. Không
   giả định mọi input cũ đều có đủ lifecycle để feed thẳng vào model mới.

**Đầu ra/kiểm tra:** reviewer nhìn thấy lỗi trước/sau mà không phải truy log
phiên làm việc. Chỉ dùng dữ liệu giả lập, không kết nối broker.

#### Task 4 (A04) — Xác minh thời gian nến và ghi thiết kế đích

**File bắt đầu:** services/mt5_service.py, core/market_models.py,
controllers/scanner_controller.py và docs/scanner/scanner-architecture.md.

**Thực hiện:**

1. Xác minh Candle.time và cơ chế loại nến đang chạy ở producer. Không tin
   chỉ vào docstring nói “closed candles”.
2. Chốt một cutoff chung cho snapshot: chỉ các H1/H4 đã đóng tại thời điểm đó
   được dùng. reference_price là close của H1 cuối hợp lệ; lưu close time của
   cây đó riêng.
3. Nếu adapter đã bảo đảm nến đóng, tái sử dụng contract. Nếu thiếu, thêm seam
   nhỏ để cung cấp closed_at theo lịch/boundary broker đã xác minh; không đoán
   rằng time là close time và không dùng wall-clock trong pure scorer.
4. Ghi mục target ngắn trong architecture: module Location riêng, raw theo H1,
   không đổi entry hoặc SMC, cùng version chỉ có một công thức live.

**Đầu ra/kiểm tra:** fixture H1/H4 đúng cadence, có một cây chưa đóng bị loại;
thêm nến tương lai không làm thay đổi dữ liệu tại cutoff cũ.
Đây là xác minh correctness của input, không xây dịch vụ lịch giao dịch mới.

#### Task 5 (B01) — Tạo module và bộ cấu hình mặc định

**File dự kiến mới:** core/location_engine.py; **test:** tests/test_location_engine.py.

**Thực hiện:**

1. Tạo LocationConfig immutable chứa các tham số ở §4.2, raw_max=25 và quy
   tắc rounding cố định.
2. Đặt model_version riêng, ví dụ location-geometry-v2, và một default config
   duy nhất trong module hoặc nguồn config chuẩn hiện có.
3. Chuẩn bị hai hàm public ở §4.1; config được resolve ở biên gọi, không đọc
   settings hoặc network bên trong phép tính.
4. Nếu không có cấu hình người dùng tùy chọn, dùng default đã ghi rõ. Khi người
   dùng cấu hình một phần, chỉ các key vắng được kế thừa default; key có giá trị
   sai không được thay bằng default.

**Đầu ra/kiểm tra:** import module không tạo file, thread, database hoặc gọi
broker. Chưa thay caller của Location hiện hành.

#### Task 6 (B02) — Validate cấu hình và input thiết yếu

**File:** core/location_engine.py và test domain mới.

**Thực hiện:**

1. Tạo LocationDataError hoặc kiểu lỗi nhỏ tương đương có code và thông tin
   field sai. Dùng một kiểu lỗi thống nhất, không một exception cho mỗi field.
2. Counts phải là integer dương và không chấp nhận bool. ATR/price/factors
   phải hữu hạn; ATR>0, giá>0; unknown_clearance_factor thuộc [0,1).
3. Các width/distance ratio phải dương; history phải đủ cho minimum input
   contract của Location. Cho phép dữ liệu thực ít hơn history mong muốn như §5.
4. Kiểm tra vùng low≤high, OHLC hợp lệ, side chỉ buy/sell và các status đã định
   nghĩa. Không dùng nhánh else để coi side viết sai thành sell.
5. Timestamp/cutoff phải thống nhất UTC aware. Chuẩn hóa ở adapter; domain
   không tự gán múi giờ cho input không rõ nghĩa.

**Đầu ra/kiểm tra:** T05 bao gồm None, bool, NaN/Inf, số âm, side sai và vùng
đảo biên. Dữ liệu invalid dẫn tới lỗi rõ, không dẫn tới raw=3/15.

#### Task 7 (B03) — Tạo Zone, Context và Result tối thiểu

**File:** core/location_engine.py.

**Thực hiện:**

1. Tạo các dataclass theo §4.3; dùng tuple cho zones và reason_codes để tránh
   BUY sửa dữ liệu mà SELL sẽ đọc.
2. Bổ sung side, cutoff và số nến H4 thực xét vào context/result khi cần giải
   thích; raw_exact có thể giữ để test rounding, không bắt buộc một field UI.
3. Chốt status kết quả: EVALUATED, LIMITED_CONTEXT, NO_VALID_ANCHOR, CONFLICT,
   UNAVAILABLE. Status này độc lập với gate PASS/BLOCK hiện có.
4. Với UNAVAILABLE, raw=null và các factor chưa tính=null. Các trạng thái đã
   đánh giá phải có raw integer 0–25. Không anchor/obstacle thì reference null,
   không dựng một zone zero-width giả.

**Đầu ra/kiểm tra:** tạo được cả BUY/SELL result và unavailable result hợp lệ;
reject status/raw mâu thuẫn. Không thêm parent revision, event log hay database ID.

#### Task 8 (B04) — Serialize detail và reason codes

> **Điểm dừng R1:** sau khi hoàn thành task 8, dừng và hỏi Tech Lead/người dùng
> theo §11.2; chưa được xác nhận thì không chuyển nhóm hoặc nghiệm thu cuối.

**File:** core/location_engine.py; core/reason_codes.py nếu repo tập trung reason
code ở đây.

**Thực hiện:**

1. Viết to_dict và parser cần dùng cho persisted detail; datetime thành ISO
   UTC, config thành dictionary số/string chuẩn.
2. Chọn các reason thực dùng: invalid data/config, no anchor, conflict,
   anchor too far, limited context. Không bắt buộc tạo mọi reason của bản
   tài liệu cũ nếu UI không cần.
3. Model version không được bỏ trống khi lưu kết quả mới. Parser không hiểu
   version thì báo unsupported; không đổi thành current version.
4. Dùng allow_nan=False hoặc validation tương đương để chặn JSON NaN/Inf.
5. Chỉ lưu anchor/obstacle đã chọn và factor cần giải thích, không toàn bộ nến.

**Đầu ra/kiểm tra:** round-trip giữ đúng raw=0, raw=null, side, reason, timestamp,
version và config. Null không biến thành 0 qua biểu thức value or default.

#### Task 9 (C01) — Lọc nến đóng và giới hạn history

**File:** core/location_engine.py; adapter ở A04 nếu cần.

**Thực hiện:**

1. Nhận cutoff tường minh và nến đã có semantics thời gian rõ.
2. Loại phần sau cutoff bằng closed_at, rồi mới lấy tối đa history_h4_bars.
3. Kiểm tra thứ tự và timestamp trùng; tuân theo adapter contract hiện có,
   không cho mỗi layer tự chọn một bản duplicate khác nhau.
4. Ghi số nến thực nhận. Đủ minimum hiện hành nhưng dưới 240 vẫn tính được.
   Thiếu minimum hoặc ATR hiện tại không tính được phải báo unavailable.
5. Chọn reference H1 cuối đã đóng qua adapter cùng cutoff, không lấy giá mới
   nhất từ MT5 bên trong Location.

**Đầu ra/kiểm tra:** một input đang chạy không bị dùng; giữ cutoff cũ và append
nến mới không đổi tập đầu vào. Không tăng yêu cầu tải nến toàn bộ Scanner chỉ
để ép đủ 240 trong bản đầu.

#### Task 10 (C02) — Swing identity và confirmed_at

**File:** core/location_engine.py, có thể gọi swing_points thuần từ smc_context.py.

**Thực hiện:**

1. Giữ tiêu chí swing hiện tại: lookback=2, extremum duy nhất trong cửa sổ.
2. ID dùng role và timestamp swing; nếu cần phân biệt symbol thì namespace ở
   context, không dùng index nến làm identity.
3. confirmed_at lấy close time của nến thứ hai bên phải; formed_at là thời
   điểm swing với semantics đã ghi ở A04.
4. Không tạo vùng nếu confirmed_at>cutoff hoặc thiếu nến bên phải.
5. Không sửa thuật toán swing của canonical SMC để phục vụ Location.

**Đầu ra/kiểm tra:** T12/T13 phần confirmation đạt; cùng swing trong cửa sổ
trượt vẫn có cùng ID khi còn đủ nến để xác nhận.

#### Task 11 (C03) — Dựng biên bằng ATR tại xác nhận

**File:** core/location_engine.py; tái sử dụng core/indicators.py.

**Thực hiện:**

1. Tính chuỗi ATR(14) một lần trên tập nến hợp lệ, tra ATR tại index xác nhận.
   Không cần gọi lại ATR cho từng prefix nếu recurrence cho cùng kết quả.
2. Swing chưa có ATR tại confirmation bị bỏ; không lấy ATR cuối để thay.
3. Dựng low/high theo §5.2. Tick size có sẵn thì làm tròn ra ngoài; thiếu tick
   size dùng biên ATR liên tục.
4. Nếu tick size được cung cấp nhưng invalid thì báo dữ liệu sai, không coi
   như chưa cung cấp.
5. Kiểm tra max width so với formation_atr, không so với ATR mới nhất. Lưu
   formation_atr cùng vùng.

**Đầu ra/kiểm tra:** T14 và các case tick/không tick. Với cùng lịch sử hình thành,
ATR ở các nến sau không làm biên cũ nở/co.

Lưu ý kiểm thử: so sánh trên cùng prefix hình thành. Khi cửa sổ trượt làm mất
warmup ATR cũ, cold rebuild có thể thay nhẹ ATR tại confirmation; không tuyên
bố biên bất biến qua mọi cửa sổ lịch sử khác nhau. Không thêm state store chỉ
để loại giới hạn này trong bản đầu.

#### Task 12 (C04) — Breach streak và tuổi vùng

**File:** core/location_engine.py.

**Thực hiện:**

1. Với từng vùng, duyệt close từ cây xác nhận tới cutoff theo thứ tự.
2. Support breach khi close<low-buffer; resistance khi close>high+buffer.
   Bằng break_line không tính breach. Buffer dùng formation_atr.
3. breach streak=1 thì SUSPECT nếu config yêu cầu 2. Đủ count thì INVALIDATED;
   close phục hồi trước đó reset streak=0 và ACTIVE.
4. INVALIDATED là terminal trong lần dựng; không hồi sinh nếu giá quay lại.
5. Tính age là số cây H4 đã đóng sau cây xác nhận: tại confirmation age=0.
   Hết hạn khi age>zone_max_age_h4_bars. Giữ INVALIDATED nếu đã bị phá trước
   đó; vùng chưa bị phá mới chuyển EXPIRED.
6. Không tự đảo role support/resistance.

**Đầu ra/kiểm tra:** T11/T12 gồm wick, close đúng biên, một/two breach, phục hồi
xen giữa và age=max/max+1 cho cả support/resistance. Close của cây xác nhận
cũng phải được kiểm tra, vì swing đã có thể mất vai trò ngay lúc khả dụng.

#### Task 13 (C05) — Dedup và thứ tự ổn định

**File:** core/location_engine.py.

**Thực hiện:**

1. Giữ một vùng cho cùng ID và cùng dữ liệu nguồn.
2. Nếu cùng ID nhưng biên/dữ liệu mâu thuẫn trong cùng context, báo invalid
   input thay vì chọn tùy thứ tự.
3. Các swing khác ID dù nằm sát nhau vẫn là các vùng riêng. Không cộng điểm
   vì có nhiều vùng và không gộp support với resistance.
4. Sắp xếp vùng theo role/confirmation/ID hoặc khóa xác định tương đương.
5. Không bổ sung confluence/test_count/số tròn giả vào model mới.

**Đầu ra/kiểm tra:** đảo thứ tự input hoặc thêm exact duplicate không đổi kết
quả lựa chọn/score. Chưa triển khai merge cụm vùng.

#### Task 14 (C06) — Kiểm tra causal và dùng chung context

> **Điểm dừng R2:** sau khi hoàn thành task 14, dừng và hỏi Tech Lead/người dùng
> theo §11.2; chưa được xác nhận thì không chuyển nhóm hoặc nghiệm thu cuối.

**File:** core/location_engine.py và tests/test_location_engine.py.

**Thực hiện:**

1. Dựng context từ một prefix nến, lưu kết quả.
2. Append nến tương lai, dựng lại với cùng cutoff và đối chiếu.
3. Gọi score BUY rồi SELL, sau đó đảo thứ tự; zone state/context phải không đổi.
4. Kiểm tra ID/timestamp không lấy wall-clock hay random.
5. Đảm bảo chỉ dựng context một lần cho hai phía; chưa cần tối ưu cache.

**Đầu ra/kiểm tra:** T13 đạt với cùng đầu vào hợp lệ. Chấp nhận thay đổi hợp lý
khi cutoff/nến correction hoặc coverage thực thay đổi; không viết test đòi
score giống nhau trên hai tập dữ liệu khác nhau.

#### Task 15 (D01) — Chọn anchor đúng phía

**File:** core/location_engine.py.

**Thực hiện:**

1. Tạo distance_to_interval: trong interval bằng 0; ngoài interval tính tới mép.
2. BUY chỉ lấy support ACTIVE và price≥low; SELL chỉ lấy resistance ACTIVE
   và price≤high.
3. Loại invalidated/expired/suspect hoặc chưa confirmed. Không thử đưa vùng
   đã bị loại trở lại bằng khoảng cách tuyệt đối.
4. Tie-break theo distance nhỏ hơn, width nhỏ hơn, confirmed_at mới hơn,
   rồi ID từ điển. Định nghĩa một tuple key, không phụ thuộc thứ tự list.
5. Không có anchor trả None để scorer xử lý NO_VALID_ANCHOR, không throw
   “thiếu dữ liệu” nếu input vẫn hợp lệ.

**Đầu ra/kiểm tra:** T01/T04, giá đúng low/high được xem nằm trong vùng; một vùng
gần hơn nhưng sai phía không che vùng hợp lệ phía sau.

#### Task 16 (D02) — Obstacle và ưu tiên xung đột

**File:** core/location_engine.py.

**Thực hiện:**

1. BUY lấy resistance ACTIVE/SUSPECT chứa giá hoặc có low>price; SELL lấy
   support ACTIVE/SUSPECT chứa giá hoặc có high<price.
2. Kiểm tra mọi obstacle hợp lệ chứa giá trước khi tính điểm proximity.
   Chứa giá tính cả hai mép interval.
3. Nếu nhiều obstacle chứa giá, chọn một để giải thích bằng tie-break ổn định,
   nhưng raw luôn bằng 0; không chọn vùng cho score đẹp hơn.
4. Không có conflict thì chọn obstacle phía trước gần nhất; clearance tới
   mép gần nhất, không tới center.
5. Không có obstacle -> None; không dùng infinity, zero hoặc vùng ở phía sau.

**Đầu ra/kiểm tra:** T02/T03/T10. Input lỗi vẫn ưu tiên UNAVAILABLE trước conflict;
geometry hợp lệ có conflict thì raw=0 kể cả không có anchor.

#### Task 17 (D03) — Tính P, C và điểm nguyên — Hoàn thành; R3 đã duyệt

**File:** core/location_engine.py; test normalization hiện có.

**Thực hiện:**

1. Dùng ATR H4 hiện tại hợp lệ để tính distance_atr/clearance_atr.
2. Áp dụng P và C đúng §6.3; không bonus, base point hoặc penalty ngoài đó.
3. Tính raw_exact=25×P×C. Thực hiện ROUND_HALF_UP tường minh, ví dụ Decimal
   với cách chuyển số thống nhất; không dùng Python round mặc định cho x.5.
4. Trả raw int 0–25. Factors/điểm chính thức được tính ở engine; formatter UI
   chỉ làm tròn cách hiển thị.
5. Kiểm thử contribution bằng scorer hiện có; không đổi raw_max hoặc Fraction.

**Đầu ra/kiểm tra:** T06–T10/T16 và các expected 25,13,5,13,0 ở §6.
Với 0.5000 ATR raw=13, 0.5001 ATR raw=12 theo half-up chuẩn; lệch 1 chấp nhận
được, không còn lệch 7 như baseline.

#### Task 18 (D04) — Result, reason và unavailable — Hoàn thành; R3 đã duyệt

**File:** core/location_engine.py.

**Thực hiện:**

1. Validate trước, sau đó xử lý conflict, no-anchor, anchor-too-far và công
   thức thông thường theo thứ tự đã định.
2. Có anchor/không obstacle thì LIMITED_CONTEXT và dùng hệ số unknown.
   Nếu no-anchor hoặc conflict thì giữ status ưu tiên đó, không ghi status
   “evaluated tốt” chỉ vì có một phần dữ liệu.
3. Lưu đúng side, reference H1, anchor/obstacle và config thực dùng; giữ None
   khi chưa tính được distance/factor.
4. Lỗi domain dự kiến có thể chuyển thành UNAVAILABLE result qua một wrapper
   rõ ràng. Không catch mọi Exception rồi trả 0; lỗi lập trình phải hiện trong
   test và được luồng error handling hiện có ghi nhận.

**Đầu ra/kiểm tra:** cùng raw nhưng lý do khác vẫn giữ được detail đúng.
UNAVAILABLE=null và NO_VALID_ANCHOR=0 không bị trộn.

#### Task 19 (D05) — Chạy invariants và review phạm vi — Hoàn thành

**File:** tests/test_location_engine.py, core/location_engine.py.

**Thực hiện:**

1. Gộp các input tương tự thành parametrized cases cho T01–T16.
2. Kiểm tra monotonicity bằng thay riêng khoảng cách anchor hoặc obstacle,
   giữ các yếu tố khác cố định để expected có ý nghĩa.
3. Test reflection BUY/SELL, duplicate, input order và causal theo §9.
4. Kiểm tra module không import news, order dispatch, AI, SMC scorer hoặc
   scenario R:R; primitive swing/ATR thuần được phép tái sử dụng.
5. Chạy targeted tests một lần, sửa lỗi rồi chạy lại các nhóm liên quan.

**Đầu ra/kiểm tra:** engine đúng các invariant; không giữ test chỉ assert kết
quả bằng chính hàm implementation thứ hai viết lại cùng công thức.

#### Task 20 (E01) — Xem 5–10 case từ biểu đồ hoặc export sẵn có — Hoàn thành; R3 đã duyệt

**Dữ liệu:** nến/snapshot/export có sẵn trên máy; không cần nguồn trả phí.

**Thực hiện:**

1. Chọn các tình huống ở §10, ưu tiên symbol người dùng đang giao dịch.
2. Gọi engine độc lập trên dữ liệu/cutoff xác định; không gọi luồng gửi lệnh.
3. Xem reference H1, vùng được chọn, vùng bị phá, clearance và điểm.
4. Nếu cần so trước/sau, dùng baseline fixture hoặc ghi chú score hiện tại,
   không nối hai scorer vào live.
5. Không có dữ liệu chart/export phù hợp thì tiếp tục F/G độc lập, ghi E01
   còn chờ dữ liệu; không lấy fixture giả rồi tuyên bố đã kiểm tra chart thật.
   Có thể lấy dữ liệu chỉ đọc qua kết nối đã có nếu được phép và sẵn sàng.

**Đầu ra/kiểm tra:** bảng case/result/note ngắn, ghi rõ giả lập hay dữ liệu thực.
Không cần bộ mô phỏng giao dịch hoặc một script evaluator lâu dài.

**Ghi nhận E01 (2026-09-09):** workspace không có raw H1/H4 candle export hoặc
ảnh chart có timestamp; dùng `tests/fixtures/smc_canonical/golden_cases.json`
như snapshot export có sẵn. Đây là fixture snapshot, không phải chart live và
không được dùng để kết luận lợi nhuận. Snapshot không có `reference_closed_at`
H1 và không có lifecycle timestamp của technical zones; adapter chỉ gán mốc
cutoff cố định để dựng `LocationContext`, với zones ACTIVE để kiểm tra geometry.

| Case snapshot | Dữ liệu | BUY | SELL | Ghi chú |
|---|---|---|---|---|
| `buy_selected_zone` | price 1.1000; ATR H4 0.0010 | `EVALUATED`, raw 0, d 1.80 ATR, g 5.80 ATR | `EVALUATED`, raw 0, d 5.80 ATR, g 1.80 ATR | Anchor/obstacle đúng role; anchor quá xa |
| `sell_selected_zone` | price 1.1000; ATR H4 0.0010 | `EVALUATED`, raw 0, d 5.80 ATR, g 1.80 ATR | `EVALUATED`, raw 0, d 1.80 ATR, g 5.80 ATR | Phản chiếu đúng phía; anchor quá xa |
| `no_zone` | price 1.1000; ATR H4 0.0010 | `EVALUATED`, raw 0, d 1.80 ATR | `EVALUATED`, raw 0, d 5.80 ATR | SMC không có canonical zone không làm Location tự mất technical zones |
| `fvg_h1_only` | price 1.1000; ATR H4 0.0010 | `EVALUATED`, raw 0, d 1.80 ATR | `EVALUATED`, raw 0, d 5.80 ATR | FVG H1 không được đưa vào Location obstacle |
| `order_block` | price 1.1000; ATR H4 0.0010 | `EVALUATED`, raw 0, d 1.80 ATR | `EVALUATED`, raw 0, d 5.80 ATR | Order block không được đưa vào Location anchor |
| `broken_stale` | price 1.1000; ATR H4 0.0010 | `EVALUATED`, raw 0, d 1.80 ATR | `EVALUATED`, raw 0, d 5.80 ATR | Snapshot không có lifecycle đủ để xác nhận broken/stale |
| `choch_cap` | price 1.1000; ATR H4 0.0010 | `EVALUATED`, raw 0, d 1.80 ATR | `EVALUATED`, raw 0, d 5.80 ATR | CHoCH cap thuộc SMC, không thay đổi Location geometry |
| `missing_data_valid` | price 1.1000; ATR H4 thiếu | `UNAVAILABLE`, raw null | `UNAVAILABLE`, raw null | Không fallback ATR/điểm; reason `LOCATION_INVALID_DATA` |

Kết luận exploratory của snapshot cũ: engine chọn đúng role/forward obstacle và
giữ đối xứng BUY/SELL, nhưng snapshot không đủ bằng chứng nghiệm thu E01. Bảng
raw H1/H4 dưới đây là bằng chứng bổ sung dùng để đóng E01.

**E01 bổ sung bằng dữ liệu raw (2026-09-09):** nguồn đọc-only là
[Yahoo Finance Chart API](https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?range=60d&interval=60m), symbol `EURUSD=X`,
`range=60d`, `interval=60m`; thu được 1.421 nến H1. Script review gom các nhóm
4 nến H1 liên tiếp theo UTC thành 345 nến H4, chọn reference H1 đã đóng tại
cutoff và gọi `build_location_context()`/`score_location_safe()` độc lập với
config mặc định. Không lưu dữ liệu raw vào repo, không gọi scanner/runtime và
không dùng kết quả để kết luận P&L.

| Case raw EUR/USD (cutoff UTC) | Reference / ATR H4 | BUY | SELL | Tình huống §10 và ghi chú |
|---|---|---|---|---|
| `2026-07-06 07:00` | 1.142465 / 0.002119 | `EVALUATED`, raw 25, d 0.000, g 1.753 | `CONFLICT`, raw 0 | Gần support; đồng thời kiểm tra conflict SELL; có zone INVALIDATED nhưng không được chọn |
| `2026-07-02 20:00` | 1.143380 / 0.002495 | `CONFLICT`, raw 0 | `EVALUATED`, raw 25, d 0.000, g 2.579 | Gần resistance; conflict BUY; zone invalidated bị loại khỏi lựa chọn |
| `2026-07-02 17:00` | 1.144165 / 0.002525 | `CONFLICT`, raw 0 | `NO_VALID_ANCHOR`, raw 0 | Conflict và thiếu anchor đối diện; có các zone SUSPECT/INVALIDATED |
| `2026-08-27 10:00` | 1.164551 / 0.001344 | `EVALUATED`, raw 25, d 0.000, g 2.462 | `CONFLICT`, raw 0 | Conflict SELL; có overlap support/resistance và lifecycle INVALIDATED/EXPIRED |
| `2026-07-02 08:00` | 1.141162 / 0.002150 | `EVALUATED`, raw 0, d 1.960, g 0.870 | `EVALUATED`, raw 3, d 0.870, g 1.960 | Vùng bị phá: zone INVALIDATED không được dùng làm anchor; điểm còn lại khớp P×C |
| `2026-07-09 00:00` | 1.142465 / 0.002041 | `EVALUATED`, raw 0, d 1.317, g 0.301 | `EVALUATED`, raw 17, d 0.301, g 1.317 | Chồng lấn support/resistance; chọn deterministic và không cộng điểm do overlap |
| `2026-07-02 13:00` | 1.145344 / 0.002136 | `LIMITED_CONTEXT`, raw 0, d 3.931, C 0.5 | `NO_VALID_ANCHOR`, raw 0 | Xa vùng và thiếu obstacle BUY; giữ cả `LOCATION_ANCHOR_TOO_FAR` + `LOCATION_LIMITED_CONTEXT` |
| `2026-08-20 10:00` | 1.171097 / 0.001842 | `LIMITED_CONTEXT`, raw 0, d 7.299, C 0.5 | `NO_VALID_ANCHOR`, raw 0 | Xa vùng; có zone EXPIRED/INVALIDATED và overlap, nhưng vùng hết hạn không được chọn |

Các case raw đã bổ sung đủ gần hỗ trợ, gần resistance, conflict, vùng bị phá,
chồng lấn, xa vùng và thiếu obstacle theo §10. Kết quả không cho thấy sai khác
cần sửa thêm; không đổi threshold/weight/config theo symbol.

#### Task 21 (E02) — Ghi kết quả và sửa sai khác — Hoàn thành; R3 đã duyệt

> **Điểm dừng R3:** đã được Tech Lead xác nhận duyệt. Task 15–21 hoàn thành;
> được phép tiếp tục nhóm F/G và sẽ dừng tại R4 sau task 28 theo §11.2.

**File:** ghi chú trong tài liệu này hoặc một mục ngắn trong docs/plans.

**Thực hiện:**

1. Với mỗi case, ghi anchor/obstacle hợp lý hay chưa và score có khớp công thức.
2. Nếu sai do implementation, tạo fixture cho đúng lỗi rồi sửa engine.
3. Nếu sai do giới hạn thiết kế (ví dụ breakout/entry limit), ghi giới hạn,
   không tự thêm một subsystem mới hoặc chỉnh tham số từng symbol.
4. Nếu thấy điểm mới thường cao/thấp hơn, ghi tác động; không tự đổi threshold
   hay weight của Scanner để bù.

**Đầu ra/kiểm tra:** logic đạt sau sửa các lỗi quan sát được; không yêu cầu
P&L/holdout report. Không dùng vài biểu đồ để khẳng định hiệu quả lợi nhuận.

**Kết luận E02 (2026-09-09, cập nhật sau review R3):** hai findings code đã
được sửa. D03 dùng Decimal nhất quán cho distance/factor/raw trước khi
`ROUND_HALF_UP`, có regression FX BUY/SELL tại `price=1.1`, `anchor.high=1.0995`,
`ATR=0.001`, raw 13. D04 giữ `LIMITED_CONTEXT` và đồng thời ghi
`LOCATION_ANCHOR_TOO_FAR` khi có anchor xa nhưng không có obstacle; raw vẫn 0.

Không đổi threshold, weight hoặc cấu hình theo symbol. E01 nay đã đủ mẫu raw
theo §10; Tech Lead đã duyệt R3 cho Task 15–21. Task 22 được triển khai ở lớp
feature/prepare; chưa nối caller production hoặc runtime trước H01.

#### Task 22 (F01) — Gắn kết quả vào feature output

**File bắt đầu:** core/scanner_features.py, core/scanner_live_producers.py.

**Thực hiện:**

1. Thêm location_detail hoặc field tương đương cạnh location trong
   SideFeatureRaws, không thay ba raw key chuẩn của SideSnapshot.
2. Chuẩn bị adapter tạo context một lần và score hai phía; raw và detail
   phải lấy từ cùng LocationResult, không gọi engine lại để tạo detail.
3. to_dict của feature phải mang detail theo side. Không mượn smc_source
   hoặc reason của Macro để nhét provenance Location.
4. Tại bước prepare, test adapter bằng fixture/new-engine call trực tiếp;
   caller production cũ chỉ đổi ở H01.
5. Không đánh dấu raw cũ bằng model_version mới để giữ test passing.

**Đầu ra/kiểm tra:** raw của BUY/SELL khớp raw trong detail đúng phía; sửa
detail của một phía không làm mutate phía còn lại.

**Kết luận F01 (2026-09-09):** `SideFeatureRaws` có thêm
`location_detail: LocationResult | None`; `to_dict()` serialize detail theo
đúng side và không thay ba raw key của `SideSnapshot`. Adapter mới
`prepare_location_results()` chọn reference H1, dựng đúng một
`LocationContext`, rồi chấm BUY/SELL; `attach_location_results()` lấy raw từ
chính result đã gắn detail. `derive_technical_raws_with_location()` là đường
prepare opt-in, giữ nguyên caller production cũ cho tới H01 và không gắn
`model_version` mới lên raw legacy. Regression feature kiểm tra một context,
raw/detail cùng nguồn, reference H1 và không mutate chéo BUY/SELL:
`python -m pytest tests/test_scanner_features.py -q --disable-warnings` —
**27 passed**.

#### Task 23 (F02) — Truyền detail qua canonical snapshot và reader

**File bắt đầu:** core/scanner_live_producers.py (build_side_snapshot),
core/scanner_release.py, core/scanner_composition.py, core/scanner_snapshot.py,
core/scanner_v4_models.py khi contract chính thức cần mở rộng.

**Thực hiện:**

1. Theo đường feature -> side snapshot -> canonical result/full envelope ->
   UI adapter, tìm field provenance/detail hợp lệ để lưu kết quả.
2. Nếu cần field mới, thêm một location_detail theo side cùng validator,
   to_dict/from_dict ở đúng lớp nhận nó. Không thêm tùy ý vào technical_raws.
3. Full detail giữ thông tin cần giải thích; compact row giữ tối thiểu hoặc
   tham chiếu tới full detail hiện có.
4. Input mới đã mang model version mới phải có detail hợp lệ và raw trùng
   giữa các lớp; reject mismatched raw/side thay vì lấy một bên tùy ý.
5. Reader historical xử lý bản cũ thiếu detail bằng “không có chi tiết”, không
   bịa detail hiện hành; tránh mở rộng validator live để nhận mọi payload cũ.

**Đầu ra/kiểm tra:** T18 round-trip tới đúng nơi UI sẽ đọc, không chỉ round-trip
LocationResult đơn lẻ. Không tạo database hoặc cơ chế snapshot thứ hai.

**Kết luận F02 (2026-09-09):** `SideSnapshot` nhận `location_detail` nhưng
không đưa detail vào `technical_raws`; canonical `SideScore` giữ full
`LocationResult` và validator bắt buộc side/raw khớp. Full composition/envelope
round-trip giữ nguyên detail; compact envelope và `ScannerRow` giữ summary
`location_raw/status/reason_codes` để UI đọc mà không nhúng toàn bộ detail.
Reader cũ thiếu detail vẫn đọc với trạng thái không có chi tiết; payload mới sai
side hoặc raw bị reject. Test `tests/test_location_canonical_detail.py` — **3
passed**; regression canonical/reader/live — **307 passed**. Chưa đổi version,
cache/hash policy hoặc nối engine mới vào runtime; các phần đó thuộc Task 24 và
H01.

#### Task 24 (F03) — Version, cấu hình và existing cache/hash

**File bắt đầu:** constants/version validators ở core/scanner_features.py,
core/scanner_v4_models.py, core/scanner_snapshot.py; hash hiện có trong
core/scanner_composition.py và các cache caller tìm được ở A01.

**Thực hiện:**

1. Ghi ngắn field version nào thực sự đổi. Dùng version hiện hành của Scanner,
   không nhầm identity legacy trong core/scoring_provenance.py.
2. Model mới không trở thành alias “tương đương” của công thức cũ.
3. Lưu config đã resolve, gồm default và override thực dùng, vào detail.
4. Nếu existing canonical input/hash/cache key được dùng cho snapshot hoặc
   tái sử dụng score, thêm identity/config liên quan để không trả kết quả cũ
   khi cấu hình đổi. Không thêm framework fingerprint mới.
5. Model/version/config mới phải được activate đồng thời với H01.
6. Snapshot/journal cũ không bị viết lại; unsupported reader báo rõ.

**Đầu ra/kiểm tra:** đổi config nhưng raw tình cờ giữ nguyên vẫn nhận biết được
config đã dùng. Cache cũ không được trả dưới identity mới.

**Kết luận F03 (2026-09-09):** không bump global Scanner
`feature_version` trước H01 và không đổi identity SMC/legacy. Đường Location
mới được nhận diện bằng `LocationResult.model_version` (`location-geometry-v2`),
`config_used` chứa toàn bộ config đã resolve, còn `TechnicalRaws.derivation`
ghi model/config tương ứng. Fingerprint hiện có chỉ bổ sung full Location detail
khi detail thực sự có mặt; feature legacy giữ nguyên hash shape. Canonical
`snapshot_id` đã hash detail từ F02 nên đổi config sẽ đổi snapshot identity dù
raw tình cờ không đổi. Không có feature-score/cache riêng cần migration; payload
lịch sử không có detail vẫn đọc theo đường tương thích cũ. Việc activate đồng
thời model/version/config mới vào runtime vẫn để H01.

Regression config/hash: `tests/test_scanner_features.py` và
`tests/test_location_canonical_detail.py` — **32 passed**; canonical/reader/
Location regression — **554 passed**; `git diff --check` đạt.

#### Kết luận F04 (2026-09-09)

`prepare_location_results()` chuyển `LocationDataError` thành
`TechnicalRawDerivationError` typed với `LOCATION_INVALID_DATA` hoặc
`LOCATION_INVALID_CONFIG`, kèm `field` và `cause`. Handler hiện hữu trong
`_analyze_one_symbol()` giữ `reason_code` khi tạo `blocked_ui_row`; row vẫn là
`DATA_UNAVAILABLE`, không có order intent và reason được truyền tới các trường
UI/diagnostic hiện có. `attach_location_results()` tiếp tục reject `raw=None`
thay vì đưa `None` vào contract raw integer. Ngược lại, `NO_VALID_ANCHOR` với
`raw=0` vẫn là kết quả hợp lệ và đi qua feature/composition path.

Regression Task 25 bao phủ ATR lỗi, zero hợp lệ, typed reason/field/cause và
handler unavailable row: `python -m pytest tests/test_scanner_features.py
tests/test_scanner_ui_adapter.py -q --disable-warnings` — **54 passed**.
Chưa mở runtime Location engine; việc đó vẫn thuộc H01.

#### Task 25 (F04) — Nối unavailable vào luồng lỗi hiện có

**File bắt đầu:** core/scanner_features.py, core/scanner_live_producers.py,
controllers/scanner_controller.py và core/scanner_row.py nếu là owner của row lỗi.

**Thực hiện:**

1. Khi Location UNAVAILABLE, adapter raise TechnicalRawDerivationError có
   reason Location và field/cause cần thiết.
2. Theo actual exception handler tới unavailable row; nếu handler chưa giữ
   reason thì bổ sung tại đúng chỗ, không thêm gate mới.
3. Không đưa None vào SideSnapshot yêu cầu int; không dùng int(value or 0).
4. Không biến NO_VALID_ANCHOR raw=0 thành exception; đó là kết quả tính hợp lệ.
5. Giữ error path hiện có: nếu lỗi raw khiến cả symbol unavailable thì ghi rõ,
   chưa mở rộng nullable score từng component trong bản đầu.

**Đầu ra/kiểm tra:** T20 với ATR lỗi đi đến row không được phép thực thi;
zero hợp lệ vẫn đi qua composition để các gate hiện có xử lý bình thường.

#### Kết luận G01 (2026-09-09)

Render path hiện hữu của Scanner Detail tiếp tục được dùng. Adapter UI làm giàu
side summary compact bằng `technical_breakdown` và `location_detail` lấy trực
tiếp từ canonical composition; không gọi lại scorer/Location engine. Presenter
giữ Location detail tùy chọn cho payload mới và chấp nhận payload lịch sử thiếu
detail. Chẩn đoán UI hiển thị raw `/25`, contribution, reference price/time của
H1, anchor/obstacle, khoảng cách/clearance theo ATR, status/reason và model/config.
Raw `0` được hiển thị là `0`; raw `null` là “Không đủ dữ liệu”; thiếu detail ghi
rõ bản lưu cũ và thiếu obstacle ghi “Chưa quan sát được trong dữ liệu đã xét”.
`price_vs_zone` vẫn chỉ là vị trí so với entry zone.

Regression G01: presentation + adapter — **43 passed**; render Location raw
`0/13/null` và H1 reference — **3 passed**. `compileall` đạt; chưa nối runtime
Location engine, vẫn thuộc H01.

**Sửa finding R4 cho G01/F02 (2026-09-10):** reader compact/full envelope và
`ScannerRow` nay validate status Location thuộc contract, raw của trạng thái
được giới hạn `0..25`, `UNAVAILABLE` bắt buộc raw `null`,
`CONFLICT`/`NO_VALID_ANCHOR` bắt buộc raw `0`, và full envelope đối chiếu summary
với `canonical.location_detail`; summary mâu thuẫn bị reject. Formatter UI dùng
độ chính xác giá theo symbol/`price_digits` hiện có, nên EUR/USD hiển thị 5 chữ
số thay vì cố định 2 chữ số.

#### Task 26 (G01) — UI đọc điểm và reference đúng

**File bắt đầu:** core/scanner_ui_adapter.py,
ui/scanner_v4_presentation.py, ui/screens/scanner_detail_screen.py.

**Thực hiện:**

1. Xác minh render path đang chạy, rồi đưa Location detail qua adapter đó.
2. Hiển thị raw/25 và contribution từ technical breakdown canonical. UI
   không gọi engine, không áp lại trọng số hay tính thêm bonus.
3. Hiển thị H1 close/time, anchor/obstacle, khoảng cách và reason dạng ngắn.
4. Raw=0 hiển thị 0; None hiển thị chưa đủ dữ liệu. Thiếu obstacle không ghi
   “không có kháng cự” mà ghi “chưa quan sát được trong dữ liệu đã xét”.
5. Cột “Vị trí”/price_vs_zone của Scanner có thể là proximity tới entry zone,
   không phải Location raw. Không ghi đè hoặc đổi tên field đó vì giống chữ.

**Đầu ra/kiểm tra:** T19 với fixture raw0/null/13 và data legacy thiếu detail.
Nhìn card biết đang chấm H1 reference, không nhầm là entry limit.

#### Task 27 (G02) — Hồi quy các phần giữ nguyên

**File:** tests/test_scanner_features.py, tests/test_scanner_live_producers.py,
tests/test_scanner_scenario_producers.py và test SMC liên quan nếu có consumer đổi.

**Thực hiện:**

1. Với cùng bộ nến, so Trend raw, Momentum raw, canonical SMC và regime với
   baseline trước thay Location.
2. Kiểm tra support_zones/resistance_zones legacy không bị mutate bởi engine mới.
3. Kiểm tra scenario plan từng side không đổi nếu input scenario không đổi.
4. Chấp nhận selected_side/candidate có thể đổi do Location mới: đây là tác
   động mong đợi của score, không được ép giống baseline bằng chỉnh threshold.
5. Không dùng “SMC/scenario phải không đổi” để khóa luôn selected_side hoặc
   candidate cuối, vì chúng phụ thuộc tổng điểm.

**Đầu ra/kiểm tra:** T17 đạt ở đúng cấp dữ liệu; các khác biệt downstream có
thể giải thích bằng Location, không do vô tình sửa helper chung.

#### Kết luận G02 (2026-09-09)

Regression với cùng bộ nến xác nhận adapter Location không làm đổi Trend raw,
Momentum raw, canonical SMC hoặc regime; `support_zones`/
`resistance_zones` và input candles không bị mutate. Scenario plan vẫn giữ
nguyên khi chỉ bổ sung Location detail vào snapshot với cùng raw. Không thêm
assertion buộc `selected_side` hoặc candidate cuối phải giống baseline: các giá
trị này được phép thay đổi khi Location raw thay đổi và đó là tác động downstream
hợp lệ của task.

Regression G02: feature/canonical/live/scenario/SMC — **118 passed**; bộ mở rộng
Location + composition + release + technical — **438 passed**; không chỉnh
threshold/weight và chưa nối runtime Location engine.

#### Task 28 (G03) — Kiểm tra card trên giao diện

> **Điểm dừng R4:** sau khi hoàn thành task 28, dừng và hỏi Tech Lead/người dùng
> theo §11.2; chưa được xác nhận thì không chuyển nhóm hoặc nghiệm thu cuối.

**File:** cùng render path G01 và test UI hiện có.

**Thực hiện:**

1. Xem card ở dark/light và chiều rộng nhỏ/lớn mà app hỗ trợ.
2. Thử reason dài, số giá nhiều chữ số, raw=null và thiếu obstacle.
3. Dùng formatter/style đang có để xuống dòng và rút gọn; không tạo màn hình,
   overlay chart hoặc bảng cấu hình mới.
4. Có thể render bằng fixture trước H01; ghi đây là UI fixture check. Đường
   runtime thật được smoke ở H02.

**Đầu ra/kiểm tra:** card không tràn/cắt nội dung quan trọng; điểm và reference
dễ đọc. Cập nhật test/style baseline chỉ nếu contract repo đòi và có thay đổi thật.

#### Kết luận G03 (2026-09-10) — **R4 đã được Tech Lead duyệt sau review lại**

Giữ nguyên render path Chẩn đoán hiện có; không tạo màn hình, overlay chart hoặc
bảng cấu hình mới. Card Location bổ sung style responsive `width:100%`,
`table-layout:fixed`, `word-wrap:break-word` và `overflow-wrap:anywhere` để
reason/mã dài, timestamp và số giá nhiều chữ số không làm tràn hoặc cắt nội
dung quan trọng ở viewport hẹp/rộng. Fixture kiểm tra cả dark/light, 320/1280
px, raw `0`, raw `null`, thiếu obstacle và historical detail thiếu; raw/reference/
reason vẫn hiển thị đúng, không nhầm với `price_vs_zone`.

Regression G03: `python -m pytest tests/test_scanner_detail_v4_diagnostics.py
-k location_html -q --disable-warnings` — **10 passed**; render QTextEdit thật
ở 320/1280 px và dark/light không có horizontal overflow; reader negative
regression `tests/test_location_canonical_detail.py` — **46 passed**. `compileall`
và `git diff --check` đạt. Đây là UI fixture check trước H01; chưa smoke runtime
thật. Tech Lead đã review lại và duyệt R4 ngày 2026-09-10; được phép tiếp tục Task 29–32 và dừng tại R5. Bằng chứng review lại được ghi ở nhật ký bên dưới.

#### Task 29 (H01) — Chuyển sang một công thức Location mới

**File bắt đầu:** core/scanner_features.py, core/scanner_live_producers.py,
core/scanner_release.py cùng version/serializer đã chuẩn bị.

**Thực hiện:**

1. Kiểm tra E02/F03/F04/G02 hoàn tất; G03 phải hoàn tất trước H02/bàn giao.
2. Đổi raw producer để gọi adapter/engine mới đúng một lần mỗi context cho hai
   side, truyền detail cùng kết quả.
3. Bỏ call Location cũ trên runtime. Nếu cần giữ expected lịch sử, chỉ giữ
   fixture/reference trong test; không thêm fallback score cũ khi engine mới lỗi.
4. Cập nhật feature derivation string/version để mô tả Location mới và các
   thành phần còn giữ nguyên; không tiếp tục ghi cả bộ raw là legacy port.
5. Chuyển caller/version/parser đồng bộ trong cùng bản phát hành. Không phát
   hành trạng thái nửa schema cũ, nửa score mới.
6. Tìm lại toàn bộ caller để bảo đảm không sót path và không có dual/shadow flag.

**Đầu ra/kiểm tra:** input live hợp lệ chỉ tạo Location bằng công thức mới;
input lỗi đi vào unavailable, không chạy công thức cũ dự phòng.

#### Kết luận H01 (2026-09-10) — Hoàn thành; Tech Lead đã DUYỆT R5 sau review lại

`derive_live_analysis()` nay gọi `derive_technical_raws_with_location()`: dựng
`LocationContext` một lần ở cutoff runtime, giữ reference H1 đã đóng, rồi chấm
BUY/SELL từ cùng context và truyền nguyên `LocationResult` cùng raw qua
`build_side_snapshot()`/composition/release. Controller truyền lại analysis đã
tạo vào `run_pair_from_live()` nên không tính analysis hai lần.

Producer runtime không còn gọi `location_quality_score_v4`; công thức cũ chỉ còn
ở public legacy/parity fixture path. Derivation runtime ghi rõ
`location=location-geometry-v2`, config resolved và `location_source`; input lỗi
Location vẫn đi typed unavailable, không fallback raw cũ. Fixture live được
điều chỉnh về cadence D1/H4/H1 thực tế, không nới cutoff hoặc minimum history.

Regression H01: `python -m pytest tests/test_location_engine.py
tests/test_scanner_features.py tests/test_scanner_live_producers.py
tests/test_scanner_release.py tests/test_scanner_composition.py
tests/test_scanner_integration.py tests/test_scanner_snapshot.py
tests/test_scanner_row.py tests/test_location_canonical_detail.py -q
--disable-warnings` — **363 passed**; `compileall` và `git diff --check` đạt.
Chưa smoke full controller/broker; phần đó thuộc Task 30.

#### Task 30 (H02) — Targeted integration tests và smoke

**File/test:** các file thực sự sửa trong F/G/H, test domain mới và existing
tests tại §9.

**Thực hiện:**

1. Chạy T01–T20 theo phạm vi hiện thực và các test regression liên quan.
2. Test từ derive_live_analysis/run_pair_from_live tới snapshot và UI adapter
   bằng fixture, mock order dispatch để không gửi lệnh.
3. Smoke một lượt Scanner với dữ liệu có sẵn trong môi trường không gửi lệnh
   thật. Không tự bật auto-trade hoặc đổi cấu hình tài khoản.
4. Kiểm tra ít nhất một evaluated, một conflict/no-anchor và một unavailable.
5. Nếu repo yêu cầu hoặc schema ảnh hưởng rộng, chạy full suite một lần cuối.
   Có failure mới thì sửa và chạy lại phạm vi tương ứng.

**Đầu ra/kiểm tra:** command/kết quả rõ; không tuyên bố smoke live nếu chỉ test
fixture. Môi trường thiếu UI/broker thì ghi phần chưa kiểm tra, hoàn thành các
kiểm tra độc lập và không giả kết quả.

#### Kết luận H02 (2026-09-10) — Hoàn thành; Tech Lead đã DUYỆT R5 sau review lại

Đã thêm `tests/test_scanner_h02_integration.py` với bốn kiểm tra: pipeline
`derive_live_analysis` → `run_pair_from_live` → snapshot row → UI adapter không
dispatch lệnh thật; ma trận `EVALUATED`, `CONFLICT`, `NO_VALID_ANCHOR`; lỗi
Location chuyển thành `UNAVAILABLE` fail-closed không fallback scorer cũ; và
context giữ cutoff/reference/history dùng chung. **4 passed**.

Đã chạy lại regression H01 theo phạm vi Location/scanner/canonical — **363
passed** — và `python scripts/scanner_smoke.py` thành công cho cả smoke chính và
PATHB. Smoke ghi `sends_real_order=False`, không gửi broker order, tạo
`reports/scanner/release_b12_smoke.json` và
`reports/scanner/release_b12_pathb_smoke.json`; PATHB xác nhận thiếu history
fail-closed bằng `TechnicalRawDerivationError`. `compileall` và
`git diff --check` đạt. Chưa kiểm tra broker/UI production thật hoặc dữ liệu
live; đây là fixture/environment smoke có kiểm soát. Tiếp tục Task 31, dừng ở
checkpoint R5 sau Task 32.

#### Task 31 (H03) — Cập nhật tài liệu và checkpoint

**File:** docs/scanner/scanner-architecture.md, scanner-features-spec.md,
technical-scoring-architecture.md, scanner-flow.md và tài liệu này; hướng dẫn
người dùng nếu hành vi hiển thị đổi.

**Thực hiện:**

1. Mô tả raw formula, reference H1, trạng thái unavailable và giới hạn chưa merge.
2. Đánh dấu phần Location port cũ là lịch sử; không xóa thông tin baseline
   cần giải thích journal cũ.
3. Ghi model/config đã triển khai và ngày cutover; chỉ ghi “live” sau H01/H02.
4. Ghi checkpoint code và config để quay lại theo workflow repo hiện có.
   Không tự tạo deployment/merge/push nếu ngoài phạm vi được yêu cầu.
5. Quay lại bằng code/config tương ứng, không rewrite journal và không thêm
   flag tự chuyển qua lại hai scorer.

**Đầu ra/kiểm tra:** docs khớp caller thực tế; có cách nhận diện bản trước/sau,
không cần tài liệu rollback nhiều trang.

#### Kết luận H03 (2026-09-10) — Hoàn thành; Tech Lead đã DUYỆT R5 sau review lại

Đã cập nhật các tài liệu chuẩn:
`docs/scanner/scanner-architecture.md`, `scanner-features-spec.md`,
`technical-scoring-architecture.md` và `scanner-flow.md`. Các tài liệu hiện ghi
Location runtime đã cutover sau H01/H02: `derive_live_analysis()` gọi
`derive_technical_raws_with_location()` với cutoff `captured_at`; reference là
H1 cuối đã đóng; H4/context dùng chung cho BUY/SELL; raw/detail đi cùng qua
canonical snapshot/row/UI; lỗi dữ liệu đi theo `TechnicalRawDerivationError`
→ unavailable; `raw=0` vẫn là kết quả hợp lệ cho no-anchor/conflict/limited
context. Công thức Location cũ được đánh dấu lịch sử.

Checkpoint nhận diện bản sau: `location-geometry-v2`,
`location-config-v1`, `location-detail-v1`, `location-context-v1` và derivation
`location=location-geometry-v2; config=location-config-v1`. Bản trước được nhận
diện bởi release/runtime version đã ghi trong các tài liệu legacy; quay lại dùng
nguyên release trước theo workflow repo, không bật flag hoặc chạy song song
scorer cũ, không rewrite journal/snapshot lịch sử và không đổi threshold.

Đã kiểm tra tài liệu bằng các regression H02/H01 đã ghi ở trên; không phát sinh
thay đổi code/runtime trong Task 31. Tiếp tục Task 32 và dừng tại checkpoint R5.

#### Task 32 (H04) — Bàn giao bản sửa gọn

> **Điểm dừng R5:** sau khi hoàn thành task 32, dừng và hỏi Tech Lead/người dùng
> theo §11.2; chưa được xác nhận thì không chuyển nhóm hoặc nghiệm thu cuối.

**Thực hiện:**

1. Đối chiếu checklist §12 và đánh dấu 32 ID theo bằng chứng thực tế; để mục
   xác nhận R5 ở trạng thái chờ, không tự đánh dấu đã nghiệm thu.
2. Báo ngắn: đã sửa lỗi gì, công thức nào đang chạy, file chính và test đã chạy.
3. Nêu việc chưa kiểm tra hoặc giới hạn còn lại: H1 reference, chưa merge cụm,
   chưa kiểm tra entry riêng, lookback giới hạn.
4. Không chờ dataset/P&L/holdout để coi code đã hoàn thành khi logic và kiểm
   tra mẫu đã đạt; cũng không khẳng định đã tăng lợi nhuận.
5. Các ý tưởng §13 giữ ở trạng thái để sau, không tự tạo thêm scope bắt buộc.

**Đầu ra/kiểm tra:** người dùng có thể đọc bàn giao và biết Location đã thay
đổi thế nào, chưa làm gì và có thể kiểm tra ở đâu.

#### Kết luận H04 (2026-09-10) — Hoàn thành; Tech Lead đã DUYỆT R5 sau review lại

Đã đối chiếu checklist §12 và chuẩn bị bàn giao. Phạm vi đã sửa gồm một scorer
Location hình học duy nhất trong runtime: vùng H4 có confirmation/ATR tại
confirmation/lifecycle, anchor-obstacle đúng phía, P×C và ROUND_HALF_UP; reference
là H1 cuối đã đóng theo cutoff; raw/detail/version đi cùng canonical snapshot và
UI; dữ liệu lỗi đi theo unavailable; SMC/Trend/Momentum, entry gates và
threshold không đổi.

File chính cần review: `core/location_engine.py`,
`core/scanner_features.py`, `core/scanner_live_producers.py`,
`core/scanner_release.py`, `controllers/scanner_controller.py`, các reader/
canonical/UI tương ứng, `tests/test_scanner_h02_integration.py` và bốn tài liệu
Scanner được cập nhật ở H03. Version nhận diện bản mới:
`location-geometry-v2`, `location-config-v1`, `location-detail-v1`,
`location-context-v1`.

Kiểm tra cuối: H02 integration **4 passed**; regression H01 **363 passed**;
`python scripts/scanner_smoke.py` đạt smoke chính và PATHB với
`sends_real_order=False`; `compileall` và `git diff --check` đạt. Không có
broker order thật, không có backtest/P&L/holdout và không tuyên bố cải thiện lợi
nhuận.

Giới hạn còn lại: chưa kiểm tra broker/UI production thật; chưa có merge cụm,
revision history, Entry Location Check, đa khung D1/H4 hay cache/evaluator
riêng; lookback vẫn theo config giới hạn. Reference H1 đã được kiểm tra bằng
fixture/cutoff nhưng chưa chứng nhận dữ liệu live production. Rollback dùng
nguyên release trước theo workflow repo, không bật dual scorer và không rewrite
snapshot/journal lịch sử.

**Tech Lead đã DUYỆT R5 sau review lại ngày 2026-09-10.** Task 1–32 hoàn thành trong phạm vi kế hoạch. Bằng chứng mới nhất ở mục review lại R5 bên dưới thay thế trạng thái chờ trước đó; chưa phát hành hoặc cho bản mới gửi lệnh thật.

#### Tech Lead review R5 (2026-09-10) — CHƯA DUYỆT

Đã review caller/runtime, H02 integration, diff cuối và checklist §12. R1–R4
đã duyệt theo bằng chứng tại các lần review trước; review diff cuối phát hiện
các điểm cần sửa dưới đây trước nghiệm thu R5:

1. **[P1] Cutoff runtime phải thuộc dữ liệu đã chụp.**
   `controllers/scanner_controller.py:3027–3044` truyền `captured_at=now` mới
   tại worker vào cả analysis/release, bỏ qua cutoff của packet. Probe độc lập
   với packet chụp `2026-08-13T11:59:55Z`, worker xử lý `12:00:05Z`: reference
   đúng phải đóng lúc `11:00:00Z` (1002.0581879642023), nhưng row nhận reference
   `12:00:00Z` (1002.004073903944). Bar H1 còn hình thành tại lúc chụp bị coi
   là đã đóng; H4 có cùng nguy cơ qua boundary. Chốt cutoff trước khi lấy
   history, truyền cùng cutoff qua packet → analysis → snapshot; thời gian
   đánh giá freshness có thể tách riêng. Không chỉ đổi sang timestamp được
   tạo sau bước lấy dữ liệu/macro. Thêm regression controller có delay qua
   boundary H1/H4, kiểm tra reference/history không thay đổi theo giờ worker.
2. **[P2] Hai regression UI adapter chưa được sửa sau cutover.**
   `tests/test_scanner_ui_adapter.py:58–76` dùng bước giá làm khoảng timestamp;
   fixture chỉ có 21 H4 đã đóng. Hai test `TestLiveWiringAdapter` fail với
   `LOCATION_INVALID_DATA: need at least 60 closed H4 candles`. Sửa cadence
   D1/H4/H1 của fixture, giữ minimum history và assertions adapter/intent.
3. **[P2] Card Location vi phạm style lock của repo.**
   `_diag_location_html()` thêm màu HEX/style cục bộ làm
   `html_style_attributes` tăng 242 → 269 và `hex_color_literals` 293 → 305.
   Hai test phase0/phase7 style guard fail. Dùng semantic palette/template
   renderer chung theo `docs/ui/style-guide.md`; không tăng lock để che lỗi.
   Sau sửa chạy lại guard và render dark/light hẹp/rộng để giữ kết quả R4.
4. **[P2] H03 chưa có checkpoint code/config có thể khôi phục.**
   Các model/schema version và câu “nguyên release trước” ở kết luận H03
   không xác định revision/artifact cùng config cần dùng. Ghi commit/tag hoặc
   artifact cụ thể cho bản trước, config đi kèm và thao tác quay lại theo
   workflow repo; ghi rõ bản mới còn ở working tree nếu chưa commit. Không
   rewrite journal hoặc thêm dual scorer. Chưa đủ bằng chứng để tick mục này.
5. **[P2] Tài liệu trạng thái còn mâu thuẫn.** Bốn tài liệu Scanner ghi đã nối
   runtime, nhưng `docs/guides/USER_GUIDE.md:27–38` còn ghi chưa có chức năng;
   docs index, kiến trúc tổng thể, product spec và screen/style guide còn nhãn
   “chưa triển khai”. Đồng bộ phần thuộc Location theo §14.1, phân biệt đã nối
   runtime với chưa nghiệm thu R5/chưa smoke broker/UI production thật.

**Bằng chứng reviewer:** regression 17 file Location/scanner/canonical/UI/H02
**579 passed, 2 failed**; full suite với QApplication offscreen và font
Segoe UI/Consolas **3498 passed, 11 failed, 8 skipped, 16 xfailed**. Bốn failure
liên quan nâng cấp là hai test adapter và hai style guard nêu trên. Bảy failure
còn lại thuộc navigation Backtest (1) và FRED fallback (6), ngoài diff Location;
không sửa các phần này trong review. JUnit full suite:
`C:/Users/tntan/AppData/Local/Temp/codex-r5-pytest.xml`.

Smoke chính/PATHB chạy lại đạt, output chuyển vào thư mục tạm
`C:/Users/tntan/AppData/Local/Temp/codex-r5-smoke`; đây là fixture smoke,
không gửi lệnh. Probe controller với ATR H4 bằng 0 xác nhận row
`DATA_UNAVAILABLE`, reason/block `LOCATION_INVALID_DATA`, không order payload.
Cutoff boundary probe ở finding 1 chưa đạt. Không coi smoke fixture là bằng
chứng đã chạy broker/UI production. Giữ task 29–31 đang thực hiện, task 32
chờ sửa/review lại; chưa nghiệm thu R5.

#### CODER sửa findings R5 (2026-09-10) — hoàn tất phần sửa, CHỜ review lại

1. **Cutoff:** `ScannerController` đóng băng `history_cutoff` trước request
   history đầu tiên; `_fetch_one_symbol_mt5` truyền `location_cutoff`/
   `v4_captured_at` qua packet, `_analyze_one_symbol` dùng cùng giá trị cho
   `derive_live_analysis` và `run_pair_from_live`, còn `v4_observed_at` tách
   riêng cho freshness. Regression
   `test_controller_packet_cutoff_survives_worker_delay_across_h1_h4_boundary`
   kiểm tra boundary H1/H4 và worker delay; **H02 5 passed**.
2. **Cadence fixture:** `test_scanner_ui_adapter.py` dùng D1 24h, H4 4h, H1
   1h; minimum history và assertions không bị giảm. Adapter regression **26
   passed**.
3. **UI/style:** card Location chuyển sang class/template trong
   `ui/rich_text.py` với semantic palette chung; `_diag_location_html` không
   thêm inline style/HEX cục bộ và không đổi lock. Style guards **8 passed**;
   Location HTML/render regression **9 passed, 10 deselected**, gồm dark/light,
   FX precision và QTextEdit ở 320/1280 px.
4. **Rollback checkpoint:** artifact cụ thể là
   `reports/scanner/location-r5-checkpoint.json`, baseline
   `b6e75542c2ae31512abf47fbf5d1fa1210b3aebe` (`Upgrade location`), tag tham
   chiếu `v3-runtime-pre-cutover`, kèm config/schema/model/threshold hiện tại,
   hai smoke artifacts và hướng dẫn restore theo workflow repo. Bản mới vẫn ở
   working tree chưa commit; không rewrite journal và không dual scorer.
5. **Tài liệu:** README, architecture, product, user guide, screen design và
   style guide đã đồng bộ “runtime đã nối, R5 chưa nghiệm thu”, giới hạn smoke
   production và `sends_real_order=False`; các tài liệu Scanner canonical đã
   nối từ H03 vẫn được giữ làm nguồn contract.

**Kiểm tra cuối sau sửa:**

- `tests/test_scanner_integration.py tests/test_scanner_snapshot.py
  tests/test_scanner_row.py tests/test_location_canonical_detail.py` — **56
  passed**; H02 — **5 passed**; adapter — **26 passed**; style guards — **8
  passed**; compileall và `git diff --check` đạt.
- `python scripts/scanner_smoke.py` — smoke chính và PATHB đạt, báo
  `sends_real_order=False`; artifacts là
  `reports/scanner/release_b12_smoke.json` và
  `reports/scanner/release_b12_pathb_smoke.json`.
- Full suite với `QT_QPA_PLATFORM=offscreen`: **3503 passed, 7 failed, 8
  skipped, 16 xfailed**; JUnit tại
  `C:/Users/tntan/AppData/Local/Temp/codex-r5-pytest-final.xml`. Bảy failure
  được phân loại ngoài phạm vi R5: 1 navigation Backtest và 6 FRED fallback;
  không có failure mới trong Location/cutoff/adapter/style.

Các finding R5 đã được sửa trong phạm vi CODER, nhưng **không tự chuyển trạng
thái sang R5 đã duyệt**. Dừng tại đây để Tech Lead review lại.

#### Tech Lead review lại R5 (2026-09-10) — DUYỆT, 32/32 task hoàn thành

Đã đóng cả 5 findings của lần review trước:

- Cutoff được chốt trước request history, đi qua packet → analysis → snapshot;
  thời gian freshness tách riêng. Probe cached/uncached qua boundary đều giữ
  cutoff trước request. Probe cùng packet tại hai giờ worker sau boundary,
  cả BUY/SELL giữ nguyên toàn bộ Location detail so với derive tại cutoff gốc.
- Fixture UI adapter đã dùng cadence D1/H4/H1 đúng; hai regression adapter đạt.
- Card dùng class/template và semantic palette chung; hai style guard đạt,
  không đổi style lock. Render độc lập 20 fixture dark/light tại 320/1280 px
  không tràn ngang; đã xem ảnh hẹp/rộng, giá FX/reference/anchor đọc được.
- Checkpoint có baseline cụ thể `b6e75542c2ae31512abf47fbf5d1fa1210b3aebe`.
  Đã xác minh revision tồn tại, policy hiện tại giống JSON tại baseline,
  config Location ghi trong artifact khớp config resolved của code. Khi quay
  lại dùng đúng baseline commit cùng config của commit đó; tag
  `v3-runtime-pre-cutover` là tham chiếu migration cũ, trỏ revision khác,
  không phải đích rollback Location. Bản mới vẫn là working tree chưa commit.
- Tài liệu hiện hành đã đồng bộ runtime đã nối và giới hạn smoke. Reviewer
  cập nhật trạng thái duyệt R5 trong plan và tài liệu liên quan sau kiểm tra.

**Kết quả reviewer chạy lại:** regression 19 file liên quan gồm engine,
canonical, live/controller, adapter/UI/H02 và style guards **590 passed**.
Full suite: **3503 passed, 7 failed, 8 skipped, 16 xfailed**; 7 failure còn lại
là navigation Backtest (1) và FRED fallback (6), giống nhóm ngoài phạm vi ở
lần review trước. Không còn failure liên quan Location hoặc style guard.
JUnit: `C:/Users/tntan/AppData/Local/Temp/codex-r5-review-again.xml`.

Smoke chính/PATHB chạy lại đạt, không dispatch lệnh; output reviewer tại
`C:/Users/tntan/AppData/Local/Temp/codex-r5-rereview-smoke`. Ảnh render tại
`C:/Users/tntan/AppData/Local/Temp/codex-r5-rereview`. `git diff --check` đạt.
Đây là fixture/environment smoke, chưa xác nhận broker/UI production thật.

**Kết luận:** không còn finding chặn trong phạm vi R5 đã review; duyệt
nghiệm thu nâng cấp Location theo kế hoạch, task 1–32 hoàn thành. Không mở
thêm scope P&L/backtest, không đổi threshold và không rewrite journal. Duyệt
R5 không đồng nghĩa full suite toàn repo xanh, không tự cấp quyền deploy,
merge/push hoặc gửi lệnh thật.

### 11.2 Tech Lead review: năm điểm dừng bắt buộc

**Yêu cầu trực tiếp của người dùng:** CODER tự kiểm tra mỗi task, nhưng đến
năm mốc dưới đây phải **DỪNG LẠI VÀ HỎI**, không tự chuyển sang nhóm tiếp theo.
Không cần duyệt từng task; chỉ có năm điểm dừng bắt buộc cho 32 task.

Sau mỗi task, CODER ghi ngắn:

~~~text
Task: số 1–32 (ID)
Đã làm: thay đổi chính và file
Kiểm tra: command/case, kết quả hoặc chưa chạy
Vấn đề còn lại: nếu có
~~~

Tại mốc, ghi “CODER hoàn tất nhóm — CHỜ REVIEW”. Không đánh dấu “Tech Lead đã
duyệt” nếu chưa có xác nhận rõ ràng cho chính mốc đó.

1. Hoàn thành phần việc và kiểm tra của nhóm, chuẩn bị diff/file và kết quả
   để người review có thể xem ngay.
2. Gửi báo cáo ngắn và câu hỏi xác nhận theo mẫu bên dưới, sau đó dừng lượt làm
   việc để chờ trả lời.
3. Không bắt đầu task của nhóm sau, kể cả task độc lập. Không coi im lặng,
   hết thời gian chờ, test pass hoặc yêu cầu thực hiện chung ban đầu là duyệt mốc.
4. Nếu được yêu cầu sửa, chỉ xử lý các sửa đổi trong nhóm đang review, chạy
   kiểm tra liên quan rồi hỏi lại. Không phải làm lại các nhóm đã được duyệt.
5. Chỉ tiếp tục khi Tech Lead/người dùng xác nhận cho qua mốc. Ghi người xác
   nhận và nội dung/thời điểm xác nhận ngắn trong nhật ký thực hiện.

#### Năm mốc review bắt buộc

| Mốc | Sau task | Phạm vi | Tech Lead tập trung kiểm tra |
|---|---|---|---|
| R1 | **8** — B04 | Task 1–8: baseline và contract | Lỗi đã tái hiện; cutoff rõ; model/config gọn; null khác 0; không mở rộng scope |
| R2 | **14** — C06 | Task 9–14: vùng và lifecycle | Swing xác nhận đúng thời điểm; ATR tại confirmation; sai phía/phá vùng/expiry; không dùng dữ liệu tương lai |
| R3 | **21** — E02 | Task 15–21: score và xem mẫu | P/C/rounding, các lỗi cũ được sửa; mẫu biểu đồ hợp lý; không tự đổi threshold hoặc xây backtest |
| R4 | **28** — G03 | Task 22–28: tích hợp và UI | Raw/detail cùng nguồn; version/reader đúng; unavailable không qua lệnh; SMC/Momentum không đổi; UI không nhầm Location với vị trí entry |
| R5 | **32** — H04 | Task 29–32 và diff cuối | Một scorer, test/smoke thực sự đạt, docs đúng, checkpoint quay lại; sẵn sàng dùng bản mới |

Các ranh giới phải giữ:

- Sau task 8: chờ R1, chưa thực hiện task 9.
- Sau task 14: chờ xác nhận R2; chỉ thực hiện task 15 sau khi R2 được duyệt.
- Sau task 21: chờ R3, chưa thực hiện task 22.
- Sau task 28: chờ R4, chưa thực hiện task 29.
- Sau task 32: chờ R5, chưa tuyên bố toàn bộ nâng cấp đã được nghiệm thu,
  chưa phát hành hoặc cho bản mới gửi lệnh thật.

Task 29/H01 chỉ chuyển caller trong bản code đang chuẩn bị. Task 30/H02 kiểm
tra bằng fixture/demo hoặc môi trường không gửi lệnh thật. Task 32 chuẩn bị
bàn giao và đề nghị review cuối; chỉ sau xác nhận R5 mới ghi nghiệm thu hoàn
tất. Xác nhận R5 không tự cấp quyền gửi lệnh thật hoặc triển khai ngoài phạm
vi người dùng đã cho phép.

Mẫu câu hỏi tại R1–R4:

~~~text
Đã hoàn thành task [đầu nhóm]–[cuối nhóm], tới mốc [R1/R2/R3/R4].
Thay đổi chính: [...]
File/diff cần xem: [...]
Kiểm tra và kết quả: [...]
Vấn đề còn lại: [...]

Theo mục 11.2, tôi dừng tại đây để chờ review.
Tech Lead xác nhận cho qua mốc này để tôi tiếp tục task [task tiếp theo] không?
~~~

Tại R5, thay câu cuối bằng:
“Tech Lead xác nhận nghiệm thu phần nâng cấp Location này không?”
Không tạo yêu cầu xác nhận phụ cho các task thường giữa hai mốc.

Review nên đọc diff, kết quả kiểm thử và một vài case quan trọng của nhóm.
Không yêu cầu Tech Lead viết lại code, chạy lại toàn bộ test hoặc backtest
lợi nhuận. Chỉ kiểm tra sâu hơn khi có dấu hiệu sai hoặc thay đổi chưa rõ.

#### Khi nào nên review ngay, không đợi tới mốc?

- CODER cần đổi công thức, default config hoặc threshold so với tài liệu.
- Muốn sửa helper chung làm ảnh hưởng Trend/Momentum/SMC/scenario.
- Có nguy cơ mất dữ liệu hoặc đổi contract/version khiến snapshot cũ bị hiểu sai.
- Không xác định được nến đã đóng/cutoff, hoặc test cho thấy có dùng dữ liệu tương lai.
- Error path có thể cho phép vào lệnh dù Location không tính được.
- Phải mở rộng phạm vi sang entry gate, database hoặc subsystem mới.

Lỗi nhỏ đã có expected rõ trong test thì CODER sửa và chạy lại test liên quan,
không cần một lượt duyệt riêng. Khi Tech Lead yêu cầu sửa, review lại phần
đã sửa và phần bị ảnh hưởng, không làm lại toàn bộ 32 task.

## 12. Điều kiện hoàn thành

- [x] Các lỗi vùng sai phía, xung đột, bonus xa và bước nhảy điểm được sửa.
- [x] Vùng có confirmation/lifecycle cơ bản; không dùng dữ liệu tương lai. Cutoff H1/H4 được cố định trước history và có regression boundary sau sửa R5.
- [x] Công thức đạt 0–25, giữ normalization/regime weights.
- [x] Dữ liệu lỗi không được biến thành điểm giả.
- [x] Không thay đổi SMC/Trend/Momentum hoặc entry gates ngoài phạm vi.
- [x] Raw/detail/version truyền nhất quán tới snapshot và UI.
- [x] Kiểm thử code liên quan đạt; regression cutoff/adapter/style/render và smoke intent-only đã có bằng chứng ở mục sửa findings R5.
- [x] Chỉ một công thức Location chạy live, dữ liệu lịch sử không bị ghi đè.
- [x] Có checkpoint code/config và hướng dẫn quay lại ngắn nếu phát hiện lỗi: `reports/scanner/location-r5-checkpoint.json`.
- [x] Tài liệu ghi đúng runtime đã nối, R5 chưa nghiệm thu và giới hạn smoke production; xem mục sửa findings R5.
- [x] R1–R5 đã có xác nhận rõ ràng; Tech Lead duyệt R5 ngày 2026-09-10 sau review lại. Nghiệm thu phạm vi nâng cấp Location; không cấp quyền deploy hoặc gửi lệnh thật.

**Không phải điều kiện hoàn thành:** dataset dài hạn, chứng nhận lợi nhuận,
backtest nhiều năm, holdout report, tối ưu trọng số, số lệnh tối thiểu, hệ thống
replay hoặc database riêng cho Location.

Quay lại bản cũ bằng code/config tương ứng; không bật một cơ chế runtime chạy
hai công thức. Snapshot phiên bản mới vẫn giữ nguyên để xem lại; reader không
hỗ trợ thì báo rõ, không gán thành version cũ.

## 13. Để sau khi có nhu cầu thực tế

| Hạng mục | Khi nào mới xem xét |
|---|---|
| Merge cụm vùng và lịch sử revision | Vùng chồng lấn gây khó chọn/hiển thị trong dữ liệu thực |
| Chuyển vai trò support/resistance, mô hình breakout riêng | Chiến lược người dùng cần và có case cụ thể |
| Entry Location Check/gate mới | Reference H1 không đủ phục vụ quyết định entry thực tế |
| Vùng đa khung D1/H4 | Bỏ sót vùng quan trọng có thể chỉ ra trên chart |
| Cache Location riêng | Có đo đạc cho thấy xử lý Location làm Scanner chậm |
| Replay/evaluator/outcome analysis | Cần điều tra lỗi hoặc câu hỏi hiệu quả cụ thể |
| Database riêng, journal migration phức tạp | Cách lưu snapshot/detail hiện có thực sự không đủ |
| Tối ưu tham số và backtest sâu | Người dùng yêu cầu riêng sau khi dùng bản đơn giản |

Không triển khai các mục này chỉ để làm kiến trúc “đầy đủ”.

## 14. Tài liệu liên quan và ghi nhận thực hiện

### 14.1 Nguồn chuẩn và quy tắc đồng bộ trước khi code

| Tài liệu | Phần chịu trách nhiệm |
|---|---|
| Plan này §4–§11 | Quy tắc thuật toán, defaults, expected test, thứ tự 32 task và năm điểm dừng |
| [Scanner architecture](../scanner/scanner-architecture.md) §3.4–§3.5 | Ranh giới canonical, phần thay đổi/giữ nguyên và ảnh hưởng downstream |
| [Scanner features spec](../scanner/scanner-features-spec.md) §0.1 | Baseline port cũ và contract Location mới, raw/detail/error |
| [Scanner flow](../scanner/scanner-flow.md) §13 | Thứ tự producer → scenario → snapshot → composition, tránh vòng phụ thuộc |
| [Technical scoring](../scanner/technical-scoring-architecture.md) §14 | Phân biệt legacy với target Location, giữ normalization/weights |
| [Kiến trúc tổng thể](../architecture/architecture.md) | Module thuần, adapter hiện có, không thêm DB/service |
| [Product spec](../product/product_spec.md) §5.3 | Giá trị sử dụng, phạm vi và giới hạn kỳ vọng |
| [Screen design](../ui/screen_design.md), [style guide](../ui/style-guide.md) §6 | Raw/contribution, trạng thái, nhãn H1, UI gọn và theme |
| [User guide](../guides/USER_GUIDE.md) §3.1 | Cách đọc kết quả và giới hạn đối với entry/lệnh đang mở |

Không sao chép bảng defaults sang nhiều tài liệu. Nếu code hiện tại khác mô
tả baseline, xác minh caller và ghi sai lệch tại A01; không tự coi code cũ là
đặc tả của model mới. Nếu cần đổi thiết kế/default/scope đã chốt, báo tại mốc
review hoặc dừng sớm theo §11.2, cập nhật nguồn chuẩn trước khi code phần đổi.

F/G có thể hoàn tất chuẩn bị nhưng vẫn ghi **chưa chuyển live**. H01 ghi nhận
việc đổi caller, H03 đồng bộ tài liệu, H04 bàn giao trạng thái thực tế chờ R5. Chỉ ghi
**đã nghiệm thu** sau xác nhận R5; không chuyển các nhãn “chưa triển khai” hàng
loạt thành “live” chỉ dựa vào việc đã sửa tài liệu hoặc test engine đã pass.

### 14.2 Liên kết và nhật ký

- [Docs index](../README.md).
- [Scanner architecture](../scanner/scanner-architecture.md): ghi target trước
  sửa, chỉ đổi trạng thái live sau khi code/test hoàn tất.
- [Scanner features spec](../scanner/scanner-features-spec.md): công thức port
  cũ cần được đánh dấu lịch sử sau khi thay Location.
- [Technical scoring architecture](../scanner/technical-scoring-architecture.md).
- [Scanner flow](../scanner/scanner-flow.md).
- [UI style guide](../ui/style-guide.md).
- [User guide](../guides/USER_GUIDE.md).

| Ngày | Thay đổi | Bằng chứng / trạng thái |
|---|---|---|
| 2026-09-09 | Rà soát công thức Location, tạo kế hoạch ban đầu | 6 counterexample; 132 baseline tests passed |
| 2026-09-09 | Rút gọn theo yêu cầu phần mềm cá nhân | 32 work item, 20 nhóm test; bỏ yêu cầu backtest sâu và hạ tầng phụ; chưa sửa runtime |
| 2026-09-09 | Bổ sung hướng dẫn thực hiện từng ID tại §11.1 | Mỗi bước có file bắt đầu, thao tác, kiểm tra và đầu ra; giữ nguyên 32 bước, chưa sửa runtime |
| 2026-09-09 | Đánh số Task 1–32, bổ sung Tech Lead review tại §11.2 | Giữ ID để tra cứu; đề xuất 5 mốc review nhóm, không duyệt từng task; chưa sửa runtime |
| 2026-09-09 | Chuyển 5 mốc review thành điểm dừng bắt buộc theo yêu cầu người dùng | Dừng và hỏi sau task 8/14/21/28/32; chờ xác nhận mới tiếp tục; chưa sửa runtime |
| 2026-09-09 | Đồng bộ docs trước implementation; bổ sung ảnh hưởng tại §1.1 và phân quyền nguồn chuẩn tại §14.1 | Kiến trúc, features, flow, product, UI và guide cùng ghi Location chưa triển khai; giữ 32 task và năm mốc dừng; chỉ sửa tài liệu |
| 2026-09-09 | Hoàn thành Task 1 (A01) | Đã dùng `git status` và `rg` để xác định caller Location, consumer `support_zones`/`resistance_zones`, và đường UI canonical; giữ nguyên vùng dùng chung, chưa sửa runtime |
| 2026-09-09 | Hoàn thành Task 2 (A02) | `python -m pytest tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py -q --disable-warnings` — **132 passed in 1.04s**; không có baseline failure |
| 2026-09-09 | Hoàn thành Task 3 (A03) | Thêm fixture legacy OLD-01..OLD-06 trong `tests/test_scanner_features.py`; kết quả lần lượt **10, 15, 5, 3, 10, 3**. Test file: **25 passed**; baseline liên quan sau khi thêm fixture: **138 passed** |
| 2026-09-09 | Hoàn thành Task 4 (A04) | Xác minh MT5 `time` là open time, bar cuối có thể đang hình thành và cutoff chưa được lọc trong runtime; ghi contract H4/H1 closed-candle + cutoff vào `docs/scanner/scanner-architecture.md`. Kiểm tra liên quan: **46 passed** |
| 2026-09-09 | Hoàn thành Task 5 (B01) | Tạo `core/location_engine.py` với `LocationConfig` immutable, default/config/model version, resolver cấu hình từng phần và public API chuẩn bị; thêm `tests/test_location_engine.py`. Test mới: **5 passed**; cùng baseline liên quan: **143 passed**; chưa nối caller/runtime |
| 2026-09-09 | Hoàn thành Task 6 (B02) | Thêm `LocationDataError` và validator thuần cho config, history H4, price, UTC timestamp/cutoff, OHLC, side và zone; invalid không bị fallback/coerce. Test domain: **19 passed**; cùng baseline liên quan: **157 passed** |
| 2026-09-09 | Hoàn thành Task 7 (B03) | Thêm `LocationZone`, `LocationContext`, `LocationResult` immutable; khóa status/raw, unavailable và factor invariants; dùng tuple cho zones/reason codes. Test domain: **25 passed**; cùng baseline liên quan: **163 passed** |
| 2026-09-09 | Hoàn tất Task 8 (B04) — **R1 đã được Tech Lead duyệt** | Thêm serialize/parse strict cho config, zone, context và result; datetime UTC `Z`, schema/model version, reason codes Location, raw `0` khác raw `null`, chặn NaN/Inf. Test domain: **31 passed**; cùng baseline liên quan: **169 passed**; chưa nối caller/runtime |
| 2026-09-09 | Sửa findings R1 của A04/B02/B03/B04 — **R1 đã được Tech Lead duyệt** | A04 thêm seam close boundary H1/H4 và reference H1 theo cutoff trong `core/location_engine.py` + fixture cadence; B02 khóa history tối thiểu 60 và version supported; B03/B04 khóa CONFLICT/NO_VALID_ANCHOR raw=0, UNAVAILABLE raw=null và parser cùng invariant. Command chính: `python -m pytest tests/test_location_engine.py tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py -q --disable-warnings` — **181 passed**; thêm `python -m pytest tests/test_scanner_observability.py -q --disable-warnings` — **21 passed**. Baseline review trước sửa: 169 passed; chưa sửa caller/runtime, chưa thực hiện Task 9 |
| 2026-09-09 | Hoàn thành Task 9 (C01) | `core/location_engine.py` thêm `closed_h4_history_at_cutoff()`: kiểm tra thứ tự/duplicate trên toàn bộ stream, lọc theo `closed_at <= cutoff` trước rồi mới giới hạn `history_h4_bars`; validator dùng cùng helper và ghi nhận số nến qua kết quả đã chọn. Bổ sung test nến đang chạy/tương lai, thiếu minimum sau cutoff, giới hạn sau lọc và out-of-order. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **48 passed**; regression liên quan `python -m pytest tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py tests/test_location_engine.py -q --disable-warnings` — **186 passed**; chưa nối caller/runtime |
| 2026-09-09 | Hoàn thành Task 10 (C02) | `core/location_engine.py` thêm immutable `LocationSwing` và `location_swing_points()`: extremum duy nhất theo lookback/config, `confirmed_at` là close của nến thứ hai bên phải, ID dùng role + timestamp swing, không dùng index; swing thiếu confirmation hoặc sau cutoff bị loại. Không sửa canonical `smc_context.swing_points`. Bổ sung test duplicate extremum, thiếu nến phải, cutoff confirmation và ID ổn định khi prefix cửa sổ thay đổi. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **52 passed**; chưa nối caller/runtime |
| 2026-09-09 | Hoàn thành Task 11 (C03) | `core/location_engine.py` thêm `build_location_zones()`: tính ATR(14) một lần trên history H4 hợp lệ, lấy ATR tại `confirmed_at`, bỏ swing thiếu ATR warmup, dựng biên cố định và lưu `formation_atr`; tick size được làm tròn ra ngoài, tick invalid bị typed error, vùng vượt `zone_max_width_atr` sau rounding bị loại. Bổ sung test ATR tại confirmation, tick rounding, max width, thiếu ATR và ATR tương lai không làm đổi biên cũ. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **57 passed**; regression gồm SMC `python -m pytest tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py tests/test_location_engine.py tests/test_smc_context.py -q --disable-warnings` — **210 passed**; chưa nối caller/runtime |
| 2026-09-09 | Hoàn thành Task 12 (C04) | `core/location_engine.py` thêm `update_location_zone_lifecycle()`, bắt đầu kiểm tra từ close của nến confirmation; support/resistance dùng break line và `formation_atr` cố định, wick hoặc close đúng biên không breach, streak một close là `SUSPECT`, đủ streak là `INVALIDATED`, phục hồi reset về `ACTIVE`, invalidated terminal, và vùng chưa invalidated hết tuổi chuyển `EXPIRED`. `build_location_zones()` trả zone đã áp lifecycle. Bổ sung test support/resistance cho wick, boundary, 1/2 breach, recovery, confirmation close và age. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **65 passed**; regression `python -m pytest tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py tests/test_location_engine.py tests/test_smc_context.py -q --disable-warnings` — **218 passed**; chưa nối caller/runtime |
| 2026-09-09 | Hoàn thành Task 13 (C05) | `core/location_engine.py` thêm `deduplicate_location_zones()`: exact duplicate cùng ID/dữ liệu chỉ giữ một, cùng ID nhưng dữ liệu mâu thuẫn báo `CONFLICTING_ZONE_ID`, vùng khác ID dù gần nhau không merge, kết quả sort theo role/confirmation/ID. Tích hợp trước lifecycle trong `build_location_zones()` và `update_location_zone_lifecycle()`. Bổ sung test đảo thứ tự, duplicate, conflict và nearby IDs. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **67 passed**; regression `python -m pytest tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py tests/test_location_engine.py tests/test_smc_context.py -q --disable-warnings` — **220 passed**; chưa nối caller/runtime |
| 2026-09-09 | Hoàn thành Task 14 (C06) — **R2 đã được Tech Lead duyệt** | `build_location_context()` dựng một context immutable từ history đã lọc, ghi `h4_bars_considered`/ATR hiện tại và dùng chung zones cho hai phía; append nến tương lai với cùng cutoff không đổi context, ID/timestamp vẫn causal. Test side-neutral context thay cho gọi scorer vì `score_location()` chỉ được hoàn thiện ở nhóm D01–D03. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **70 passed**; regression `python -m pytest tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py tests/test_location_engine.py tests/test_smc_context.py -q --disable-warnings` — **223 passed**; chưa nối caller/runtime |
| 2026-09-09 | Sửa findings Tech Lead trước R2 — **R2 chưa duyệt tại thời điểm ghi nhận** | Task 11 dùng tolerance theo ULP để không loại vùng đúng ngưỡng max width do sai số float, nhưng vẫn loại vùng thực sự vượt; thêm test dưới/đúng/vượt ngưỡng. Task 9/14 truyền `LocationReference` hoặc `reference_closed_at` vào `build_location_context()`, kiểm tra không sau cutoff và giữ timestamp H1; thêm fixture append H1 tương lai. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **75 passed**; regression `python -m pytest tests/test_scanner_features.py tests/test_technical_signal_scorer.py tests/test_scanner_scenario_producers.py tests/test_location_engine.py tests/test_smc_context.py -q --disable-warnings` — **228 passed**; test đảo thứ tự gọi scorer vẫn để nhóm D vì scorer chưa triển khai |
| 2026-09-09 | Sửa bổ sung max-width theo finding P2 — **R2 chưa duyệt tại thời điểm ghi nhận** | `_width_exceeds_max()` nay tính error budget từ low/high đã làm tròn, low/high trước rounding, tick size, width và phép nhân ATR; không loại sai vùng đúng ngưỡng ở giá 100/2000, nhưng vẫn loại overflow thực sự. Thêm regression tick `0.01` với `[100.27,100.28]`, `[2000.32,2000.33]`, vùng dưới/đúng/vượt và builder có tick. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **78 passed**; regression — **231 passed**; `git diff --check` đạt |
| 2026-09-09 | **Tech Lead (Codex) xác nhận DUYỆT R2 — Task 9–14 hoàn thành** | Xác nhận trong cuộc trò chuyện sau lần review sửa max-width cuối: không còn điểm chặn R2; chạy lại regression **231 passed**, kiểm tra độc lập qua builder trên **240 trường hợp giá** đạt cả giữ vùng đúng ngưỡng và loại vùng thực sự vượt, `git diff --check` đạt. Cho phép tiếp tục task 15–21 và dừng tại R3 sau task 21; bổ sung test đảo thứ tự gọi BUY/SELL khi hoàn thiện scorer. Ghi nhận này chỉ duyệt phạm vi R2, chưa nghiệm thu task 15 trở đi hoặc nối runtime. |
| 2026-09-09 | Hoàn thành Task 15 (D01) — **R2 đã được Tech Lead duyệt** | `core/location_engine.py` thêm `distance_to_interval()` và `select_location_anchor()`: BUY chỉ chọn support ACTIVE đúng phía, SELL chỉ chọn resistance ACTIVE đúng phía; loại SUSPECT/INVALIDATED/EXPIRED/chưa confirmation, giá đúng biên được tính trong vùng, tie-break distance/width/confirmation mới/ID deterministic, không có anchor trả `None`. Bổ sung test đối xứng BUY/SELL, wrong-side, lifecycle, boundary, tie-break đảo thứ tự và no-anchor. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **89 passed**; regression — **242 passed**; chưa nối vào scorer |
| 2026-09-09 | Hoàn thành Task 16 (D02) — **R2 đã được Tech Lead duyệt** | `core/location_engine.py` thêm `LocationObstacleSelection` và `select_location_obstacle()`: BUY xét resistance, SELL xét support; ACTIVE/SUSPECT chứa giá được ưu tiên conflict, chọn explanation deterministic nhưng giữ `conflict=True`; nếu không conflict chọn obstacle phía trước gần nhất theo clearance tới mép, không dùng vùng phía sau hoặc trạng thái loại. Bổ sung test hai phía interval, forward edge, suspect, invalidated/expired/unconfirmed, no obstacle và conflict không có anchor. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **96 passed**; regression — **249 passed**; chưa nối vào scorer |
| 2026-09-09 | Task 17 (D03) bản đầu — **bị finding tại R3** | `core/location_engine.py` có scorer P/C/raw và ROUND_HALF_UP, nhưng regression FX tại đúng 0.5 ATR còn bị ảnh hưởng bởi sai số float. Bằng chứng bản đầu: `tests/test_location_engine.py` **102 passed**, regression **255 passed**; đã sửa lại trong entry “Sửa findings Tech Lead R3”. |
| 2026-09-09 | Task 18 (D04) bản đầu — **bị finding tại R3** | `score_location_safe()` đã phân biệt `UNAVAILABLE` với raw 0, nhưng scorer còn đổi `LIMITED_CONTEXT` thành `EVALUATED` khi anchor xa/không obstacle. Bằng chứng bản đầu: `tests/test_location_engine.py` **104 passed**, regression **257 passed**; đã sửa lại trong entry “Sửa findings Tech Lead R3”. |
| 2026-09-09 | Hoàn thành Task 19 (D05) — **R2 đã được Tech Lead duyệt; chờ R3 sau Task 21** | Bổ sung invariant test cho monotonicity theo riêng khoảng cách anchor/clearance obstacle, reflection BUY/SELL, đảo thứ tự zones, causal khi append nến tương lai và import-scope không phụ thuộc news/order/AI/SMC/scenario/R:R. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **114 passed**; regression — **267 passed**; `git diff --check` đạt |
| 2026-09-09 | Task 20 (E01) exploratory — **CHƯA ĐỦ NGHIỆM THU** | Chạy độc lập Location trên 8 case từ `tests/fixtures/smc_canonical/golden_cases.json`; đây là snapshot fixture, không phải chart live. 7 case có ATR đều raw 0 do anchor xa và 1 case thiếu ATR là unavailable; ghi nhận này bị thay thế bởi raw H1/H4 evidence bên dưới. |
| 2026-09-09 | Hoàn thành Task 20 (E01) — **R3 vẫn CHƯA DUYỆT** | Bổ sung 8 raw EUR/USD cases từ Yahoo Chart API (1.421 H1 → 345 H4), bao phủ gần support/resistance, conflict, invalidated/expired, overlap, far anchor và no obstacle. Kết quả khớp status/raw/reason contract; không lưu raw vào repo, không nối runtime/send order. |
| 2026-09-09 | Task 21 (E02) ghi nhận sau bổ sung E01 — **CHỜ REVIEW R3** | Hai findings code đã sửa, E01 đã có đủ mẫu raw theo §10; không đổi threshold/weight/config và chưa bắt đầu Task 22. |
| 2026-09-09 | Sửa findings Tech Lead R3 — **R3 vẫn CHƯA DUYỆT** | D03 chuyển distance/clearance/P/C/raw_exact sang Decimal nhất quán trước ROUND_HALF_UP; thêm regression HALF_UP 0.5 ATR cho BUY/SELL. D04 giữ `LIMITED_CONTEXT` khi thiếu obstacle dù anchor xa và thêm cả hai reason codes. `python -m pytest tests/test_location_engine.py -q --disable-warnings` — **117 passed**; regression — **270 passed**; E01 hạ về chưa hoàn thành vì snapshot chưa đủ mẫu §10; chưa chuyển Task 22. |

| 2026-09-09 | **Tech Lead (Codex) review R3 — CHƯA DUYỆT** | Chạy lại regression **267 passed**; kiểm tra độc lập đạt thứ tự gọi BUY/SELL, context không đổi, đảo zones, exact duplicate và result round-trip. Còn 3 điểm: D03 với price=1.1, anchor.high=1.0995, ATR=0.001, C=1 trả raw=12 thay vì HALF_UP 13 do sai số trước bước Decimal; D04 có anchor xa/không obstacle trả EVALUATED và mất lý do LIMITED_CONTEXT; E01 dùng fixture SMC thiếu H1/lifecycle, 7 case có ATR đều raw=0 nên chưa đủ kiểm tra mẫu §10, cần dữ liệu phù hợp hoặc xác nhận thay đổi phạm vi trước khi ghi hoàn thành. Kết luận review thay thế nhận định CODER đã hoàn tất nhóm; giữ R3 chờ sửa/review lại, chưa chuyển task 22. |
| 2026-09-09 | **Tech Lead (Codex) review lại R3 — D03/D04 ĐẠT; R3 CHỜ E01** | Đóng hai findings code: Decimal được dùng từ distance/clearance/P/C tới HALF_UP; anchor xa và thiếu obstacle giữ LIMITED_CONTEXT cùng hai reason codes. Chạy lại regression **270 passed**; **8 case độc lập** đạt cho BUY/SELL tại 0.4999/0.5/0.5001 ATR, limited context và round-trip; `git diff --check` đạt. Không phát hiện điểm chặn mới trong phần sửa code. E01 vẫn chưa có mẫu phù hợp §10, do đó chưa nghiệm thu toàn bộ R3; task 20 chưa hoàn thành, task 21 chờ E01, chưa xác nhận chuyển task 22. |
| 2026-09-09 | **Tech Lead (Codex) xác nhận DUYỆT R3 — Task 15–21 hoàn thành** | Đã lấy lại dữ liệu độc lập từ Yahoo Chart API ghi tại E01: 1.421 H1, gom 345 H4 theo nhóm đủ 4 nến liên tiếp tại boundary UTC. Tái chạy cả 8 cutoff trong bảng E01 bằng reference H1 đã đóng và config mặc định; reference/ATR/status/raw/distance/clearance khớp bảng, có conflict, invalidated/expired, overlap, far anchor và limited context. Chạy lại regression **270 passed**. Hai findings D03/D04 đã đóng ở lần review trước; nay E01 đạt, không còn điểm chặn R3. Cho phép tiếp tục task 22–28, dừng tại R4 sau task 28; chưa duyệt cutover runtime hoặc gửi lệnh thật. |
| 2026-09-09 | Hoàn thành Task 22 (F01) — **R3 đã duyệt** | `core/scanner_features.py` thêm `location_detail` theo side và adapter `prepare_location_results()` dựng một context rồi score BUY/SELL; `attach_location_results()` lấy raw từ chính `LocationResult`, `to_dict()` serialize detail độc lập. Thêm `derive_technical_raws_with_location()` làm đường prepare opt-in; caller production cũ chưa đổi trước H01. Regression feature kiểm tra một context, reference H1, raw/detail khớp và không mutate chéo: **27 passed**; chưa nối detail qua canonical snapshot/reader (Task 23). |
| 2026-09-09 | Hoàn thành Task 23 (F02) — **R3 đã duyệt** | Truyền `location_detail` qua `SideSnapshot` → canonical `SideScore` → full composition/envelope; compact envelope và `ScannerRow` giữ `location_raw/status/reason_codes`. Validator reject detail sai side/raw; reader chấp nhận payload lịch sử thiếu detail. Thêm `tests/test_location_canonical_detail.py`; regression canonical/reader/live — **307 passed**; chưa đổi version/cache/hash hoặc nối runtime. |
| 2026-09-09 | Hoàn thành Task 24 (F03) — **R3 đã duyệt** | Giữ global Scanner feature identity hiện hành trước H01; Location mới nhận diện bằng `location-geometry-v2`, config resolved nằm trong detail, derivation ghi model/config. Fingerprint hiện có bổ sung detail khi dùng Location mới; canonical snapshot ID đã phân biệt config dù raw không đổi; không tạo cache/fingerprint riêng, payload cũ vẫn đọc. Regression config/hash **32 passed**; bộ canonical/reader/Location **554 passed**; `git diff --check` đạt. |
| 2026-09-09 | Hoàn thành Task 25 (F04) — **R3 đã duyệt** | `TechnicalRawDerivationError` có `reason_code/field/cause`; adapter Location chuyển lỗi dữ liệu/cấu hình sang typed reason, controller giữ reason khi tạo `DATA_UNAVAILABLE` row. `raw=None` bị reject đúng contract, còn `NO_VALID_ANCHOR` `raw=0` vẫn đi qua composition. Regression Task 25 — **54 passed**; `git diff --check` đạt; chưa nối runtime trước H01. |
| 2026-09-09 | Hoàn thành Task 26 (G01) — **R3 đã duyệt** | UI adapter làm giàu side summary bằng canonical `technical_breakdown` và `location_detail`; presentation giữ detail tùy chọn; Scanner Detail hiển thị Location raw/contribution, H1 reference, anchor/obstacle, khoảng cách ATR và reason, không nhầm với `price_vs_zone`. Raw `0`, raw `null` và payload lịch sử thiếu detail có regression riêng. Presentation + adapter **43 passed**; Location render **3 passed**; `compileall` đạt; chưa nối runtime trước H01. |
| 2026-09-09 | Hoàn thành Task 27 (G02) — **R3 đã duyệt** | Regression xác nhận cùng nến giữ nguyên Trend/Momentum raw, canonical SMC, regime, vùng legacy và scenario plan khi chỉ thêm Location detail; input không mutate. Không khóa selected side/candidate vì chúng được phép đổi theo Location. Feature/canonical/live/scenario/SMC **118 passed**; regression mở rộng **438 passed**; chưa nối runtime trước H01. |
| 2026-09-10 | Hoàn thành Task 28 (G03) — **R3 đã duyệt; dừng tại checkpoint R4** | Giữ render path Chẩn đoán, bổ sung CSS responsive cho Location card và fixture matrix dark/light, 320/1280 px, reason dài, số giá nhiều chữ số, raw `0`/`null`, thiếu obstacle và historical detail thiếu. Sau finding R4, render QTextEdit thật ở 320/1280 px đạt không overflow; `tests/test_scanner_detail_v4_diagnostics.py -k location_html` — **10 passed**; reader negative/canonical — **46 passed**; `compileall` và `git diff --check` đạt. Chưa smoke runtime thật; chờ Tech Lead/người dùng xác nhận R4 trước Task 29. |
| 2026-09-10 | Sửa findings Tech Lead R4 (Task 23/26/28) — **R4 vẫn chờ review** | Reader compact/full/ScannerRow reject status/raw Location sai contract và full envelope reject summary lệch canonical detail; UI formatter giữ 5 chữ số EUR/USD; QTextEdit fixture thực tế dark/light tại 320/1280 px không overflow. Reader/canonical **46 passed**; Location render **10 passed**; presentation/adapter **43 passed**; `compileall` và `git diff --check` đạt. Chưa nối runtime hoặc chuyển Task 29. |
| 2026-09-10 | **Tech Lead (Codex) review R4 — CHƯA DUYỆT** | Regression 15 file liên quan **557 passed** với QApplication offscreen. Còn 2 findings P2: F02 reader EnvelopeSideScore/SideScoreSummary nhận status/raw sai (UNAVAILABLE/25, CONFLICT/25, EVALUATED/99, status lạ); full envelope còn nhận summary khác canonical detail. G01 định dạng giá cố định 2 decimals, tái hiện reference 1.142465 thành 1.14 và anchor [1.14211,1.14267] thành [1.14,1.14]. Cần validate contract summary và đối chiếu full canonical; dùng formatter giá theo độ chính xác symbol/tick, thêm negative/FX regressions. G03 test viewport_width chưa điều khiển renderer (chỉ assert tham số); cần render qua QTextEdit/set_rich_html với font/theme thực ở 320/1280 sau sửa và ghi đúng bằng chứng. Reviewer đã render offscreen xác nhận lỗi giá. Các kết luận hoàn tất F02/G01/G03 trước đó chưa đủ nghiệm thu; giữ task 28 chờ sửa/review lại, chưa chuyển task 29. |
| 2026-09-10 | **Tech Lead (Codex) review lại — DUYỆT R4, Task 22–28 hoàn thành** | Đã đóng hai findings P2 của lần review trước: reader compact/full/ScannerRow validate status/raw và các field bắt buộc, full envelope đối chiếu raw/status/reasons với canonical detail; UI dùng formatter giá theo symbol/price_digits, EUR/USD hiển thị reference 1.14247 và anchor [1.14211, 1.14267]. Regression 15 file **565 passed** với QApplication offscreen và font Segoe UI/Consolas. Probe độc lập **37 payload sai bị từ chối** đúng. Render độc lập **20 fixture** (FX, raw 0, unavailable, historical thiếu detail, giá lớn) qua QTextEdit/set_rich_html với palette dark/light tại 320/1280 px: không overflow ngang; đã xem ảnh render hẹp/rộng xác nhận reference/anchor đọc được. Không còn finding chặn R4 trong phạm vi đã review. Cập nhật Task 22–28 Hoàn thành; cho phép CODER tiếp tục Task 29–32, dừng tại R5. Đây là kiểm tra fixture trước H01; smoke runtime thật thuộc H02 và nghiệm thu cuối thuộc R5. |
| 2026-09-10 | Hoàn thành Task 29 (H01) — **R4 đã duyệt** | Runtime `derive_live_analysis` chuyển sang Location engine mới; shared context/reference H1 dùng một lần cho BUY/SELL; controller truyền lại analysis để không dual-call. `location_quality_score_v4` bị loại khỏi runtime path; derivation ghi `location-geometry-v2`/config, input lỗi vẫn typed unavailable. Regression H01 — **363 passed**; cadence fixture D1/H4/H1 được sửa đúng timeframe; `compileall` và `git diff --check` đạt. Chưa smoke controller/broker; tiếp tục Task 30 H02. |
| 2026-09-10 | Hoàn thành Task 30 (H02) | Thêm `tests/test_scanner_h02_integration.py`: live-to-snapshot/UI không dispatch, `EVALUATED/CONFLICT/NO_VALID_ANCHOR`, unavailable fail-closed và cutoff/reference. H02 **4 passed**; regression H01 **363 passed**; `python scripts/scanner_smoke.py` đạt smoke chính + PATHB, `sends_real_order=False`; `compileall` và `git diff --check` đạt. Chỉ là fixture/environment smoke, chưa kiểm tra broker/UI production thật; tiếp tục Task 31 và dừng R5 sau Task 32. |
| 2026-09-10 | Hoàn thành Task 31 (H03) | Cập nhật `scanner-architecture.md`, `scanner-features-spec.md`, `technical-scoring-architecture.md` và `scanner-flow.md` theo caller H01/H02; đánh dấu Location legacy, ghi reference H1/cutoff, unavailable, version/model/config và đường rollback nguyên release trước. Không đổi threshold, không rewrite journal, không đổi code/runtime; tiếp tục Task 32 và dừng tại R5. |
| 2026-09-10 | Hoàn tất Task 32 (H04) — **CHỜ REVIEW R5** | Đối chiếu checklist §12: 10 mục kỹ thuật/tài liệu đã có bằng chứng; mục xác nhận R5 còn chờ Tech Lead/người dùng. Bàn giao scorer duy nhất, file chính, version/config, regression **4 + 363 passed**, smoke chính/PATHB intent-only, giới hạn broker/UI production và đường rollback nguyên release trước. Chưa đánh dấu nghiệm thu cuối, chưa phát hành, chưa gửi lệnh thật. |
| 2026-09-10 | **Tech Lead (Codex) review R5 — CHƯA DUYỆT** | Năm findings: cutoff worker làm bar còn hình thành tại lúc chụp trở thành closed; 2 regression UI adapter do cadence fixture; 2 style guard fail do card Location thêm local style/HEX; thiếu checkpoint code/config cụ thể; docs/guide còn trạng thái chưa triển khai mâu thuẫn. Regression 17 file **579 passed, 2 failed**; full suite **3498 passed, 11 failed, 8 skipped, 16 xfailed** (4 failure liên quan, 7 navigation/FRED ngoài diff). Smoke chính/PATHB fixture đạt; probe unavailable qua controller đạt; boundary cutoff probe fail. Chi tiết và yêu cầu sửa tại mục Tech Lead review R5 sau H04. Task 29–31 trả về đang thực hiện, Task 32 chờ sửa/review lại; checklist §12 chưa đủ nghiệm thu. |
| 2026-09-10 | **CODER sửa findings R5 — CHỜ Tech Lead review lại** | Đóng băng cutoff trước history và truyền packet → analysis → snapshot; regression H02 **5 passed** tại boundary H1/H4. Fixture cadence D1/H4/H1 đúng **24h/4h/1h**; adapter **26 passed**. Card Location dùng semantic template/palette chung; style guards **8 passed**, render Location dark/light 320/1280 **9 passed**. Checkpoint cụ thể tại `reports/scanner/location-r5-checkpoint.json` với baseline `b6e75542c2ae31512abf47fbf5d1fa1210b3aebe` và config kèm theo. Docs đã đồng bộ runtime/R5/production-smoke limits. Full suite **3503 passed, 7 failed, 8 skipped, 16 xfailed**; 1 navigation Backtest + 6 FRED ngoài phạm vi, không có failure mới thuộc Location. Smoke intent-only chính/PATHB đạt, `sends_real_order=False`; chưa tự duyệt R5. |
| 2026-09-10 | **Tech Lead (Codex) review lại — DUYỆT R5, 32/32 task hoàn thành** | Đóng 5 findings: cutoff cố định trước history (probe cached/uncached và 2 worker delays × 2 sides đạt), cadence fixture đúng, semantic UI/style guards đạt, checkpoint baseline/config xác minh được, docs đồng bộ. Regression 19 file **590 passed**; full suite **3503 passed, 7 failed, 8 skipped, 16 xfailed**, 7 failure navigation/FRED ngoài phạm vi như trước. Smoke chính/PATHB đạt không dispatch; 20 render fixture dark/light 320/1280 không overflow. Cập nhật task 29–32 Hoàn thành và checklist R1–R5; nghiệm thu phạm vi Location, chưa smoke broker/UI production thật, không cấp quyền deploy hoặc gửi lệnh. |

CODER chỉ cần ghi ngắn: bước đã làm, file, test/kết quả và việc còn lại.
Không cần một báo cáo riêng cho mỗi work item.
