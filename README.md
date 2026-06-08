# AI Market Analyst

Desktop trading analysis app built with PyQt6.

Core stack:
- PyQt6 desktop shell
- QWebEngineView for embedded web charts
- Python core for MT5 data, indicators, SMC context, AI prompts, scoring, and risk
- Simple AI configuration: provider, model, API key, and API key test

Supported markets:
- 28 Forex pairs
- XAU/USD

MT5 note:
- Broker symbols may include suffixes such as `m` or `c`, for example `USDCADm`, `USDCADc`, `NZDUSDm`, `NZDUSDc`.
- The MT5 service must resolve app symbols like `USD/CAD` to the broker-specific symbol available in Market Watch.
