# AI Market Analyst

Desktop trading analysis app built with PyQt6.

Core stack:
- PyQt6 desktop shell
- QWebEngineView for embedded web charts
- Python core for MT5 data, indicators, SMC context, AI prompts, scoring, and risk
- Simple AI configuration: provider, model, API key, and API key test
- Scanner auto-scan can optionally place MT5 market orders for `ready` + `allowed` setups when the user enables the `Tự động vào lệnh MT5` toggle button, using risk-based lot sizing and one-order-per-symbol protection

Supported markets:
- 28 Forex pairs
- XAU/USD
- XAG/USD
- BTC/USD

MT5 note:
- Broker symbols may include suffixes such as `m` or `c`, for example `USDCADm`, `USDCADc`, `NZDUSDm`, `NZDUSDc`.
- The MT5 service must resolve app symbols like `USD/CAD` to the broker-specific symbol available in Market Watch.
- Auto-entry is active only in auto-scan mode and only when the `Tự động vào lệnh MT5` toggle button is on. Manual one-shot scans do not place MT5 orders.
- Auto-entry checks existing positions and pending orders for the broker symbol before sending a new order.
