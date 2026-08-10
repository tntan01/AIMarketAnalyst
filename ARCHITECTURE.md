# ARCHITECTURE.md — Bản đồ module

> Bản đồ định vị nhanh. Đọc file này trước khi mò vào code. Chi tiết đầy đủ xem `docs/architecture/architecture.md`.

## Tổng quan

App desktop **AI Market Analyst** (PyQt6) phân tích trading MT5: lấy dữ liệu thị trường → phân tích kỹ thuật (SMC) + vĩ mô + AI → chấm điểm → xếp hạng → hiển thị bảng scanner → (tùy chọn) tự vào lệnh MT5.

**Luồng dữ liệu chính:**
```
MT5 / Yahoo / ForexFactory ──► services (data) ──► core (phân tích) ──► workers (nền) ──► controllers ──► ui (PyQt6)
                                                                                              │
                                                              AI prompts (services/ai) ◄──────┘
```

## Các lớp (layer)

| Thư mục | Vai trò |
|---------|---------|
| `main.py` | Entry point: khởi tạo runtime, QApplication, AppController, MainWindow |
| `controllers/` | **DI container + điều phối.** `AppController` giữ singleton mọi service/controller. Mỗi màn hình nhận cùng 1 instance |
| `core/` | **Logic nghiệp vụ thuần** (không phụ thuộc UI). Phân tích, SMC, scoring, risk, backtest, scanner engine |
| `services/` | **Truy cập bên ngoài + hạ tầng**: MT5, AI providers, news, journal (SQLite), telegram, storage, logging |
| `workers/` | **Thread nền** (QThread/QObject) chạy tác vụ nặng: scan, analyze, backtest, param sweep |
| `ui/` | **Giao diện PyQt6**: screens, components, theme, chart bridge |
| `config/` | Cấu hình: constants, paths, settings, risk params, AI providers, symbol profiles |
| `data/` | SQL migrations + seed data (journal DB) |
| `prompts/` | Prompt AI (full analysis + sections) |
| `tools/`, `scripts/` | Tiện ích dev/audit/validation (chạy thủ công, không phải runtime) |
| `packaging/` | Build Windows (PyInstaller) |
| `tests/` | Pytest |

## Module then chốt (đọc khi cần)

### Luồng phân tích 1 symbol
- `core/analysis_pipeline.py` — **orchestrator** chính: gọi tuần tự các engine, trả dict kết quả
- `core/analysis_engine.py` — engine phân tích tổng
- `core/indicators.py` — tính chỉ báo kỹ thuật
- `core/smc_*.py` — Smart Money Concepts: context, zones, confluence, scorer, validation
- `core/signal_engine.py` — bias, risk condition, scenario score
- `core/risk_engine.py` — scenarios, trade permission, contract size, RR
- `core/final_score_engine.py` — điểm tổng
- `core/decision_engine.py` — quyết định cuối (entry/stand aside...)
- `core/correlation_check.py` — điều chỉnh tương quan

### Scanner (bảng quét thị trường)
- `core/scanner.py` — models + build scanner output
- `core/scanner_candidate_engine.py` — build candidate order payload
- `core/scanner_ranking_engine.py` — xếp hạng (READY_NOW / WAITING / WATCH / BLOCKED)
- `core/scanner_strategy_engine.py` + `scanner_strategy_router.py` — chọn chiến lược
- `core/scanner_ai_auditor.py` — AI audit setup
- `core/scanner_observability.py` / `scanner_performance.py` — theo dõi + hiệu năng
- `controllers/scanner_controller.py` — điều phối scan (thread pool)
- `workers/scanner_worker.py` — chạy scan nền

### Backtest
- `core/backtest_engine.py` — engine chính
- `core/backtest_*.py` — config, execution, statistics, portfolio, walk-forward, monte-carlo, golden replay, validation
- `controllers/backtest_controller.py` + `workers/backtest_worker.py`

### Vào lệnh MT5 (auto-entry)
- `core/entry_engine.py` — logic vào lệnh
- `core/execution_*_engine.py` — readiness, quality, revalidation
- `core/order_management_state_machine.py` — state machine lệnh
- `services/order_management_service.py` + `order_management_state_store.py`
- `core/account_guard.py` — bảo vệ tài khoản
- `core/portfolio_risk_engine.py` — rủi ro danh mục

### Journal (nhật ký giao dịch)
- `services/journal_service.py` + `journal_models.py` + `journal_converters.py`
- `core/journal_feedback_engine.py` — phản hồi từ journal
- `controllers/journal_controller.py` + `ui/screens/journal_*.py`

### AI
- `services/ai_service.py` — facade AI
- `services/ai/provider_adapter.py` + `providers/*.py` — adapter từng provider (openai, anthropic, gemini, deepseek, openai_compatible)
- `services/ai_provider_catalog_service.py` — catalog provider
- `prompts/` — nội dung prompt

### Dữ liệu thị trường
- `services/mt5_service.py` — MT5
- `services/market_data_service.py` + `data_provider.py` + `candle_history_cache.py`
- `services/yahoo_chart_fetcher.py` — Yahoo fallback
- `services/forex_factory_client.py` + `event_impact_assessor.py` + `macro_*` — tin tức/vĩ mô

## Ghi chú
- **DI container:** mọi service/controller là singleton lazy trong `AppController` — thêm dependency mới thì đăng ký ở đó.
- **UI không gọi service trực tiếp** — đi qua controller/worker để giữ UI thread không bị block.
- **Version tracking:** nhiều engine có hằng `*_VERSION` (SMC_DOMAIN_VERSION, PORTFOLIO_ENGINE_VERSION...) — dùng để truy vết thay đổi logic.