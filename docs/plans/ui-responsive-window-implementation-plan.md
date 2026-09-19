# Kế hoạch triển khai cửa sổ và responsive UI

**Ngày chốt:** 2026-09-18
**Nguồn contract:** [UI Screen Design](../ui/screen_design.md#contract-kích-thước-cửa-sổ-và-responsive-2026-09-18) và [UI Style Guide](../ui/style-guide.md).
**Mục tiêu:** UI desktop hiển thị đúng theo `QScreen.availableGeometry()` (logical pixel) ở các Windows scale phổ biến, đặc biệt Full HD/150% (`~1280×720` logical), mà không làm font/chart bị scale thêm hoặc làm thay đổi logic phân tích/giao dịch.

## 1. Quyết định và phạm vi

- Lần chạy đầu mở cửa sổ chính ở trạng thái **maximized desktop window**; không borderless fullscreen và không `setFixedSize()`.
- Sau lần đầu, khôi phục geometry/state người dùng đã lưu nếu còn nhìn thấy được trên màn hình hiện tại; nếu không hợp lệ hoặc nằm ngoài màn hình, quay về policy lần chạy đầu.
- Geometry luôn tính theo `QScreen.availableGeometry()`; cấm dùng độ phân giải vật lý hoặc `devicePixelRatio()` để nhân/chia kích thước.
- Breakpoint cần hỗ trợ: `≥1520×850`, rộng `1150–1519`, rộng `900–1149`, và compact khi rộng `<900` hoặc cao `<560` logical pixel.
- Các vùng cần nghiệm thu: app shell, Dashboard, Scanner, Scanner Detail, Journal, Journal Detail, Orders và Settings; light/dark theme.

Ngoài phạm vi: thuật toán SMC, selection/gate/plan/risk/execution, dữ liệu MT5, cache, persistence, nội dung chart/zoom/mật độ nến, màu/theme token, policy giao dịch, thay đổi golden/skip/xfail. Dialog chỉ được sửa nếu một lỗi overflow tái lập được tại viewport nghiệm thu; không nhân tiện chuẩn hoá dialog.

## 2. Cách làm và điểm dừng

Coder thực hiện đúng thứ tự R0 → R4. Mỗi lô phải có caller/source map, diff boundary, kiểm chứng, đối chiếu baseline và `git diff --check`; **dừng chờ Tech Lead review** trước khi sang lô tiếp theo. Không commit/reset/xoá, không cập nhật lock/golden/skip/xfail chỉ để xanh test. Nếu contract xung đột layout hiện hữu, ghi blocker và đề xuất phương án; không tự đặt breakpoint hoặc kích thước thứ ba ngoài kế hoạch.

### R0 — Snapshot, inventory và acceptance matrix (discovery-only)

**Mục đích:** chốt baseline và các owner thực tế trước khi thay đổi UI.

1. Ghi snapshot Git và `git status --short`; phân biệt worktree UI Chart đang có với thay đổi của lô này. Không giả định HEAD là baseline của worktree.
2. Lập caller map từ `main.py`/`controllers/app_controller.py` đến `MainWindow`: hiện có `main.py:51 showMaximized()`, `ui/main_window.py:69 resize(1280,800)` và `:70 setMinimumSize(1024,700)`; tìm toàn bộ nơi gọi `show()`, `showMaximized()`, `resize`, `setMinimumSize`, `setFixedSize`, `setGeometry`, `QSettings`, `QSplitter` có ảnh hưởng app shell/screen.
3. Rà từng screen thuộc phạm vi tại bốn viewport contract, hai theme; ghi rõ overflow, clipping, widget overlap, sidebar/table/chart không còn đọc được và dialog nào thực sự bị block. Không sửa code trong R0.
4. Chốt ma trận test dùng **logical viewport**: `1280×720`, `1366×768`, `1920×1080`, compact `900×560`; chỉ bổ sung viewport khi có thiết bị/môi trường cụ thể đòi hỏi.

**Điều kiện hoàn thành:** inventory có file/function/line và screenshot hoặc audit tái lập được; baseline tests/audit ghi rõ kết quả; không có diff code.
**Điểm dừng:** Tech Lead chọn thứ tự screen/blocker trước R1.

### R1 — Owner geometry và vòng đời cửa sổ chính

**Mục đích:** tạo một owner duy nhất cho startup, restore và persist geometry; không thay layout screen.

**Contract kỹ thuật:**

1. `MainWindow` hoặc một helper UI chuyên trách là owner duy nhất của policy geometry. `main.py` không được vừa gọi `showMaximized()` vừa để `MainWindow` áp một policy khác.
2. Dùng `QSettings` dành riêng cho **UI window state** (không trộn vào app/business settings, không ghi credential hay config trading). Lưu bằng `saveGeometry()`/`saveState()` hoặc format Qt tương đương; restore phải chịu được missing/corrupt/obsolete value.
3. Lần đầu hoặc state invalid: maximize. Khi người dùng unmaximize và đóng app, lưu normal geometry/state. Khi restore, geometry phải intersect vùng `availableGeometry()` hiện tại với diện tích nhìn thấy hợp lý; geometry off-screen, kích thước vô lý hoặc màn hình đã mất phải bị bỏ qua và quay về maximize.
4. Nếu một caller chủ động cần cửa sổ normal (test/dev), dùng policy tường minh: `min(1440, 0.92×availableWidth)` × `min(900, 0.90×availableHeight)`. Không dùng giá trị này để ghi đè state người dùng hợp lệ.
5. Mức minimum app shell không vượt quá viewport Full HD/150% sau taskbar. Mức kỹ thuật `800×500`; compact layout sẽ xử lý bên dưới full-desktop threshold. Không sửa fixed/minimum của dialog trong R1.

**Kiểm chứng bắt buộc:** first launch, saved normal, saved maximized, corrupt/missing state, geometry ngoài màn hình, đổi screen/available geometry, close→new instance restore; các test dùng QSettings tạm và fake/injected screen geometry, không ghi settings thật của người dùng. Test `main.py` chứng minh có đúng một owner startup policy.
**Điểm dừng:** Tech Lead review behavior startup/restore ở Windows scale 100/125/150% trước R2.

### R2 — App shell, Scanner và Scanner Detail theo breakpoint

**Mục đích:** hoàn thiện đường dùng thường xuyên nhất ở mọi viewport contract, ưu tiên chart và Entry/SL/TP.

1. App shell: rail điều hướng app-wide giữ cố định `48px` theo contract hiện có, không biến nó thành sidebar rộng `280–320px`. Ở compact chỉ chuyển navigation/list sang drawer/tab khi R0 chứng minh cần thiết, không để content stack bị ép hẹp.
2. Scanner: bảng dùng `QTableView`/scroll hợp lệ; header/filter/action wrap hoặc menu khi thiếu ngang; không bóp font/cột để vừa màn hình.
3. Scanner Detail: chart lấy phần diện tích dư; panel dài cuộn dọc hoặc tab; H1 tiếp tục chỉ candle, giá, Entry/SL/TP; không đưa lại SMC overlay vào H1. Ghi chú freshness vẫn nằm trên “Quét lúc …” theo quyết định UI Chart hiện hành.
4. Dùng `QSplitter`, layout và `SizePolicy`; không định vị bằng `move()/setGeometry()`, không tự zoom chart/nến khi resize. Chỉ panel **danh sách kết quả Scanner** (nếu nằm cạnh Detail) có minimum `280–320px` khi viewport rộng ≥1150; rail điều hướng vẫn `48px`. Breakpoint nhỏ hơn dùng layout compact đã chốt.

**Kiểm chứng bắt buộc:** mỗi viewport × light/dark có Scanner và Scanner Detail có dữ liệu; kiểm sidebar/table/chart/detail, no clipping/overlap, scroll/drawer hoạt động và Entry/SL/TP đọc được. Refresh chart 30 giây, chart density `200/1.5`, SMC H1 policy và row snapshot không đổi phải có regression test.
**Điểm dừng:** Tech Lead xem capture viewport 1280×720 và compact trước R3.

### R3 — Dashboard, Journal, Orders, Settings và screen detail còn lại

**Mục đích:** áp dụng cùng contract layout cho toàn bộ app, không tái thiết kế chức năng.

1. Mỗi screen dùng layout co giãn; xác định một vùng nội dung chính, panel phụ, điểm scroll và behavior compact. Không thay data/caller/logic của screen.
2. Settings giữ splitter hiện hữu khi đủ rộng, xếp dọc hoặc dùng tab/drawer ở compact; không làm mất khả năng truy cập cài đặt.
3. Journal/Orders giữ bảng đọc được bằng scroll; Dashboard ưu tiên status/action chính, không cắt card hoặc tạo grid chồng lấn.
4. Dialog chỉ xử lý các case R0 đã chứng minh không thể hoàn thành tác vụ ở viewport hỗ trợ; nêu riêng từng dialog và lý do.

**Kiểm chứng bắt buộc:** từng screen qua 4 viewport × 2 theme; chuyển route, resize, maximize/unmaximize và đổi theme không reset screen state, không crash, không overlap.
**Điểm dừng:** Tech Lead review inventory toàn app và các exception dialog trước R4.

### R4 — Regression, visual QA và handoff

**Mục đích:** chứng minh toàn bộ contract thay vì chỉ test helper layout.

1. Chạy UI style/density/layout audit theo `docs/ui/style-guide.md`; artifacts/capture tạm thời nằm ngoài `reports/` trừ khi style guide yêu cầu artifact tracked và Tech Lead chấp thuận cập nhật. Không tự sửa style/density lock.
2. Chạy smoke khởi động `MainWindow`, route/screen matrix, Scanner/Detail chart smoke (light/dark), targeted UI tests và full suite. Tests dùng settings/temp storage cách ly, không sửa setting runtime, không gọi MT5/trade.
3. Đo baseline worktree đúng snapshot R0 và đối chiếu từng failure mới theo tên, file và nguyên nhân; không gắn nhãn failure nền chỉ vì trùng nhóm.
4. Cập nhật `docs/ui/screen_design.md` nếu implementation buộc phải làm rõ contract; cập nhật `docs/ui/style-guide.md` chỉ khi ma trận audit thực tế thay đổi. Ghi kết quả và decision vào progress document được Tech Lead chỉ định, không tạo báo cáo phụ.

**Điều kiện REVIEW PASS:** startup/restore có một owner; Full HD/150% và ba viewport contract không clip/overlap; compact giữ đường dùng chính; dark/light đạt; không thay UI thành scale cứng; không có regression thật; `git diff --check` pass; mọi artifact nằm đúng phạm vi.
**Điểm dừng:** Coder bàn giao, Tech Lead review độc lập; không commit/push và không tự bắt đầu lô UI khác.

## 3. Tiêu chí báo cáo của Coder cho từng lô

Mỗi báo cáo phải nêu: snapshot/baseline; file/function/caller bị chạm; contract đã thực hiện; viewport/theme đã quan sát; test/audit command và kết quả; failure mới (nếu có) với tái lập; diff boundary; `git diff --check`; work còn blocked/deferred. “Test xanh” hoặc “smoke mở được” không thay thế kiểm tra screenshot/viewport và đường caller thật.

## 5. Bàn giao R1 — owner geometry và vòng đời cửa sổ chính (2026-09-18)

**Trạng thái:** R1 IMPLEMENTED — WAITING_REVIEW R2.

### 5.1 Caller/source map trước → sau

| Vị trí | Trước | Sau |
|---|---|---|
| `main.py:51` | `window.showMaximized()` — policy startup tự phát | `main.py:53` `window.apply_startup_policy()` — uỷ quyền cho owner |
| `ui/main_window.py:69` | `self.resize(1280, 800)` (policy chết, bị `showMaximized()` ghi đè) | đã gỡ |
| `ui/main_window.py:70` | `self.setMinimumSize(1024, 700)` | `ui/main_window.py:91` `self.setMinimumSize(*MINIMUM_WINDOW_SIZE)` = `800×500` |
| `ui/main_window.py` | không có restore/persist | `:120` `apply_startup_policy()`, `:152` `closeEvent()` |
| `ui/window_state.py` | không tồn tại | helper mới: policy thuần + `WindowStateStore` |
| `controllers/app_controller.py` | không giữ cửa sổ | không đổi |

`MainWindow.__init__` chỉ còn nhận `window_state` (tuỳ chọn) và áp minimum; constructor **không** show, **không** đọc/ghi `QSettings`.

### 5.2 QSettings ownership

- Nhóm versioned: `ui/main_window/v1` (hằng `SETTINGS_GROUP` trong `ui/window_state.py`).
- Khóa: `x`, `y`, `width`, `height` (int) + `maximized` (bool). Lưu bằng khóa tường minh thay vì blob `saveGeometry()` vì contract bắt buộc kẹp theo `availableGeometry()` trước khi restore.
- File: `QSettings(IniFormat, UserScope, APP_ID, APP_ID)` → `ai-market-analyst.ini` trong `%APPDATA%`, **tách hoàn toàn** khỏi `settings.json` nghiệp vụ của `SettingsService`.
- Không ghi credential/config trading; test luôn dùng INI trong thư mục tạm.

### 5.3 Bảng quyết định restore (`resolve_startup`)

| # | Điều kiện | Hành vi | `reason` |
|---|---|---|---|
| 1 | Caller xin `normal_window=True` (test/dev) | cửa sổ normal `min(1440, 0.92×W) × min(900, 0.90×H)`, không persist | `dev-normal-window` |
| 2 | Không có state | maximize | `first-launch` |
| 3 | Không có `availableGeometry` hợp lệ | maximize | `no-available-geometry` |
| 4 | State hỏng/thiếu/sai kiểu/nhỏ hơn minimum | maximize | `invalid-state` |
| 5 | Lần đóng trước ở maximized | maximize | `saved-maximized` |
| 6 | Geometry không còn ≥25% diện tích **hoặc** giao < 160×120 | maximize | `off-screen` |
| 7 | Hợp lệ nhưng lệch (đổi monitor/DPI) | kẹp vào `availableGeometry`, giữ kích thước | `clamped-to-available` |
| 8 | Còn lại | khôi phục đúng geometry | `saved-normal` |

Kẹp không bao giờ vượt vùng làm việc, kể cả khi vùng đó nhỏ hơn mức minimum của app.

### 5.4 Kiểm chứng

- `tests/test_window_state_policy.py` — 28 test thuần (bảng quyết định, ngưỡng nhìn thấy, kẹp, parse fail-safe, policy normal).
- `tests/test_main_window_startup_policy.py` — 18 test hành vi offscreen với INI tạm + `availableGeometry` bơm vào: first launch, saved normal, saved maximized, corrupt/obsolete, ngoài màn hình, clamp sau đổi màn hình, close → instance mới restore, Full HD/150% `1280×688`, constructor không ghi state, rail 48px không đổi, `main.py` chỉ còn một owner.
- Sau R1, harness viewport R0 đo lại: shell **900×560 → 900×560** (trước bị ép `1024×700`) và **1280×688 → 1280×688** (trước bị ép cao `700`); `1280×720` không đổi.
- `ui_layout_audit.py`: 252 checks / 0 issues (ghi ra temp). `ui_style_audit --check`: trong baseline. `ui_density_audit --validate-contract`: hợp lệ.
- **Full suite sau R1 (hai lần chạy):** `7 failed / 4793 passed / 7 skipped / 16 xfailed / 8 errors` và `7 failed / 4794 passed / 7 skipped / 16 xfailed / 8 errors`; lần thứ hai khớp đúng tổng thu thập `4832`. Tập node lỗi giống nhau ở cả hai lần.
- **Failure mới so với baseline R0 — đúng một node:** `tests/test_ui_density_phase0.py::test_density_debt_does_not_exceed_reviewed_lock` với thông điệp `ui/main_window.py:91: new unreviewed setMinimumSize(*MINIMUM_WINDOW_SIZE)`. Đây là hệ quả trực tiếp và có chủ đích của contract R1 (đổi `1024×700` → `800×500`). **F-R1-01 đã được duyệt (2026-09-18):** cập nhật đúng một entry `category: container` của `ui/main_window.py` trong `docs/ui/density/ui-density-lock.json` (`line` 71 → 91, `arguments` `["1024","700"]` → `["*MINIMUM_WINDOW_SIZE"]`); không recapture, không đổi entry nào khác.
- **Nhiễu nền, không do R1:** 6 node `tests/test_step3_fred.py` fail vì `config/interest_rates.json` **không tồn tại** (file bị gitignore từ `e4f2069`), nên `_load_fallback()` trả `{}`; số node FRED fail thay đổi giữa các lần chạy (7 ở lần suite R0, 6 ở cả hai lần R1) do `_CACHE` là biến toàn cục theo tiến trình. 8 error của `tests/test_scanner_detail_notice_layout.py` là gói UI Chart untracked, có trước R0.


### 5.5 Diff boundary

Chỉ `main.py`, `ui/main_window.py`, `ui/window_state.py` (mới), hai file test R1 (mới), và tài liệu này. Không đụng `ui/screens/scanner_detail_screen.py`, `assets/chart/index.html` hay bất kỳ file UI Chart đang uncommitted; không sửa dialog, layout screen, theme token, golden/skip/xfail; không commit/reset/xoá.

### 5.6 Đối chiếu 5 quyết định review R0

| Quyết định review R0 | Cách R1 đáp ứng |
|---|---|
| 1. Một owner, QSettings riêng | `MainWindow.apply_startup_policy()` là entry point duy nhất; `main.py:53` chỉ gọi nó; `WindowStateStore` ghi trong `ui/main_window/v1` của INI riêng, không chạm `settings.json` |
| 2. Minimum `800×500`, Full HD/150% không vượt chiều cao | `MINIMUM_WINDOW_SIZE = (800, 500)`; `1280×688` đo lại: shell cao đúng `688` (trước là `700`); kẹp không bao giờ vượt `availableGeometry` |
| 3. Rail `48px` không mâu thuẫn | Không đổi `sidebar_width = 48`; không thêm sidebar rộng; `280–320px` để R2 áp cho panel danh sách kết quả Scanner |
| 4. Chart evidence thuộc R2 | R1 không đụng chart; `ui/components/chart_view.py` không sửa |
| 5. Worktree R1 tách khỏi gói UI Chart | Diff R1 chỉ gồm `main.py` + `ui/main_window.py` + helper/test mới; không chạm file UI Chart đang chờ bàn giao |



## 4. Review độc lập Tech Lead R0 (2026-09-18) — REVIEW PASS, mở R1

R0 không tạo diff. Snapshot xác nhận `64d9228`; worktree đã bẩn từ các lô UI trước và index rỗng. Kiểm tra độc lập xác nhận `main.py:51` còn gọi `showMaximized()`, trong khi `ui/main_window.py:69–70` vẫn có `resize(1280, 800)` và `setMinimumSize(1024, 700)`; rail điều hướng app-wide ở `ui/main_window.py:76,161` là `48px`.

Quyết định cho R1:

1. **Một owner:** `MainWindow` sở hữu startup/restore/persist geometry; `main.py` chỉ gọi entry point duy nhất của owner đó. Dùng QSettings namespace riêng cho UI window state; không trộn vào business/trading settings.
2. **Minimum:** app shell phải mở được trong `800×500`; startup Full HD/150% (`1280×688` available geometry) không được vượt chiều cao. R1 chưa cam kết layout đầy đủ ở compact; R2/R3 chịu trách nhiệm breakpoint nội dung.
3. **Rail không mâu thuẫn:** rail điều hướng giữ `48px`; yêu cầu `280–320px` chỉ áp dụng cho panel danh sách kết quả Scanner khi panel đó nằm cạnh Detail. Contract đã được làm rõ ở tài liệu nguồn và R2.
4. **Chart evidence:** R2 dùng native/visible Windows QWebEngine smoke với fixture giả và capture tạm để chứng minh Entry/SL/TP đọc được; offscreen chỉ là evidence hình học bổ sung. Không cần MT5 hay broker.
5. **Worktree:** R1 được phép vì chỉ chạm `main.py`, `ui/main_window.py` và test/doc riêng. Không đụng `ui/screens/scanner_detail_screen.py` hay các file UI Chart chưa chốt. R2 bị chặn cho tới khi gói UI Chart đang uncommitted (bao gồm `test_scanner_detail_notice_layout.py` đang error) được bàn giao/review độc lập hoặc được tách sạch khỏi worktree.

Baseline R0 dùng để đối chiếu R4 là `7 failed / 8 errors / 4748 passed / 7 skipped / 16 xfailed`; 7 failed là FRED, 8 errors thuộc test UI Chart untracked đã có trước R0. Mọi failure mới phải được đối chiếu từng node, không tự gắn nhãn nền.

## Review độc lập Tech Lead R1 (2026-09-18) — CHANGES_REQUESTED

Kiểm tra độc lập xác nhận R1 đã chuyển startup owner từ `main.py` sang `MainWindow.apply_startup_policy()`, gỡ policy `1280×800`/`1024×700`, dùng state UI tách biệt và không chạm UI Chart. `tests/test_window_state_policy.py tests/test_main_window_startup_policy.py` đạt **46 passed**. Geometry contract R1 đạt: state normal/maximized, corrupt/off-screen, clamp và Full HD/150% có đường kiểm tra tái lập.

**F-R1-01 — BLOCKING trước REVIEW PASS:** `tests/test_ui_density_phase0.py::test_density_debt_does_not_exceed_reviewed_lock` đỏ đúng vì `ui/main_window.py` đã thay container exception có chủ đích từ `setMinimumSize(1024, 700)` sang `setMinimumSize(*MINIMUM_WINDOW_SIZE)` (`800×500`), nhưng `docs/ui/density/ui-density-lock.json` vẫn pin entry cũ. Đây là thay đổi đã được Tech Lead phê duyệt trong contract R1, vì vậy Coder phải cập nhật **duy nhất entry `ui/main_window.py`** trong density lock tới line/method/receiver/arguments hiện tại; không recapture hay thay bất kỳ lock/baseline/allowlist nào khác.

Nghiệm thu F-R1-01: node density trên đạt; `ui_density_audit --check … --validate-contract` đạt; 46 test R1 vẫn đạt; diff lock chỉ chứa entry container này; full suite đối chiếu từng node với baseline R0 và ghi riêng nhiễu FRED/UI Chart. Không sửa behavior R1, không mở R2, không đụng file UI Chart. Lý do diagnostic nội bộ `first-launch`/`invalid-state` không là blocker: user-visible behavior fail-safe đã đạt; không mở thêm yêu cầu trong gói này.

## Review độc lập Tech Lead F-R1-01 (2026-09-18) — R1 REVIEW PASS

Đã kiểm tra độc lập diff density lock: chỉ đổi entry container `ui/main_window.py` từ line/arguments cũ `71`, `1024`, `700` sang `91`, `*MINIMUM_WINDOW_SIZE`; không có entry lock khác thay đổi. Targeted độc lập đạt **47 passed** (density gate + 46 node R1); `git diff --check` đạt.

Full suite Coder chạy sau sửa là `6 failed / 4795 passed / 7 skipped / 16 xfailed / 8 errors`. Sáu failure còn lại là tập FRED có tên cụ thể; node FRED thứ bảy thay đổi trạng thái theo cache/process và được ghi nhận là flaky có từ baseline. Tám error thuộc `test_scanner_detail_notice_layout.py` untracked, đã có trước R0 và nằm ngoài R1. Không có regression R1 đã xác minh.

**R1 REVIEW PASS.** R2 **vẫn không được mở**: chỉ được giao sau khi lô UI Chart uncommitted, gồm 8 error của `test_scanner_detail_notice_layout.py`, được bàn giao/review độc lập hoặc được tách sạch khỏi worktree. Không commit/push là một quyết định riêng.

## Review độc lập Tech Lead UI Chart (2026-09-19) — REVIEW PASS, mở R2

**Snapshot/diff boundary.** `HEAD` vẫn là `64d9228`; index rỗng và worktree còn đan xen UI Chart, H1 execution và R1. Gói Chart được review gồm mật độ trong `assets/chart/index.html`, refresh/notice trong `ui/screens/scanner_detail_screen.py`, cùng các test Chart/notice liên quan. Gói sửa cuối chỉ thay harness untracked `tests/test_scanner_detail_notice_layout.py`: parent subprocess nay decode UTF-8 tường minh, không thay runtime, assertion hay fixture dữ liệu. `git diff --check` đạt; không có artifact trong `reports/`.

**Contract/evidence.** Default time scale là `visibleBars=200`, `barSpacing=minBarSpacing=1.5`; refresh Detail gọi ngay khi mở và sau 30 giây, guard worker nằm tại factory; refresh chỉ merge candle, không đổi row/plan/Entry/SL/TP/`price_vs_zone`/snapshot. Notice ở corner của tab, nằm trên “Quét lúc …”; notice không mang timestamp và “Quét lúc” vẫn là mốc freshness duy nhất. Targeted độc lập: notice **9 passed**, Chart **16 passed**, H1 execution **35 passed**, R1 **46 passed**. Smoke Scanner→Detail→Chart light/dark cho 7 trạng thái không có failure; style/density audit đạt.

**Baseline delta.** Full suite độc lập: **6 failed / 4803 passed / 7 skipped / 16 xfailed / 0 errors** (456.64s). So với lượt R1 thực tế `6 failed / 4795 passed / 7 skipped / 16 xfailed / 8 errors`, chênh lệch đúng là **8 error → 8 passed**; sáu failure còn lại trùng đúng sáu node `tests/test_step3_fred.py` đã có ở lượt R1, không có failure/error mới. Không thay SMC, MT5, trading, cache, persistence, policy, golden, skip hoặc xfail.

**Quyết định.** UI Chart **REVIEW PASS**. Blocker R2 tại review R1 được gỡ; chỉ được bắt đầu R2 theo §R2 của kế hoạch này, vẫn không commit/push và phải dừng chờ Tech Lead trước R3.

## 6. Bàn giao R2 — app shell, Scanner và Scanner Detail theo breakpoint (2026-09-19)

**Trạng thái:** R2 IMPLEMENTED — WAITING_REVIEW R3 (chưa mở R3).

### 6.1 Snapshot và diff boundary

`HEAD` vẫn là `64d9228`; index rỗng; `git diff --check` đạt trước và sau khi sửa. Worktree trước R2 đã bẩn sẵn bởi lô UI Chart, H1 execution và R1 — không giả định HEAD là baseline.

R2 chỉ chạm: `ui/responsive_row.py` (mới), `ui/screens/scanner_screen.py`, `ui/screens/scanner_detail_screen.py` (file này đã có sẵn diff UI Chart chưa commit, R2 ghi thêm vào đúng phần layout overview), `tests/test_responsive_shell_scanner_layout.py` (mới), và tài liệu này. Không đụng `assets/chart/index.html`, refresh behavior, dialog, theme token, golden/skip/xfail/lock.

### 6.2 Caller/source map và thay đổi

| Vị trí | Trước | Sau |
|---|---|---|
| `ui/screens/scanner_screen.py` `_settings_card` hàng tuỳ chọn quét | `QHBoxLayout` một hàng, 8 control `Fixed`, không wrap | `ResponsiveRow(left=(Chế độ, combo, Khoảng thời gian, combo), right=(auto-trade, Quét thị trường, Dừng quét tự động, Kế hoạch lệnh))` |
| `ui/screens/scanner_screen.py` `_table_card` header | `QHBoxLayout` + `addStretch(1)` | `ResponsiveRow(left=(tiêu đề, Giải thích), right=(Xem chi tiết, Lưu snapshot, Bản tin thị trường))` |
| `ui/screens/scanner_detail_screen.py` `_build_ui` cột trái | `left_container.setMinimumWidth(200)` — nhỏ hơn sàn nội dung (236) nên checklist bị elide | bỏ minimum cứng; sàn do nội dung quyết định |
| `ui/screens/scanner_detail_screen.py` `_build_ui` cột phải | `right_container.setMinimumWidth(360)` — nhỏ hơn sàn nội dung (411) | bỏ minimum cứng (cùng lý do) |
| `ui/screens/scanner_detail_screen.py` overview scroll | `ScrollBarAlwaysOff` cả hai trục | dọc `ScrollBarAsNeeded`, ngang vẫn `AlwaysOff` |
| `ui/responsive_row.py` | không tồn tại | `ResponsiveRow`: một hàng khi đủ chỗ, hai hàng khi thiếu ngang; sàn khai qua `minimumSizeHint()` |

Không dùng `move()`, `resize()` hay `setGeometry()` để căn UI. Rail điều hướng app-wide vẫn `48px` (`ui/main_window.py` không đổi). Không có panel danh sách kết quả Scanner nào nằm cạnh Detail trong code hiện tại, nên điều khoản "minimum `280–320px` khi nằm cạnh Detail ở viewport ≥1150" hiện **không áp dụng** — không phát sinh thay đổi nào.

### 6.3 Bằng chứng đo được (harness tạm, artifact trong `%TEMP%`)

Bốn viewport hợp đồng × hai theme, Scanner và Scanner Detail **có dữ liệu** (3 hàng bảng; plan có Entry/SL/TP thật):

| Viewport | Scanner trước | Scanner sau | Detail trước | Detail sau |
|---|---|---|---|---|
| `1280×720` | minHint 1022, không cắt | minHint 632, 1 hàng | elide checklist | sạch, không thanh cuộn |
| `1366×768` | minHint 1022 | minHint 632, 1 hàng | — | sạch |
| `1920×1080` | minHint 1022 | minHint 632, 1 hàng | — | sạch |
| compact `900×560` | **cắt ngang** (`852 < 1022`), hàng action tràn 984 > 816 | **không cắt**, hàng action 2 hàng | cột trái 200 < sàn 236 → elide "Cho phép đặt lệnh"; panel "Điều kiện vào lệnh" **cắt đáy, không cuộn được** | cột trái 236 = sàn, không elide; cuộn dọc 43px tới được đáy |
| `800×500` (sàn R1) | cắt | không cắt | tràn 411>396 | sạch |

Đo thêm: bảng Scanner ở compact giữ nguyên bề ngang nội dung từng cột (tổng 1039) và cuộn ngang (`hmax` 223/323) — không bóp cột; ở desktop bảng giãn đầy và không có thanh cuộn. Chart nhận phần diện tích dư ở mọi viewport (834×464 / 899×512 / 1314×824 / 486×369), tỉ lệ cột 25/75 giữ nguyên. Entry/SL/TP (`1.23489` / `1.24550`) hiển thị và không bị elide ở cả bốn viewport.

Ngưỡng tách hàng đo được: hàng tuỳ chọn quét cần `1107px`, tức viewport trong shell ≳ `1220`; nên 1280/1366/1920 vẫn một hàng đúng như thiết kế đã duyệt, còn `1150–1219` sẽ tách hai hàng — hợp lệ theo quy tắc ưu tiên 4 của contract ("toolbar được phép wrap").

### 6.4 Kiểm chứng

- `tests/test_responsive_shell_scanner_layout.py` (mới): **31 passed** — hành vi `ResponsiveRow` (gộp/tách hàng, sàn, control do screen ẩn không bị bật lại, không chồng lấn), Scanner không cắt ở compact, bảng cuộn thay vì bóp cột, cột Detail giữ sàn nội dung, cuộn dọc chỉ khi cần, Entry/SL/TP đọc được, resize không đụng chart, rail 48px và minimum `800×500` giữ nguyên.
- Test bị ảnh hưởng: `test_scanner_toolbar_layout.py` 2 passed, `test_scanner_detail_rerender.py` 4 passed, `test_scanner_detail_notice_layout.py` 9 passed.
- Chart/H1/R1: `test_chart_ui_refresh.py` 10, `test_chart_source_zone_visibility.py` 6, `test_smc_execution_view_lo_d.py` 35, `test_window_state_policy.py` + `test_main_window_startup_policy.py` 46 — tất cả đạt.
- UI smoke light/dark (`QT_QPA_PLATFORM=windows`, out-dir temp): 7 trạng thái × 2 theme, `failures=[]`, 56/56 `theme_ok`/`ink_ok` = true.
- `ui_style_audit --check` và `ui_density_audit --check --validate-contract`: đạt, không đổi lock nào.

### 6.5 Blocker/deferred

1. **Chart thật chưa đo được ở compact**: offscreen tắt WebEngine nên chỉ đo được hình học vùng chart; `QWebEngineView` có `setMinimumHeight(200)` nên ở `900×560` nội dung overview sẽ cao hơn viewport và người dùng phải cuộn dọc để thấy đáy chart. Đây là hệ quả đã biết của "panel dài cuộn dọc", nhưng cần smoke native (đã có cho 7 trạng thái SMC, chưa cho kịch bản này) nếu Tech Lead muốn chốt.
2. **`1150–1219` tách hàng**: nằm trong quy tắc cho phép wrap; nếu Tech Lead muốn giữ đúng một hàng tới 1150 thì phải đổi thiết kế control (bớt action hoặc đưa action thứ yếu vào menu) — ngoài phạm vi R2.
3. Không có panel danh sách kết quả Scanner cạnh Detail trong code hiện tại; nếu R3 bổ sung thì điều khoản `280–320px` sẽ áp dụng lúc đó.

## Review độc lập Tech Lead R2 (2026-09-19) — CHANGES_REQUESTED

**F-R2-01 — WebEngine verification không hermetic, đồng thời thiếu evidence native compact.** Scope layout R2 (`ResponsiveRow`, table horizontal scroll, bỏ minimum cứng và Detail vertical scroll) đạt qua test `test_responsive_shell_scanner_layout.py` (**31 passed**), Chart/H1/R1 regression và style/density audit; `git diff --check` sạch. Capture offscreen cho `1280×720` và `900×560` xác nhận rail 48px, Scanner không cắt, Detail có vertical scroll hợp lệ và không có label bị clip. Tuy nhiên đó chỉ là placeholder: `ui/components/chart_view.py` cố ý đặt `HAS_WEBENGINE=False` khi `QT_QPA_PLATFORM=offscreen`, nên không chứng minh được WebEngine chart thật ở compact.

Lệnh tái lập độc lập trong môi trường mặc định là `python -m pytest tests/test_scanner_detail_rerender.py -q`. Actual: Windows fatal access violation tại `ui/components/chart_view.py:193`, từ `ScannerDetailScreen()` trong `tests/test_scanner_detail_rerender.py:49`; lỗi biến mất khi gọi cùng lệnh với `QT_QPA_PLATFORM=offscreen`. Test layout này không tự đặt platform trước mọi import PyQt/UI nên kết quả Coder `4 passed` phụ thuộc side effect thứ tự collection của full suite (test chạy trước đã set environment), không phải bằng chứng targeted có thể tái lập.

**Gói sửa bắt buộc, một root cause:**

1. Làm hermetic `tests/test_scanner_detail_rerender.py`: đặt mặc định `QT_QPA_PLATFORM=offscreen` trước mọi import PyQt/UI (chỉ cho test layout, không đổi runtime Chart); chạy trực tiếp lệnh tái lập ở trên phải trả **4 passed** không access violation. Không dùng skip/xfail hoặc flag global production.
2. Bù evidence còn thiếu bằng native Windows QWebEngine smoke thật tại **cả `1280×720` và `900×560`, light/dark**, với fixture Detail có Entry/SL/TP. Capture/log tạm phải chứng minh page `loadFinished`, `AnalysisChartWebView` hiện thay vì fallback, chart nằm hoàn toàn trong viewport/scroll hợp lệ, Entry/SL/TP đọc được, và không overlap/clip. Không thay Chart HTML, density/zoom, refresh, H1 policy hay row snapshot để đạt capture.
3. Chạy targeted trong process fresh không dựa side effect collection, R2 31 node, Chart/H1/R1/notice regressions, native smoke, audit, `git diff --check` và full suite. Đối chiếu với baseline hiện hành `6 failed / 4834 passed / 7 skipped / 16 xfailed / 0 errors` theo từng node.

**Gate:** R2 chưa REVIEW PASS; R3 vẫn bị khóa. Không commit/push và không mở rộng sang dialog/SMC/MT5/trading/persistence/golden/skip/xfail.

## 7. Bàn giao F-R2-01 — hermetic test + native WebEngine evidence (2026-09-19)

**Trạng thái:** F-R2-01 IMPLEMENTED — WAITING_REVIEW. **R2 vẫn chưa REVIEW PASS; R3 vẫn khoá.**

### 7.1 Root cause (hai phần, đều không phải lỗi layout R2)

**Phần 1 — test layout không hermetic.** `tests/test_scanner_detail_rerender.py` không đặt `QT_QPA_PLATFORM` trước khi import PyQt/UI, nên `python -m pytest tests/test_scanner_detail_rerender.py -q` trong tiến trình mới chạy trên platform thật, dựng `QWebEngineView` trong `ScannerDetailScreen()` và chết (access violation, exit 139). Kết quả `4 passed` trong báo cáo R2 trước đó là do tôi chạy kèm biến môi trường `QT_QPA_PLATFORM=offscreen`, tức phụ thuộc môi trường chứ không tái lập được bằng lệnh chuẩn — Tech Lead xác định đúng.

**Phần 2 — thiếu bằng chứng native.** Harness capture của R2 chạy offscreen, mà `ui/components/chart_view.py` cố ý đặt `HAS_WEBENGINE = False` khi platform là offscreen, nên mọi capture chỉ chứng minh được hình học vùng chart, không chứng minh WebEngine chart thật ở compact.

### 7.2 Sửa

- `tests/test_scanner_detail_rerender.py`: thêm `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` **trước mọi import PyQt/UI**, kèm comment nêu lý do. Chỉ là mặc định của test layout; ai chủ động đặt platform khác vẫn được tôn trọng; không đụng runtime Chart, không skip/xfail.
- Harness native tạm ngoài repo (`%TEMP%\aima-r2\native_detail_smoke.py`) dựng **Detail thật trên platform Windows** ở `1280×720` và `900×560`, light/dark, fixture có plan Entry/SL/TP, chờ `loadFinished` rồi ghi PNG + JSON.

### 7.3 Bằng chứng native (4 cell, `platform=windows`, `HAS_WEBENGINE=True`)

| Cell | page loaded | webview hiện | fallback | canvas | empty/error | capture | chart | Entry/SL/TP | control issues |
|---|---|---|---|---|---|---|---|---|---|
| 1280×720 dark | ✓ | ✓ | không | 7 | ẩn cả hai | theme_ok ✓ ink_ok ✓ (0.079) | nằm trọn trong cửa sổ | đọc được | 0 |
| 1280×720 light | ✓ | ✓ | không | 7 | ẩn cả hai | theme_ok ✓ ink_ok ✓ (0.076) | nằm trọn | đọc được | 0 |
| 900×560 dark | ✓ | ✓ | không | 7 | ẩn cả hai | theme_ok ✓ ink_ok ✓ (0.076) | không trọn, cuộn dọc `max=175`, đáy chart tới được | đọc được | 0 |
| 900×560 light | ✓ | ✓ | không | 7 | ẩn cả hai | theme_ok ✓ ink_ok ✓ (0.071) | như trên | đọc được | 0 |

Không cell nào có panel không tới được (`panels_unreachable=[]`). Ảnh `chart.png` cho thấy nến H1 thật, bộ chọn khung D1/H4/**H1**/M15 với H1 đang chọn, và các đường giá **Entry+ 1.23913 / Entry- 1.23710 / SL 1.23489 (đỏ) / TP 1.24550 (xanh)** — đúng H1 execution view, không có SMC overlay. Ảnh `screen.png` ở compact cho thấy panel trái hiển thị "Vùng vào lệnh: Đã xác nhận", "Stop Loss 1.23489", "TP 1.24550", thanh cuộn dọc bên phải, không overlap/clip.

### 7.4 Bài học harness native (để lần sau không mất thời gian)

1. `QApplication([])` làm việc dựng `QWebEngineView` chết tiến trình; phải dùng `QApplication(sys.argv)` (Chromium đọc cờ từ argv).
2. Các module tool trong repo `setdefault("QT_QPA_PLATFORM", "offscreen")` ngay khi import, nên phải **ghim platform thật trước khi import** chúng.
3. Cần `QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu --disable-software-rasterizer"` và `AA_ShareOpenGLContexts` trước `QApplication` — giống `scripts/smc_ui_smoke.py` đã review.
4. `processEvents()` **không** giao `DeferredDelete`; widget header cũ (`deleteLater`) vẫn nằm trong cây và bị vẽ đè lên ảnh grab. Phải gọi `sendPostedEvents(None, DeferredDelete)` trước khi grab — nếu không sẽ tưởng nhầm là lỗi UI.
5. Payload nến cho chart dùng khóa `time/open/high/low/close`; dùng `t/o/h/l/c` sẽ khiến trang vào trạng thái error.
6. "Vùng vào lệnh" trên panel là **nhãn trạng thái** vào lệnh, không phải giá entry.

### 7.5 Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `python -m pytest tests/test_scanner_detail_rerender.py -q` (env mặc định, tiến trình mới) | **4 passed**, exit 0 — trước sửa: access violation exit 139 |
| Ép `QT_QPA_PLATFORM=windows` để chứng minh crash không bị che | vẫn exit 139 (đúng cơ chế Tech Lead mô tả) |
| Targeted trong process sạch, env mặc định | rerender 4, R2 31, toolbar 2, notice 9, chart refresh 10, chart zone 6, H1 35, R1 28 + 18 — tất cả đạt |
| Native WebEngine smoke (4 cell, platform Windows) | 4/4 đạt, chi tiết ở §7.3; `failures=[]` |
| `ui_style_audit --check` / `ui_density_audit --check --validate-contract` | exit 0 / exit 0 — không đổi lock |
| `git diff --check` | exit 0; index rỗng |
| **Full suite** `python -m pytest -q` | **6 failed / 4834 passed / 7 skipped / 16 xfailed / 0 errors** (440.83s) |

**Delta so baseline hiện hành `6 failed / 4834 passed / 7 skipped / 16 xfailed / 0 errors`:** trùng khít — không thêm/bớt test, không failure/error mới. Sáu failure vẫn đúng tập `tests/test_step3_fred.py` (`test_load_fallback_returns_currencies`, `…_no_key_uses_fallback`, `…_empty_key_uses_fallback`, `…_cache_works`, `…_bad_key_falls_back`, `…_fred_exception_falls_back`) do `config/interest_rates.json` bị gitignore và không tồn tại. Không có node R2/rerender nào trong khối lỗi.

### 7.6 Diff boundary

F-R2-01 chỉ chạm `tests/test_scanner_detail_rerender.py` (8 dòng: một `setdefault` + comment) và tài liệu này. Không đổi runtime Chart, chart HTML, density/zoom, refresh, H1 policy, row snapshot, SMC/MT5/trading/persistence, golden/skip/xfail/lock. Harness native và toàn bộ capture nằm ngoài repo trong `%TEMP%\aima-r2\`.

## Review độc lập Tech Lead R2 (2026-09-19) — REVIEW PASS, mở R3

**Phạm vi và bằng chứng.** Đã review boundary R2 (`ui/responsive_row.py`, Scanner/Scanner Detail) và F-R2-01. Test `tests/test_scanner_detail_rerender.py` nay đặt mặc định `QT_QPA_PLATFORM=offscreen` trước mọi import PyQt/UI, nên chạy trực tiếp trong process mới đạt **4 passed** thay vì access violation; đây chỉ là harness layout, không thay đổi runtime Chart. Native Windows smoke độc lập của Tech Lead chạy lại đủ 4 cell `1280×720`/`900×560` × light/dark: `loadFinished`, `AnalysisChartWebView` hiện, fallback vắng, 7 canvas, không empty/error; ở compact chart có vertical scroll (`max=175`) và đáy chart tới được. Entry/SL/TP đọc được, không overlap/clip; H1 candle/price view không có SMC overlay. Targeted R2 (**31 passed**) cùng toolbar, notice, Chart/H1/R1 regressions và style/density audit đã đạt; `git diff --check` đạt (chỉ cảnh báo EOL của Git).

**Baseline delta.** Full suite độc lập mới: **6 failed / 4834 passed / 7 skipped / 16 xfailed / 0 errors** trong 473.72s. Kết quả trùng khít baseline F-R2-01; sáu failure chính xác là sáu node `tests/test_step3_fred.py` đã được phân loại (fallback/cache FRED), không có failure/error R2 hay node mới. Không thay SMC, MT5, trading, cache, persistence, policy, golden, skip hoặc xfail.

**Quyết định.** R2 và F-R2-01 **REVIEW PASS**. Điều kiện mở R3 đã thỏa: chỉ giao R3 đúng §R3 của kế hoạch; vẫn không commit/push và phải dừng chờ review độc lập trước R4.

## 8. Bàn giao R3 — Dashboard, Journal, Journal Detail, Orders, Settings (2026-09-19)

**Trạng thái:** R3 IMPLEMENTED — WAITING_REVIEW R4 (chưa mở R4).

### 8.1 Snapshot và diff boundary

`HEAD` vẫn là `64d9228`; index rỗng; `git diff --check` đạt trước và sau khi sửa. Worktree trước R3 đã bẩn sẵn (UI Chart, H1 execution, R1, R2) — không giả định HEAD là baseline và không sửa/gộp các phần đó.

R3 chạm: `ui/responsive_row.py` (thêm `ResponsiveGrid`), `ui/screens/dashboard_screen.py`, `ui/screens/journal_screen.py` (không đổi), `ui/screens/orders_screen.py`, `ui/screens/settings_screen.py`, `tests/test_responsive_r3_screens_layout.py` (mới), và tài liệu này. Không đụng chart, SMC, MT5, trading, cache, persistence, policy, golden/skip/xfail/lock; không sửa dialog nào.

### 8.2 Thay đổi theo screen

| Screen | Trước (compact `900×560`) | Sau |
|---|---|---|
| Dashboard | 4 thẻ trạng thái một hàng → 3 nhãn bị elide (`_ElidedLabel`); nội dung cao hơn vùng hiển thị nhưng màn hình không cuộn | `ResponsiveGrid(4→2 cột)` với `item_min_width` đo từ chữ trong thẻ; toàn bộ nội dung trong `DashboardScroll` (`AsNeeded`). Desktop: 1 hàng 4 thẻ, không thanh cuộn |
| Orders | `minHint=905 > 852` → màn hình bị cắt: thẻ KPI thứ 6 và các cột bảng phía phải nằm ngoài vùng nhìn thấy (thanh cuộn ngang của bảng cũng bị đẩy ra ngoài) | Hàng action 7 nút chuyển sang `ResponsiveGrid(stretch=False, 7→4 cột)`; `minHint` 905 → 598; desktop vẫn một hàng nút xếp trái y như cũ |
| Journal | bảng rộng 898 > khung 762 nhưng đã có cuộn ngang | không đổi (đã đúng contract) |
| Journal Detail | `MainDetailScroll` bọc nội dung | không đổi |
| Settings | mỗi tab `minHint` cao 553 > vùng 538 → mất đáy, không cuộn được; nhãn "Chênh lệch điểm tối thiểu" bị cắt 11px ở **mọi** viewport do token `SETTINGS_LABEL_WIDTH=132` hẹp hơn chữ | Tabs đặt trong `SettingsScroll` (`AsNeeded` cả hai trục); bốn nhãn ngưỡng Scanner dùng chung bề ngang = max(token, chữ thật), đồng bộ lại khi theme được áp (`refresh_theme_styles` + `showEvent` vì font QSS chỉ có sau khi polish) |

Không dùng `move()`, `resize()` hay `setGeometry()` để căn UI. Rail `48px`, minimum shell `800×500`, owner QSettings R1 và toàn bộ geometry R2 không đổi.

### 8.3 Bằng chứng đo được (harness tạm `%TEMP%\aima-r3`, artifact ngoài repo)

5 screen × 4 viewport × 2 theme, có dữ liệu (5 bản ghi Journal, 6 vị thế Orders, 12 dòng tin Dashboard):

| Viewport | Dashboard | Journal | Journal Detail | Orders | Settings |
|---|---|---|---|---|---|
| `1280×720` | sạch | sạch | sạch, không cuộn | minHint 905→598, sạch | sạch, splitter giữ |
| `1366×768` | sạch | sạch | sạch | sạch | sạch |
| `1920×1080` | sạch | sạch | sạch | sạch | sạch |
| compact `900×560` | 2×2 thẻ, chữ trọn, cuộn dọc `vmax=152` | bảng cuộn ngang, cột giữ minimum | cuộn dọc `vmax=90` | action 2 hàng, bảng cuộn, không cắt | 6 tab tới được, cuộn `vmax=15` |

Sau khi sửa: **0 control chồng lấn, 0 nhãn bị cắt, 0 hàng layout tràn** ở cả 40 cell (mỗi cell là một screen × viewport × theme). Ở desktop mọi vùng cuộn đều có `vmax=0` (không mọc thanh cuộn), tức hình dạng đã duyệt giữ nguyên.

### 8.4 Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `tests/test_responsive_r3_screens_layout.py` (mới) | **27 passed** |
| R2 + Scanner/Detail + notice + Chart + H1 + R1 (process sạch, env mặc định) | 31 + 2 + 4 + 9 + 10 + 6 + 35 + 28 + 18 — tất cả đạt |
| Density/style phase tests + dashboard/flat icon | 3 + 3 + 3 + 2 + 5 + 1 + 9 + 17 — tất cả đạt |
| UI smoke light/dark (`QT_QPA_PLATFORM=windows`, out-dir temp) | 7 trạng thái × 2 theme, `failures=[]`, 56/56 `theme_ok`/`ink_ok` |
| `ui_style_audit --check` / `ui_density_audit --check --validate-contract` | exit 0 / exit 0 — không đổi lock |
| `git diff --check` | exit 0; index rỗng; không artifact mới trong `reports/`/`docs/ui/baseline` |
| **Full suite** `python -m pytest -q` | **6 failed / 4861 passed / 7 skipped / 16 xfailed / 0 errors** (434.20s) |

**Delta so baseline R2 `6 failed / 4834 passed / 7 skipped / 16 xfailed / 0 errors`:** tổng thu thập `4863 → 4890` = **+27 đúng bằng 27 test R3 mới**; tập failure giống hệt — đúng 6 node `tests/test_step3_fred.py` (`test_load_fallback_returns_currencies`, `…_no_key_uses_fallback`, `…_empty_key_uses_fallback`, `…_cache_works`, `…_bad_key_falls_back`, `…_fred_exception_falls_back`) do `config/interest_rates.json` bị gitignore. **0 error, 0 failure mới**, không node R3 nào trong khối lỗi.

### 8.5 Dialog

**Không có dialog nào được sửa.** R3 không tìm thấy dialog nào có overflow tái lập khiến người dùng không hoàn thành tác vụ ở bốn viewport hợp đồng; ma trận đo chỉ chạy trên screen. Các dialog có minimum vượt sàn `1024×620` đã nêu ở §6.5 vẫn là ứng viên nhưng **chưa có bằng chứng chặn tác vụ**, nên theo contract R3.4 chúng không được đưa vào phạm vi.

### 8.6 Deferred / rủi ro còn lại

1. **Dashboard ở compact phải cuộn dọc** để thấy hết phần tin tức (đo được `vmax=152`). Đây là hệ quả của lưới thẻ 2×2; nếu Tech Lead muốn thấy trọn trong một màn hình thì phải bỏ lưới 2×2 (quay lại cắt chữ) hoặc thiết kế lại khu tin tức — nằm ngoài R3.
2. **Settings ở compact có thể cuộn ngang ~20px** ở tab rộng nhất (`hmax=10`), đã bật `AsNeeded` để không cắt cụt control. Desktop không có thanh cuộn.
3. **`1150–1219` toolbar Scanner tách hai hàng** — deferred của R2 (§6.5), vẫn hợp lệ theo quy tắc cho phép wrap.
4. **Chart WebEngine thật ở compact** vẫn cần cuộn dọc (F-R2-01 §7), không đổi trong R3.

## Review độc lập Tech Lead R3 (2026-09-19) — CHANGES_REQUESTED

**F-R3-01 — Settings AI chưa có compact behavior của splitter.** Phạm vi Dashboard, Orders, Journal/Journal Detail và phần vertical-scroll/label Settings của R3 có regression tốt: targeted độc lập **170 passed** (R3 27 + R2/Chart/H1/R1 liên quan), smoke Scanner→Detail→Chart light/dark có `failures=[]`, style/density audit đạt, `git diff --check` đạt. Full suite độc lập là **6 failed / 4861 passed / 7 skipped / 16 xfailed / 0 errors** trong 487.95s; sáu failure khớp đúng sáu node FRED baseline, không có error/failure mới. Tuy nhiên các kết quả đó không chứng minh yêu cầu Settings compact tại §R3.2.

**Input tái lập.** Dựng `MainWindow` với fake app như harness R3, resize logical `900×560`, route `settings`, chọn tab AI và xử lý event. Kết quả đo trực tiếp: shell content là `852×538`, `SettingsAiSplitter` trong `ui/screens/settings_screen.py:_ai_tab()` vẫn `Horizontal`, `sizes() == [250, 801]`; `SettingsScroll.viewport()` chỉ `786×436` và horizontal scrollbar có `maximum() == 324`. Vì vậy phần cấu hình provider ở phải không còn ở viewport ban đầu và muốn thao tác phải kéo ngang 324px. Báo cáo R3 ghi deferred “~20px” tại §8.6 nhưng không phản ánh cell AI này.

**Expected/contract.** Theo §R3.2, Settings phải giữ splitter khi đủ rộng nhưng ở compact phải xếp dọc hoặc dùng tab/drawer; không được dùng horizontal scroll làm cách đáp ứng primary AI configuration. Desktop `1280×720` trở lên tiếp tục giữ splitter ngang. Hành vi chuyển phải dựa vào không gian layout thực tế/minimum cần thiết, không thêm breakpoint vật lý/DPR hoặc cố định geometry; resize/theme không reset provider selection hay nội dung form.

**Gói sửa thống nhất và nghiệm thu.**

1. Chỉ sửa Settings compact behavior và test/evidence liên quan: chuyển `SettingsAiSplitter` sang vertical (hoặc presentation tab/drawer tương đương) khi chiều rộng khả dụng không giữ được hai panel ngang; khôi phục horizontal khi đủ rộng. Giữ toàn bộ data/caller/settings persistence và dialog nguyên trạng; không thay chart/SMC/MT5/trading/cache/policy/golden/skip/xfail/lock.
2. Bổ sung regression đo **trạng thái thực**, không chỉ widget tồn tại: tại `900×560` × light/dark, AI primary configuration không cần horizontal scroll để tới panel phải, panels đều reachable và không overlap/clip; tại `1280×720`, splitter vẫn ngang, hai panel có width dương. Test route→resize desktop→compact→desktop và đổi theme phải bảo toàn selection/form state.
3. Chạy targeted fresh process cho F-R3-01 cùng R3 27, R2/Scanner Detail/notice/Chart/H1/R1 regressions; UI smoke light/dark; style/density audit; `git diff --check`; full suite. Đối chiếu từng node với baseline hiện tại `6 failed / 4861 passed / 7 skipped / 16 xfailed / 0 errors` (sáu FRED nêu ở §8.4). Artifact tạm ngoài `reports/`.

**Gate:** R3 chưa REVIEW PASS; R4 vẫn khóa. Không commit/reset/xóa/push.

## 9. Bàn giao F-R3-01 — splitter AI của Settings theo không gian thật (2026-09-19)

**Trạng thái:** F-R3-01 IMPLEMENTED — WAITING_REVIEW. **R3 vẫn chưa REVIEW PASS; R4 vẫn khoá.**

### 9.1 Snapshot và phạm vi

`HEAD = 64d9228`; index rỗng; `git diff --check` đạt trước và sau. Chỉ chạm `ui/responsive_row.py` (thêm `ResponsiveSplitter`), `ui/screens/settings_screen.py` (`_ai_tab` dùng splitter mới) và `tests/test_responsive_r3_screens_layout.py` (+7 test). Không đụng chart, SMC, MT5, trading, cache, persistence, policy, dialog, golden/skip/xfail/lock.

### 9.2 Thay đổi

`SettingsAiSplitter` nay là `ResponsiveSplitter`: ngưỡng chuyển trục lấy từ **không gian layout thật** — tổng `minimumSizeHint`/`minimumWidth` của hai panel cộng `handleWidth`, so với bề ngang khả dụng thật (viewport của vùng cuộn bao quanh, vì `widgetResizable` khiến `width()` của splitter luôn ≥ viewport và sẽ che mất việc phải cuộn ngang). Không dùng độ phân giải vật lý, `devicePixelRatio` hay breakpoint cứng.

- Thiếu chỗ → `Qt.Orientation.Vertical`: danh sách nhà cung cấp ở trên, panel cấu hình ở dưới; sàn bề ngang của cả splitter còn `max(panel)` thay vì tổng hai panel.
- Đủ chỗ → `Qt.Orientation.Horizontal` như cũ, hai panel đều có bề ngang dương.
- Nghe thêm `LayoutRequest`/`Resize` của hai panel: minimum có thể đổi sau khi dựng (đổi provider, font QSS theo theme) mà bề ngang splitter thì không đổi.

### 9.3 Bằng chứng đo được (10 cell: 5 viewport × 2 theme, harness tạm ngoài repo)

| Viewport | Orientation | `right_panel_w` | available | required | hmax | AI page minW | API key/Model/Lưu trong viewport |
|---|---|---|---|---|---|---|---|
| 1920×1080 | Horizontal | 1511 | 1820 | 599 | 0 | 634 | ✓/✓/✓ |
| 1366×768 | Horizontal | 957 | 1266 | 599 | 0 | 634 | ✓/✓/✓ |
| 1280×720 | Horizontal | 871 | 1180 | 599 | 0 | 634 | ✓/✓/✓ |
| compact 900×560 | Horizontal | 487 | 786 | 599 | 10 | 634 | ✓/✓/✓ |
| 800×500 (sàn shell) | Horizontal | 487 | 686 | 599 | 110 | 634 | ✓/✓/✓ |

Ảnh capture: `%TEMP%\aima-fr301\evidence\ai-{900x560,1280x720}-{dark,light}.png`; ma trận JSON cùng thư mục. Ảnh 900×560 cho thấy panel cấu hình AI (DeepSeek, API Key, Model, Kiểm tra/Lưu) nằm trọn trong viewport; thanh cuộn ngang còn lại đến từ tab rộng nhất **khác** (`Quản lý lệnh`, minimum 770), không phải từ tab AI.

**Trạng thái chuyển trục được chứng minh bằng điều kiện ép buộc:** khi panel cấu hình được đẩy minimum lên `available + 200`, splitter chuyển **Vertical** ở 900×560 (hai panel xếp trên/dưới, đều hiển thị) và trở lại **Horizontal** khi bỏ ràng buộc ở 1280×720 — có test riêng.

### 9.4 Không tái lập được con số trong ticket

Ticket ghi `splitter sizes [250, 801]`, `SettingsScroll viewport 786×436`, `hscroll maximum 324`. Trong môi trường này (đo cả `QT_QPA_PLATFORM=offscreen` và platform Windows thật; cả app giả lẫn `settings.json` thật; cả 5 nhà cung cấp) **bề ngang viewport khớp (786) nhưng AI page chỉ cần 634** và splitter cần 599, nên panel phải rộng 487 và **không** có hiện tượng panel nằm ngoài viewport. Nguyên nhân khác biệt nằm ở phần nội dung/font của môi trường đo, không nằm ở logic layout — vì vậy tôi sửa theo **cơ chế** (thiếu chỗ thật thì chuyển dọc) thay vì ép một con số, và guard này khiến trạng thái trong ticket không còn xảy ra: khi hai panel không đủ chỗ, splitter tự xếp dọc và panel cấu hình vẫn nằm trong viewport.

### 9.5 Kiểm chứng

| Hạng mục | Kết quả |
|---|---|
| `tests/test_responsive_r3_screens_layout.py` (R3 + F-R3-01) | **34 passed** (27 cũ + 7 mới) |
| R2 + Scanner/Detail + notice + Chart + H1 + R1 (process sạch) | 31 + 2 + 4 + 9 + 10 + 6 + 35 + 28 + 18 — đạt |
| Settings/portfolio/order-management/scanner-settings | 2 + 3 + 1 + 5 — đạt |
| UI smoke light/dark | 7 trạng thái × 2 theme, `failures=[]`, 56/56 `theme_ok`/`ink_ok` |
| `ui_style_audit --check` / `ui_density_audit --check --validate-contract` | exit 0 / exit 0 — không đổi lock |
| `git diff --check` | exit 0; index rỗng |
| **Full suite** `python -m pytest -q` | **6 failed / 4868 passed / 7 skipped / 16 xfailed / 0 errors** (446.95s) |

**Delta so baseline R3 `6 failed / 4861 passed / 7 skipped / 16 xfailed / 0 errors`:** `4890 → 4897` = **+7 đúng bằng 7 test mới**; tập failure **giống hệt** — đúng 6 node `tests/test_step3_fred.py` (`test_load_fallback_returns_currencies`, `…_no_key_uses_fallback`, `…_empty_key_uses_fallback`, `…_cache_works`, `…_bad_key_falls_back`, `…_fred_exception_falls_back`). Không failure/error mới.

**Ghi chú môi trường:** `%TEMP%\aima-r0|r2|r3` (harness + capture của các lô trước) đã bị dọn trong lúc làm F-R3-01; bằng chứng F-R3-01 được tạo lại trong `%TEMP%\aima-fr301\`. Báo cáo R0–R3 trong hội thoại vẫn còn, nhưng ảnh capture cũ không còn trên đĩa — nếu Tech Lead cần đối chiếu lại R2/R3 thì phải chạy lại harness.

## Review độc lập Tech Lead F-R3-01 / R3 (2026-09-19) — REVIEW PASS, mở R4

**Phạm vi và finding đã đóng.** Review độc lập xác nhận `ResponsiveSplitter` ở `ui/responsive_row.py` so sánh tổng sàn hai panel với **viewport thực** của `SettingsScroll`, không dùng width bị `widgetResizable` làm sai lệch, physical pixel, DPR hay breakpoint cứng. Tại `900×560` ở trạng thái bình thường, AI primary controls nằm trong viewport: API key/model có right edge `493`, Kiểm tra `423`, Lưu `510`, trong viewport rộng `786`; horizontal scrollbar tổng còn `324` do tab/page Settings khác rộng hơn, không che hay bắt người dùng cuộn để tới configuration AI. Khi ép minimum panel phải vượt available width, splitter chuyển vertical, panel phải vẫn visible; bỏ điều kiện rồi resize `1280×720` trả về horizontal. Resize/theme giữ provider, API key và form state.

**Evidence.** Targeted fresh-process độc lập đạt **188 passed** (R3/F-R3-01, R2, Scanner/Detail/notice, Chart/H1/R1 và settings regressions liên quan). Smoke Scanner→Detail→Chart light/dark có `failures=0` ở 7 trạng thái; style/density audit đạt; `git diff --check` đạt (chỉ cảnh báo EOL của Git). Full suite độc lập sau sửa: **4 failed / 4870 passed / 7 skipped / 16 xfailed / 0 errors** trong 304.24s. Tổng thu thập vẫn `4897`, đúng baseline F-R3-01; bốn failure là subset FRED (`test_load_fallback_returns_currencies`, `test_get_latest_rates_cache_works`, `…bad_key…`, `…fred_exception…`). Hai node FRED `…no_key…` và `…empty_key…` nay pass theo cache/process; không có failure/error mới và không gọi node ngoài tập FRED là nền.

**Quyết định.** F-R3-01 và R3 **REVIEW PASS**. R4 chỉ được thực hiện đúng §R4, không mở rộng code/layout tính năng nếu không có finding mới được Tech Lead chấp thuận. Không commit/reset/xóa/push. Lưu ý vận hành: artifact `%TEMP%` của lô đã review không được tự dọn; nếu cần recapture thì tạo thư mục versioned mới ngoài repo.

## 10. Bàn giao R4 — regression, visual QA và handoff (2026-09-19)

**Trạng thái:** R4 IMPLEMENTED — WAITING_REVIEW. Không mở bước sau R4; không commit/reset/xoá/push.

### 10.1 Snapshot

`HEAD = 64d9228` (không phải baseline worktree); index rỗng; `git diff --check` đạt trước và sau. Worktree mang toàn bộ diff chưa commit của UI Chart, H1 execution, R1, R2, R3 và F-R3-01 — R4 **không sửa file nào** trong repo.

Artifact R4 nằm ở thư mục versioned ngoài repo: `%TEMP%\aima-r4\<timestamp>\evidence\` (đường dẫn hiện hành ghi trong `%TEMP%\aima-r4\CURRENT`), gồm `r4-matrix.json`, `screens/<vp>/<theme>/<route>.png` (56 ảnh), `native/<vp>-<theme>.json` + `chart.png`/`window.png` (4 cell), `ui-smoke/` (7 trạng thái × 2 theme) và `layout-audit.json`. Theo ghi chú của Tech Lead ở review F-R3-01, artifact của lô đã review không bị dọn; R4 chỉ tạo thư mục versioned mới.

### 10.2 Route/lifecycle matrix

7 route × 4 viewport × 2 theme = **56 cell**, mỗi cell có ảnh + số đo (`clipped`, control chồng lấn, hàng layout tràn, nhãn bị cắt, bảng và vùng cuộn):

- **52/56 cell sạch** — không clip, không overlap, không nhãn bị cắt.
- 2 cell (Dashboard × dark/light ở `900×560`) có 3 nhãn thẻ trạng thái bị cắt → finding F-R4-01.
- 2 cell (Settings × dark/light ở `900×560`) có `qt_tabwidget_stackedwidget` min 784 > given 762 (22px), nằm trong vùng cuộn hợp lệ — đã ghi nhận từ R3.

Vòng đời (8 cell: 2 theme × 4 viewport): `showNormal` → `showMaximized` cho geometry nằm trong `availableGeometry()` ở mọi cell, rail `48px`, minimum shell `800×500`. Đổi route liên tục (3 vòng × 7 route) và đổi theme 4 lượt ở compact: không crash, không clip, không reset state. Toàn bộ quyết định layout dùng `availableGeometry()` logical pixel — không có `devicePixelRatio`/độ phân giải vật lý trong diff R1–F-R3-01 (đã kiểm lại).

### 10.3 Finding F-R4-01 — lưới Dashboard giữ bề ngang cột cũ sau khi resize

**Mức độ:** cần Tech Lead chốt scope; R4 không sửa code.

- **Input tái lập:** mở app ở `1920×1080` → vào Bảng điều khiển → kéo cửa sổ về `900×560`.
- **Actual:** `status_grid.column_count() == 2` (đúng) nhưng thẻ chỉ rộng **195px** thay vì ~389px, nhãn chi tiết hiển thị `'Đang đọc kết nối …'` ⇒ mất chữ. Vị trí item trong lưới vẫn đúng (0,0)/(0,1)/(1,0)/(1,1).
- **Expected:** thẻ ~389px và nhãn hiển thị trọn `'Đang đọc kết nối dữ liệu'` — đúng như khi cửa sổ **được dựng mới** ở `900×560` (đo được cardW 389, label 319, không cắt).
- **Nguyên nhân:** `ui/responsive_row.py::ResponsiveGrid._relayout` chỉ đặt `setColumnStretch(column, 1)` cho `range(target)`; khi giảm từ 4 cột xuống 2 cột, **stretch của cột 2–3 còn sót**, nên phần bề ngang dư bị chia cho cả bốn cột và hai cột không có item vẫn chiếm chỗ.
- **Ảnh hưởng:** chỉ Dashboard dùng `ResponsiveGrid(stretch=True)`. `ResponsiveRow` và `ResponsiveGrid(stretch=False)` (Scanner, Orders) **không** bị — đã đo lại: thanh Scanner wrap đúng 2 hàng ở cả đường resize lẫn đường dựng mới.
- **Hệ quả contract:** vi phạm "Dashboard … không cắt card" (R3.3) và "resize … không clip", nhưng chỉ trên **đường resize**, không phải đường khởi động.

### 10.4 Native chart smoke (Scanner Detail, WebEngine thật)

4/4 cell (`1280×720` và `900×560` × dark/light): `platform=windows`, `HAS_WEBENGINE=True`, trang load xong, `AnalysisChartWebView` hiện (**không** fallback), 7 canvas, empty/error ẩn, `theme_ok` + `ink_ok`, Entry/SL/TP đọc được (`Đã xác nhận` / `1.23489` / `1.24550`), `control_issues=0`, và `smc_caption == ''` trên H1 ⇒ H1 execution view không có SMC overlay.

Repo smoke `scripts/smc_ui_smoke.py` (Scanner → Detail → Chart, light/dark): 7 trạng thái, 56/56 `theme_ok`/`ink_ok`, `failures=[]`.

### 10.5 Inventory dialog ở viewport hợp đồng (không sửa dialog nào)

11 dialog dựng được, đo ở `900×560` (toạ độ nút thấp nhất trong dialog so với chiều cao màn hình, và bề ngang dialog so với màn hình):

| Dialog | size | nút thấp nhất y | Kết luận |
|---|---|---|---|
| Scanner Detail "Xem đầy đủ" | 1040×680 | 663 | ngoài màn hình (cao + rộng) |
| Scanner "Giải thích cột" | 1040×680 | 663 | ngoài màn hình (cao + rộng) |
| Dashboard "Trợ giúp chỉ số" | 960×680 | 655 | ngoài màn hình (cao + rộng) |
| Scanner "Bản tin thị trường" | 850×650 | 629 | ngoài màn hình (cao) |
| Scanner "Kế hoạch lệnh" | 980×620 | 599 | ngoài màn hình (cao + rộng) |
| Orders "Trailing Stop" | 650×626 | 601 | ngoài màn hình (cao) |
| Scanner "Giải thích dòng" | 880×600 | 579 | ngoài màn hình (cao) |
| Journal "Giải thích chỉ số" | 920×620 | 603 | ngoài màn hình (cao + rộng) |
| Dashboard headline / event | 750×480 / 750×520 | 455 / 495 | trong màn hình ✓ |
| Scanner "Chọn mã quét" | 560×520 | 503 | trong màn hình ✓ |

Đây là bằng chứng đo được rằng ở viewport compact, hàng nút của **8 dialog** nằm ngoài màn hình (dialog không co được dưới minimum của nó). Theo contract R3.4, dialog chỉ vào phạm vi khi đã chứng minh chặn hoàn thành tác vụ — Tech Lead cần chốt có mở lô riêng hay không. R4 **không sửa dialog nào**.

### 10.6 Audit, targeted và full suite

| Hạng mục | Kết quả |
|---|---|
| `ui_style_audit --check` | exit 0 — trong baseline, không đổi lock |
| `ui_density_audit --check --validate-contract` | exit 0 — trong baseline + runtime contract hợp lệ |
| `ui_layout_audit --write <R4>/layout-audit.json` | 252 checks, **0 issues** |
| Targeted UI (process sạch, env mặc định) | R3 34, R2 31, toolbar 2, rerender 4, notice 9, chart refresh 10, chart zone 6, H1 35, R1 28 + 18, density phase5/6 3 + 2, style phase7 5 — tất cả đạt |
| Native chart smoke | 4/4 cell, `failures=[]` |
| Repo smoke Scanner → Detail → Chart | 7 trạng thái × 2 theme, `failures=[]` |
| `git diff --check` | exit 0; index rỗng; R4 không sửa file repo nào |
| **Full suite** `python -m pytest -q` | **6 failed / 4868 passed / 7 skipped / 16 xfailed / 0 errors** (451.39s) |

**Delta so baseline Tech Lead nêu (`4 failed / 4870 passed / 7 skipped / 16 xfailed / 0 errors`):** tổng thu thập **giống hệt** (`4897`); khác biệt nằm trọn trong nhóm FRED — lần này 6 node `tests/test_step3_fred.py` fail thay vì 4: `test_load_fallback_returns_currencies`, `test_get_latest_rates_no_key_uses_fallback`, `test_get_latest_rates_empty_key_uses_fallback`, `test_get_latest_rates_cache_works`, `test_get_latest_rates_bad_key_falls_back`, `test_get_latest_rates_fred_exception_falls_back` — cùng nguyên nhân `config/interest_rates.json` bị gitignore và không tồn tại, số node dao động theo cache/process như đã ghi ở §5.4/§7.5/§8.4. **Không có failure/error mới ngoài nhóm FRED.**

### 10.7 Deferred cần Tech Lead quyết

1. **F-R4-01** (§10.3) — nếu mở scope thì sửa một dòng trong `ResponsiveGrid._relayout` (reset stretch cho các cột không còn dùng) kèm test hành vi cho đường resize.
2. **8 dialog ở §10.5** — có mở lô dialog riêng không; R4 chỉ báo cáo.
3. **Style guide chưa ghi ma trận logical viewport**: contract rule 5 yêu cầu bổ sung `1280×720`, `1366×768`, `1920×1080` và compact `900×560` vào ma trận audit trong `docs/ui/style-guide.md`, nhưng §R4.4 chỉ cho cập nhật style guide khi ma trận audit **thực tế** thay đổi (R4 không đổi tool) → R4 không sửa; cần quyết định.
4. Deferred cũ vẫn mở: chart compact cần cuộn dọc (F-R2-01), toolbar Scanner wrap ở `1150–1219` (R2), Dashboard compact phải cuộn dọc và Settings compact cuộn ngang ~20px (R3), bề ngang tối thiểu của tab "Quản lý lệnh" (F-R3-01).

## Review độc lập Tech Lead R4 (2026-09-19) — CHANGES_REQUESTED

**F-R4-01 — `ResponsiveGrid` để lại stretch cột không còn dùng sau resize.** Tái lập độc lập với fake app/offscreen: dựng MainWindow tại `1920×1080`, route Dashboard, rồi resize logical về `900×560`. `status_grid.column_count()` đổi đúng sang 2 nhưng bốn card chỉ còn **285px**, detail label **215px** và bị elide; dựng Dashboard mới ngay tại `900×560` cho card **569–570px**, detail **499–500px** và text đầy đủ. Root cause xác nhận ở `ui/responsive_row.py:390–410`: `_relayout()` chỉ đặt stretch cho `range(target)`, vì vậy khi grid từ 4 sang 2 cột, stretch cột 2–3 còn tồn tại và Qt chia phần dư cho bốn cột. Đây là regression Dashboard `stretch=True` trên đường resize, vi phạm R3.3/R4 route lifecycle; không phải failure assertion đơn lẻ. `ResponsiveRow` và Orders `stretch=False` không thuộc root cause này.

**Gói sửa bắt buộc.** Reset stretch của mọi cột mà `ResponsiveGrid` đã có thể sử dụng trước khi áp stretch cho active columns, hoặc cơ chế tương đương không để state layout cũ tồn tại. Bổ sung test behavior `wide → compact → wide` cho grid generic và Dashboard thật, light/dark, đối chiếu với dựng mới compact: card/detail không bị elide, cột không dùng không nhận stretch. Giữ nguyên behavior `stretch=False`, hidden widget handling, Scanner/Chart/SMC/MT5/trading/cache/persistence/policy/dialog/golden/skip/xfail/lock. Chạy targeted fresh process, smoke/audit, `git diff --check`, full suite; đối chiếu tổng `4897` và từng node FRED thay vì giả định số failure cố định.

**Dialog decision.** Inventory R4 xác nhận 8 dialog candidate có hàng nút ngoài `900×560`; đây là một root cause/ownership khác, không gộp vào F-R4-01. Tech Lead **chấp thuận mở F-R4-02 Dialog reachability sau khi F-R4-01 REVIEW PASS**. Gói đó phải trước hết tái lập từng action completion/keyboard path và caller/source map cho 8 dialog nêu tại §10.5, rồi mới sửa các dialog thực sự chặn hoàn thành tác vụ. Không thay dialog trong F-R4-01.

**Style-guide decision.** Không cập nhật `docs/ui/style-guide.md` trong F-R4-01: R4 không thay audit matrix/tool, còn bốn logical viewport là contract đã nằm trong `docs/ui/screen_design.md` và kế hoạch này. Chỉ mở cập nhật style guide khi một audit thực tế bắt đầu tiêu thụ hoặc thay đổi matrix đó.

**Gate:** R4 chưa REVIEW PASS; không có bước sau R4 và không commit/reset/xóa/push.

## 11. Bàn giao F-R4-01 — stale column stretch trong ResponsiveGrid (2026-09-19)

**Trạng thái:** F-R4-01 IMPLEMENTED — WAITING_REVIEW. R4 vẫn chưa REVIEW PASS; F-R4-02 (dialog) chưa thực hiện; không commit/reset/xoá/push.

### 11.1 Snapshot và phạm vi

`HEAD = 64d9228`; index rỗng; `git diff --check` đạt trước và sau. Chỉ chạm `ui/responsive_row.py` (6 dòng trong `ResponsiveGrid._relayout`) và `tests/test_responsive_r3_screens_layout.py` (+4 test), cùng tài liệu này. Không đụng Dashboard business/data logic, `ResponsiveGrid(stretch=False)`, hidden-widget handling, `ResponsiveRow`, Orders, dialog, Chart, SMC, MT5, trading, cache, persistence, policy, golden/skip/xfail hay lock.

### 11.2 Sửa

```python
# Xoá stretch của MỌI cột lưới từng dùng trước khi áp cho các cột đang hoạt động.
for column in range(max(self._columns, self._compact_columns) + 1):
    self._grid.setColumnStretch(column, 0)
for column in range(target):
    self._grid.setColumnStretch(column, 1 if self._stretch else 0)
```

Trước đây chỉ `range(target)` được đặt stretch, nên khi lưới Dashboard giảm 4 → 2 cột, stretch của cột 2–3 còn sót và Qt chia phần bề ngang dư cho cả bốn cột ⇒ thẻ chỉ còn 195px thay vì 389px và nhãn bị elide.

### 11.3 Kiểm chứng

Input tái lập (MainWindow → Dashboard ở `1920×1080` → resize `900×560`), đo trước/sau và so với Dashboard **dựng mới** ở cùng viewport:

| Trạng thái | cols | cardW | labelW | elide |
|---|---|---|---|---|
| Trước sửa, 900 sau resize | 2 | 195 | 125 | **có** |
| Sau sửa, 900 sau resize | 2 | **389** | **319** | không |
| Dashboard dựng mới tại 900 (tham chiếu) | 2 | 389 | 319 | không |
| Sau sửa, 1920 trở lại | 4 | 449 | 379 | không |
| Dựng mới tại 1920 (tham chiếu) | 4 | 449 | 379 | không |

`columnStretch` sau khi về 4 cột: `[1, 1, 1, 1, 0, 0]` — cột không dùng có stretch 0.

Matrix R4 chạy lại trong thư mục versioned mới (`%TEMP%\aima-r4\<timestamp>-postfix\evidence\`): **56 cell, chỉ còn 2 cell có issue** — đúng hai cell Settings × dark/light ở `900×560` với 22px tràn `qt_tabwidget_stackedwidget` nằm trong vùng cuộn (đã ghi từ R3). **Không còn cell Dashboard nào bị cắt nhãn**; rail 48px, minimum `800×500`, `failures=[]`.

### 11.4 Regression test mới (4 node)

1. `test_grid_clears_stale_column_stretch_across_resizes` — generic `stretch=True`: wide → compact → wide; khẳng định cột đang dùng có stretch 1 và nhận trọn phần dư, cột không dùng stretch **0**, và quay lại desktop trùng bề ngang dựng mới.
2. `test_dashboard_after_resize_matches_a_fresh_compact_build[dark|light]` — Dashboard thật: resize `1920×1080` → `900×560` cho kết quả **khớp dựng mới compact** (số cột, bề ngang thẻ, không elide), rồi quay lại desktop vẫn không elide.
3. `test_orders_button_grid_keeps_zero_stretch` — xác nhận `stretch=False` (Orders) giữ mọi cột stretch 0 và không đổi.

### 11.5 Kết quả chạy

| Hạng mục | Kết quả |
|---|---|
| `tests/test_responsive_r3_screens_layout.py` | **38 passed** (34 cũ + 4 mới) |
| R2 + Scanner/Detail/notice + Chart + H1 + R1 + dashboard regressions (process sạch) | 31 + 2 + 4 + 9 + 10 + 6 + 35 + 28 + 18 + 1 + 9 — đạt |
| UI smoke light/dark (`QT_QPA_PLATFORM=windows`, out-dir temp) | 7 trạng thái × 2 theme, `failures=[]`, 56/56 `theme_ok`/`ink_ok` |
| `ui_style_audit --check` / `ui_density_audit --check --validate-contract` | exit 0 / exit 0 — không đổi lock |
| `git diff --check` | exit 0; index rỗng |
| **Full suite** `python -m pytest -q` | **6 failed / 4872 passed / 7 skipped / 16 xfailed / 0 errors** (443.73s) |

**Delta so tổng collection 4897 (F-R3-01):** `4897 → 4901` = **+4 đúng bằng 4 test mới**; `passed 4868 → 4872` (+4); tập failure **không đổi** — đúng 6 node `tests/test_step3_fred.py`: `test_load_fallback_returns_currencies`, `test_get_latest_rates_no_key_uses_fallback`, `test_get_latest_rates_empty_key_uses_fallback`, `test_get_latest_rates_cache_works`, `test_get_latest_rates_bad_key_falls_back`, `test_get_latest_rates_fred_exception_falls_back` (cùng do `config/interest_rates.json` bị gitignore). Không failure/error mới ngoài tập FRED.

## Review độc lập Tech Lead F-R4-01 (2026-09-19) — REVIEW PASS, mở F-R4-02

**Scope/evidence.** Diff F-R4-01 chỉ xử lý state stretch cũ trong `ResponsiveGrid` và bốn regression test. Tái lập độc lập `1920×1080 → 900×560` nay cho Dashboard 2 cột với card `569–570px`, detail `499–500px`, không elide, stretch `[1, 1, 0, 0, 0, 0]`; resize lại desktop trả `[1, 1, 1, 1, 0, 0]` và card `449px`. Không đổi Dashboard data/business logic, `stretch=False`, `ResponsiveRow` hay các vùng cấm. Targeted fresh-process đạt **193 passed**; smoke light/dark `failures=0`; style/density audit và `git diff --check` đạt.

**Baseline delta.** Full suite độc lập sau sửa: **6 failed / 4872 passed / 7 skipped / 16 xfailed / 0 errors** trong 461.78s. Tổng `4901` tăng đúng bốn test so với `4897`; sáu failure chính xác là sáu node FRED đã biết, không có failure/error mới.

**Quyết định.** F-R4-01 **REVIEW PASS**. Mở **F-R4-02 Dialog reachability** theo decision §10: rà caller/source và completion path thực của tám dialog candidate ở `900×560`, chỉ sửa dialog đã chứng minh chặn hoàn thành tác vụ. R4 tổng thể vẫn **WAITING_REVIEW** cho tới F-R4-02; không commit/reset/xóa/push.

## 12. Bàn giao F-R4-02 — dialog reachability tại viewport compact (2026-09-19)

**Trạng thái:** F-R4-02 IMPLEMENTED — WAITING_REVIEW. R4 vẫn chưa REVIEW PASS; không commit/reset/xoá/push.

### 12.1 Snapshot và phạm vi

`HEAD = 64d9228`; index rỗng; `git diff --check` đạt trước và sau. Chỉ chạm `ui/screens/orders_screen.py` (dialog Trailing Stop), `ui/layout_system.py` (thêm hàm thuần `dialog_body_height`) và `tests/test_responsive_r3_screens_layout.py` (+4 test). Không đụng dialog khác, logic Scanner/Orders/Journal/Dashboard, trading, MT5, cache, persistence, Chart/SMC, policy, golden/skip/xfail hay lock.

### 12.2 Pha 1 — caller/source map và đo native

| # | Dialog | Class / factory | Hành động chính | Đóng/Huỷ | Đường bàn phím |
|---|---|---|---|---|---|
| 1 | Scanner Detail "Xem đầy đủ" | `ScannerDetailScreen._show_scan_detail_dialog` (scanner_detail_screen.py:820) | cuộn nội dung | `Đóng` | `Đóng` là nút mặc định + Escape |
| 2 | Scanner "Giải thích cột" | `ScannerColumnsHelpDialog` (scanner_screen.py:3146) qua `_show_columns_help` (:1636) | đọc bảng | `Đóng` | mặc định + Escape |
| 3 | Scanner "Giải thích dòng" | `ScannerRowExplanationDialog` (:2354) qua `_show_columns_help` khi có dòng chọn (:1641) | đọc | `Đóng` | mặc định + Escape |
| 4 | Dashboard "Trợ giúp chỉ số" | `DashboardScreen._show_market_help` (dashboard_screen.py:1585) | `Phân tích AI` | `Đóng` | `Phân tích AI` là nút mặc định + Escape |
| 5 | Scanner "Bản tin thị trường" | `_show_market_brief` → `_show_market_brief_impl` (scanner_screen.py:2008/2015) | `Sao chép` | `Đóng` | mặc định + Escape; thân có vùng cuộn |
| 6 | Scanner "Kế hoạch lệnh" | `_show_orders_dialog` (:1108) | đọc bảng lệnh | `Đóng` | Escape (nút mặc định `Đã có lệnh` đang disabled) |
| 7 | **Orders "Trailing Stop"** | `_show_trailing_dialog` (orders_screen.py:830) | `Bật/Cập nhật/Tắt Trailing Stop` | `Đóng` | nút mặc định là nút trợ giúp `?` ⇒ Enter **không** hoàn thành hành động |
| 8 | Journal "Giải thích chỉ số" | `MetricsExplanationDialog` (journal_screen.py:2019) qua :1475 | đọc | `Đóng` | mặc định + Escape |

Đo native (platform Windows) cho cả 11 dialog dựng được qua chính đường code của app, mô phỏng màn hình `900×560`:

| Dialog | size | nút thấp nhất y | nút phải nhất x | Escape đóng | nút mặc định | vùng cuộn |
|---|---|---|---|---|---|---|
| Scanner Detail "Xem đầy đủ" | 1040×680 | 664 | 1020 | ✓ | `Đóng` | 1 |
| Dashboard "Trợ giúp chỉ số" | 960×680 | 656 | 936 | ✓ | `Phân tích AI` | 0 |
| Dashboard headline | 750×480 | 456 | 726 | ✓ | `Tóm tắt AI` | 0 |
| Dashboard event | 750×520 | 496 | 726 | ✓ | `Xem tác động` | 0 |
| Scanner "Bản tin thị trường" | 850×650 | 630 | 826 | ✓ | `Sao chép` | 1 |
| Scanner "Kế hoạch lệnh" | 980×620 | 600 | 960 | ✓ | `Đã có lệnh` (disabled) | 0 |
| **Orders "Trailing Stop"** | 650×629 | **605** | 626 | ✓ | `?` | **0** |
| Scanner "Chọn mã quét" | 560×520 | 504 | 540 | ✓ | `Chọn tất cả khả dụng` | 1 |
| Scanner "Giải thích dòng" | 880×600 | 580 | 860 | ✓ | `Đóng` | 0 |
| Scanner "Giải thích cột" | 1040×680 | 664 | 1020 | ✓ | `Đóng` | 0 |
| Journal "Giải thích chỉ số" | 920×620 | 604 | 900 | ✓ | `Đóng` | 0 |

**Kết luận Pha 1:** mọi dialog đều có đường Escape để huỷ, và 10/11 có nút mặc định để hoàn thành bằng Enter kể cả khi nút nằm ngoài màn hình; các dialog nội dung dài có vùng cuộn nội bộ hoặc nút mặc định `Đóng`. **Chỉ một dialog thực sự chặn hoàn thành tác vụ**: Orders "Trailing Stop" — `minimumSizeHint` cao 629 > 560 (không co được), không có vùng cuộn, và **nút mặc định là nút trợ giúp `?`** nên Enter không kích hoạt `Bật/Cập nhật/Tắt Trailing Stop` (nút này ở y=581–605, ngoài màn hình). Bảy dialog còn lại **không sửa** vì vẫn hoàn thành/huỷ được bằng đường đã nêu.

### 12.3 Pha 2 — remediation cho dialog đã xác minh

`ui/screens/orders_screen.py::_show_trailing_dialog`:

1. Thân dialog (tiêu đề + 3 card + phần xem trước) đặt trong `DialogBodyScroll` (`objectName` `TrailingDialogScroll`); hàng nút vẫn nằm ngoài vùng cuộn nên **luôn trong tầm nhìn**.
2. `ui/layout_system.py::DialogBodyScroll` — `QScrollArea` có `sizeHint()` cao theo nội dung nhưng kẹp theo `QScreen.availableGeometry().height()` (logical pixel) qua hàm thuần `dialog_body_height(desired, available)` (sàn 240, chừa 160 cho lề + hàng nút). `minimumSizeHint()` trả sàn nhỏ nên dialog co được trên màn hình thấp.
3. `dlg.adjustSize()` trước `dlg.exec()` để dialog nhận đúng `sizeHint` sau khi đã dựng đủ nội dung.

Không dùng độ phân giải vật lý, `devicePixelRatio`, fixed fullscreen, monkey-patch toàn cục `QDialog`, và **không** gọi API chiều cao bị density audit gác (`setFixedHeight`/`setMinimumHeight`/`setMinimumSize`…) — nên không phát sinh deviation lock.

### 12.4 Kiểm chứng

| Hạng mục | Trước | Sau |
|---|---|---|
| Hàng nút ở màn hình compact | y=605 > 560, không nút mặc định tương ứng, không vùng cuộn ⇒ **chặn hoàn thành** | nằm **ngoài vùng cuộn** ⇒ luôn thấy; thân cuộn thay vì đẩy nút ra ngoài |
| `sizeHint` của dialog | 629 (không co được: minimum = 629) | 629 khi màn hình đủ chỗ; trên màn hình `available=560` công thức cho thân **400** ⇒ tổng ≤ 560 |
| Desktop (native, available 1920×1032) | 650×629, không thanh cuộn | **650×629, không thanh cuộn** (giữ nguyên) |
| `dialog_body_height` | — | `(626,560)=400`, `(626,688)=528`, `(626,1080)=626`, `(626,0)=626`, `(300,560)=300`, `(626,200)=240` |

Test mới (4 node): `test_dialog_body_height_clamps_to_the_work_area`, `test_trailing_dialog_keeps_its_action_row_reachable[1280×720|900×560]` (nút hành động nằm ngoài vùng cuộn, dialog lọt vùng làm việc, chrome + thân compact ≤ 560), `test_trailing_dialog_shows_everything_at_desktop` (đủ chỗ ⇒ không thanh cuộn).

**Ghi chú môi trường:** `QWidget.adjustSize()` bị Qt kẹp còn 2/3 màn hình, nên trên platform offscreen (màn hình 800×800) dialog mở ở 533 và có thanh cuộn; trên màn hình desktop thật (1920×1032) dialog mở đúng 629 và **không** thanh cuộn — đã đo native.

### 12.5 Deviations

Không còn deviation: `ui_density_audit --check` và `--validate-contract` đều exit 0, lock không đổi.

### 12.6 Full suite và đối chiếu node

| Lần | Kết quả | Node fail |
|---|---|---|
| 1 | `6 failed / 4876 passed / 7 skipped / 16 xfailed / 0 errors` (379.22s) | 5 node `tests/test_step3_fred.py` + **1 node ngoài FRED**: `tests/test_scanner_toolbar_layout.py::test_scanner_starts_in_manual_mode_without_scheduling_a_scan` |
| 2 | `6 failed / 4876 passed / 7 skipped / 16 xfailed / 0 errors` (440.59s) | đúng 6 node `tests/test_step3_fred.py`, **không còn node ngoài FRED** |

- Tổng thu thập `4897 → 4905` = **+8**? Không: collection hiện tại `4905` so với `4901` của F-R4-01 ⇒ **+4 đúng bằng 4 test mới**, `passed 4872 → 4876` (+4).
- Sáu node FRED (liệt kê exact theo lần 2): `test_load_fallback_returns_currencies`, `test_get_latest_rates_no_key_uses_fallback`, `test_get_latest_rates_empty_key_uses_fallback`, `test_get_latest_rates_cache_works`, `test_get_latest_rates_bad_key_falls_back`, `test_get_latest_rates_fred_exception_falls_back`.
- Node `test_scanner_starts_in_manual_mode_without_scheduling_a_scan` ở lần 1 **không tái lập**: chạy trong process sạch 2/2 đạt và lần suite thứ hai không xuất hiện ⇒ flake theo thứ tự thu thập, không phải regression của F-R4-02 (thay đổi chỉ chạm dialog Trailing Stop và `ui/layout_system.py`, không chạm Scanner hay timer).
- Smoke Scanner→Detail→Chart light/dark: 7 trạng thái, `failures=[]`. `ui_style_audit --check`, `ui_density_audit --check --validate-contract`, `git diff --check`: exit 0. Artifact: `%TEMP%\aima-r4\<timestamp>-fr402b\` (dialog probe + ảnh + smoke) và `…-fr402\` (probe một phần).

## Review độc lập Tech Lead F-R4-02 (2026-09-19) — REVIEW PASS

**Phạm vi và evidence.** Review xác nhận F-R4-02 chỉ xử lý dialog Orders “Trailing Stop”: thân dialog nằm trong `DialogBodyScroll`, action row ở ngoài vùng cuộn. Tái lập trực tiếp tại app `900×560`: dialog cao `533px`, vùng thân có `vmax=93`, hai nút “Bật Trailing Stop” và “Đóng” ở `y=485` trong dialog. Desktop vẫn giữ hình dáng đầy đủ. Không chạm bảy dialog candidate còn lại, Scanner/Chart/SMC/MT5/trading/cache/persistence/policy, golden, skip/xfail hoặc lock.

**Kiểm chứng độc lập.** Targeted `tests/test_responsive_r3_screens_layout.py -q`: **42 passed**. Smoke Scanner→Detail→Chart light/dark: `failures=[]`, mọi capture có `theme_ok`/`ink_ok`; artifact ngoài repo tại `%TEMP%\aima-techlead-fr402-20260919-201523`. `ui_style_audit --check`, `ui_density_audit --check --validate-contract`, và `git diff --check` đều đạt (chỉ warning LF→CRLF của Git).

**Baseline delta.** Full suite process sạch: **6 failed / 4876 passed / 7 skipped / 16 xfailed / 0 errors** trong **462.81s**. Collection `4905` tăng đúng bốn test so với F-R4-01 (`4901`); sáu failure trùng chính xác sáu node FRED (`test_load_fallback_returns_currencies`, `test_get_latest_rates_no_key_uses_fallback`, `test_get_latest_rates_empty_key_uses_fallback`, `test_get_latest_rates_cache_works`, `test_get_latest_rates_bad_key_falls_back`, `test_get_latest_rates_fred_exception_falls_back`). Không có failure/error mới.

**Quyết định.** F-R4-02 **REVIEW PASS**. Điều kiện R4 (route/lifecycle matrix, Dashboard resize F-R4-01, và dialog reachability F-R4-02) đã hoàn tất, nên **R4 REVIEW PASS**. Các mục deferred giữ nguyên và không tự mở lô mới: chart compact cuộn dọc; Scanner wrap `1150–1219`; Dashboard compact cuộn dọc; Settings compact cuộn ngang/tab “Quản lý lệnh”; chuẩn hoá bảy dialog còn lại; và ma trận logical viewport trong style guide. Không commit/reset/xoá/push.

## 13. Bàn giao F-R5-01 — restore geometry “giả maximized” (2026-09-19)

**Trạng thái:** `F-R5-01 IMPLEMENTED — WAITING_REVIEW`. R4 đã REVIEW PASS; đây là lô follow-up độc lập, không mở lô khác và không commit/reset/xoá/push.

### 13.1 Snapshot và diff boundary

`HEAD = 64d9228`; index **rỗng**; `git diff --check` exit 0 **trước và sau** (chỉ warning LF→CRLF của Git). Danh sách file trong worktree trước và sau **giống hệt nhau** — lô này không tạo file mới, chỉ sửa file trong phạm vi được duyệt.

| File | Trạng thái git | Delta của lô | Hash sau (sha256/16) |
|---|---|---|---|
| `ui/window_state.py` | untracked (tạo ở R1) | +2 hằng số (`DEFAULT_CHROME_INSET`, `FAUX_MAXIMIZED_COVERAGE_RATIO`), +1 reason code, +3 hàm thuần, +tham số `chrome_inset` và +1 nhánh quyết định; cập nhật docstring module và bảng quyết định. File hiện tại **417 dòng** (không có bản lưu trước để so số dòng) | `741d6479d35429fb` |
| `ui/main_window.py` | tracked, đang M | **+26 / −0** (1 import `QStyle`, `_title_bar_inset()`, 5 dòng docstring, 1 dòng `chrome_inset=…`) | `a6c8d93b797bb92a` |
| `tests/test_window_state_policy.py` | untracked (tạo ở R1) | +9 node (28 → 37) | `901137370e62101b` |
| `tests/test_main_window_startup_policy.py` | untracked (tạo ở R1) | +4 node (18 → 22) | `d66b83418c0e7bd9` |
| `docs/plans/ui-responsive-window-implementation-plan.md` | untracked | mục §13 này | `ace50c5ab9eb6050`‡ |

**Mốc so sánh cho file untracked.** `ui/window_state.py` và hai file test chưa từng được commit nên không có bản lưu nào để đối chiếu byte; `git diff` cũng không hiển thị chúng. Mốc “trước sửa” của lô này là **bản dựng lại chức năng** ở `%TEMP%\aima-fr501\window_state_prefix.py`: mã của mọi hàm/hằng y hệt bản gốc (kiểm chứng bằng diff — chỉ khác phần docstring đã rút gọn và docstring của chính harness), nên **hash của nó không phải hash bản gốc** và không được dùng làm mốc byte; nó chỉ dùng để chạy probe trước/sau ở §13.2. Tech Lead đối chiếu `ui/window_state.py` hiện tại bằng cách đọc trực tiếp.

**Với `ui/main_window.py`** (tracked) delta được tách bằng cách đảo đúng bốn sửa đổi của lô để dựng lại nội dung trước sửa (`%TEMP%\aima-fr501\main_window_prefix.py`, LF-normalized) rồi diff từng dòng — kết quả in ra ở `%TEMP%\aima-fr501\` là **+26 / −0** và chỉ chứa bốn sửa đổi nêu trên. Hash trước của riêng file này tính theo LF (`d538e239ce5bfbab`), không phải byte CRLF trên đĩa.


`‡` Hash của tài liệu này tính **trước** khi mục §13 được thêm vào.

**Không chạm:** screen/layout Scanner, Chart (kể cả `assets/chart/index.html`), SMC, H1, MT5, trading, cache, persistence nghiệp vụ, policy ngoài window state, golden, skip/xfail, lock/audit baseline. Không gộp hay sửa diff UI Chart/H1/R1–R4 đang có.

### 13.2 Root cause, state thật và input tái lập

**Input tái lập (đúng như Tech Lead nêu):** máy 1920×1200 @150% ⇒ vùng làm việc logical `1280×760`; state đã lưu `QRect(30, 0, 1250, 752)`, `maximized=False`.

| Đại lượng | Giá trị |
|---|---|
| `availableGeometry` logical | `(0, 0, 1280, 760)` |
| rect đã lưu | `(30, 0, 1250, 752)`, `maximized=False` |
| độ phủ | **97.7% bề ngang × 99.0% bề cao** |
| lệch mép trên | **0px** (áp sát mép trên vùng làm việc) |

Chạy cùng input qua bản dựng lại trước sửa và qua mã hiện tại:

| | `maximized` | `rect` | `reason` |
|---|---|---|---|
| **Trước F-R5-01** | `False` | `QRect(30, 0, 1250, 752)` | `saved-normal` |
| **Sau F-R5-01** | `True` | `None` | `faux-maximized-normal` |

**Cơ chế (đo native, không suy đoán).** Khi client area áp sát mép trên vùng làm việc, khung cửa sổ của OS nằm **phía trên** vùng đó: đo trên platform Windows cho state cũ `geometry=(30, 0, 1250, 752)` nhưng `frameGeometry=(30, −30, 1250, 782)` ⇒ **toàn bộ caption + nút hệ thống nằm ngoài màn hình 30px logical**. Đó chính là “title bar/nút maximize không thao tác được”: cửa sổ trông như maximized (phủ 98–99% vùng làm việc) nhưng state là normal, nên OS vẽ khung như cửa sổ thường và đẩy khung lên trên mép màn hình.

Sáu lớp quyết định bất biến được chạy lại trước/sau và **giữ nguyên**: first launch, saved maximized, off-screen, no-available-geometry, cửa sổ normal giữa màn hình, và clamp khi đổi monitor.

### 13.3 Quyết định/algorithm

Chỉ thêm **một nhánh** vào bảng quyết định; các nhánh cũ không đổi thứ tự tương đối:

| # | Điều kiện | Hành vi | `reason` |
|---|---|---|---|
| 1 | Caller xin `normal_window=True` (test/dev) | cửa sổ normal tường minh | `dev-normal-window` |
| 2 | Không có state | maximize | `first-launch` |
| 3 | Không có `availableGeometry` hợp lệ | maximize | `no-available-geometry` |
| 4 | State hỏng/thiếu/sai kiểu/nhỏ hơn minimum | maximize | `invalid-state` |
| 5 | Lần đóng trước ở maximized | maximize | `saved-maximized` |
| 6 | Geometry không còn ≥25% diện tích **hoặc** giao < 160×120 | maximize | `off-screen` |
| **7** | **Sau khi kẹp: chạm dải chrome trên VÀ phủ ≥95% cả hai chiều** | **maximize** | **`faux-maximized-normal`** |
| 8 | Hợp lệ nhưng lệch (đổi monitor/DPI) | kẹp vào `availableGeometry`, giữ kích thước | `clamped-to-available` |
| 9 | Còn lại | khôi phục đúng geometry | `saved-normal` |

API mới trong `ui/window_state.py` (tên tường minh, kiểm tra được độc lập):

```python
DEFAULT_CHROME_INSET = 0            # 0 = "không có tri thức nền tảng", KHÔNG hard-code DPI
FAUX_MAXIMIZED_COVERAGE_RATIO = 0.95
REASON_FAUX_MAXIMIZED = "faux-maximized-normal"

covers_work_area(rect, available, *, coverage=...)          # điều kiện "phủ gần toàn"
violates_top_chrome(rect, available, *, chrome_inset=...)   # điều kiện "chạm dải chrome trên"
is_faux_maximized_normal_rect(rect, available, *, chrome_inset=..., coverage=...)
resolve_startup(..., chrome_inset: int = DEFAULT_CHROME_INSET)
```

`chrome_inset` là chiều cao title bar **logical pixel** do caller truyền vào; `MainWindow._title_bar_inset()` đọc `QStyle.PixelMetric.PM_TitleBarHeight` (đo được: **21** trên desktop Windows, **24** trên platform offscreen) rồi truyền tường minh, nên `resolve_startup()` vẫn thuần/deterministic và không hard-code 30/32px.

**Hai quyết định thiết kế đáng review:**

1. **Kiểm tra trên geometry SAU khi kẹp, không phải rect thô.** Kẹp một state cao hơn vùng làm việc sẽ hạ mép trên xuống `available.top()` và phủ trọn vùng làm việc — tức chính nó tạo ra một cửa sổ faux-maximized. Nếu chỉ kiểm tra rect thô thì nhánh 8 vẫn trả về cửa sổ không thao tác được chrome. Đo được: `QRect(30, 40, 1220, 745)` trên vùng làm việc `1280×688` bị kẹp thành `(30, 0, 1220, 688)` ⇒ phải maximize.
2. **Phải thỏa cả hai điều kiện.** Chỉ chạm mép trên (cửa sổ nhỏ nằm sát trên) hoặc chỉ phủ rộng (còn chừa dải chrome) đều vẫn thao tác được ⇒ vẫn restore. Vì vậy `QRect(240, 120, 800, 520)` (giữa màn hình) và `QRect(0, 0, 800, 520)` (sát trên nhưng nhỏ) đều giữ `saved-normal`.

### 13.4 Test

`tests/test_window_state_policy.py`: 28 → **37 node** (9 node mới); `tests/test_main_window_startup_policy.py`: 18 → **22 node** (4 node mới). Tổng **+13 node**.

| Node mới | Chứng minh |
|---|---|
| `test_reported_state_is_faux_maximized_and_maximizes` | nghiệm thu 1 — đúng input `1280×760` + `(30,0,1250,752)`: `maximized=True`, `rect=None`, reason riêng; đúng cả khi `chrome_inset=0` và `=21` |
| `test_faux_maximized_requires_both_conditions` | cả hai điều kiện đều bắt buộc |
| `test_faux_maximized_uses_the_platform_chrome_inset` | metric nền tảng được tôn trọng: rect chừa 12px chỉ bị coi là faux khi inset > 12 |
| `test_covers_work_area_requires_both_dimensions` | ngưỡng 95% theo từng chiều, kể cả biên và vùng làm việc suy biến |
| `test_violates_top_chrome_counts_the_platform_band` | dải chrome tính theo inset; mặc định 0 vẫn bắt cửa sổ áp sát mép |
| `test_faux_maximized_reason_code_is_its_own` | reason mới không lẫn `invalid-state`/`off-screen`/`saved-normal`/`clamped` |
| `test_full_width_geometry_taller_than_the_work_area_maximizes` | state R0 `(0,0,1280,700)` trên vùng `1280×688` nay là faux ⇒ maximize |
| `test_clamping_never_produces_a_faux_maximized_window` | nhánh kẹp không được trả về cửa sổ faux |
| `test_genuinely_normal_window_is_still_restored` | nghiệm thu 2 — cửa sổ normal giữa màn hình vẫn `saved-normal`, `maximized=False` |
| `test_faux_maximized_saved_state_opens_maximized` | nghiệm thu 4 — **entry production** `MainWindow.apply_startup_policy()` gọi nhánh maximize cho state faux, `window.isMaximized() is True` |
| `test_startup_policy_uses_the_style_title_bar_metric` | metric thật từ `window.style()` được truyền vào policy (không hard-code, không cố định 0) |
| `test_genuinely_normal_saved_state_is_still_restored` | entry production vẫn restore đúng geometry normal |
| `test_full_coverage_geometry_taller_than_the_work_area_opens_maximized` | bản phủ trọn bề ngang của state R0 qua entry production |

**Hai node cũ đổi input để giữ nguyên bảo đảm (không đổi kỳ vọng):** `test_saved_geometry_taller_than_the_work_area_is_capped` và `test_full_hd_150_never_exceeds_the_available_height` dùng `900×700` thay `1280×700`. Bản `1280×700` là bản **phủ trọn bề ngang**, nay thuộc nhánh faux (đã có node riêng ở trên); bảo đảm gốc của hai node này — *app shell không bao giờ cao hơn vùng làm việc* — được giữ nguyên và vẫn khẳng định `decision.rect.height() == 688`, `window.height() <= 688`. Không node nào bị xoá hay đổi tên.

**Mutation check (test không rỗng).** Vô hiệu hoá nhánh mới (`is_faux_maximized_normal_rect` luôn trả `False` qua plugin `%TEMP%\aima-fr501\disable_faux_plugin.py`) rồi chạy lại hai file: **đúng 8 node fail** — chính các node khẳng định faux-maximized — và **51 node còn lại vẫn xanh**. Nghĩa là các test mới thực sự chứng minh quyết định runtime, còn các bất biến (restore/maximize/clamp) không phụ thuộc nhánh mới. Ở lần chạy đó, node `test_full_coverage_geometry_taller_than_the_work_area_opens_maximized` fail với kết quả trước sửa hiện nguyên hình: `StartupDecision(maximized=False, rect=QRect(0, 0, 1280, 688), reason='clamped-to-available')` — tức cửa sổ chạm mép trên và phủ trọn vùng làm việc vẫn bị restore.


### 13.5 Bằng chứng native/smoke

Native harness (`%TEMP%\aima-fr501\native_smoke_fr501.py`, platform **`windows`**, 2 cấu hình × 3 lớp state × 2 theme = **12 cell, `failures=[]`**):

| Cấu hình | Vùng làm việc logical | Lớp state | `reason` | client (native) | rail |
|---|---|---|---|---|---|
| màn hình thật | `(0,0,2560,1392)` dpr 1.5 | `literal` `(30,0,1250,752)` (phủ 49%×54%) | `saved-normal` — **không over-reach** | `(30, 0, 1250, 752)` y nguyên | 48 |
| màn hình thật | `(0,0,2560,1392)` | `fitted` `(30,0,2530,1392)` (98.8%×100%) | `faux-maximized-normal` | `(0, 23, 2560, 1369)` — phải/đáy áp sát vùng làm việc, phủ **98.4%** | 48 |
| màn hình thật | `(0,0,2560,1392)` | `centered` `(240,120,800,520)` | `saved-normal` | `(240, 120, 800, 520)` y nguyên | 48 |
| `QT_SCALE_FACTOR=2` (viewport hợp đồng) | `(0,0,1280,696)` dpr 3.0 | **`literal` `(30,0,1250,752)`** | **`faux-maximized-normal`** | `(0, 11, 1280, 685)` | 48 |
| `QT_SCALE_FACTOR=2` | `(0,0,1280,696)` | `fitted` `(30,0,1250,696)` | `faux-maximized-normal` | `(0, 11, 1280, 685)` | 48 |
| `QT_SCALE_FACTOR=2` | `(0,0,1280,696)` | `centered` `(240,120,800,520)` | `saved-normal` | `(240, 120, 800, 520)` y nguyên | 48 |

Cấu hình `QT_SCALE_FACTOR=2` biến panel 4K/150% thành **viewport logical 1280×696** — cùng bề ngang và cùng lớp với hợp đồng `1280×760`/`1280×752` — nên state **nguyên văn của người dùng** được đo ở đó: faux ⇒ maximize, shell lấp vùng làm việc (client phủ 98.4%, mép phải/đáy áp sát) và **rail vẫn 48px**. Cửa sổ maximized thật của Windows có client `(0, 23, …)` vì OS vẽ caption ở trên, và frame chỉ vượt vùng làm việc đúng viền resize vô hình (đo: 7px) — tiêu chí “lấp available work area” được kiểm đúng theo ngữ nghĩa native này.

| Hạng mục khác | Kết quả |
|---|---|
| Repo native UI smoke Scanner→Detail→Chart light/dark (`QT_QPA_PLATFORM=windows`) | **exit 0**, `failures=[]` (7 trạng thái × 2 theme) |
| `ui_style_audit --check docs/ui/style/ui-style-lock.json` | exit 0 — trong baseline |
| `ui_density_audit --check docs/ui/density/ui-density-lock.json --validate-contract` | exit 0 — trong baseline + runtime contract hợp lệ |
| Targeted `tests/test_window_state_policy.py tests/test_main_window_startup_policy.py` | **59 passed** (46 → 59 = +13) |
| `git diff --check` | exit 0; index rỗng |

**Deviation của lô này — bề mặt WebEngine native.** Harness native phải đặt `HAS_WEBENGINE=False` (nhánh suy giảm có sẵn của `ui/components/chart_view.py`, chart hiển thị nhãn thông báo) vì `QWebEngineView` native **fast-fail `0xC0000409`** khi dựng `MainWindow` trong môi trường harness: tái lập được khi dựng **riêng** `ScannerDetailScreen(...)` trên platform Windows, khi `ui/window_state.py` không nằm trên đường đó và `apply_startup_policy` chưa từng được gọi ⇒ điều kiện có trước, ngoài phạm vi F-R5-01. Phép đo ở bảng trên là của **app shell** (geometry cửa sổ + rail), không phải của chart, và repo smoke — vốn dựng chart thật — vẫn đạt exit 0. Không sửa `ui/screens/scanner_detail_screen.py`, `ui/components/chart_view.py` hay `assets/chart/index.html`.

### 13.6 Full suite và đối chiếu node

| Lần | Kết quả | Node fail |
|---|---|---|
| 1 | `6 failed / 4889 passed / 7 skipped / 16 xfailed / 0 errors` (**517.48s**) | đúng 6 node `tests/test_step3_fred.py`, không có node nào khác |

- Collection `4905 → 4918` = **+13 đúng bằng 13 test mới**; `passed 4876 → 4889` (**+13**).
- Sáu node FRED exact (không đổi so baseline): `test_load_fallback_returns_currencies`, `test_get_latest_rates_no_key_uses_fallback`, `test_get_latest_rates_empty_key_uses_fallback`, `test_get_latest_rates_cache_works`, `test_get_latest_rates_bad_key_falls_back`, `test_get_latest_rates_fred_exception_falls_back` (cùng do `config/interest_rates.json` bị gitignore).
- **Không có failure/error mới ngoài tập FRED.**

### 13.7 Artifact ngoài repo

Toàn bộ nằm trong `%TEMP%\aima-fr501\` (không có artifact trong `reports/`):

- `window_state_prefix.py` — bản dựng lại nguyên văn `ui/window_state.py` trước sửa (mốc “trước”).
- `root_cause_probe.py` + `root-cause.json` — probe trước/sau trên cùng input và sáu lớp bất biến.
- `main_window_delta.py` + `main_window_prefix.py` — tách delta `+26/−0` của `ui/main_window.py`.
- `native_smoke_fr501.py`, `native-default.json`, `native-scale2.json`, ảnh `native-{tag}-{state}-{theme}.png` (12 ảnh) + `legacy-restore-probe.png`.
- `native_probe.py`, `webengine_probe.py`, `webengine_cd_probe.py`, `native_config_probe.py`, `native_main_window.py` — các probe cô lập fast-fail WebEngine.
- `disable_faux_plugin.py` — plugin mutation check (vô hiệu hoá nhánh faux) cho §13.4.
- `ui-smoke/` — 7 trạng thái × 2 theme của repo smoke.
- INI state tạm (`window-state-*.ini`): harness **không** đọc/ghi INI thật của người dùng.

### 13.8 Ghi chú cho Tech Lead

1. **Hai node test cũ đổi input** (§13.4) là thay đổi có chủ đích để bảo toàn bảo đảm R0; nếu Tech Lead muốn giữ nguyên input `1280×700`, kỳ vọng của node đó phải đổi thành `faux-maximized-normal` — khi đó bảo đảm “không cao hơn vùng làm việc” chỉ còn được khẳng định qua nhánh maximize.
2. **Ngưỡng 95%** (`FAUX_MAXIMIZED_COVERAGE_RATIO`) và **inset mặc định 0** là hai tham số chính sách; cả hai đều là hằng số có tên, đo được và truyền được, không nhúng vào logic.
3. **Màn hình phụ (chưa đo được).** Nếu state faux nằm trên màn hình **phụ**, policy trả `maximized=True` như mọi nhánh maximize khác, nên vị trí cửa sổ maximized do Qt/OS quyết định chứ không phải geometry đã lưu. Đây là hệ quả của việc chọn maximize thay vì restore, không phải nhánh mới; phiên đo hiện tại chỉ thấy **một** màn hình nên ca này chưa có số đo, và các hành vi multi-monitor cũ (chọn màn hình theo giao lớn nhất, kẹp khi đổi monitor) vẫn được test phủ và không đổi.
4. **Chưa mở lô nào khác.** Các deferred cũ của R4 giữ nguyên.

## Review độc lập Tech Lead F-R5-01 (2026-09-19) — REVIEW PASS

**Phạm vi/evidence.** Review xác nhận root cause là saved normal geometry `QRect(30, 0, 1250, 752)` trên work area logical `1280×760`: client geometry chạm mép trên trong khi native frame đưa chrome lên ngoài vùng nhìn thấy. Nhánh `faux-maximized-normal` chỉ áp dụng khi geometry đã kẹp vừa phủ ≥95% theo cả hai chiều vừa chạm dải chrome; metric chrome lấy từ `QStyle.PM_TitleBarHeight` logical ở `MainWindow`, còn resolver vẫn thuần. Tái lập qua production entry trả `faux-maximized-normal`, `isMaximized=True`, rail giữ `48px`; normal restore và clamp đổi monitor vẫn không đổi.

**Kiểm chứng độc lập.** Targeted R1/F-R5: **59 passed**. UI smoke Scanner→Detail→Chart: 7 trạng thái × 2 theme, `failures=[]`; style/density audit (`--validate-contract`) và `git diff --check` đạt (chỉ warning LF→CRLF của Git). Artifact review ngoài repo: `%TEMP%\aima-techlead-fr501-smoke-20260919-212818` và `%TEMP%\aima-techlead-fr501-full2-20260919-214038`.

**Baseline delta.** Full suite process sạch: **6 failed / 4889 passed / 7 skipped / 16 xfailed / 0 errors** trong **464.09s**. Collection `4918` và passed `4889` khớp baseline F-R5-01; sáu failure trùng chính xác sáu node FRED đã biết, không failure/error mới.

**Quyết định.** F-R5-01 **REVIEW PASS**. Không còn lô đang mở; các deferred R4 giữ nguyên. Không commit/reset/xoá/push.
