# SD Implementation Plan

> Người lập: PO. Ngày: 08/09/2026.
> Trạng thái: kế hoạch triển khai, **chưa thực hiện các bước trong tài liệu này**.
> Phạm vi: phần mềm cá nhân, phân tích/cảnh báo SD; MT5 chỉ đọc.
> Tổng cộng **172 bước**, đánh số liên tục từ **001 đến 172**, chia thành 15 nhóm.

## 1. Cách coder thực hiện

Nguồn chuẩn là [01](01-scope-and-requirements.md) về phạm vi,
[02](02-trading-rules.md) về nghiệp vụ,
[03](03-technical-design.md) về contract/kiến trúc,
[04](04-ui-and-alerts.md) về UI và
[05](05-acceptance-criteria.md) về kết quả kiểm tra.
Kế hoạch này chỉ chia công việc, không đặt thêm công thức hoặc ngưỡng giao dịch.

- Làm theo số tăng dần. Mỗi dòng là một thay đổi có đầu ra và điều kiện hoàn
  thành riêng; không cần một commit hoặc một file riêng cho mỗi dòng.
- Sau mỗi bước hoàn thành, coder báo kết quả và thêm **một câu về mốc review**
  theo mục 2.1. Không chỉ cập nhật file tiến độ rồi bỏ qua thông báo này.
- Đường dẫn trong kế hoạch tính từ root repository. Trong một nhóm, dùng các
  file được chỉ định ở đầu nhóm; mở rộng file hiện có theo từng bước, không
  tạo module rỗng hàng loạt hoặc dựng kiến trúc feature-first.
- Mỗi bước logic đi cùng kiểm tra nhỏ đúng hành vi trong cột hoàn thành. Dùng
  dữ liệu giả lập/mẫu có expected kiểm chứng được; không dùng chính hàm đang
  kiểm tra để tạo expected. Không đợi tới nhóm cuối mới viết test logic.
- Bước UI đơn giản được kiểm tra bằng harness/thao tác trực tiếp; ưu tiên test
  tự động cho giá, state, identity, restore, dedup và race. Không bắt buộc viết
  test chỉ để kiểm tra một label hoặc sao chép từng dòng implementation.
- Các nhóm sau dùng contract/kết quả nhóm trước. Khi chưa có nguồn MT5 hoặc
  một convention broker chưa rõ, dùng fake port/boundary đã định nghĩa để làm
  core, store, worker và UI. Không làm giả kết quả xác minh broker.
- Bước chờ đầu vào/PO ghi đúng phần thiếu và tiếp tục bước độc lập có số lớn
  hơn. Không vượt bước chốt rules để bật runtime; có thể hoàn thành UI và
  tích hợp có khóa DRAFT bằng harness trước đó.
- Việc chỉ tạo file hoặc chạy một test xanh chưa đủ: đối chiếu cả cột công
  việc và điều kiện hoàn thành. Không thêm lệnh MT5, đổi Market Watch, reuse
  decision Scanner/SMC, backtest hay tối ưu tham số vào phạm vi.
- Chỉ cập nhật trạng thái bước khi có bằng chứng: ghi cạnh tên bước
  **Đang làm / Đã xong / Chờ đầu vào / Chờ PO**, kèm file/test hoặc lý do.
  Bước chưa có ghi chú trạng thái được hiểu là **Chưa làm**. Không đổi số bước
  khi cập nhật tiến độ, để coder khác có thể tiếp tục đúng chỗ.
- Các quyết định nghiệp vụ còn thiếu phải được ghi với ví dụ input/output
  cần chốt. Không sửa rules hoặc tự chọn expected để test qua. Chủ ứng dụng
  chốt quy tắc theo cơ chế PO hiện có, không yêu cầu phê duyệt từng bước code.
- Không cần lịch sử test có sẵn, lợi nhuận, win rate hoặc benchmark. Kiểm tra
  hai cấu hình UI tối thiểu vẫn là yêu cầu riêng: **1366 × 768/100%** và
  **1920 × 1080/150%**, có taskbar/shell trong diện tích khả dụng.

Ở thời điểm lập kế hoạch, chưa tìm thấy module nghiệp vụ `supply_demand_*`
trong repository. Coder phải kiểm tra lại ở bước 002 vì code có thể được bổ
sung sau khi tài liệu này được viết.

## 2. Thứ tự nhóm và đầu ra

| Nhóm | Bước | Đầu ra chính |
|---|---|---|
| 1. Chuẩn bị và xác định đầu vào | 001–007 | Môi trường, điểm tích hợp và dữ liệu mẫu tách khỏi dữ liệu cá nhân. |
| 2. Model, tham số và định danh | 008–023 | DTO bất biến, registry hợp lệ và ID xác định. |
| 3. Settings, mapping và lịch phiên | 024–034 | Settings độc lập, symbol mapping và lịch phiên/biên có contract rõ. |
| 4. Adapter dữ liệu chỉ đọc | 035–047 | Snapshot an toàn từ fake port hoặc đường MT5 trung tính. |
| 5. Chỉ báo và detector vùng | 048–060 | Vùng hình thành đúng pattern/biên/ID, không lookahead. |
| 6. Vòng đời vùng và liên kết đa khung | 061–073 | Vòng đời D1/H4/H1 và quan hệ đa khung đúng quy tắc. |
| 7. Kế hoạch giá và chấm chất lượng | 074–083 | Entry/SL/TP/RR sau rounding, điểm và bối cảnh cản. |
| 8. Entry latch, M15 và state machine | 084–096 | Latch/M15/mode/conflict và transitions xác định. |
| 9. Pipeline phân tích thuần | 097–102 | Full/incremental analysis thuần Python. |
| 10. SQLite, evidence và inbox | 103–114 | Evidence/ledger atomic, inbox bền vững và lỗi lưu rõ ràng. |
| 11. Khôi phục và service điều phối | 115–124 | Restore không hồi sinh setup hoặc phát cảnh báo quá khứ. |
| 12. Worker, controller và vòng đời ứng dụng | 125–135 | Single-flight/cancellation/shutdown không chặn UI. |
| 13. Presentation và khung UI thích ứng | 136–146 | Màn hình SD cơ bản dùng được ngay ở diện tích tối thiểu. |
| 14. Chart, detail và thông báo | 147–158 | Chart/detail/inbox/popup đầy đủ và scale đúng. |
| 15. Tích hợp, kiểm tra trực tiếp và bàn giao | 159–172 | Route có kiểm soát, kết quả kiểm tra và chạy cá nhân sau chốt rules. |

Những bước chuẩn bị contract và dữ liệu mẫu phải hoàn thành trước module
phụ thuộc. Các bước xác minh nguồn thật và kiểm tra màn hình cần môi trường
thực tế; nếu chưa có, ghi Chờ đầu vào/Chưa kiểm tra, không suy ra đã đạt từ fake.

### 2.1 Các mốc review của Tech Lead và câu thông báo sau mỗi bước

Quyết định PO: không review từng bước. Coder tự kiểm tra điều kiện hoàn thành
của từng bước; chuyển Tech Lead review tại sáu mốc sau:

| Mốc | Sau bước | Phạm vi review |
|---|---:|---|
| R1 — Contract và định danh | 023 | Model, registry/validation, Decimal/timestamp và canonical ID; đổi mode không đổi setup ID. |
| R2 — Pipeline nghiệp vụ | 102 | Adapter chỉ đọc, detector, vòng đời/đa khung, kế hoạch/điểm, latch/M15, conflict/READY; tính xác định và không lookahead. |
| R3 — Lưu trữ và khôi phục | 124 | Commit atomic, evidence/revision inputs, ledger chống lặp và replay; không hồi sinh terminal hoặc phát cảnh báo quá khứ. |
| R4 — Worker và điều phối | 135 | Single-flight, cancellation, generation/commit, config/scope switch và shutdown; UI không bị chặn. |
| R5 — UI hoàn chỉnh | 158 | Chart/detail/inbox/popup, layout thích ứng, giữ form/selection khi resize/scale; UI không tự tính nghiệp vụ. |
| R6 — Tích hợp trước khi dùng | 167 | Kết quả kiểm tra core/service/UI, hai cấu hình màn hình, hồi quy MT5/DI và các lỗi/giới hạn còn lại. |

Sau **mỗi bước hoàn thành**, coder thêm đúng một câu phù hợp vào thông báo
tiến độ cho người dùng, sau phần việc đã làm và kết quả kiểm tra:

- **Chưa đến mốc:** “Bước {NNN} chưa tới mốc review; mốc tiếp theo là
  {R/tên mốc}, sau bước {MMM}.”
- **Đúng bước mốc:** “Đã tới mốc quan trọng {R/tên mốc} sau bước {NNN}; cần
  chuyển Tech Lead review {phạm vi ngắn gọn}.”
- **Còn mốc trước đang chờ review:** “Mốc {R/tên mốc} sau bước {MMM} đang chờ
  Tech Lead review; bước {NNN} vừa hoàn thành là phần độc lập.”
- **Sau R6:** “Bước {NNN} nằm sau mốc review cuối R6; {trạng thái review R6
  và phần thay đổi/lỗi mới cần xem lại, nếu có}.”

Ví dụ sau bước 023: **“Đã tới mốc quan trọng R1 — Contract và định danh sau
bước 023; cần chuyển Tech Lead review model, tham số và canonical ID.”**

Nếu một lần báo cáo hoàn thành nhiều bước, vẫn ghi câu mốc cho từng bước;
không bỏ qua mốc nằm giữa các bước đó. Bước còn chờ đầu vào chưa được báo là
hoàn thành. Khi chạm số bước mốc nhưng phần review còn thiếu, vẫn thông báo
đã tới mốc và liệt kê phần thiếu trong hồ sơ, không tự đánh dấu mốc đã đạt.

Tại mỗi mốc, chuẩn bị hồ sơ ngay trong ghi chú tiến độ: bước/file thay đổi,
kết quả/lệnh kiểm tra, vấn đề còn vướng và phần dự định làm tiếp. Thông báo
“cần chuyển review” không đồng nghĩa đã có người review hoặc đã thông qua.
Ghi trạng thái riêng cho mốc: **Chưa tới / Cần review / Đang review /
Cần sửa / Đã thông qua**, kèm kết luận thực tế của Tech Lead khi có.

Trong lúc chờ review, coder tiếp tục phần độc lập. Không dùng contract hoặc
hành vi đang có lỗi/mâu thuẫn chưa giải quyết làm nền cho phần phụ thuộc.
Nếu phát sinh mâu thuẫn đặc tả, cần đổi contract hoặc ảnh hưởng đường MT5
dùng chung, yêu cầu review ngay thay vì chờ mốc; thay quy tắc giao dịch/phạm
vi phải chuyển PO quyết định. Không yêu cầu người dùng duyệt từng bước code.

Bước **169** là PO chốt rules, không thay thế review kỹ thuật. Bước **172**
là tổng hợp bàn giao; Tech Lead chỉ cần xem lại thay đổi/lỗi mới sau R6 nếu
có, không mặc định review lại toàn bộ 172 bước. Review UI tại R5 không thay
thế kết quả kiểm tra thực tế hai cấu hình màn hình tại R6.

## 3. Các bước thực hiện

### Nhóm 1. Chuẩn bị và xác định đầu vào

**File/phạm vi:** `docs/SD/01–05`, `docs/ui/style-guide.md`, `ARCHITECTURE.md`; chưa sửa runtime.

**Nguồn:** Toàn bộ phạm vi `01`; `03` mục 1–3.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 001 | Đọc nguồn chuẩn | Đọc 01 → 02 → 03 → 04 → 05 và style guide; ghi các ràng buộc áp dụng cho phần sắp làm. | Biết nguồn công thức, contract, UI; không dùng câu trả lời hội thoại thay rules đã đồng bộ. |
| 002 | Kiểm tra trạng thái repository | Ghi branch, thay đổi đang có và module SD đã tồn tại tại thời điểm nhận việc; không ghi đè công việc khác. | Có danh sách file sẽ dùng/sửa; bước đã được người khác làm được kiểm tra thay vì tạo lại. |
| 003 | Kiểm tra môi trường Python/Qt | Dùng môi trường dự án, xác định Python, pytest, PyQt6/WebEngine và lệnh chạy ứng dụng hiện tại. | Import các dependency cần thiết được hoặc ghi cụ thể dependency thiếu; chưa đổi phiên bản thư viện không cần thiết. |
| 004 | Kiểm tra điểm tích hợp hiện có | Đọc AppController, MT5Service, main window/navigation, chart và đường app_data_dir trong 03. | Xác định đúng instance MT5, khóa chung, DI và shutdown; chưa nối SD vào runtime. |
| 005 | Lập danh sách điểm chưa đủ contract | Đối chiếu rules với thiết kế, nhất là broker boundary, replay mode/config, thứ tự sự kiện cùng thời gian. | Mỗi điểm có nguồn, câu hỏi cụ thể và phần phụ thuộc; không tự đặt expected nghiệp vụ để qua test. |
| 006 | Tạo bộ dữ liệu giả lập dùng chung | Tạo helper nến/quote/symbol/session và clock truyền tường minh trong tests/fixtures/supply_demand hoặc helper có tiền tố supply_demand_. | Có thể tạo input nhỏ, xác định; không đọc tài khoản, DB hay dữ liệu cá nhân. |
| 007 | Ghi cách chạy kiểm tra SD | Xác định lệnh pytest theo từng file và cách mở UI bằng harness dữ liệu giả lập. | Có lệnh tái chạy được; harness không bật route runtime và không phát cảnh báo vào inbox cá nhân. |

### Nhóm 2. Model, tham số và định danh

**File/phạm vi:** `core/supply_demand_models.py`, `core/supply_demand_parameters.py`, `core/supply_demand_reason_codes.py`, `core/supply_demand_identity.py`; `config/supply_demand_defaults.json`; test tương ứng.

**Nguồn:** `02` mục 17–18; `03` mục 4, 10.1.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 008 | Khai báo enum nghiệp vụ | Tạo timeframe, side, hướng, zone/setup state và entry mode theo registry; TESTED chỉ hợp lệ cho D1. | Giá trị ngoài enum bị từ chối; không trộn operational status với setup state. |
| 009 | Khai báo reason codes | Chép đầy đủ enum đóng và thứ tự nhóm từ 02; thêm helper sắp xếp reasons. | Một tập reasons luôn xuất cùng thứ tự; không phát chuỗi tự do từ core. |
| 010 | Tạo model nguồn và thời gian | Tạo source scope, symbol spec, quote có precision/source_time/received_at và metadata lịch biên. | Giữ được tick mili giây, candle giây nguyên và revision nguồn riêng biệt. |
| 011 | Tạo model nến và snapshot | Tạo candle, series, session policy, market snapshot, request và safety report bất biến. | Dữ liệu truyền qua thread không bị widget sửa; mỗi series có watermark riêng. |
| 012 | Tạo model zone và retest | Tạo zone/retest với source refs, formation ATR, biên, ordinal và touch source. | Phân biệt source zone đầy đủ với entry sub-zone; không dùng 0 thay trường chưa có. |
| 013 | Tạo model plan và điểm | Tạo trade plan, quality breakdown và D1 structure/zone context. | Thiếu TP/RR là None; D1 có formation /50 riêng; COMPLETE khác PENDING. |
| 014 | Tạo model setup và kết quả | Tạo setup, transition, analysis result và batch result. | Giữ latch/M15 ref/mode, revisions và lỗi riêng từng symbol; mode không định nghĩa danh tính. |
| 015 | Tạo model evidence và lỗi vận hành | Tạo replay evidence, revision input, operational issue và kết quả store typed. | Đủ trường SOURCE_TOUCH/ENTRY_TOUCH/MODE_CHANGE, sequence và refs; DB lỗi không thành reason giao dịch giả. |
| 016 | Thiết lập quy ước Decimal | Tạo helper chuyển số hữu hạn, decimal context và serialize giá theo contract 03. | NaN/Infinity bị từ chối; float nguồn đi qua str; giá JSON không mất độ chính xác. |
| 017 | Khai báo registry tham số | Chép tên/kiểu/đơn vị/default/min/max của 02 vào code và defaults JSON. | Defaults khớp 02, gồm ba tham số D1 và base_max_bars tối đa 4; không đặt ngưỡng mới. |
| 018 | Validate từng tham số | Kiểm tra kiểu, min/max, unknown fields và giá trị không hữu hạn. | Invalid trả lỗi theo trường; không clamp hoặc âm thầm dùng default. |
| 019 | Validate ràng buộc chéo | Thực thi toàn bộ quan hệ tại mục 17 của 02. | Có ví dụ vi phạm từng quan hệ và cấu hình default hợp lệ; base 5/10 bị từ chối. |
| 020 | Tạo rules descriptor | Tách rules_version, DRAFT/APPROVED, schema version và config revision. | DRAFT không nối vào ID; có đường kiểm tra chưa cho bật runtime. |
| 021 | Tạo canonical zone ID | Serialize canonical array đúng thứ tự/UTC/tick rounding rồi hash. | Golden input gồm JSON và digest được tính/đối chiếu độc lập; timestamp candle phần lẻ bị từ chối. |
| 022 | Tạo setup/retest/alert ID | Thực thi công thức ID hiện tại của 02, setup ID không chứa mode. | A→B giữ ID; thay grade/TP/RR không đổi ID; scope/config hash không bị chèn vào canonical input. |
| 023 | Kiểm tra round-trip contract | Serialize rồi đọc lại price, timestamp, enums và evidence đại diện. | Cùng input cho cùng ID và giá; quote mili giây còn nguyên sau round-trip. |

### Nhóm 3. Settings, mapping và lịch phiên

**File/phạm vi:** `services/supply_demand_settings_service.py`, `services/supply_demand_session_service.py`, `services/supply_demand_data_adapter.py`; defaults và tests tương ứng.

**Nguồn:** `01` FR-01/11; `02` mục 16–18; `03` mục 5.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 024 | Tạo settings SD riêng | Định nghĩa settings schema dưới namespace sd và đường app_data_dir()/supply_demand/settings.json. | Không phụ thuộc settings chiến lược cũ; defaults chỉ dùng khi chưa có cấu hình. |
| 025 | Seed registry symbol | Khai báo rõ 31 canonical symbol, asset class và alias theo 03; watchlist ban đầu bốn mã. | Mapping không suy từ hậu tố/contract size; watchlist rỗng vẫn rỗng. |
| 026 | Resolve broker symbol | Áp thứ tự mapping cá nhân rồi alias visible hợp lệ; phát hiện ambiguous/trùng đích. | Không gọi symbol_select; unresolved có lý do, không thay bằng một mã đoán. |
| 027 | Resolve session policy | Áp symbol override → asset class override → profile mặc định; override thay toàn policy. | Override thiếu trường trả invalid, không merge ngầm hoặc fallback che lỗi. |
| 028 | Load settings và validate | Đọc cấu hình rồi chạy validation trước khi cấp active config. | File hỏng/invalid được báo cụ thể; không báo save/load thành công bằng defaults. |
| 029 | Save settings an toàn | Ghi file tạm cùng thư mục, flush/replace và backup hợp lệ; chỉ tăng revision sau save thành công. | Giả lập lỗi ghi giữ config đang dùng; không làm mất bản hợp lệ trước đó. |
| 030 | Tạo lịch mở phiên | Thực thi FOREX/METAL/CRYPTO theo IANA, ngày mở/đóng và nghỉ ngày. | Mẫu ngày thường/cuối tuần/giờ nghỉ cho kết quả is_open đúng policy. |
| 031 | Tạo contract lịch biên nến | Biểu diễn boundary có provenance, effective range và revision, tách khỏi lịch mở thị trường. | Có fake boundary provider; không mặc định mọi kỳ đóng tại open+duration. |
| 032 | Sinh expected opens/closes | Dùng policy và boundary để liệt kê các biên kỳ vọng trong khoảng. | Mẫu nghỉ phiên/DST không tự sinh nến hoặc tự cắt kỳ H4/D1. |
| 033 | Tạo lỗi thiếu biên xác thực | Trả DATA_CANDLE_BOUNDARY_UNRESOLVED kèm symbol/timeframe/mốc chưa rõ. | Chặn READY đúng phạm vi; các bước tiếp theo vẫn chạy bằng provider giả lập rõ convention. |
| 034 | Kiểm tra IANA và đổi policy | Kiểm tra timezone data khi khởi tạo, invalidation safety/cache khi policy revision đổi. | Thiếu IANA có lỗi rõ; policy mới không tiếp tục dùng safety của revision cũ. |

### Nhóm 4. Adapter dữ liệu chỉ đọc

**File/phạm vi:** `services/mt5_service.py`, `services/supply_demand_data_adapter.py`; `tests/test_supply_demand_data_adapter.py`.

**Nguồn:** `02` mục 1, 16, 18; `03` mục 6; AC-01/15.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 035 | Tạo market data port giả lập | Cài port đọc snapshot bằng fixture cùng chữ ký contract. | Core/service có thể chạy mà không import hoặc kết nối MT5. |
| 036 | Thêm đường đọc MT5 trung tính | Bổ sung API raw batch trong MT5Service dùng instance/serialization boundary hiện có. | API trả raw metadata/rates/tick, không gọi scoring, order DTO hoặc symbol_select. |
| 037 | Kiểm tra allowlist lời gọi | Dùng SDK spy để ghi lời gọi của riêng đường đọc SD. | Chỉ các API đọc cho phép được gọi; không gửi/sửa/đóng/hủy lệnh hay đổi Market Watch. |
| 038 | Kiểm tra scope đầu/cuối batch | Đọc scope trước/sau, loại batch nếu account/server/generation đổi. | Không trộn nến hoặc quote của hai nguồn; trả lỗi để caller tái dựng. |
| 039 | Chuyển quote và timestamp | Chuyển Bid/Ask/time/time_msc, kiểm tra nhất quán và giữ source precision. | Tick sát biên M15 giữ đúng thời điểm; không dịch broker offset thêm cho UTC MT5. |
| 040 | Chuyển rates thành nến đóng | Kết hợp raw open time với boundary/closed evidence; chỉ nhận close_time <= as_of. | Bar đang mở không đi vào core; không coi phần tử cuối tự động là nến đóng. |
| 041 | Validate chuỗi nến | Kiểm tra OHLC hữu hạn/hình học, thứ tự tăng nghiêm ngặt và timestamp trùng. | Input lỗi bị báo; không sort/dedup/sửa nến âm thầm. |
| 042 | Resolve tick size và price basis | Dùng trade_tick_size dương, fallback point dương; xác minh basis nhất quán. | Không suy từ digits; thiếu cả hai chặn dữ liệu của symbol. |
| 043 | Tạo history request mức sàn | Tính công thức theo tham số 02, không hardcode số nến default. | Default D1/H4/H1/M15 là 395/395/515/253; override tự thay độ sâu. |
| 044 | Ghép snapshot và watermark | Chốt as_of sau batch đọc, giữ fetched_at/watermark riêng từng timeframe. | Không đưa dữ liệu sau cutoff vào snapshot hoặc gắn timestamp mới cho dữ liệu cũ. |
| 045 | Phân loại gap/stale | Dùng expected boundaries và session; tách khoảng nghỉ khỏi thiếu dữ liệu trong phiên. | Gap chưa giải thích/stale chặn READY; nghỉ phiên không làm tuổi/stale tăng sai. |
| 046 | Tạo cache và data revision | Cache theo scope/symbol/TF/basis/mapping; phát hiện broker sửa nến đóng. | Nến sửa làm tăng revision và yêu cầu replay; không ghép kết quả theo index cũ. |
| 047 | Đối chiếu broker đang dùng | Khi có nguồn, đọc mẫu chỉ đọc và đối chiếu lịch biên/precision, ghi convention thực tế. | Có bằng chứng nguồn hoặc ghi CHỜ ĐẦU VÀO; không chặn core/UI giả lập và không tự nhận đã xác minh. |

### Nhóm 5. Chỉ báo và detector vùng

**File/phạm vi:** `core/supply_demand_indicators.py`, `core/supply_demand_zone_detector.py`; tests indicators/detector và fixture nhỏ.

**Nguồn:** `02` mục 1, 3–8, 11.1/11.2; AC-02/05.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 048 | Tính True Range | Thực thi TR dùng close trước mỗi nến. | Ví dụ có gap ra đúng TR; thiếu close đầu báo không đủ input. |
| 049 | Tính ATR hữu hạn | Thực thi Wilder seed và cửa sổ warmup chính xác theo 02. | Kết quả bằng tính tay trên mẫu nhỏ; thiếu cửa sổ không lấy ATR process cũ. |
| 050 | Tính epsilon | Thực thi max tick/ATR với ATR đúng timeframe và đúng mốc quy định. | Boundary so sánh dùng cùng helper; không dùng ATR hiện tại thay formation ATR. |
| 051 | Phát hiện swing xác nhận | Tạo pivot có nến hai phía và confirmed_at; xử lý bằng nhau theo epsilon. | Chưa đủ nến phải không thấy pivot; thêm tương lai không làm lộ pivot sớm. |
| 052 | Phát hiện Rally/Drop | Tính net move, tỷ trọng directional range và body theo registry. | Ví dụ đạt/không đạt từng điều kiện và BUY/SELL đối xứng. |
| 053 | Tìm base hợp lệ | Kiểm tra số nến, range/body/cluster, overlap cặp và gap. | Base một nến xử lý đúng; cấu hình 1–4; chọn cụm ngắn nhất rồi hẹp nhất. |
| 054 | Xác nhận departure | Kiểm tra move, breakout, re-entry và body; gắn formation ATR trước base. | Chỉ tạo xác nhận khi departure cuối đóng; nến departure chưa là retest. |
| 055 | Chọn arrival và pattern | Thử cửa sổ đúng thứ tự, chọn dài nhất cùng hướng hoặc loại ambiguous. | Bốn pattern đúng loại vùng; không có arrival thì không tạo zone. |
| 056 | Tạo biên vùng | Tính proximal/distal từ base rồi rounding ra ngoài theo side. | Biên nằm trên lưới tick và không hẹp hơn raw zone. |
| 057 | Loại vùng sai độ rộng | Kiểm tra zone 0 sau rounding, quá rộng hoặc quá hẹp theo registry. | Reason đúng; không tạo zone giá 0 để thay candidate bị loại. |
| 058 | Tính điểm formation để khử trùng | Tính Departure/Base theo 11.1/11.2, swing bonus chỉ từ quá khứ hợp lệ. | Không dùng freshness/location/RR động khi chọn duplicate. |
| 059 | Khử trùng và tạo ID | Quét confirmation từ cũ đến mới, áp overlap/window/tie-break, gắn canonical ID. | Cùng input luôn giữ cùng candidate; một base chỉ dùng departure đầu xác nhận. |
| 060 | Kiểm tra detector theo tiền tố | Chạy fixture từng đoạn nến tăng dần, đối chiếu vùng tại cùng cutoff. | Không lookahead; formation ATR/biên/ID không đổi chỉ do thêm nến tương lai. |

### Nhóm 6. Vòng đời vùng và liên kết đa khung

**File/phạm vi:** `core/supply_demand_lifecycle.py`, `core/supply_demand_context.py`; tests lifecycle/context.

**Nguồn:** `02` mục 8–10, 18; AC-03/04.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 061 | Tạo reducer vòng đời | Nhận previous entity và sự kiện có thời gian; trả entity mới. | Không mutate input; có thứ tự xác định cho nhóm sự kiện cùng timestamp. |
| 062 | Bắt đầu retest bằng tick | Dùng Ask Demand/Bid Supply trên source zone đầy đủ. | Tick đầu tạo ordinal đúng; tick lặp không nhân bản retest. |
| 063 | Bắt đầu retest bằng nến fallback | Áp nến đóng giao vùng và quan hệ với nến lifecycle trước. | Lưu nguồn/ref đúng; departure không tính retest. |
| 064 | Hợp nhất touch tick/nến | Ghép evidence của cùng lần chạm, không tạo ordinal mới cho fallback phát hiện sau. | Tick trước close và nến chứa tick thuộc một retest; không mất thời điểm nguồn. |
| 065 | Kết thúc retest | Chỉ kết thúc khi nến source timeframe đã đóng không còn giao vùng. | Tick rời vùng không tự kết thúc; chuỗi nến giao vùng giữ cùng retest. |
| 066 | Tính mitigation | Theo dõi cực trị trong retest, chuẩn hóa và clamp 0–1. | Mitigation chỉ trình bày/log, không tự trừ điểm hoặc đổi state. |
| 067 | Xử lý broken | Áp close vượt distal hoặc wick buffer đúng formation ATR. | Broken thắng expiration khi cùng chu kỳ; entry sub-zone không có broken riêng. |
| 068 | Xử lý tuổi vùng | Đếm nến theo lịch hợp lệ từ confirmation và giới hạn từng timeframe. | H4 120/H1 240/D1 120 mặc định; nghỉ phiên không cộng tuổi lịch. |
| 069 | Hoàn thiện vòng đời H4/H1 | Kết thúc retest đầu thì EXPIRED nếu chưa broken. | Vùng không hồi sinh ở lần chạm thứ hai, kể cả chưa từng READY. |
| 070 | Hoàn thiện vòng đời D1 | Thực thi FRESH/RETESTING/TESTED, nhiều retest tới broken/quá tuổi. | Không reset TESTED về FRESH hoặc áp expiration retest đầu của H4. |
| 071 | Tính D1 bias/dealing range | Dùng swings đã xác nhận, lookback và current price theo 02. | BUY/SELL/NEUTRAL, UNKNOWN, discount/equilibrium/premium đúng ranh giới. |
| 072 | Liên kết H1 với H4 | Áp side/time/overlap/state và lựa chọn cha theo quy tắc. | Không có H4 hợp lệ thì chặn READY; parent broken/expired truyền đúng xuống setup. |
| 073 | Liên kết H4 với D1 | Áp confirmation/overlap/state và tie-break, trả aligned/unaligned. | D1 mất hiệu lực chỉ đánh giá lại context; không tự làm H4 invalidated. |

### Nhóm 7. Kế hoạch giá và chấm chất lượng

**File/phạm vi:** `core/supply_demand_trade_plan.py`, `core/supply_demand_quality.py`, `core/supply_demand_context.py`; tests plan/quality.

**Nguồn:** `02` mục 9.1, 11–13, 15; AC-05/06.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 074 | Chọn source/entry/protective | Dùng toàn H1 nếu nested hợp lệ; H4-only dùng phần proximal làm entry và toàn H4 bảo vệ. | Ba role rõ ràng; nhiều role cùng zone không tạo zone mới. |
| 075 | Tính entry sub-zone và rounding | Tính tỷ lệ H4 rồi làm biên trong vào trong; Entry tại proximal. | Sub-zone 0 bị loại, không tự nới rộng; H1 không bị thu hẹp thêm. |
| 076 | Tính SL | Tính buffer từ protective formation ATR/tick rồi làm tròn ra ngoài BUY/SELL. | SL dùng distal đầy đủ; không dùng distal của entry sub-zone. |
| 077 | Lọc opposing zones | Tập cản gồm H4 fresh và D1 hoạt động đã xác nhận tại cutoff. | Không dùng vùng chưa xác nhận/broken/expired; D1 TESTED vẫn có thể là cản. |
| 078 | Phát hiện Entry trong cản | Kiểm tra Entry với mọi cản hợp lệ theo epsilon của cản. | ENTRY_INSIDE_OPPOSING_ZONE chặn READY kể cả proximal nằm sau Entry. |
| 079 | Chọn TP | Chọn proximal phía trước gần nhất, tie-break D1 rồi ID; rounding bảo thủ. | Không có cản trả None/reason, không tạo TP số R cố định. |
| 080 | Tính risk/RR sau rounding | Kiểm tra geometry, min risk rồi RR Decimal chưa format. | BUY/SELL đúng chiều; RR 1.9996 không vượt min_rr 2.0. |
| 081 | Tính cản D1 gần nhất | Tính khoảng cách từ Entry theo current ATR H4, nhãn near theo registry. | Cản D1 vẫn hiển thị dù TP chọn H4; near không tự thêm penalty. |
| 082 | Tính đủ năm thành phần điểm | Ghép formation, freshness, location và target space; grade theo registry. | Tổng /100, D1 /50 riêng; điểm 0 khác None; không bonus timeframe hoặc retest. |
| 083 | Kiểm tra cập nhật điểm động | Đổi position hoặc tập cản, tính lại plan/score khi input phụ thuộc đổi. | 94→79 đúng ví dụ 02; formation giữ nguyên, READY không suy từ grade đơn độc. |

### Nhóm 8. Entry latch, M15 và state machine

**File/phạm vi:** `core/supply_demand_confirmation.py`, `core/supply_demand_setup_state.py`; tests confirmation/state.

**Nguồn:** `02` mục 12, 14–15; AC-07/08/09.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 084 | Tạo entry-touch latch | Dùng tick đúng phía giá hoặc M15 đóng giao entry zone, gắn setup/first retest. | Source touch không tự bật entry latch; lần đầu được giữ nguyên. |
| 085 | Gán M15 candle ref | Tick dùng khoảng nửa mở; fallback giữ ref chính nến giao vùng. | Tick đúng biên thuộc nến mới, close fallback không gán nhầm nến tiếp. |
| 086 | Tính cửa sổ M15 | Đếm từ nến chứa first entry touch, theo lịch nguồn và max bars. | Không reset khi giá rời/vào lại hoặc đổi mode; retest source vẫn riêng. |
| 087 | Xác nhận rejection | Thực thi body/wick/ATR/proximal và wick thực sự giao entry. | BUY/SELL đối xứng, doji và wick không chạm bị loại. |
| 088 | Xác nhận engulfing | Thực thi bao thân trước và close vượt high/low theo epsilon. | Không lấy engulfing chưa đóng; có ví dụ đạt và thiếu từng điều kiện. |
| 089 | Xác nhận micro BOS | Lấy swing M15 hợp lệ trong cửa sổ trước touch và close phá đúng hướng. | Không có swing thì không xác nhận; pivot tương lai không lọt vào lookback. |
| 090 | Chọn mode theo grade | A nested TOUCH; B/H4-only M15; grade C theo policy 02. | A→B→A không đổi setup ID, latch hoặc mốc cửa sổ. |
| 091 | Xử lý timeout và mode change | Xét nến số 8 trước timeout; TOUCH không tự timeout; đổi sang M15 muộn xét cửa sổ gốc. | B timeout→A vẫn EXPIRED; lưu input MODE_CHANGE cần replay. |
| 092 | Áp invalidation/expiration | Ưu tiên protective/parent broken, quá tuổi, retest end và timeout theo rules. | Terminal không hồi sinh; latch cũ không mở cơ hội mới. |
| 093 | Tính các gate READY | Tạo kết quả cho từng predicate gồm latch, D1, grade, M15, RR, safety và vùng active. | Mỗi gate có trường hợp âm/dương; không biến lỗi store thành reason nghiệp vụ. |
| 094 | Xếp hạng candidate cùng hướng | Áp thứ tự grade/score/RR/distance/newness/ID đúng 02. | Tie-break xác định; UI sorting không thay thứ tự chọn nghiệp vụ. |
| 095 | Phát hiện direction conflict | Xét hai phía theo điều kiện riêng, loại candidate Entry trong cản. | D1 bias không tự xóa conflict; cả hai WATCHING khi conflict tồn tại. |
| 096 | Chọn tối đa một READY/symbol | Kết hợp rank, conflict, gate và ưu tiên terminal để sinh state/transitions. | READY mất điều kiện về WATCHING; quay lại cùng retest giữ cùng key. |

### Nhóm 9. Pipeline phân tích thuần

**File/phạm vi:** `core/supply_demand_analysis.py`; tests pipeline/prefix và fake port.

**Nguồn:** `03` mục 7; AC-01–09.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 097 | Ghép full analysis | Điều phối validation→indicators→detector→lifecycle→context→plan→quality→state. | Một snapshot giả lập tạo đầy đủ result, không import UI/MT5/service vào core. |
| 098 | Gom sự kiện cùng close time | Cập nhật đầy đủ các timeframe cùng cutoff trước chọn state. | Kết quả không phụ thuộc thứ tự fetch D1/H4/H1/M15. |
| 099 | Tạo tick-only update | Không có nến mới thì chỉ cập nhật các phụ thuộc quote theo cadence 02. | Tick không tạo pattern/swing/broken/M15 confirmation. |
| 100 | Tạo cập nhật khi có nến mới | Recompute đúng các phần phụ thuộc timeframe và data revision thay đổi. | Target/score/state không bị giữ cũ khi vùng cản hoặc nến bị sửa. |
| 101 | Ghép safety toàn snapshot | Tổng hợp thiếu nến/quote/spread/ATR/gap/stale/biên chưa rõ. | Symbol không an toàn tối đa WATCHING nếu chưa terminal; reasons đầy đủ. |
| 102 | Kiểm tra tính xác định pipeline | So full/incremental tại cùng input, chạy nhiều lần và từng tiền tố thời gian. | Zone/ID/plan/state/reasons khớp; mismatch được sửa trước khi dùng store. |

### Nhóm 10. SQLite, evidence và inbox

**File/phạm vi:** `services/supply_demand_state_store.py`, `services/supply_demand_alert_service.py`; tests store/alerts với DB tạm.

**Nguồn:** `03` mục 9; `02` mục 18.5; AC-10/12.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 103 | Tạo đường dữ liệu SD | Dùng app_data_dir/supply_demand cho DB, backup và quarantine. | Không viết dữ liệu cá nhân vào source tree hoặc database chiến lược khác. |
| 104 | Khởi tạo metadata/scope schema | Tạo schema version và scope table, foreign keys, writer ownership. | Schema không hỗ trợ trả lỗi typed; không coi DB lạ là rỗng. |
| 105 | Tạo snapshot refs schema | Lưu refs và cursor/checksum đúng contract. | Không lưu state/plan làm nguồn sự thật cho restore. |
| 106 | Tạo revision inputs schema | Lưu nội dung config/session/boundary và candle slices cần replay. | Ref truy được nội dung, không chỉ hash của input đã bị mất. |
| 107 | Tạo evidence schema | Lưu event/sequence/type, quote/time/ref/revisions với unique key. | Tick cùng timestamp giữ thứ tự; insert lại không nhân bản evidence. |
| 108 | Tạo ledger và receipt schema | Lưu alert key/payload bất biến và trạng thái đã đọc/trình bày riêng. | Đọc/đóng thông báo không xóa key; cùng key không ghi đè thời gian/plan ban đầu. |
| 109 | Thực thi commit_cycle atomic | Ghi revisions/evidence/refs/alerts trong một transaction. | Lỗi bất kỳ phần nào rollback tất cả; RAM chỉ nhận cycle sau commit. |
| 110 | Thực thi truy vấn inbox | Đọc có phân trang/filter/cursor và upsert receipt. | Mở inbox không cần MT5/Start; đọc lại không tạo event. |
| 111 | Tạo alert event từ transition | Tính key chuẩn, payload LIVE/RESTORE_CURRENT, insert unique sau kiểm tra scope. | READY lặp hoặc WATCHING→READY cùng key không phát lại. |
| 112 | Xử lý DB/snapshot lỗi | Phân biệt snapshot hỏng, ledger hỏng, schema/scope mismatch và IO_ERROR. | Giữ ledger tốt; ledger không tin cậy thì dừng phát mới, không tự tạo ledger trống. |
| 113 | Backup và bảo toàn lịch sử | Dùng SQLite backup API, cách ly bản hỏng; không TTL xóa ledger/evidence cần terminal. | Backup phục hồi được trong test DB tạm; không copy DB đang ghi hoặc xóa dữ liệu để tự chữa. |
| 114 | Kiểm tra fault tại commit | Giả lập lỗi trước/trong/sau commit và trước signal UI. | Không event nửa vời, không popup trước commit, crash sau commit đọc lại đúng một bản ghi. |

### Nhóm 11. Khôi phục và service điều phối

**File/phạm vi:** `services/supply_demand_service.py`, adapter/history request, store; `tests/test_supply_demand_restore.py`.

**Nguồn:** `02` mục 18.4–18.5; `03` mục 10; AC-11/12.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 115 | Load restore bundle | Đọc settings/scope/refs/evidence/revision inputs/ledger và validate. | Giữ RESTORING/FULL_ANALYSIS_PENDING; chưa công bố READY hiện tại. |
| 116 | Tính mốc replay mở rộng | Tìm mốc sớm nhất từ source confirmation/touch/offline và nhu cầu grade/mode. | M15 có thể vượt 253; các timeframe khác được mở rộng đủ input lịch sử. |
| 117 | Tải bổ sung lịch sử | Adapter lấy đủ dữ liệu cho replay/warmup và đối chiếu revisions. | Thiếu nguồn báo phần thiếu; không âm thầm rút cửa sổ hoặc đoán state. |
| 118 | Replay theo event time | Dùng nến/quote/config tại từng sự kiện, không dùng quote cuối cho quá khứ. | Kết quả prefix không nhìn trước; config cũ cần terminal còn truy được. |
| 119 | Tái dựng latch/mode/terminal | Ghép entity bằng ID, replay touch, M15 và thay đổi mode. | Timeout/EXPIRED/INVALIDATED không hồi sinh sau restart/config đổi. |
| 120 | Xử lý ref không tái dựng được | Phân biệt thiếu input cần bổ sung với zone thực sự không thể dựng. | Pending hoặc ZONE_NOT_RECONSTRUCTED đúng rules; không tạo vùng giá 0. |
| 121 | Đánh giá hiện tại sau restore | Thoát replay, full analysis và quote an toàn rồi xét event hiện tại riêng. | READY chưa key ghi RESTORE_CURRENT; setup chỉ đạt trong quá khứ không phát bù. |
| 122 | Hoàn thiện poll service | Đọc→analyze→validate revision→commit→publish theo symbol. | Lỗi một symbol không làm dữ liệu cũ của nó trông như mới; symbol khác còn kết quả riêng. |
| 123 | Khôi phục sau lỗi lưu/nguồn | Giữ last-good có nhãn cũ; khi phục hồi buộc full analysis trước phát mới. | Không publish kết quả dở; lỗi store không bị che bằng reason giao dịch. |
| 124 | So chạy liên tục với restart | Chạy cùng timeline fixture liên tục và ngắt ở các mốc touch/mode/commit. | ID/latch/state/ledger tương đương; kiểm tra cả touch cũ hơn cửa sổ mặc định. |

### Nhóm 12. Worker, controller và vòng đời ứng dụng

**File/phạm vi:** `workers/supply_demand_worker.py`, `controllers/supply_demand_controller.py`, `controllers/app_controller.py`; tests controller/DI.

**Nguồn:** `03` mục 8; `04` mục 3; AC-13.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 125 | Tạo worker QObject | Đưa fetch/core/store vào worker thread với signal progress/result/error/finished. | Widget không bị gọi trực tiếp từ worker; DB writer ở đúng thread. |
| 126 | Tạo controller và IDLE | Sở hữu timer/worker/run intent; đăng ký service SD qua DI lazy. | Ứng dụng chưa Start không tự quét; dùng cùng instance MT5 của AppController. |
| 127 | Thực thi Start | Restore/full rồi poll khi điều kiện cấu hình phù hợp. | Start lặp không tạo job thứ hai; DRAFT chỉ chạy qua harness tách biệt. |
| 128 | Thực thi single-flight | Gộp tối đa một pending request và ưu tiên full hơn poll. | Refresh liên tiếp không hàng đợi vô hạn; không mất pending full. |
| 129 | Thực thi Refresh | IDLE chạy một full rồi về IDLE; ACTIVE yêu cầu full và giữ run intent. | Cùng đường commit/alert, không tạo kết quả bằng widget. |
| 130 | Thực thi Stop | Dừng timer, set cancellation, tăng generation; hiển thị STOPPING nếu I/O còn chạy. | UI phản hồi; không terminate thread hoặc disconnect MT5 để ép hủy. |
| 131 | Bảo vệ generation/commit | Dùng coordinator lock cho kiểm tra generation và commit; loại stale result. | Đổi config/Stop đúng lúc commit không phát sự kiện của generation bị hủy. |
| 132 | Xử lý đổi watchlist/config/scope | Validate, tăng revision, cancel tác vụ cũ và tái dựng đúng run intent. | Watchlist rỗng không quét; giữ ledger/evidence và dữ liệu form khi lỗi save. |
| 133 | Xử lý session đóng/mở lại | Không poll quote để đổi state khi đóng; mở lại catch-up trước READY. | Không tăng tuổi ngoài phiên; không giữ READY cũ như hiện tại. |
| 134 | Ghép shutdown | Dừng SD, chờ quyền điều khiển trả về, đóng store/worker rồi AppController disconnect nguồn. | Không wait dài trên UI handler; đổi màn hình không shutdown service SD. |
| 135 | Kiểm tra race và hồi quy DI | Giả lập nguồn chậm, scope switch, cancel giữa phase, shutdown và callback trễ. | Không deadlock/job chồng/commit cũ; đường MT5 dùng chung không đổi hành vi ngoài SD. |

### Nhóm 13. Presentation và khung UI thích ứng

**File/phạm vi:** `ui/supply_demand_presentation.py`, `ui/screens/supply_demand_screen.py`, components SD, UI harness; style chung theo `docs/ui/style-guide.md`.

**Nguồn:** `04` mục 2–5, 10–11; `01` SD-NFR-11; AC-14/16/17.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 136 | Tạo adapter hiển thị | Chuyển result thành row/detail/chart payload và nhãn reason tiếng Việt. | None hiển thị thiếu dữ liệu, 0 giữ 0; không tính lại grade/RR/state. |
| 137 | Tạo khung SD bằng dữ liệu mẫu | Tạo controls/status, watchlist, vùng bảng/chart/detail và inbox trong harness. | Mở UI không cần MT5 hoặc rules APPROVED; dữ liệu demo không vào DB cá nhân. |
| 138 | Thiết kế bố cục tối thiểu ngay từ đầu | Dựa diện tích client sau shell/taskbar, dùng tab/thu gọn/scroll thay min-size cố định. | Dùng được 1366×768/100% và 1920×1080/150%; không chờ cuối mới thu nhỏ layout. |
| 139 | Áp theme/control chung | Dùng tokens, semantic palette, icons và renderer chung. | Dark/light cùng cấu trúc; không setStyleSheet/màu cục bộ hoặc thu font để nhét nội dung. |
| 140 | Nối controls với controller | Start/Stop/Refresh/Cấu hình theo availability và run intent. | Controls/status luôn thấy; lỗi dài không đẩy nút ngoài viewport. |
| 141 | Tạo watchlist view | Hiển thị symbol, trạng thái nguồn, update time và chọn mã xem. | Chọn mã không đổi danh sách theo dõi; thu panel còn lối mở. |
| 142 | Tạo editor watchlist | Tìm/chọn nhiều mã, Áp dụng/Hủy và lỗi mapping/config. | Dialog vừa vùng khả dụng, footer dùng được; danh sách rỗng không thành bật tất cả. |
| 143 | Tạo bảng setup và filter | Hiển thị cột theo 04, lọc symbol/hướng/state, chọn bằng ID. | Bảng cuộn đủ giá dài, không nhân dòng khi mode đổi; UI sort không đổi core ranking. |
| 144 | Tạo status/last-good/empty/error | Hiển thị ba trục operational/data/setup và thời điểm từng symbol. | Dữ liệu cũ không mang nhãn READY hiện tại; D1 pending khác unaligned. |
| 145 | Tạo cấu hình theo nhóm | Theo dõi, Thông báo, Nâng cao; render tên/đơn vị/validation từ registry. | Không sửa ID/state/rules approval; form cuộn và Áp dụng/Hủy không ngoài màn hình. |
| 146 | Giữ ngữ cảnh khi update | Upsert theo ID/revision, giữ selection/filter và form chưa lưu. | Poll/scope change không dùng response trễ của symbol trước hoặc mất dữ liệu đang nhập. |

### Nhóm 14. Chart, detail và thông báo

**File/phạm vi:** `ui/components/supply_demand_chart_view.py`, `ui/supply_demand_presentation.py`, screen/components và asset SD trong vị trí chart hiện có.

**Nguồn:** `04` mục 6–11; AC-10/14/16/17.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 147 | Tạo bridge chart SD | Nhận payload versioned riêng và resize viewport; dùng hạ tầng chart trung tính. | Không nhận order/SMC payload; WebEngine lỗi vẫn có bảng/detail. |
| 148 | Vẽ nến và đổi timeframe | Vẽ candles theo payload D1/H4/H1/M15 và giữ as-of/watermarks. | Chart không tính pattern; trục/labels/vùng bấm khớp ở scale 100%/150%. |
| 149 | Vẽ overlay vùng | Vẽ supply/demand, proximal/distal, roles và FRESH/TESTED/RETESTING/BROKEN/EXPIRED. | Một zone nhiều role vẫn một entity; nhãn/nét không chỉ dựa màu. |
| 150 | Vẽ kế hoạch và cản D1 | Vẽ Entry/SL/TP, selected target, nearest D1 obstacle và chú giải. | Giá trùng core; vùng D1 không giả làm entry; controls chart không bị cắt. |
| 151 | Tạo detail điểm và kế hoạch | Hiển thị breakdown /100, D1 /50, Entry/SL/TP/RR và None/reason. | Không % xác suất; RR sát ngưỡng có thông tin đủ chính xác để giải thích gate. |
| 152 | Tạo detail latch/M15/context | Hiển thị first touch, mode, window, evidence, D1 alignment/near và reasons. | Source touch khác entry touch; near đo từ Entry; terminal không bị UI hồi sinh. |
| 153 | Tạo inbox phân trang | Hiển thị payload sự kiện bất biến, unread count, filters và đọc/đánh dấu đã đọc. | Chưa Start vẫn xem được; kế hoạch hiện tại không ghi đè lịch sử. |
| 154 | Tạo thao tác mở setup từ inbox | Điều hướng theo ID/scope tới kết quả hiện tại, báo rõ nếu chưa có/khác scope. | Không dựng READY hiện tại từ event lịch sử hoặc tự Start vì mở inbox. |
| 155 | Tạo popup sự kiện mới | Sau commit mới trình bày, gộp batch theo 04, không focus steal. | Popup trong vùng khả dụng, không che controls chính; reload không phát backlog. |
| 156 | Thêm âm thanh tùy chọn | Mặc định tắt; chỉ áp cho event mới cùng chính sách receipt. | Tắt sound/popup không mất inbox; không tự bật Telegram/email. |
| 157 | Hoàn thiện bàn phím và dialog | Tab order, focus, Escape/Enter, tooltip và lỗi validation theo 04. | Nút đóng/Áp dụng/Hủy luôn dùng được bằng chuột/bàn phím trên hai cấu hình. |
| 158 | Hoàn thiện resize/scale/geometry | Đổi layout theo diện tích, clamp geometry cũ, chart cập nhật kích thước. | Giữ selection/form/worker; không nhân scale hai lần, sai hit target hoặc phát lại alert. |

### Nhóm 15. Tích hợp, kiểm tra trực tiếp và bàn giao

**File/phạm vi:** `controllers/app_controller.py`, `ui/main_window.py`, `ui/navigation.py`, dependency/packaging khi cần; tests SD; `docs/SD/05-acceptance-criteria.md`.

**Nguồn:** AC-01–17; SD-UI-01–19; `03` mục 13, 15.

| Bước | Công việc nhỏ | Thực hiện cụ thể | Điều kiện hoàn thành / kiểm tra |
|---|---|---|---|
| 159 | Đăng ký route SD có khóa rules | Thêm route/screen factory trong shell, wiring DI và shutdown. | DRAFT hiển thị trạng thái chưa đủ đặc tả; không bật phân tích runtime hoặc gắn order callback. |
| 160 | Kiểm tra dependency/packaging cần thiết | Kiểm tra IANA data, WebEngine và asset SD trong môi trường cá nhân/đóng gói đang dùng. | Bổ sung dependency chỉ nếu thiếu; chart unavailable có fallback rõ ràng. |
| 161 | Chạy các kiểm tra core SD liên quan | Chạy parameter/identity/indicator/detector/lifecycle/context/plan/confirmation/state/pipeline. | AC-01–09 có kết quả thực tế; sửa lỗi rồi chỉ chạy lại phần ảnh hưởng và phụ thuộc cần thiết. |
| 162 | Chạy kiểm tra service/restore/race | Chạy fake port, store fault, alerts, replay, worker/controller và read-only spy. | AC-10–13/15 đúng; không ảnh hưởng DB hoặc cảnh báo cá nhân. |
| 163 | Kiểm tra UI 1366×768 ở 100% | Maximize trong work area với taskbar/shell, dữ liệu dài, đầy đủ dialog, dark/light. | Ghi AC-16 cho cấu hình này; controls/giá/form/popup đều truy cập đủ và phản hồi khi worker chạy. |
| 164 | Kiểm tra UI Full HD ở 150% | Thực hiện riêng 1920×1080/150%, không thay bằng viewport Full HD 100%. | Ghi AC-16 riêng; bố cục vừa khoảng logic 1280×720 trừ taskbar/shell, không giảm scale để qua kiểm tra. |
| 165 | Kiểm tra đổi scale/geometry | Đổi giữa hai cấu hình, resize và mở lại cửa sổ khi form đang có dữ liệu. | AC-17 đạt hoặc ghi lỗi cụ thể; không mất selection/form, không popup lặp. |
| 166 | Kiểm tra đủ hành vi UI/alert | Đi qua SD-UI-01–19 bằng dữ liệu mẫu và store tạm, gồm mất nguồn/chart/store. | Ghi thực tế, không mặc định đạt các mục chưa chạy; sửa lỗi nội dung/thao tác trước dùng UI liên quan. |
| 167 | Kiểm tra hồi quy điểm tích hợp | Chạy test hiện có liên quan DI/MT5/shutdown/navigation/style của các file đã sửa. | Chức năng cũ không đổi do SD; không mở rộng kiểm tra vô hạn khi không có thay đổi hoặc lỗi mới. |
| 168 | Tổng hợp phần cần PO/nguồn chốt | Ghi mọi điểm nghiệp vụ còn thiếu và tình trạng boundary broker, kèm bằng chứng code/test/UI hiện có. | Hồ sơ cụ thể để chủ ứng dụng chốt; không yêu cầu backtest hoặc lịch sử test sẵn. |
| 169 | Ghi nhận chốt rules trước runtime | Chủ ứng dụng chốt APPROVED khi các quy tắc sử dụng đã rõ; coder chỉ cập nhật descriptor/tài liệu theo quyết định đó. | Không tự duyệt rules. Nếu chưa chốt, để bước này CHỜ PO và runtime khóa; những phần độc lập trước đó vẫn hoàn thành. |
| 170 | Chạy thử nguồn thật chỉ đọc | Sau khi rules được chốt và có nguồn, Start/Stop/Refresh với watchlist cá nhân, kiểm tra boundary và lỗi nguồn. | Không order/symbol_select; chưa rõ boundary thì symbol bị chặn đúng, không nhận đã xác minh. |
| 171 | Chạy restart cá nhân và kiểm tra tải thực tế | Theo dõi ít mã, đổi màn hình, đóng/mở ứng dụng và tăng watchlist theo nhu cầu. | UI không treo/job chồng; inbox không lặp. Không đòi READY thật xuất hiện, benchmark p95 hay số lượt cố định. |
| 172 | Cập nhật kết quả bàn giao | Ghi AC-01–17: Đạt/Chưa đạt/Chưa kiểm tra, lệnh kiểm tra, file sửa và giới hạn còn lại. | Chủ ứng dụng biết phần dùng được, phần bị chặn và cách tái kiểm tra; không đánh dấu hoàn thành nếu còn lỗi bắt buộc. |

## 4. Quy tắc ghi nhận kết quả

Sau mỗi phần triển khai, ghi ngắn gọn ngay cạnh bước hoặc trong ghi chú tiến độ
bên dưới:

- Bước đã làm và file cụ thể thay đổi.
- Lệnh kiểm tra hoặc thao tác UI đã chạy, kết quả thực tế.
- Nếu chờ: thiếu đầu vào nào, ảnh hưởng bước nào và phần độc lập đã tiếp tục.
- Nếu phát hiện khác đặc tả: nguồn mâu thuẫn và câu hỏi cần chốt.
- Câu thông báo mốc review sau mỗi bước và trạng thái R1–R6 theo mục 2.1;
  hoàn thành code một bước không tự đồng nghĩa mốc đã được Tech Lead thông qua.

Bảng `05` ghi kết quả theo AC-01–17; kiểm tra UI chi tiết theo SD-UI-01–19 của
`04`. Không đánh dấu cả nhóm hoàn thành khi mới chạy một vài trường hợp.
Thay đổi code sau khi test chỉ cần chạy lại các kiểm tra liên quan; không
lặp benchmark hoặc toàn bộ suite vô hạn khi không có thay đổi/rủi ro mới.

Việc hoàn tất kế hoạch được xác nhận bằng code đã thực hiện và các kiểm tra
phù hợp, không bởi số lượng file/test/commit. Nếu còn bước chờ rules, dữ liệu
broker hoặc cấu hình màn hình chưa kiểm tra, báo rõ giới hạn và giữ trạng
thái tương ứng; không tuyên bố SD đã dùng được đầy đủ.

### Ghi chú tiến độ

Chưa có bước nào được xác nhận đã thực hiện trong kế hoạch này.

Ngày 08/09/2026 — làm trước theo yêu cầu chủ ứng dụng: thêm menu Cung–cầu
trong `ui/navigation.py`, đăng ký route ở `ui/main_window.py` và tạo trang
thông báo “đang được xây dựng” tại `ui/screens/supply_demand_screen.py`.
Trang chưa khởi tạo core/service/worker SD; không đánh dấu bước 159 hoàn tất.
Kiểm tra click/route bằng app giả lập không gọi MT5/Scanner; style/density và
10 test UI liên quan đạt, 24 kiểm tra layout placeholder dark/light ở scale
100%/150% đạt. Full suite: 3695 passed, 1 failed, 8 skipped, 16 xfailed;
test FRED `test_get_latest_rates_bad_key_falls_back` kỳ vọng 3.75 nhưng nhận
3.63, chạy riêng vẫn lỗi; không thuộc thay đổi menu SD.

Phần menu làm trước chưa tới mốc review; mốc chính tiếp theo vẫn là R1 sau
bước 023, khi contract/định danh và các bước liên quan đã hoàn thành.
