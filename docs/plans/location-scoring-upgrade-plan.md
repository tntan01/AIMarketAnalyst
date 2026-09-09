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

### Giai đoạn A — Xác nhận lỗi và ranh giới

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi |
|---:|---|---|---|---|
| 1 | A01 | Kiểm tra caller Location và consumer vùng dùng chung | — | Biết chính xác file cần sửa; bảo toàn thay đổi người dùng |
| 2 | A02 | Chạy baseline tests liên quan | A01 | Ghi command và kết quả ngắn |
| 3 | A03 | Thêm fixture sáu case OLD-01..06 | A02 | Tái hiện đúng công thức cũ |
| 4 | A04 | Xác minh nến H4 đóng/cutoff và ghi target vào architecture | A01 | Quy ước thời gian rõ; docs chưa tuyên bố đã live |

### Giai đoạn B — Mô hình tối thiểu

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi |
|---:|---|---|---|---|
| 5 | B01 | Tạo location_engine.py, cấu hình mặc định có version | A04 | Không service/database mới |
| 6 | B02 | Validate cấu hình và input thiết yếu | B01 | T05 đạt; default khác với fallback che config lỗi |
| 7 | B03 | Tạo LocationZone/Context/Result nhỏ | B02 | Field đủ cho tính điểm và giải thích |
| 8 | B04 | Viết serialize detail và reason codes cần dùng | B03 | Null/0/status/version có ý nghĩa rõ; **DỪNG và hỏi tại R1, chờ xác nhận** |

### Giai đoạn C — Dựng vùng đúng

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi |
|---:|---|---|---|---|
| 9 | C01 | Lọc closed candles theo cutoff, giới hạn history | B03,A04 | Không dùng nến tương lai |
| 10 | C02 | Tạo swing ID/confirmed_at | C01 | Không dùng index làm ID; swing có đủ xác nhận |
| 11 | C03 | Dựng biên bằng ATR tại confirmation, tick nếu có | C02 | T14 đạt; max width được kiểm tra |
| 12 | C04 | Viết breach streak BUY/SELL và expiry | C03 | T11,T12 đạt |
| 13 | C05 | Dedup chính xác và sắp xếp ổn định | C04 | Không merge/revision framework; duplicate không tăng điểm |
| 14 | C06 | Kiểm tra causal và context dùng chung hai phía | C05 | T13 đạt; context dựng một lần; **DỪNG và hỏi tại R2, chờ xác nhận** |

### Giai đoạn D — Chấm Location

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi |
|---:|---|---|---|---|
| 15 | D01 | Chọn anchor đúng phía/trạng thái | C06 | T01,T04 đạt |
| 16 | D02 | Chọn obstacle và xử lý conflict trước | D01 | T02,T03 đạt |
| 17 | D03 | Viết P,C,raw và rounding | D02 | T06–T10,T16 đạt |
| 18 | D04 | Hoàn thiện reason/detail/unavailable | D03,B04 | Không tạo điểm giả; raw0 khác null |
| 19 | D05 | Chạy invariants và regression của engine | D04 | T01–T16 liên quan đạt; không đọc SMC score/macro/R:R |

### Giai đoạn E — Xem thử ngắn, không xây backtest

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi |
|---:|---|---|---|---|
| 20 | E01 | Chọn 5–10 case biểu đồ/export sẵn có và xem kết quả mới | D05 | Kiểm tra các tình huống §10, không cần evaluator riêng |
| 21 | E02 | Ghi ghi chú ngắn, sửa lỗi nếu có | E01 | Kết quả hợp lý về logic; không yêu cầu report lợi nhuận; **DỪNG và hỏi tại R3, chờ xác nhận** |

### Giai đoạn F — Tích hợp canonical gọn

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi |
|---:|---|---|---|---|
| 22 | F01 | Gắn raw và một LocationResult/detail nhỏ vào feature output | D04 | Một nguồn kết quả, raw hợp lệ vẫn int |
| 23 | F02 | Truyền detail qua snapshot chính thức và reader | F01 | T18 đạt; không thêm key lạ vào technical_raws |
| 24 | F03 | Ghi version/config, cập nhật existing hash/cache nếu cần | F02 | Nhận diện dữ liệu cũ/mới; không hệ thống fingerprint mới |
| 25 | F04 | Nối typed unavailable vào luồng lỗi hiện có | F01 | T20 error path đạt; không null leak hoặc default điểm |

### Giai đoạn G — Giao diện và hồi quy

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi |
|---:|---|---|---|---|
| 26 | G01 | UI đọc raw/contribution/detail, hiển thị reference H1 rõ | F02,F04 | T19 đạt; không tự tính score |
| 27 | G02 | Kiểm tra SMC/Trend/Momentum/scenario không đổi ngoài scope | G01 | T17 và existing tests liên quan đạt |
| 28 | G03 | Kiểm tra card trên giao diện hẹp/rộng, dark/light | G01 | Không overflow; không thêm overlay/màn hình mới; **DỪNG và hỏi tại R4, chờ xác nhận** |

### Giai đoạn H — Chuyển công thức và hoàn tất

| Task | ID | Việc làm | Phụ thuộc | Hoàn tất khi |
|---:|---|---|---|---|
| 29 | H01 | Nối duy nhất engine mới vào runtime, bỏ call cũ | E02,F03,F04,G02 | Không dual/shadow scoring; version đúng công thức |
| 30 | H02 | Chạy targeted integration tests và smoke check | H01,G03 | T01–T20 thuộc phạm vi đạt; kiểm tra không gửi lệnh thật |
| 31 | H03 | Cập nhật docs và checkpoint code/config để có thể quay lại | H02 | Không rewrite journal; không đổi threshold ngoài yêu cầu |
| 32 | H04 | Bàn giao kết quả, giới hạn và các mục để sau | H03 | Checklist §12 đạt; không đợi backtest lợi nhuận; **DỪNG và hỏi tại R5, chờ xác nhận** |

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

#### Task 17 (D03) — Tính P, C và điểm nguyên

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

#### Task 18 (D04) — Result, reason và unavailable

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

#### Task 19 (D05) — Chạy invariants và review phạm vi

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

#### Task 20 (E01) — Xem 5–10 case từ biểu đồ hoặc export sẵn có

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

#### Task 21 (E02) — Ghi kết quả và sửa sai khác

> **Điểm dừng R3:** sau khi hoàn thành task 21, dừng và hỏi Tech Lead/người dùng
> theo §11.2; chưa được xác nhận thì không chuyển nhóm hoặc nghiệm thu cuối.

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
- Sau task 14: chờ R2, chưa thực hiện task 15.
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

- [ ] Các lỗi vùng sai phía, xung đột, bonus xa và bước nhảy điểm được sửa.
- [ ] Vùng có confirmation/lifecycle cơ bản; không dùng dữ liệu tương lai.
- [ ] Công thức đạt 0–25, giữ normalization/regime weights.
- [ ] Dữ liệu lỗi không được biến thành điểm giả.
- [ ] Không thay đổi SMC/Trend/Momentum hoặc entry gates ngoài phạm vi.
- [ ] Raw/detail/version truyền nhất quán tới snapshot và UI.
- [ ] Kiểm thử code liên quan đạt; đã xem một số case biểu đồ.
- [ ] Chỉ một công thức Location chạy live, dữ liệu lịch sử không bị ghi đè.
- [ ] Có checkpoint code/config và hướng dẫn quay lại ngắn nếu phát hiện lỗi.
- [ ] Tài liệu ghi đúng đã triển khai/chưa triển khai và giới hạn còn lại.
- [ ] R1–R5 đã có xác nhận rõ ràng; chưa qua R5 thì trạng thái là chờ nghiệm thu.

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

CODER chỉ cần ghi ngắn: bước đã làm, file, test/kết quả và việc còn lại.
Không cần một báo cáo riêng cho mỗi work item.
