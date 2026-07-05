# PLAN NÂNG CẤP PHẦN VĨ MÔ — AIMarketAnalyst

> Mục tiêu: 4 nâng cấp độc lập, không phá vỡ các chức năng đang chạy.
> Thứ tự làm: 1 → 2 → 3 → 4 (mỗi thay đổi test riêng trước khi làm bước tiếp).

---

## THAY ĐỔI 1 — yfinance: Đảm bảo DXY/VIX/US10Y/US2Y luôn có dữ liệu

### Vấn đề
`correlation_context` hiện truyền `None` nếu yfinance lỗi hoặc chưa cài,
dẫn đến `correlation_adjustment = 0` và bỏ qua toàn bộ tầng này.

### Phạm vi file thay đổi
- `services/market_data_service.py` — chỉnh hàm `fetch_macro_correlation_context`
- `requirements.txt` — đảm bảo `yfinance>=0.2` đã có (✅ đã có)

### Việc cần làm

**Bước 1.1** — Trong `fetch_macro_correlation_context`, bổ sung fallback:
```python
# Nếu yfinance không có, thử dùng requests lấy từ Yahoo Finance API thô
# URL mẫu: https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=10d
```
Cụ thể: wrap từng `ex.submit(download, ...)` trong try-except,
nếu lỗi thì gọi hàm `_fetch_via_requests(ticker)` dùng `requests` thuần.

**Bước 1.2** — Viết hàm `_fetch_via_requests(ticker, period="10d")`:
```python
def _fetch_via_requests(ticker: str, period: str = "10d") -> list[Candle] | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval": "1d", "range": period}
    headers = {"User-Agent": "Mozilla/5.0"}
    # parse JSON response → list[Candle]
    # trả None nếu lỗi, không raise exception
```

**Bước 1.3** — Log rõ ràng khi nào dùng fallback:
```python
import logging
logger = logging.getLogger(__name__)
logger.warning("yfinance failed for %s, using requests fallback", ticker)
```

**Bước 1.4** — Tăng TTL cache từ 15 phút → 30 phút để giảm số lần gọi mạng.

### Test sau khi làm
```python
# tests/test_market_data_service.py — thêm test case:
def test_fallback_khi_yfinance_loi():
    # mock yfinance raise Exception
    # kiểm tra vẫn trả về dict có đủ 4 key, giá trị không None
```

### Không được đụng tới
- Logic trong `correlation_check.py` — không thay đổi gì
- Các nơi gọi `fetch_macro_correlation_context` trong `scanner_controller.py`

---

## THAY ĐỔI 2 — Mở rộng correlation cho EUR/USD, GBP/USD, AUD/USD, NZD/USD, CAD/USD

### Vấn đề
`_us10y_score()` và `_us2y_score()` trong `correlation_check.py` chỉ chạy khi
symbol chứa `XAU`, `XAG`, hoặc `JPY`. Các cặp EUR/GBP/AUD/NZD/CAD bị
`return 0.0` ngay từ đầu.

### Phạm vi file thay đổi
- `core/correlation_check.py` — chỉ 2 hàm `_us10y_score` và `_us2y_score`

### Việc cần làm

**Bước 2.1** — Trong `_us10y_score`, bổ sung block sau block JPY:
```python
# Thêm sau elif "JPY" in sym_upper:
# Với các cặp XXX/USD thông thường (EUR, GBP, AUD, NZD, CAD):
# US10Y tăng → USD mạnh → SELL XXX/USD
# US10Y giảm → USD yếu → BUY XXX/USD
elif sym_upper.endswith("/USD") and base not in ("XAU", "XAG"):
    # Chỉ tính Tier 1 Directional, bỏ Tier 2 và 3 (không đủ context)
    if (side == "buy" and not y_up) or (side == "sell" and y_up):
        directional = 1.5   # thuận — nhẹ hơn XAU/JPY vì quan hệ ít trực tiếp hơn
    else:
        directional = -1.5  # ngược
    total = directional
    return round(total, 1)
```

**Bước 2.2** — Tương tự cho `_us2y_score`, logic giống Bước 2.1 nhưng hệ số
nhỏ hơn (US2Y ít tác động hơn với major pairs):
```python
elif sym_upper.endswith("/USD") and base not in ("XAU", "XAG"):
    if (side == "buy" and not y_up) or (side == "sell" and y_up):
        directional = 1.0
    else:
        directional = -1.0
    return round(directional, 1)
```

**Bước 2.3** — Trong `_dxy_score`, hàm này đã xử lý USD pairs đúng rồi,
nhưng cần kiểm tra lại logic `buy_usd` với EUR/USD:
```python
# EUR/USD: side="buy" → mua EUR = bán USD → usd_bullish = False
# Logic hiện tại: symbol.upper().endswith("/USD") and side == "sell" → buy_usd = True
# ✅ Đúng rồi, không cần sửa
```
→ Chỉ cần đọc lại, không sửa.

### Test sau khi làm
```python
# tests/test_correlation_check.py — thêm:
def test_eurusd_us10y_tang_sell_duoc_thuong():
    candles_tang = [Candle(close=4.0), Candle(close=4.5)]  # US10Y tăng
    score = _us10y_score("sell", "EUR/USD", candles_tang)
    assert score > 0  # SELL EUR/USD khi US10Y tăng = thuận

def test_audusd_us10y_giam_buy_duoc_thuong():
    candles_giam = [Candle(close=4.5), Candle(close=4.0)]  # US10Y giảm
    score = _us10y_score("buy", "AUD/USD", candles_giam)
    assert score > 0
```

### Không được đụng tới
- Toàn bộ các hàm khác trong `correlation_check.py`
- Không thay đổi range đầu ra (-18 đến +7) của `compute_correlation_adjustment`

---

## THAY ĐỔI 3 — FRED API: Tự động cập nhật lãi suất thay file JSON tĩnh (Sử dụng API: 300a8bf84914c7336977fea8199032b0)

### Vấn đề
`config/interest_rates.json` cập nhật tay → lãi suất cũ khi Fed/ECB/BOJ họp.
Tầng Tier 1 macro phụ thuộc file này → sai khi lãi suất thay đổi mà quên sửa.

### Phạm vi file thay đổi
- `services/interest_rate_service.py` — **tạo file mới**, không đụng file cũ
- `services/news_service.py` — chỉ sửa hàm `_load_interest_rates`
- `config/interest_rates.json` — giữ nguyên làm fallback

### Việc cần làm

**Bước 3.1** — Tạo file `services/interest_rate_service.py`:

```python
"""Tự động cập nhật lãi suất từ FRED API (miễn phí).
Fallback về interest_rates.json nếu FRED không khả dụng.
"""
import json
import logging
from datetime import datetime, timedelta, UTC
from pathlib import Path
import requests

logger = logging.getLogger(__name__)

# Map tiền tệ → series ID trên FRED
FRED_SERIES: dict[str, str] = {
    "USD": "FEDFUNDS",      # Fed Funds Rate
    "EUR": "ECBDFR",        # ECB Deposit Facility Rate
    "GBP": "BOEBR",         # Bank of England Base Rate
    "JPY": "IRSTCI01JPM156N", # BOJ Policy Rate
    "AUD": "RBATCTR",       # RBA Cash Rate
    "NZD": "RBNZ_OCR",      # RBNZ OCR (nếu không có thì dùng fallback)
    "CAD": "BOCWATCH",      # BOC Rate (nếu không có thì dùng fallback)
    "CHF": "SNPOLICYR",     # SNB Policy Rate (nếu không có thì dùng fallback)
}

_CACHE: dict[str, object] | None = None
_CACHE_TIME: datetime | None = None
_CACHE_TTL = timedelta(hours=6)  # cập nhật tối đa 4 lần/ngày
_FALLBACK_PATH = Path(__file__).resolve().parents[1] / "config" / "interest_rates.json"


def get_latest_rates(fred_api_key: str | None = None) -> dict[str, object]:
    """Trả về dict lãi suất. Ưu tiên FRED nếu có API key, fallback về JSON."""
    global _CACHE, _CACHE_TIME

    now = datetime.now(UTC)
    if _CACHE and _CACHE_TIME and (now - _CACHE_TIME) < _CACHE_TTL:
        return _CACHE

    if fred_api_key:
        try:
            rates = _fetch_from_fred(fred_api_key)
            if rates:
                _CACHE = rates
                _CACHE_TIME = now
                return _CACHE
        except Exception as e:
            logger.warning("FRED fetch failed: %s, dùng fallback JSON", e)

    return _load_fallback()


def _fetch_from_fred(api_key: str) -> dict[str, object] | None:
    """Gọi FRED API lấy lãi suất mới nhất cho từng tiền tệ."""
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    fallback = _load_fallback()
    result = dict(fallback)  # bắt đầu từ fallback, override từng currency có data

    for currency, series_id in FRED_SERIES.items():
        try:
            resp = requests.get(base_url, params={
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 2,  # lấy 2 điểm để tính trend
            }, timeout=5)
            if resp.status_code != 200:
                continue

            obs = resp.json().get("observations", [])
            valid = [o for o in obs if o.get("value", ".") != "."]
            if not valid:
                continue

            latest_rate = float(valid[0]["value"])
            prev_rate = float(valid[1]["value"]) if len(valid) > 1 else latest_rate

            # Tính trend so với kỳ trước
            if latest_rate > prev_rate + 0.1:
                trend = "hike"
            elif latest_rate < prev_rate - 0.1:
                trend = "cut"
            else:
                trend = "hold"

            # Merge vào result, giữ các field khác từ fallback
            existing = dict(fallback.get(currency, {}))
            existing.update({
                "rate": latest_rate,
                "rate_label": f"{latest_rate:.2f}%",
                "trend": trend,
                "_source": "FRED",
                "_updated": valid[0]["date"],
            })
            result[currency] = existing

        except Exception as e:
            logger.debug("FRED error cho %s/%s: %s", currency, series_id, e)
            continue

    return result


def _load_fallback() -> dict[str, object]:
    try:
        raw = json.loads(_FALLBACK_PATH.read_text(encoding="utf-8"))
        return raw.get("currencies", {})
    except Exception:
        return {}
```

**Bước 3.2** — Sửa `_load_interest_rates` trong `news_service.py`:
```python
# TRƯỚC (hiện tại):
@classmethod
def _load_interest_rates(cls) -> dict[str, object]:
    if cls._interest_rates is not None:
        return cls._interest_rates
    try:
        path = Path(...) / "config" / "interest_rates.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        cls._interest_rates = raw.get("currencies", {})
    except Exception:
        cls._interest_rates = {}
    return cls._interest_rates

# SAU (sửa lại):
@classmethod
def _load_interest_rates(cls) -> dict[str, object]:
    # Không cache ở đây nữa — để InterestRateService tự cache
    from services.interest_rate_service import get_latest_rates
    from services.settings_service import SettingsService
    try:
        settings = SettingsService().load()
        fred_key = getattr(settings, "fred_api_key", None) or ""
    except Exception:
        fred_key = ""
    return get_latest_rates(fred_api_key=fred_key or None)
```

**Bước 3.3** — Thêm `fred_api_key` vào Settings (optional):
```python
# config/settings.py — class AISettings hoặc class mới MacroSettings:
fred_api_key: str = ""  # để trống = dùng fallback JSON
```

**Bước 3.4** — Thêm ô nhập FRED API key trong Settings screen (optional, làm sau):
```
UI: Settings → Macro → FRED API Key (để trống để dùng dữ liệu tĩnh)
```
→ Nếu chưa có key thì hệ thống vẫn chạy bình thường với file JSON.

### Test sau khi làm
```python
# tests/test_interest_rate_service.py — file mới:
def test_fallback_khi_khong_co_fred_key():
    rates = get_latest_rates(fred_api_key=None)
    assert "USD" in rates
    assert "rate" in rates["USD"]

def test_fred_key_sai_van_tra_ve_fallback():
    rates = get_latest_rates(fred_api_key="key_sai")
    assert "USD" in rates  # không crash, dùng fallback
```

### Không được đụng tới
- `config/interest_rates.json` — giữ nguyên làm fallback
- Toàn bộ logic `_macro_tier1`, `_macro_tier2`, `_macro_tier3`
- Không thay đổi signature của bất kỳ public method nào trong `NewsService`

---

## THAY ĐỔI 4 — AI phân tích hawkish/dovish thay keyword matching

### Vấn đề
`currency_stance()` dùng list từ khóa cứng → "budget cut" match "cut" → sai.
Cần AI đọc headline thật và cho output chuẩn hơn.

### Phạm vi file thay đổi
- `services/news_service.py` — chỉ thêm method mới, không xóa method cũ
- Không thay đổi interface `_compute_macro_tiers`

### Việc cần làm

**Bước 4.1** — Thêm method `_ai_currency_stance` vào `NewsService`:
```python
def _ai_currency_stance(
    self,
    currency: str,
    headlines: list[str],
    ai_service: object | None = None,
) -> str:
    """
    Dùng AI đánh giá hawkish/dovish cho 1 tiền tệ từ danh sách headline.
    Trả về: "hawkish" | "dovish" | "neutral"
    Fallback về keyword matching nếu AI không khả dụng.
    """
    if not ai_service or not headlines:
        # Fallback về logic cũ
        return currency_stance(headlines, self.HAWKISH_TERMS, self.DOVISH_TERMS)

    prompt = f"""Bạn là chuyên gia phân tích vĩ mô forex.
Đọc các headline dưới đây liên quan đến {currency} và đánh giá xu hướng chính sách tiền tệ.
Trả lời DUY NHẤT 1 từ: hawkish, dovish, hoặc neutral. Không giải thích.

Headlines:
{chr(10).join(f'- {h}' for h in headlines[:8])}

Trả lời:"""

    try:
        response = ai_service.analyze(prompt, max_tokens=10)
        result = response.strip().lower().split()[0]
        if result in ("hawkish", "dovish", "neutral"):
            return result
    except Exception:
        pass

    # Fallback nếu AI lỗi hoặc trả về không hợp lệ
    return currency_stance(headlines, self.HAWKISH_TERMS, self.DOVISH_TERMS)
```

**Bước 4.2** — Sửa `_compute_macro_tiers` để nhận thêm `ai_service=None`:
```python
# TRƯỚC:
def _compute_macro_tiers(self, symbol, currencies, headlines, events, themes, hotspots):
    base_stance = currency_stance(...)
    quote_stance = currency_stance(...)

# SAU:
def _compute_macro_tiers(self, symbol, currencies, headlines, events, themes, hotspots,
                          *, ai_service=None):
    base_headlines = [str(h.get("title","")) for h in headlines if self._matches_currency(h, base)]
    quote_headlines = [str(h.get("title","")) for h in headlines if self._matches_currency(h, quote)]

    base_stance = self._ai_currency_stance(base, base_headlines, ai_service)
    quote_stance = self._ai_currency_stance(quote, quote_headlines, ai_service)
    # ... phần còn lại giữ nguyên
```

**Bước 4.3** — Sửa `latest_macro_context` để nhận và truyền `ai_service`:
```python
# TRƯỚC:
def latest_macro_context(self, symbol, *, include_latest_statements=True):
    ...
    tier_scores = self._compute_macro_tiers(symbol, currencies, headlines, events, themes, hotspots)

# SAU:
def latest_macro_context(self, symbol, *, include_latest_statements=True, ai_service=None):
    ...
    tier_scores = self._compute_macro_tiers(..., ai_service=ai_service)
```

**Bước 4.4** — Truyền `ai_service` từ `scanner_controller.py`:
```python
# scanner_controller.py — chỗ gọi latest_macro_context hoặc data_quality_flags:
active_ai = settings.ai.active_provider()
ai_svc = None
if active_ai and active_ai.api_key:
    from services.ai_service import AIService, AIProviderConfig
    ai_svc = AIService(AIProviderConfig(
        provider=active_ai.provider,
        model=active_ai.model,
        api_key=active_ai.api_key,
    ))

macro_context = news_service.latest_macro_context(symbol, ai_service=ai_svc)
```

**Bước 4.5** — Cache kết quả AI stance để tránh gọi lặp:
```python
# Trong _ai_currency_stance, thêm cache cấp instance:
_stance_cache: dict[str, tuple[str, datetime]] = {}

def _ai_currency_stance(self, currency, headlines, ai_service=None):
    cache_key = f"{currency}_{hash(tuple(headlines[:5]))}"
    cached = self._stance_cache.get(cache_key)
    if cached and (datetime.now(UTC) - cached[1]).seconds < 1800:  # cache 30 phút
        return cached[0]
    result = ... # logic như trên
    self._stance_cache[cache_key] = (result, datetime.now(UTC))
    return result
```

### Test sau khi làm
```python
# tests/test_news_service.py — thêm:
def test_ai_stance_fallback_khi_khong_co_ai():
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed cuts rate by 25bps"], ai_service=None)
    assert result in ("hawkish", "dovish", "neutral")  # không crash

def test_ai_stance_fallback_khi_ai_loi():
    mock_ai = MagicMock()
    mock_ai.analyze.side_effect = Exception("AI lỗi")
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed hikes rate"], ai_service=mock_ai)
    assert result in ("hawkish", "dovish", "neutral")  # dùng keyword fallback

def test_ai_stance_tra_ve_dung():
    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "hawkish"
    svc = NewsService()
    result = svc._ai_currency_stance("USD", ["Fed raises rate"], ai_service=mock_ai)
    assert result == "hawkish"
```

### Không được đụng tới
- Hàm `currency_stance()` — giữ nguyên, vẫn dùng làm fallback
- `HAWKISH_TERMS`, `DOVISH_TERMS` — giữ nguyên
- Toàn bộ `_macro_tier2`, `_macro_tier3`

---

## TỔNG KẾT CÁC FILE THAY ĐỔI

| Thay đổi | File tạo mới | File sửa | File KHÔNG đụng |
|---|---|---|---|
| 1. yfinance fallback | — | `market_data_service.py` | `correlation_check.py`, `scanner_controller.py` |
| 2. Mở rộng correlation | — | `correlation_check.py` (2 hàm) | Tất cả file khác |
| 3. FRED API | `interest_rate_service.py` | `news_service.py` (1 method), `settings.py` (1 field) | `interest_rates.json`, `_macro_tier1/2/3` |
| 4. AI stance | — | `news_service.py` (3 method), `scanner_controller.py` (1 chỗ) | `currency_stance()`, `HAWKISH_TERMS` |

## QUY TẮC CHUNG CHO AI KHI THỰC HIỆN

1. Mỗi thay đổi làm 1 commit riêng, message rõ ràng.
2. Không refactor code không liên quan.
3. Mọi method mới phải có `try-except` và fallback — không được để crash.
4. Sau mỗi thay đổi chạy `pytest tests/` để đảm bảo không break test cũ.
5. Nếu test cũ fail do thay đổi hợp lý (thêm parameter mới) → cập nhật test, không xóa.
6. Không thay đổi kiểu trả về của bất kỳ public method nào đang được gọi từ ngoài.
