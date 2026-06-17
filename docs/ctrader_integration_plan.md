# Kế hoạch tích hợp Pepperstone (cTrader) — Multi-Data-Source

> **Ngày**: 2026-06-17 | **Trạng thái**: Chờ triển khai | **Ước lượng**: 1-2 ngày

---

## 1. Mục tiêu

Cho phép người dùng chọn giữa **MT5** và **Pepperstone (cTrader)** làm nguồn dữ liệu trong màn hình Settings. Hệ thống hiện tại đã có pattern DataProvider ABC — việc thêm Pepperstone là thêm một implementation mới, không đụng đến scanner, backtest, journal, AI.

---

## 2. Hiện trạng kiến trúc

```
AppController (DI container)
  ├── settings_service → AppSettings (data_source: "mt5" | "oanda")
  ├── mt5_service (MT5Service)
  ├── oanda_service (OandaService)
  ├── data_provider (property) → trả về service theo data_source
  └── Các controller (scanner, backtest, journal) → dùng data_provider
```

DataProvider ABC (`services/data_provider.py`) định nghĩa contract:
- `connect()` / `disconnect()` / `connection_status()`
- `available_symbols()` / `resolve_symbol()`
- `load_ohlcv()` / `load_ohlcv_range()` / `load_primary_timeframes()`
- `symbol_data_quality()` / `quote_to_usd_rate()` / `server_time_utc()`
- `has_open_position_or_order()` / `place_market_order()` / `closed_trade_history()`

---

## 3. Công nghệ cTrader Open API

| Thành phần | Chi tiết |
|---|---|
| **Protocol** | Protobuf qua TCP (port 5035) |
| **Auth** | Client Credentials flow (Client ID + Secret → Access Token) |
| **Python SDK** | `ctrader-open-api` (PyPI, chính thức từ Spotware, dùng Twisted async) |
| **Demo endpoint** | `demo.ctraderapi.com:5035` |
| **Live endpoint** | `live.ctraderapi.com:5035` |
| **Docs** | https://help.ctrader.com/open-api/ |
| **GitHub** | https://github.com/spotware/OpenApiPy |

### Các message type cần dùng

| Thao tác | Request | Response |
|---|---|---|
| Auth app | `ProtoOAApplicationAuthReq` | `ProtoOAApplicationAuthRes` |
| Auth account | `ProtoOAAccountAuthReq` | `ProtoOAAccountAuthRes` |
| Account info | `ProtoOAGetAccountInfoReq` | `ProtoOAGetAccountInfoRes` |
| Symbol list | `ProtoOAGetSymbolListReq` | `ProtoOAGetSymbolListRes` |
| Candles (OHLCV) | `ProtoOAGetCandlesReq` | `ProtoOAGetCandlesRes` |
| Market order | `ProtoOANewOrderReq` | `ProtoOANewOrderRes` |
| Open positions | `ProtoOAGetPositionsReq` | `ProtoOAGetPositionsRes` |
| Deal history | `ProtoOAGetDealsReq` | `ProtoOAGetDealsRes` |

---

## 4. Danh sách file thay đổi

### 4.1. Sửa đổi (7 file)

| # | File | Mức độ | Nội dung |
|---|---|---|---|
| 1 | `config/settings.py` | Thấp | Thêm `PepperstoneSettings` dataclass, mở rộng `data_source` |
| 2 | `config/symbol_profiles.json` | Thấp | Thêm `pepperstone_symbol` cho mỗi cặp |
| 3 | `services/settings_service.py` | Thấp | Thêm `_load_pepperstone_settings()` |
| 4 | `controllers/app_controller.py` | Thấp | Thêm `pepperstone_service` property, mở rộng `data_provider` và `switch_data_source()` |
| 5 | `ui/screens/settings_screen.py` | Trung bình | Đổi tab "MT5" → "Dữ liệu", thêm selector nguồn + form Pepperstone |
| 6 | `ui/screens/dashboard_screen.py` | Thấp | Cập nhật hiển thị tên provider |
| 7 | `requirements.txt` | Thấp | Thêm `ctrader-open-api` |

### 4.2. Tạo mới (1 file)

| # | File | Mức độ | Nội dung |
|---|---|---|---|
| 8 | `services/pepperstone_service.py` | **Cao** | `PepperstoneService(DataProvider)` — ~600 dòng |

---

## 5. Kế hoạch chi tiết từng bước

### Bước 1: `config/settings.py` — Thêm PepperstoneSettings

```python
@dataclass(slots=True)
class PepperstoneSettings:
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    account_id: int = 0
    environment: str = "demo"   # "demo" | "live"

# AppSettings:
pepperstone: PepperstoneSettings = field(default_factory=PepperstoneSettings)
data_source: str = "mt5"        # "mt5" | "oanda" | "pepperstone"
```

### Bước 2: `config/symbol_profiles.json` — Thêm mapping

Thêm `"pepperstone_symbol"` vào mỗi profile. cTrader dùng định dạng `EUR/USD` (có dấu `/`), trùng với app symbol, nên mapping đơn giản:

```json
"EUR/USD": {
  "base": "EUR", "quote": "USD",
  "mt5_aliases": ["EURUSD", "EURUSDm", "EURUSDc"],
  "oanda_symbol": "EUR_USD",
  "pepperstone_symbol": "EUR/USD"
}
```

### Bước 3: `services/settings_service.py` — Load/save

Thêm phương thức `_load_pepperstone_settings()` tương tự `_load_oanda_settings()`:

```python
def _load_pepperstone_settings(self, data: dict | None) -> PepperstoneSettings:
    data = data or {}
    env = str(data.get("environment", "demo")).strip().lower()
    if env not in ("demo", "live"):
        env = "demo"
    return PepperstoneSettings(
        client_id=str(data.get("client_id", "")).strip(),
        client_secret=str(data.get("client_secret", "")).strip(),
        access_token=str(data.get("access_token", "")).strip(),
        account_id=int(data.get("account_id", 0) or 0),
        environment=env,
    )
```

Cập nhật `load()` để gọi `_load_pepperstone_settings(data.get("pepperstone", {}))`.

### Bước 4: `services/pepperstone_service.py` — Core implementation

Đây là bước quan trọng nhất. Class `PepperstoneService(DataProvider)` implement toàn bộ contract.

**Thiết kế:**

```python
class PepperstoneConfig:
    client_id: str
    client_secret: str
    access_token: str
    account_id: int
    environment: str  # "demo" | "live"

class PepperstoneService(DataProvider):
    def __init__(self, config, symbol_profile_path=None):
        self._config = config
        self._client = None        # ctrader_open_api.Client
        self._connected = False
        self._authed = False
        self._pending = {}         # deferred response tracking
        self._symbols = []         # cached symbol list

    # Kết nối
    def connect(self) -> bool:
        # 1. Tạo Client với EndPoints phù hợp (demo/live)
        # 2. Đăng ký callbacks (connected, disconnected, message_received)
        # 3. Start TCP connection
        # 4. Gửi ProtoOAApplicationAuthReq(clientId, clientSecret)
        # 5. Gửi ProtoOAAccountAuthReq(accountId, accessToken)
        # 6. Đồng bộ chờ kết quả (dùng threading.Event)

    # Dữ liệu thị trường
    def load_ohlcv(self, broker_symbol, timeframe, bars, skip_select=False):
        # 1. Map timeframe → cTrader timeframe (D1→D, H4→H4, H1→H1, M15→M15)
        # 2. Gửi ProtoOAGetCandlesReq(symbol, timeframe, count)
        # 3. Parse ProtoOAGetCandlesRes → list[Candle]

    # Giao dịch
    def place_market_order(self, *, symbol, broker_symbol, side, volume,
                           stop_loss, take_profit, comment=""):
        # 1. Tính volume theo đơn vị cTrader (1 lot = 100,000 units)
        # 2. Gửi ProtoOANewOrderReq với ORDER_TYPE_MARKET
        # 3. Parse response → OrderResult
```

**Lưu ý kỹ thuật:**
- `ctrader-open-api` dùng Twisted (async). Cần wrapper để biến thành sync cho tương thích với codebase hiện tại
- Dùng `threading.Event` hoặc `concurrent.futures` để chờ deferred response
- Cần parse protobuf message type từ raw bytes để dispatch đúng handler
- Symbol list nên cache sau lần fetch đầu tiên

### Bước 5: `controllers/app_controller.py` — DI

```python
from services.pepperstone_service import PepperstoneService, PepperstoneConfig

class AppController:
    def __init__(self):
        self._pepperstone_service = None

    @property
    def pepperstone_service(self) -> PepperstoneService:
        if self._pepperstone_service is None:
            cfg = self.settings.pepperstone
            self._pepperstone_service = PepperstoneService(
                config=PepperstoneConfig(
                    client_id=cfg.client_id,
                    client_secret=cfg.client_secret,
                    access_token=cfg.access_token,
                    account_id=cfg.account_id,
                    environment=cfg.environment,
                ),
            )
        return self._pepperstone_service

    @property
    def data_provider(self) -> DataProvider:
        if self._data_provider is None:
            if self.settings.data_source == "pepperstone":
                self._data_provider = self.pepperstone_service
            elif self.settings.data_source == "oanda":
                self._data_provider = self.oanda_service
            else:
                self._data_provider = self.mt5_service
        return self._data_provider

    def switch_data_source(self, source: str) -> None:
        self.settings.data_source = source
        self._data_provider = None
        self._scanner_controller = None
        self._backtest_controller = None
        self._journal_controller = None
```

### Bước 6: `ui/screens/settings_screen.py` — UI

**Thay đổi tab thứ hai:**
- Đổi tên tab từ "MT5" → **"Dữ liệu"**
- Thêm **data source selector** (QComboBox) ở đầu tab: `MT5 | Oanda | Pepperstone`
- Khi chọn source, form cấu hình bên dưới tự động đổi:
  - **MT5**: giữ nguyên giao diện hiện tại (bảng symbol + nút kiểm tra kết nối)
  - **Pepperstone**: hiện form mới với các trường Client ID, Client Secret, Access Token, Account ID, Environment
- Bảng cấu hình mã quét (symbol table) dùng chung cho mọi provider

**Layout tab Dữ liệu mới:**

```
┌────────────────────────────────────────────────────────┐
│ 1. Nguồn dữ liệu:  [ MT5 | Oanda | Pepperstone  ▼]   │
├────────────────────────────────────────────────────────┤
│ 2. Cấu hình kết nối                                     │
│                                                          │
│   [Nếu Pepperstone]:                                     │
│   Client ID:       [                              ]     │
│   Client Secret:   [                              ]     │
│   Access Token:    [                              ]     │
│   Account ID:      [                              ]     │
│   Môi trường:      [ Demo | Live                ▼]     │
│                                                          │
│   [🔄 Kiểm tra kết nối]  [💾 Lưu]                      │
│   Trạng thái: Đã kết nối / Chưa kết nối                 │
├────────────────────────────────────────────────────────┤
│ 3. Cấu hình mã quét (dùng chung)                        │
│   [Bảng symbol với backtest, min_score, regime...]      │
│   [🔍 Tự phát hiện mã broker]  [💾 Lưu cấu hình mã]    │
└────────────────────────────────────────────────────────┘
```

### Bước 7: `ui/screens/dashboard_screen.py` — Cập nhật hiển thị

Cập nhật connection status card để hiển thị đúng tên provider ("Pepperstone" thay vì "MT5").

### Bước 8: `requirements.txt` — Dependencies

```
ctrader-open-api>=1.0
protobuf>=4.0
```

---

## 6. Thứ tự triển khai khuyến nghị

| # | Bước | Ước lượng |
|---|---|---|
| 1 | `config/settings.py` — Thêm dataclass | 15 phút |
| 2 | `services/settings_service.py` — Load/save | 15 phút |
| 3 | `config/symbol_profiles.json` — Mapping | 20 phút |
| 4 | `services/pepperstone_service.py` — **Core** | 4-6 giờ |
| 5 | `controllers/app_controller.py` — DI | 20 phút |
| 6 | `ui/screens/settings_screen.py` — UI | 1-2 giờ |
| 7 | `ui/screens/dashboard_screen.py` — Tên provider | 15 phút |
| 8 | `requirements.txt` — Deps | 5 phút |

---

## 7. Rủi ro & giảm thiểu

| Rủi ro | Giảm thiểu |
|---|---|
| `ctrader-open-api` dùng Twisted async, codebase hiện tại dùng sync | Dùng `threading.Event` chờ deferred response; wrap mỗi call thành blocking với timeout |
| Access Token hết hạn 30 ngày | Lưu refresh token; auto-refresh khi phát hiện lỗi auth |
| cTrader demo có ít dữ liệu lịch sử | Cảnh báo cho user; backtest cần tối thiểu 500 nến D1 |
| Pepperstone có thể có endpoint khác | Thêm field custom endpoint trong settings nâng cao |

---

## 8. Tiêu chí hoàn thành

- [ ] User chọn "Pepperstone" trong Settings → form cấu hình hiện ra
- [ ] Điền đúng thông tin → bấm "Kiểm tra kết nối" → hiện trạng thái connected + balance
- [ ] Symbol table hiển thị mã khớp giữa app và Pepperstone
- [ ] Scanner chạy được với dữ liệu từ Pepperstone (D1/H4/H1/M15)
- [ ] Backtest chạy được với dữ liệu lịch sử từ Pepperstone
- [ ] Journal sync được closed trades từ Pepperstone
- [ ] Dashboard hiển thị đúng tên provider "Pepperstone"
- [ ] Chuyển qua lại giữa MT5 và Pepperstone không lỗi
