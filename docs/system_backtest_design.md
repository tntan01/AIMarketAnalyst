# Thiết Kế Chức Năng System Backtest

> Quy tắc bắt buộc: file này phải luôn được lưu bằng **UTF-8**. Không dùng ANSI, Windows-1258, Windows-1252 hoặc bất kỳ encoding cục bộ nào. Khi chỉnh bằng VS Code, kiểm tra góc dưới bên phải phải là `UTF-8`. Khi đọc bằng PowerShell, dùng `Get-Content -Encoding utf8`.

## Mục Tiêu

Chức năng System Backtest dùng để đo hiệu quả của toàn bộ hệ thống phân tích hiện tại, không chỉ kiểm tra riêng một indicator hay một module SMC.

Hệ thống hiện tại có nhiều lớp quyết định:

- Dữ liệu MT5: D1, H4, H1, M15.
- Technical context: EMA, RSI, MACD, ATR, support/resistance, market regime.
- SMC context: BOS, CHOCH, displacement, supply/demand, order block, FVG, liquidity sweep, premium/discount.
- Score engine: buy/sell score, macro alignment, risk condition, correlation adjustment.
- Entry engine: entry zone, H1 confirmation, M15 quality, ready_to_trade.
- Trade gate: MT5 status, spread, news, score gap, M15, expected effective R:R, account guard.
- Final score và decision engine.

Backtest cần replay lại các lớp này theo dữ liệu lịch sử để trả lời các câu hỏi:

- Hệ thống có expectancy dương không?
- Điều kiện nào tạo edge tốt nhất?
- Score từ bao nhiêu trở lên mới đáng trade?
- M15 strict có thật sự cải thiện kết quả không?
- SMC zone_score cao có liên quan tới win rate/expectancy không?
- Market regime nào nên trade, regime nào nên bỏ qua?
- Max drawdown và chuỗi thua có nằm trong mức account guard chịu được không?

## Nguyên Tắc Quan Trọng

### 1. Không Nhìn Dữ Liệu Tương Lai

Tại mỗi bước backtest, engine chỉ được nhìn thấy các cây nến đã đóng trước hoặc tại thời điểm đang xét.

Ví dụ khi backtest tại `2025-03-10 14:00`, các input phải là:

- `D1`: các nến D1 đã có tới thời điểm đó.
- `H4`: các nến H4 đã có tới thời điểm đó.
- `H1`: các nến H1 đã có tới thời điểm đó.
- `M15`: các nến M15 đã có tới thời điểm đó.

Không được dùng swing, ATR, EMA, SMC zone hoặc macro data từ tương lai.

### 2. Gọi Pipeline Thật Của Hệ Thống

Backtest không nên viết lại logic phân tích. Hàm trung tâm cần gọi là:

```python
from core.analysis_engine import analyze_symbol
```

Bên trong `analyze_symbol()` hệ thống đã gọi các module quan trọng:

```text
build_technical_snapshot()
build_smc_context()
score_scenario()
calculate_direction_bias()
build_scenarios()
evaluate_entry()
check_trade_gates()
calculate_final_score()
make_final_decision()
```

Backtest chỉ nên làm 3 việc:

- Cắt dữ liệu lịch sử thành từng snapshot không có future leak.
- Gọi `analyze_symbol()` với snapshot đó.
- Giả lập khớp lệnh, SL/TP, và thống kê kết quả.

### 3. Không Ghi Vào Journal Thật

Backtest không được ghi vào bảng journal giao dịch thật. Kết quả backtest nên lưu riêng:

```text
data/backtests/backtest_YYYYMMDD_HHMMSS.json
```

Hoặc nếu dùng SQLite:

```text
backtest_runs
backtest_trades
```

## Kiến Trúc Đề Xuất

Thêm các file mới:

```text
core/system_backtest_engine.py
controllers/backtest_controller.py
workers/backtest_worker.py
ui/screens/backtest_screen.py
```

Sau đó cập nhật:

```text
ui/main_window.py
ui/navigation.py
```

để thêm route Backtest vào ứng dụng.

## Module `core/system_backtest_engine.py`

### Dataclass Chính

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass(frozen=True, slots=True)
class BacktestRequest:
    symbol: str
    broker_symbol: str
    start: datetime
    end: datetime
    initial_balance: float
    risk_percent: float
    account_currency: str = "USD"
    lot_step: float = 0.01
    minimum_lot: float = 0.01
    contract_size_override: float | None = None
    timezone_name: str = "Asia/Ho_Chi_Minh"
    spread_price: float = 0.0
    slippage_price: float = 0.0
    max_holding_bars: int = 96
    setup_expiry_bars: int = 12
    step_timeframe: str = "H1"
    allow_macro: bool = False
    conservative_same_bar: bool = True

@dataclass(slots=True)
class BacktestTrade:
    symbol: str
    side: str
    decision: str
    entry_time: str
    exit_time: str | None
    entry_price: float
    stop_loss: float
    take_profit: float
    result: str
    result_r: float
    holding_bars: int
    final_score: int
    signal_score: int
    buy_score: int
    sell_score: int
    score_gap: float
    market_regime: str
    entry_status: str
    m15_quality: str | None
    expected_effective_rr: float | None
    selected_zone_score: int | None
    selected_zone_type: str | None
    liquidity_sweep_aligned: bool
    displacement_aligned: bool
    choch_against_direction: bool
    reason_codes: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    block_codes: list[str] = field(default_factory=list)
    analysis_snapshot: dict[str, Any] | None = None

@dataclass(slots=True)
class BacktestResult:
    request: BacktestRequest
    summary: dict[str, Any]
    trades: list[BacktestTrade]
    equity_curve: list[dict[str, Any]]
    breakdowns: dict[str, Any]
    skipped_setups: list[dict[str, Any]]
    diagnostics: dict[str, Any]
```

### Public API

```python
def run_system_backtest(
    request: BacktestRequest,
    candles_by_timeframe: dict[str, list[Candle]],
) -> BacktestResult:
    ...
```

`candles_by_timeframe` gồm:

```python
{
    "D1": list[Candle],
    "H4": list[Candle],
    "H1": list[Candle],
    "M15": list[Candle],
}
```

### Luồng Xử Lý

```text
1. Validate request và dữ liệu.
2. Xác định danh sách mốc thời gian cần replay, thường là từng nến H1.
3. Tại mỗi mốc thời gian:
   - Cắt D1/H4/H1/M15 tới mốc hiện tại.
   - Bỏ qua nếu chưa đủ warmup.
   - Gọi analyze_symbol().
   - Đọc decision, gate, scenario.
   - Nếu có setup hợp lệ thì tạo lệnh giả lập.
4. Nếu đang có lệnh mở:
   - Không mở thêm lệnh cùng symbol.
   - Cập nhật lệnh bằng các nến sau entry.
5. Khi SL/TP/expiry được kích hoạt:
   - Tính result_r.
   - Cập nhật balance/equity curve.
6. Sau khi hết dữ liệu:
   - Đóng lệnh đang mở theo giá cuối hoặc đánh dấu expired/open.
   - Tính summary và breakdown.
```

## Gọi `analyze_symbol()` Trong Backtest

Tại mỗi snapshot:

```python
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput

analysis_input = AnalysisInput(
    symbol=request.symbol,
    broker_symbol=request.broker_symbol,
    account_balance=current_balance,
    risk_percent=request.risk_percent,
    account_currency=request.account_currency,
    lot_step=request.lot_step,
    minimum_lot=request.minimum_lot,
    contract_size_override=request.contract_size_override,
    timezone_name=request.timezone_name,
)

data_quality = {
    "price_source": "BACKTEST",
    "terminal_connected": True,
    "broker_logged_in": True,
    "display_symbol": request.symbol,
    "broker_symbol": request.broker_symbol,
    "spread_points": request.spread_price,
    "spread_status": "normal",
    "warning": None,
    "news_in_3h": False,
    "high_impact_event_within_30m": False,
}

result = analyze_symbol(
    analysis_input,
    {
        "D1": d1_until_now,
        "H4": h4_until_now,
        "H1": h1_until_now,
    },
    data_quality=data_quality,
    macro_alignment={"buy": 15, "sell": 15},
    macro_confidence=1.0,
    ai_commentary=None,
    ai_meta=None,
    m15_candles=m15_until_now,
    correlation_context=None,
    quote_to_usd_rate=quote_to_usd_rate,
    closed_trades=closed_trades_for_account_guard,
    open_trades=open_trades_for_account_guard,
    account_guard_settings=account_guard_settings,
    trade_date=current_time,
    use_decision_engine_action=True,
)
```

Giai đoạn MVP nên đặt macro trung tính:

```python
macro_alignment = {"buy": 15, "sell": 15}
macro_confidence = 1.0
```

Lý do: hệ thống news/macro hiện tại lấy dữ liệu live. Nếu dùng live data để backtest quá khứ sẽ gây sai lệch nghiêm trọng.

## Điều Kiện Vào Lệnh

Nên hỗ trợ nhiều chế độ để so sánh.

### Chế Độ Chặt

Chỉ vào lệnh khi:

```python
result["decision_engine"]["decision"] == "READY_TO_TRADE"
result["trade_gate"]["allowed"] is True
result["trade_permission"]["status"] == "allowed"
```

Và scenario cùng hướng có:

```python
scenario["ready_to_trade"] is True
scenario["entry_status"] == "confirmed_entry"
scenario["m15_quality"] == "strict"
```

### Chế Độ Legacy

Dùng luồng UI/scanner hiện tại:

```python
result["decision_summary"]["action"] == "ready"
result["trade_permission"]["status"] == "allowed"
```

### Chế Độ Research

Cho phép test cả các setup chưa ready:

- `WATCH_ONLY`
- `WAITING_CONFIRMATION`
- `m15_quality == "loose"`

Chế độ này chỉ dùng để nghiên cứu, không nên xem là rule auto trade thật.

## Lấy Scenario Giao Dịch

```python
best_side = result["decision_summary"]["best_side"]

scenario = next(
    (
        item for item in result.get("scenarios", [])
        if isinstance(item, dict) and item.get("type") == best_side
    ),
    None,
)
```

Thông tin cần lấy:

```python
entry_zone = scenario["entry_zone"]
stop_loss = scenario["stop_loss"]
take_profit = scenario["take_profit"][0]
expected_effective_rr = scenario.get("expected_effective_rr")
m15_quality = scenario.get("m15_quality")
entry_status = scenario.get("entry_status")
```

SMC flags:

```python
smc_flags = result.get("smc_trade_flags", {})
selected_zone_score = smc_flags.get("selected_zone_score")
selected_zone_type = smc_flags.get("selected_zone_type")
liquidity_sweep_aligned = smc_flags.get("liquidity_sweep_aligned")
displacement_aligned = smc_flags.get("displacement_aligned")
choch_against_direction = smc_flags.get("choch_against_direction")
```

## Giả Lập Khớp Lệnh

### MVP: Vào Tại Close Hiện Tại

Nếu analysis báo `READY_TO_TRADE`, vào tại giá close của nến H1 hiện tại:

```python
entry_price = h1_until_now[-1].close
```

Ưu điểm:

- Đơn giản.
- Dễ debug.
- Phù hợp để test nhanh logic decision/entry.

Nhược điểm:

- Có thể không đúng với thực tế nếu giá chỉ mới nằm trong entry zone một phần.
- Chưa mô phỏng pending order.

### Bản Nâng Cấp: Pending Entry Zone

Khi có setup tốt, lưu setup vào danh sách pending. Trong `setup_expiry_bars` nến tiếp theo:

- Buy: nếu `candle.low <= entry_high` và `candle.high >= entry_low` thì khớp.
- Sell: nếu `candle.low <= entry_high` và `candle.high >= entry_low` thì khớp.

Entry price có thể là:

- Midpoint của entry zone.
- Biên gần giá hơn.
- Close của candle chạm zone.

Để bảo thủ nên dùng midpoint:

```python
entry_price = (entry_zone[0] + entry_zone[1]) / 2
```

## Giả Lập SL/TP

Sau khi có lệnh, quét các nến M15 hoặc H1 sau entry.

Nên dùng M15 nếu có để giảm sai số thứ tự chạm SL/TP.

Buy:

```python
if candle.low <= stop_loss:
    result = "loss"
    exit_price = stop_loss
elif candle.high >= take_profit:
    result = "win"
    exit_price = take_profit
```

Sell:

```python
if candle.high >= stop_loss:
    result = "loss"
    exit_price = stop_loss
elif candle.low <= take_profit:
    result = "win"
    exit_price = take_profit
```

Nếu trong cùng một nến chạm cả SL và TP, mặc định nên tính SL trước:

```text
conservative_same_bar = True
```

Lý do: OHLC không cho biết thứ tự giá di chuyển trong nến, tính SL trước là cách bảo thủ hơn.

## Tính R Result

Buy:

```python
risk = abs(entry_price - stop_loss)
result_r = (exit_price - entry_price) / risk
```

Sell:

```python
risk = abs(stop_loss - entry_price)
result_r = (entry_price - exit_price) / risk
```

Nếu có spread/slippage:

- Buy entry tăng thêm slippage/spread.
- Sell entry giảm thêm slippage/spread.
- Reward giảm, risk tăng.

MVP có thể dùng `expected_effective_rr` của scenario để filter, nhưng khi tính kết quả nên tính theo giá entry/SL/TP đã điều chỉnh.

## Metrics Tổng Quan

Các chỉ số bắt buộc:

```text
total_trades
wins
losses
breakeven
expired
win_rate
loss_rate
average_r
median_r
expectancy_r
average_win_r
average_loss_r
profit_factor
max_drawdown_r
max_consecutive_losses
max_consecutive_wins
total_r
trade_frequency
average_holding_bars
```

### Expectancy R

Đây là chỉ số quan trọng nhất:

```python
expectancy_r = sum(result_r_list) / len(result_r_list)
```

Hoặc:

```python
expectancy_r = win_rate * average_win_r - loss_rate * abs(average_loss_r)
```

Nếu `expectancy_r > 0`, hệ thống có kỳ vọng dương trên mẫu test.

Ví dụ:

```text
100 lệnh
win_rate = 42%
average_win_r = 1.8R
average_loss_r = -1.0R

expectancy = 0.42 * 1.8 - 0.58 * 1.0 = +0.176R/lệnh
```

### Profit Factor

```python
profit_factor = gross_profit_r / abs(gross_loss_r)
```

Ngưỡng tham khảo:

- `< 1.0`: hệ thống âm.
- `1.0 - 1.2`: rất yếu, dễ chết khi có slippage.
- `1.2 - 1.5`: có tiềm năng.
- `> 1.5`: đáng nghiên cứu sâu hơn.

### Max Drawdown R

Tính trên equity curve bằng R:

```python
peak = max(equity_so_far)
drawdown = peak - current_equity
max_drawdown = max(max_drawdown, drawdown)
```

Cần so sánh với account guard. Nếu max consecutive losses và max drawdown quá lớn, hệ thống có thể không chạy được ngoài đời dù expectancy dương.

## Breakdown Để Tìm Edge

Tổng kết tổng quan chưa đủ. Cần breakdown để biết hệ thống hiệu quả trong điều kiện nào.

### Theo Symbol

```text
EUR/USD
GBP/USD
XAU/USD
BTC/USD
...
```

Mục tiêu: tránh kết luận sai vì chỉ một symbol kéo lợi nhuận.

### Theo Side

```text
buy
sell
```

Mục tiêu: kiểm tra hệ thống có lệch hướng không.

### Theo Decision

```text
READY_TO_TRADE
WATCH_ONLY
WAITING_CONFIRMATION
TRADE_BLOCKED
STAND_ASIDE
```

Mục tiêu: xác nhận `READY_TO_TRADE` có tốt hơn các nhóm khác không.

### Theo Score Bucket

```text
50-59
60-69
70-79
80-89
90-100
```

Mục tiêu: tìm ngưỡng score nên trade. Ví dụ nếu `80-89` lợi nhuận tốt nhưng `70-79` âm, rule auto trade nên đặt ngưỡng 80.

### Theo Final Score Bucket

Tương tự signal score, nhưng dùng `result["final_score"]`.

Mục tiêu: kiểm tra final score có giá trị hơn signal score không.

### Theo M15 Quality

```text
strict
loose
none
missing
```

Mục tiêu: kiểm tra M15 strict có làm expectancy tăng không.

### Theo Market Regime

```text
trend_up
trend_down
range
volatile
unknown
```

Mục tiêu: biết nên trade trong trend hay range.

### Theo SMC Metadata

```text
selected_zone_score >= 75
selected_zone_score 55-74
selected_zone_score < 55
no selected zone
```

Và:

```text
liquidity_sweep_aligned true/false
displacement_aligned true/false
choch_against_direction true/false
selected_zone_type
```

Mục tiêu: biết những thành phần SMC nào thật sự có edge.

### Theo Expected Effective R:R

```text
< 1.0
1.0 - 1.3
1.3 - 1.5
1.5 - 2.0
> 2.0
```

Mục tiêu: xác nhận gate `EXPECTED_RR_TOO_LOW` có hợp lý không.

## Điều Kiện Đánh Giá Phương Pháp Hiệu Quả

Không nên dựa vào win rate đơn lẻ. Một phương pháp bắt đầu đáng quan tâm khi:

```text
total_trades >= 100
expectancy_r > 0.10R
profit_factor > 1.2
max_drawdown_r chấp nhận được
max_consecutive_losses nằm trong mức account guard
kết quả không phụ thuộc vào duy nhất một symbol
```

Tốt hơn:

```text
expectancy_r > 0.20R
profit_factor > 1.5
out-of-sample vẫn dương
kết quả ổn định trên nhiều tháng/năm và nhiều symbol
```

Cần cảnh giác nếu:

```text
win_rate cao nhưng average_loss lớn hơn average_win quá nhiều
profit factor chỉ hơn 1.0 một chút
lợi nhuận đến từ 1-2 lệnh cực lớn
chỉ có 1 symbol lời, các symbol khác âm
drawdown quá sâu
trade count quá ít
```

## Walk-Forward Và Out-Of-Sample

Nên chia dữ liệu thành 2 phần:

```text
In-sample: dùng để nghiên cứu rule và ngưỡng.
Out-of-sample: dùng để xác nhận rule sau khi đã chọn.
```

Ví dụ:

```text
2024-01-01 -> 2024-12-31: in-sample
2025-01-01 -> 2025-06-30: out-of-sample
```

Không nên tối ưu ngưỡng bằng out-of-sample. Nếu đã nhìn out-of-sample để sửa rule, cần tạo một giai đoạn test mới hơn.

## Controller

`controllers/backtest_controller.py` nên chịu trách nhiệm:

- Đọc settings.
- Resolve broker symbol.
- Tải dữ liệu lịch sử từ MT5.
- Thêm warmup period.
- Gọi `run_system_backtest()`.
- Lưu snapshot kết quả.

API đề xuất:

```python
class BacktestController:
    def create_backtest_worker(self, request: BacktestRequest) -> tuple[QThread, BacktestWorker]:
        ...

    def run_backtest(
        self,
        *,
        request: BacktestRequest,
        _progress_callback=None,
    ) -> dict[str, Any]:
        ...
```

## MT5 Historical Data

Cần thêm method vào `services/mt5_service.py`:

```python
def load_ohlcv_range(
    self,
    broker_symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> list[Candle]:
    ...
```

Nó nên dùng MetaTrader5:

```python
mt5.copy_rates_range(broker_symbol, timeframe_id, start, end)
```

Backtest cần warmup:

```text
D1: thêm tối thiểu 250-500 nến trước start
H4: thêm tối thiểu 250-500 nến trước start
H1: thêm tối thiểu 100-300 nến trước start
M15: thêm tối thiểu 200 nến trước start
```

## Worker

`workers/backtest_worker.py` nên giống pattern của `AnalysisWorker` và `ScannerWorker`:

```python
class BacktestWorker(QObject):
    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(dict)
    failed = pyqtSignal(str)
    finished = pyqtSignal()
```

Backtest có thể rất chậm, nên worker là bắt buộc.

## Thiết Kế Màn Hình Backtest

### Mục Tiêu UI

Màn hình Backtest phải giúp user:

- Chọn symbol và khoảng thời gian.
- Chạy backtest.
- Xem tổng quan hiệu quả.
- Xem breakdown theo nhóm.
- Xem danh sách trade.
- Mở chi tiết trade để debug vì sao hệ thống vào lệnh.

Không nên làm như landing page. Đây là màn hình công cụ, cần rõ ràng và dày thông tin.

### Layout Tổng Thể

```text
+---------------------------------------------------------------+
| Header: Backtest                                              |
| Symbol | Date from | Date to | Risk % | Mode | Run | Export   |
+---------------------------------------------------------------+
| KPI strip                                                     |
| Total Trades | Expectancy | Profit Factor | Max DD | Win Rate |
+---------------------------------------------------------------+
| Main split                                                    |
| Left: Equity Curve + Drawdown                                 |
| Right: Summary Diagnostics                                    |
+---------------------------------------------------------------+
| Tabs                                                          |
| Trades | Breakdown | Score Buckets | SMC | Settings | Logs    |
+---------------------------------------------------------------+
```

### Header Controls

Controls:

- Symbol combobox.
- Broker symbol readonly/resolved.
- Date from picker.
- Date to picker.
- Initial balance input.
- Risk percent input.
- Spread/slippage input.
- Mode segmented control:
  - Strict
  - Legacy
  - Research
- Time step:
  - H1
  - H4
- Button:
  - Run
  - Stop
  - Export JSON

### KPI Strip

Hiển thị:

```text
Total trades
Win rate
Expectancy R
Total R
Profit factor
Max drawdown R
Max consecutive losses
Average holding bars
```

Màu sắc:

- Expectancy > 0: xanh.
- Expectancy <= 0: đỏ/cảnh báo.
- Profit factor < 1.2: cảnh báo.
- Max drawdown cao: cảnh báo.

### Equity Curve

Chart nên có 2 đường:

- Cumulative R.
- Drawdown R.

Nếu chưa có chart native Python, có thể dùng chart bridge hiện có hoặc table tạm trong MVP.

### Diagnostics Panel

Hiển thị:

```text
Data range actual
Warmup candles used
Snapshots evaluated
Setups detected
Trades opened
Trades skipped
Blocked by gate
Missing data count
Average analysis time
```

Mục tiêu là debug vì sao backtest ít lệnh hoặc không có lệnh.

### Trades Tab

Bảng trade:

```text
Time
Symbol
Side
Decision
Entry
SL
TP
Exit
Result
R
Final score
Signal score
M15
Regime
Zone score
Reason
```

Click vào một trade mở detail panel:

```text
Decision summary
Scenario
SMC trade flags
Trade gate
Reason codes
Warning codes
Entry checklist
Analysis snapshot JSON
```

### Breakdown Tab

Bảng breakdown:

```text
Group
Trades
Win rate
Expectancy R
Profit factor
Total R
Max DD
Avg win
Avg loss
```

Group selector:

- Symbol
- Side
- Decision
- Score bucket
- Final score bucket
- M15 quality
- Market regime
- SMC zone score
- Liquidity sweep
- Displacement aligned
- CHOCH against direction
- Expected effective R:R bucket

### Score Buckets Tab

Tập trung vào ngưỡng score:

```text
Signal score bucket | Trades | Expectancy | PF | Win rate
Final score bucket  | Trades | Expectancy | PF | Win rate
Score gap bucket    | Trades | Expectancy | PF | Win rate
```

Dùng tab này để quyết định ngưỡng auto trade.

### SMC Tab

Tập trung vào chất lượng SMC:

```text
Zone score bucket
Selected zone type
Liquidity sweep aligned
Displacement aligned
CHOCH against direction
Premium/discount location
```

Mục tiêu là biết SMC component nào đang có giá trị.

### Settings Tab

Hiển thị cấu hình đã dùng cho run:

```text
Backtest mode
Date range
Warmup bars
Risk percent
Spread/slippage
Macro mode
Same-bar rule
Max holding bars
Setup expiry bars
Entry fill model
```

Cần lưu cùng result để sau này xem lại không bị mất context.

### Logs Tab

Hiển thị progress và cảnh báo:

```text
Loaded D1/H4/H1/M15 candles
Skipped snapshot because insufficient warmup
Skipped setup because gate blocked
Opened trade
Closed trade TP/SL
```

## Output JSON Đề Xuất

```json
{
  "mode": "system_backtest",
  "timestamp": "2026-06-10T12:00:00+07:00",
  "request": {},
  "summary": {
    "total_trades": 0,
    "win_rate": 0.0,
    "expectancy_r": 0.0,
    "profit_factor": 0.0,
    "max_drawdown_r": 0.0
  },
  "equity_curve": [],
  "breakdowns": {},
  "trades": [],
  "skipped_setups": [],
  "diagnostics": {}
}
```

## MVP Nên Làm Theo Thứ Tự

### Phase 1: Core Engine Không UI

- Tạo `core/system_backtest_engine.py`.
- Tạo `BacktestRequest`, `BacktestTrade`, `BacktestResult`.
- Viết walk-forward loop.
- Gọi `analyze_symbol()`.
- Giả lập entry tại close hiện tại.
- Giả lập SL/TP bằng M15.
- Tính summary cơ bản.
- Viết unit tests với candles synthetic.

### Phase 2: Script Chạy Thử

- Tạo `scripts/run_system_backtest.py`.
- Cho phép chạy 1 symbol, 1 date range.
- Export JSON.

### Phase 3: MT5 Historical Range

- Thêm `MT5Service.load_ohlcv_range()`.
- Controller load dữ liệu lịch sử.
- Cache optional.

### Phase 4: UI Backtest

- Thêm Backtest screen.
- Thêm worker.
- Hiển thị KPI, trades table, breakdown table.
- Export JSON.

### Phase 5: Nâng Cấp Simulation

- Pending entry zone.
- Setup expiry.
- Slippage/spread theo symbol.
- Multi-symbol batch backtest.
- Out-of-sample comparison.

### Phase 6: Historical Macro/News

- Chỉ làm sau khi core technical/SMC backtest đã ổn.
- Cần nguồn historical calendar/headlines đúng thời điểm.
- Không dùng news live cho quá khứ.

## Rủi Ro Và Giới Hạn

### OHLC Ambiguity

Nếu cùng một nến chạm SL và TP, backtest không biết giá chạm cái nào trước. Mặc định nên tính SL trước.

### Survivorship Và Data Quality

MT5 broker data có thể khác nhau theo broker. Backtest trên broker nào thì chỉ nên kết luận cho broker đó.

### Macro Live Không Đúng Cho Quá Khứ

Không được lấy macro/news hiện tại để đánh giá setup quá khứ.

### Speed

Gọi `analyze_symbol()` mỗi H1 bar có thể chậm. MVP chấp nhận cho 1 symbol và khoảng thời gian ngắn. Sau đó mới tối ưu.

### Overfitting

Nếu dùng backtest để sửa quá nhiều ngưỡng, kết quả sẽ bị overfit. Bắt buộc cần out-of-sample.

## Quy Tắc Chống Lỗi Dấu

Để không bao giờ bị lỗi dấu trong tài liệu và UI:

- Tất cả file `.py`, `.md`, `.json`, `.qss`, `.sql` phải lưu bằng `UTF-8`.
- VS Code phải hiện `UTF-8` ở góc dưới bên phải trước khi lưu.
- Không mở/sửa file bằng editor cũ chỉ hỗ trợ ANSI.
- PowerShell khi đọc file nên dùng:

```powershell
Get-Content docs\system_backtest_design.md -Encoding utf8
```

- Nếu terminal hiển thị sai dấu, sửa terminal trước, không sửa nội dung file hàng loạt:

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

- Không chạy script tự động replace kiểu `KhĂ´ng -> Không` trên toàn repo nếu chưa xác nhận file thật sự bị hỏng. Rất dễ làm hỏng file đang đúng UTF-8.

## Kết Luận

Chức năng backtest nên được xây như một system-level replay engine. Cách dùng đúng nhất là gọi lại `analyze_symbol()` trên từng snapshot lịch sử, sau đó có trade simulator riêng để tính khớp lệnh, SL/TP và R.

Chỉ nên kết luận hệ thống hiệu quả khi:

- Expectancy R dương.
- Profit factor đủ mạnh.
- Drawdown và chuỗi thua nằm trong giới hạn chấp nhận.
- Kết quả ổn định theo symbol, side, regime, M15 quality và score bucket.
- Out-of-sample vẫn giữ được edge.
