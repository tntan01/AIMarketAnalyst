# Hướng dẫn cài đặt, chạy và đóng gói

## Mục tiêu

Tài liệu này mô tả cách chuẩn bị môi trường phát triển, chạy ứng dụng PyQt6 và đóng gói để cài trên máy khác.

## Yêu cầu hệ thống

* Windows 10 hoặc Windows 11 64-bit.
* Python 3.11 hoặc 3.12 64-bit.
* MetaTrader 5 đã cài và đăng nhập broker nếu dùng dữ liệu thật.
* Visual C++ Redistributable nếu package `MetaTrader5` hoặc thư viện native yêu cầu.
* Kết nối internet nếu dùng AI provider hoặc tin tức.

## Cài môi trường phát triển

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Nếu chưa có `requirements.txt`, MVP nên bắt đầu với các nhóm dependency:

```text
PyQt6
PyQt6-WebEngine
pandas
numpy
MetaTrader5
requests
python-dotenv
keyring
pytest
pyinstaller
yfinance
```

## Cấu hình runtime

Ứng dụng phải tự tạo thư mục user data khi chạy lần đầu:

```text
%APPDATA%/ai-market-analyst/
  settings.json
  journal.db
  logs/
  exports/
  cache/
```

## API Keys (tùy chọn)

AI Provider API Key được lưu an toàn qua **Windows Credential Manager** (thư viện `keyring`), không lưu plaintext trong `settings.json`.

| Key | Dùng cho | Lưu ở đâu |
|---|---|---|
| AI Provider API Key (DeepSeek, OpenAI, Anthropic, Gemini) | Gọi AI phân tích, market brief, audit | Windows Credential Manager (qua `services/credential_service.py`) |
| `fred_api_key` (trong settings → advanced) | Tự động cập nhật lãi suất từ FRED API | `settings.json` (plaintext trong advanced section) |
| `brave_api_key` (trong settings → advanced) | Tìm kiếm tin tức qua Brave Search API | `settings.json` (plaintext trong advanced section) |

### Cấu hình AI Provider

1. Mở **Settings → AI**.
2. Chọn provider từ danh sách bên trái.
3. Nhập API Key vào ô password.
4. Chọn Model từ combobox (hoặc gõ model tùy chỉnh).
5. Bấm **Kiểm tra** để xác thực.
6. Bấm **Lưu** — API Key được lưu vào Windows Credential Manager.

### Migration từ phiên bản cũ

Nếu `settings.json` đang chứa API Key dạng plaintext (phiên bản cũ), hệ thống sẽ **tự động migrate** sang Windows Credential Manager ở lần lưu đầu tiên sau khi nâng cấp. Không cần nhập lại API Key.

Không có key, app vẫn chạy bình thường với dữ liệu fallback.

## Chạy ứng dụng khi phát triển

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

Màn hình Dashboard phải mở được dù MT5 hoặc AI chưa cấu hình. Khi thiếu cấu hình, UI hiển thị trạng thái chưa sẵn sàng và hướng dẫn người dùng vào Settings.

## Kiểm tra trước khi build

```powershell
pytest
python main.py
```

Checklist tối thiểu:

* App mở bằng `python main.py`.
* Dashboard không lỗi khi MT5 chưa mở.
* Settings lưu và đọc lại được.
* Journal database tự tạo nếu chưa tồn tại.
* Log file được tạo trong `%APPDATA%/ai-market-analyst/logs/`.
* Không có API key xuất hiện trong log.
* UI không bị tràn ở 1366x768 và 1920x1080.

## Đóng gói Windows bằng PyInstaller

Script build nên nằm trong `packaging/build_windows.ps1`.

Lệnh tham khảo:

```powershell
.\.venv\Scripts\Activate.ps1
pyinstaller packaging\pyinstaller.spec --clean --noconfirm
```

Spec phải include:

* `assets/icons`.
* `assets/fonts`.
* `assets/chart`.
* `ui/styles/dark.qss`.
* `data/migrations`.
* validated `data/vix_pair_sensitivity.json` làm readonly runtime fallback.
* Các package hidden import cần cho PyQt6, PyQt6-WebEngine và MetaTrader5.

## Kiểm tra bản đóng gói

Sau khi build, test trên máy sạch hoặc Windows user profile mới:

* Chạy được bằng double click.
* Tạo user data trong `%APPDATA%`.
* Mở Settings, lưu cấu hình, đóng app, mở lại vẫn còn cấu hình.
* Không cần mở terminal để chạy app.
* Nếu thiếu MT5, app báo lỗi dễ hiểu.
* Nếu thiếu AI key, app vẫn chạy rule-based.
* Chart trong `QWebEngineView` render được khi chạy file `.exe`.
* Export JSON hoạt động.
* Checkbox VIX pair-aware mặc định OFF và sống sót qua save/reload Settings.
* Bundled schema-2 VIX map đọc được; APPDATA map hợp lệ override bundle;
  APPDATA seed/stale bị bỏ qua và loader thử bundle; thiếu mọi eligible map vẫn
  giữ flat scoring.

`scripts/run_vix_pair_backtest.py` hiện là công cụ vận hành từ source checkout,
không được PyInstaller bundle và packaged UI chưa có nút revalidate/status. Bản
phát hành không được hướng dẫn người dùng bật VIX pair-aware nếu chưa có quy
trình operator tạo, review và phân phối map còn hạn.

## Cài đặt trên máy khác

Gói phát hành nên gồm:

```text
AI-Market-Analyst/
  AI Market Analyst.exe
  assets/
  data/vix_pair_sensitivity.json
  README_USER.md
  LICENSE.txt
```

Nếu dùng installer, installer chỉ đặt file app vào `Program Files` hoặc thư mục người dùng. Dữ liệu cá nhân vẫn nằm trong `%APPDATA%`.

## Lưu ý bảo mật

* Không đóng gói sẵn API key.
* Không ghi API key vào `settings.json` dạng plain text nếu có thể dùng keyring.
* Không gửi journal hoặc log ra ngoài nếu người dùng chưa đồng ý.

## Scanner — Checklist vận hành live (từ 15/08/2026)

Từ 15/08/2026, theo quyết định của owner (phần mềm cá nhân), ứng dụng chạy
thật trực tiếp: cơ chế rollout V3 (stage ladder `SHADOW → DEMO → CANARY →
PRODUCTION`, kill switch, release/canary readiness) đã bị gỡ bỏ hoàn toàn khỏi
codebase. Kiến trúc hiện hành là Scanner V4:
[`scanner-v4-architecture.md`](../scanner/scanner-v4-architecture.md).

An toàn không còn dựa vào rollout stage mà dựa vào các lớp kỹ thuật fail-closed:

1. `config/scanner_v4_order_policy.json` phải `certified()` — thiếu/hỏng file,
   scan phát `ORDER_POLICY_FAULT` và mọi candidate bị chặn
   (`order_enabled=False`).
2. MarketSafetyGate/MacroGate: dữ liệu thiếu hoặc thị trường không an toàn →
   `BLOCKED`/`DATA_UNAVAILABLE`.
3. Nút **Tự động vào lệnh MT5** phải được người dùng chủ động bật cho lần quét
   đó.
4. Mọi lệnh (auto lẫn manual) đi qua
   `ScannerController.execute_order_candidate()`: execution snapshot mới, tính
   lại lot, news, account/portfolio guard, `revalidate_execution` rồi mới
   `place_market_order`. Không gọi `MT5Service.place_market_order()` trực tiếp.
5. Order Management V2 (SL/BE/trailing) mặc định bật; gate còn lại là feature
   flag + `account.trade_allowed`.

Khuyến nghị cho lần chạy live đầu tiên: bắt đầu với **1 symbol và risk percent
nhỏ**, theo dõi lệnh đầu end-to-end; kiểm tra Orders pane hiển thị `LIVE`
(`execution_allowed=true`) và event mutation thật. Không còn kill switch phần
mềm — dừng khẩn cấp = tắt feature flag, đóng lệnh ở terminal broker hoặc ngắt
kết nối MT5. Trạng thái chi tiết:
[`runtime-status.md`](../architecture/runtime-status.md).

## Auto Trade Safety Checklist trước Scanner V2 (lịch sử)

> Mục dưới đây chỉ lưu tham chiếu cho phiên bản cũ. Checklist live phía trên là
> yêu cầu vận hành hiện hành.

Before enabling auto-scan with MT5 auto-entry on a real account:

* Confirm MT5 is open, connected, logged in, and `trade_allowed=True`.
* Confirm broker symbols in Market Watch match the symbols selected in Scanner.
* Confirm `Default Risk Percent` and `Max Risk Percent` in Settings > Trading.
* Confirm Scanner is in auto-scan mode and the `Tự động vào lệnh MT5` toggle button is intentionally on.
* Confirm the auto-entry toggle button is visually highlighted before expecting the app to place MT5 orders.
* Test first on demo account or very small risk.
* Confirm each broker symbol has no existing position or pending order if a new entry is expected.
* Confirm SL and TP are visible in the scanner detail before relying on auto-entry.
* Confirm the live price is still inside the displayed final execution zone
  and current R:R remains above the configured minimum. The source zone is
  reference-only and must not be used as an execution boundary.

Runtime behavior:

* One-shot/manual scan does not place orders.
* Auto-scan can place orders only when `Tự động vào lệnh MT5` is on and rows are `ready` and `allowed`.
* The system checks existing MT5 positions and pending orders per broker symbol before sending a new order.
* If an order already exists for that broker symbol, auto-entry skips that symbol.
* Immediately before execution, the system uses live ask/bid to re-check the
  final `entry_zone` from the same-side scenario and current spread-adjusted
  R:R. It skips the order when price is outside the zone, the final zone is
  missing, or current R:R is below `min_rr`.
* Lot comes from `position_sizing.suggested_lot`, calculated from MT5 balance and the capped risk percent.
* The first TP from the trade plan is used for the MT5 order.
