from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from core.analysis_engine import analyze_symbol, fallback_ai_commentary
from core.market_models import Candle
from core.prompt_builder import build_full_analysis_prompt
from core.risk_engine import AnalysisInput, contract_size_override_for_symbol
from PyQt6.QtCore import QThread
from config.paths import CONFIG_DIR
from services.ai_service import AIProviderConfig, AIService
from services.journal_service import JournalService
from services.mt5_service import MT5Service
from services.news_service import NewsService
from services.settings_service import SettingsService
from ui.translation import vi_text
from workers.analysis_worker import AnalysisWorker


class AnalysisController:
    _SECTION_HEADER = re.compile(r"^\s*(\d+)\.\s+(.+)")
    _BULLET_LINE = re.compile(r"^\s*[-•]\s+(.*)")
    _CLEAN_MD = re.compile(r"[*_~`]")
    _REASONING_LEAK = re.compile(
        r"^(bullet\s*\d*\s*:?\s*|maybe\s+add\s*:?\s*|note\s*:?\s*|also\s+add\s*:?\s*|consider\s+adding\s*:?\s*)",
        re.IGNORECASE,
    )
    _SECTION_TITLES: dict[int, str] = {
        1: "1. Tình hình vĩ mô",
        2: "2. Sự kiện kinh tế sắp tới",
        3: "3. Nhận định theo số liệu tính toán",
        4: "4. Lời khuyên hành động",
    }
    _SECTION_LIMITS: dict[int, int] = {1: 3, 2: 5, 3: 5, 4: 3}

    def __init__(
        self,
        settings_service: SettingsService | None = None,
        mt5_service: MT5Service | None = None,
        news_service: NewsService | None = None,
        journal_service: JournalService | None = None,
    ) -> None:
        self.settings_service = settings_service or SettingsService()
        self.mt5_service = mt5_service or MT5Service()
        self.news_service = news_service or NewsService()
        self.journal_service = journal_service  # optional, chỉ dùng cho account guard

    def build_prompt(self, values: dict[str, object]) -> str:
        return build_full_analysis_prompt(values)

    def create_single_analysis_worker(
        self,
        *,
        symbol: str,
        broker_symbol: str | None,
        account_balance: float,
        risk_percent: float,
        timezone_name: str,
    ) -> tuple[QThread, AnalysisWorker]:
        request = {
            "symbol": symbol,
            "broker_symbol": broker_symbol,
            "account_balance": account_balance,
            "risk_percent": risk_percent,
            "timezone_name": timezone_name,
        }
        thread = QThread()
        worker = AnalysisWorker(self.run_single_analysis, request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        return thread, worker

    def run_single_analysis(
        self,
        *,
        symbol: str,
        broker_symbol: str | None,
        account_balance: float,
        risk_percent: float,
        timezone_name: str,
        _progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, object]:
        progress = _progress_callback or (lambda _percent, _message: None)
        progress(10, "Đang đọc cài đặt phân tích...")
        settings = self.settings_service.load()
        mt5_balance = self.mt5_service.account_balance()
        effective_balance = mt5_balance if (mt5_balance is not None and mt5_balance > 0) else float(account_balance or settings.trading.account_balance or 0.0)
        if effective_balance <= 0:
            raise RuntimeError(
                "Không có số dư hợp lệ để tính khối lượng. Hãy kiểm tra MT5 đã đăng nhập broker hoặc đặt 'Số dư mặc định' tại Cài đặt > Giao dịch."
            )
        progress(15, "Đang kiểm tra mã broker trong Market Watch...")
        resolved_broker_symbol = broker_symbol or self._resolve_broker_symbol(symbol)
        bars_by_timeframe = {
            "D1": settings.advanced.d1_bars,
            "H4": settings.advanced.h4_bars,
            "H1": settings.advanced.h1_bars,
        }
        candles = {}
        for percent, timeframe in [(30, "D1"), (45, "H4"), (60, "H1")]:
            progress(percent, f"Đang lấy dữ liệu {timeframe} từ MT5...")
            candles[timeframe] = self.mt5_service.load_ohlcv(resolved_broker_symbol, timeframe, bars_by_timeframe[timeframe])
        progress(63, "Đang lấy dữ liệu M15 từ MT5...")
        m15_candles = self.mt5_service.load_ohlcv(resolved_broker_symbol, "M15", 200)
        correlation_context = self._fetch_correlation_data(symbol)
        progress(68, "Đang kiểm tra chất lượng dữ liệu và lịch kinh tế...")
        data_quality = self.mt5_service.symbol_data_quality(symbol, resolved_broker_symbol)
        news_flags = self.news_service.data_quality_flags(symbol)
        macro_context = news_flags.pop("macro_context", {"events": []})
        if isinstance(macro_context, dict):
            macro_context["latest_headlines"] = self._localized_news_items(macro_context.get("latest_headlines", []))
            macro_context["latest_statements"] = self._localized_news_items(macro_context.get("latest_statements", []))
        data_quality.update(news_flags)
        freshness = self.news_service.macro_freshness_status()
        macro_confidence = float(macro_context.get("macro_data_quality", 1.0)) if isinstance(macro_context, dict) else 1.0
        macro_confidence = macro_confidence * float(freshness.get("confidence_multiplier", 1.0))
        data_quality["macro_freshness"] = freshness
        contract_override = contract_size_override_for_symbol(
            symbol,
            data_quality,
            settings.trading.contract_size_override,
        )
        request = AnalysisInput(
            symbol=symbol,
            broker_symbol=resolved_broker_symbol,
            account_balance=effective_balance,
            risk_percent=risk_percent,
            account_currency=settings.trading.account_currency,
            lot_step=settings.trading.lot_step,
            minimum_lot=settings.trading.minimum_lot,
            contract_size_override=float(contract_override) if contract_override else None,
            timezone_name=timezone_name,
        )

        ai_meta: dict[str, object] = {}
        active_ai = settings.ai.active_provider()
        if active_ai and active_ai.api_key:
            ai_meta = {
                "provider_name": active_ai.provider,
                "model_macro": active_ai.model,
                "model_writer": active_ai.model,
                "fallback": True,
            }

        progress(78, "Đang tính indicator, score, trade plan và lot...")
        macro_alignment = macro_context.get("macro_alignment_scores") if isinstance(macro_context, dict) else None
        quote_currency = request.symbol.split("/")[-1] if "/" in request.symbol else request.symbol[-3:]
        quote_to_usd = self.mt5_service.quote_to_usd_rate(quote_currency)
        closed_trades = self.journal_service.list_closed_trades_for_account_guard() if self.journal_service else []
        account_guard_settings = {
            "max_daily_loss_pct": 2.0,
            "max_weekly_loss_pct": 5.0,
            "max_consecutive_losses": 3,
            "max_open_risk_pct": 3.0,
            "trader_timezone": settings.display.timezone or "Asia/Ho_Chi_Minh",
        }
        result = analyze_symbol(
            request,
            candles,
            data_quality=data_quality,
            macro_alignment=macro_alignment if isinstance(macro_alignment, dict) else None,
            macro_confidence=macro_confidence,
            ai_meta=ai_meta,
            m15_candles=m15_candles,
            correlation_context=correlation_context,
            quote_to_usd_rate=quote_to_usd,
            closed_trades=closed_trades,
            open_trades=[],
            account_guard_settings=account_guard_settings,
            use_decision_engine_action=True,
        )
        result["economic_events"] = self._localized_events(macro_context.get("events", []))
        result["macro"]["driver_context"] = macro_context
        result["latest_news"] = macro_context.get("latest_statements", []) if isinstance(macro_context, dict) else []
        if isinstance(macro_context, dict):
            result["macro"]["macro_tier_detail"] = macro_context.get("macro_tier_detail", {})
            result["macro"]["macro_data_quality"] = macro_context.get("macro_data_quality", 1.0)
        progress(85, "Đang gọi AI tạo nhận định...")
        if active_ai and active_ai.api_key:
            self._combined_ai_call(result, active_ai)
        else:
            best_side = result["decision_summary"]["best_scenario"]
            best_score = result["decision_summary"]["best_score"]
            result["macro"]["ai_summary"] = self._fallback_ai_commentary_from_result(result, best_side, best_score)
        if active_ai and active_ai.api_key:
            ai_summary_text = str(result["macro"].get("ai_summary", ""))
            result["ai_provider"] = {
                "provider_name": active_ai.provider,
                "model_macro": active_ai.model,
                "model_writer": active_ai.model,
                "fallback": ai_summary_text.startswith("Không thể tạo nhận định AI"),
            }
        else:
            result["ai_provider"] = {
                "provider_name": None,
                "model_macro": None,
                "model_writer": None,
                "fallback": True,
                "fallback_reason": "AI chưa được cấu hình, macro score tạm đặt trung tính.",
            }
        return result

    def _resolve_broker_symbol(self, symbol: str) -> str:
        available = self.mt5_service.available_symbols(market_watch_only=True)
        resolved = self.mt5_service.resolve_symbol(symbol, available)
        if not resolved:
            aliases = ", ".join(self.mt5_service.aliases_for(symbol))
            raise RuntimeError(f"Không tìm thấy mã broker cho {symbol} trong Market Watch. Gợi ý: {aliases}")
        return resolved

    def _fetch_correlation_data(self, symbol: str) -> dict[str, object]:
        import yfinance as yf
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from core.market_models import Candle

        ctx: dict[str, object] = {}
        tickers = {"dxy": "DX-Y.NYB", "vix": "^VIX", "us10y": "^TNX"}

        def _download_one(key: str, ticker: str):
            try:
                data = yf.download(ticker, period="5d", interval="1d", progress=False)
                if data is None or data.empty:
                    return key, None

                candles: list[Candle] = []
                for idx, row in data.iterrows():
                    close_val = row["Close"]
                    if hasattr(close_val, "iloc"):
                        close_val = close_val.iloc[0]
                    open_val = row["Open"]
                    if hasattr(open_val, "iloc"):
                        open_val = open_val.iloc[0]
                    high_val = row["High"]
                    if hasattr(high_val, "iloc"):
                        high_val = high_val.iloc[0]
                    low_val = row["Low"]
                    if hasattr(low_val, "iloc"):
                        low_val = low_val.iloc[0]

                    candles.append(Candle(
                        time=idx.to_pydatetime(),
                        open=float(open_val),
                        high=float(high_val),
                        low=float(low_val),
                        close=float(close_val),
                    ))
                return key, candles
            except Exception:
                return key, None

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_download_one, key, ticker): key for key, ticker in tickers.items()}
            for future in as_completed(futures):
                key, candles = future.result()
                ctx[f"{key}_candles"] = candles

        return ctx

    def _write_ai_commentary(self, result: dict[str, object], active_ai) -> str:
        best_side = result["decision_summary"]["best_scenario"]
        best_score = result["decision_summary"]["best_score"]
        if not active_ai or not active_ai.api_key:
            return self._fallback_ai_commentary_from_result(result, best_side, best_score)

        prompt = self.build_prompt(
            {
                "symbol": result["symbol"],
                "base_currency": str(result["symbol"]).split("/")[0],
                "quote_currency": str(result["symbol"]).split("/")[-1],
                "macro_flow": self._json_block(self._macro_prompt_payload(result)),
                "behavior_model": self._json_block(self._behavior_prompt_payload(result)),
                "technical_smc": self._json_block(self._technical_prompt_payload(result)),
                "output_schema": self._ai_output_schema(),
            }
        )
        try:
            commentary = AIService(
                AIProviderConfig(active_ai.provider, active_ai.model, active_ai.api_key)
            ).analyze(prompt)
            return self._normalize_ai_commentary(commentary, result)
        except Exception as exc:
            return self._normalize_ai_commentary(
                "Không thể tạo nhận định AI tại thời điểm này. Hệ thống vẫn hiển thị phân tích kỹ thuật, "
                "điểm kịch bản và quản trị rủi ro dựa trên dữ liệu đã tính toán. "
                f"Lý do kỹ thuật: {exc}",
                result,
            )

    def _enrich_macro_news_with_ai(self, result: dict[str, object], active_ai) -> None:
        events = self._localized_events(result.get("economic_events", []))
        macro = result.get("macro", {}) if isinstance(result.get("macro"), dict) else {}
        driver_context = macro.get("driver_context", {}) if isinstance(macro.get("driver_context"), dict) else {}
        statements = self._localized_news_items(driver_context.get("latest_statements", []))
        if not events and not statements:
            return
        payload = {
            "symbol": result.get("symbol"),
            "base_currency": str(result.get("symbol", "")).split("/")[0],
            "quote_currency": str(result.get("symbol", "")).split("/")[-1],
            "economic_events": events[:8],
            "latest_official_statements": statements[:10],
        }
        prompt = (
            "Bạn là trợ lý macro cho phần mềm giao dịch. Chỉ dùng dữ liệu JSON dưới đây, không tự thêm tin mới.\n"
            "Hãy dịch đầy đủ tên tin/phát biểu sang tiếng Việt và nhận định ảnh hưởng ngắn gọn tới đồng tiền liên quan.\n"
            "Trả về JSON hợp lệ, không markdown, theo schema:\n"
            '{"economic_events":[{"index":0,"event_vi":"...","impact_assessment":"..."}],'
            '"latest_official_statements":[{"index":0,"title_vi":"...","impact_assessment":"..."}]}\n'
            f"Dữ liệu:\n{self._json_block(payload)}"
        )
        try:
            raw = AIService(AIProviderConfig(active_ai.provider, active_ai.model, active_ai.api_key)).analyze(prompt)
            enriched = self._parse_ai_json_object(raw)
        except Exception:
            return
        if not isinstance(enriched, dict):
            return
        self._apply_ai_event_enrichment(result, enriched.get("economic_events"))
        self._apply_ai_statement_enrichment(driver_context, enriched.get("latest_official_statements"))

    def _parse_ai_json_object(self, raw: object) -> dict[str, object]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end >= start:
            text = text[start : end + 1]
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}

    def _apply_ai_event_enrichment(self, result: dict[str, object], items: object) -> None:
        events = result.get("economic_events", [])
        if not isinstance(events, list) or not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index", -1))
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(events) and isinstance(events[index], dict):
                if item.get("event_vi"):
                    events[index]["event_vi"] = str(item["event_vi"])
                if item.get("impact_assessment"):
                    events[index]["impact_assessment"] = str(item["impact_assessment"])

    def _apply_ai_statement_enrichment(self, driver_context: dict[str, object], items: object) -> None:
        statements = driver_context.get("latest_statements", [])
        if not isinstance(statements, list) or not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index", -1))
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(statements) and isinstance(statements[index], dict):
                if item.get("title_vi"):
                    statements[index]["title_vi"] = str(item["title_vi"])
                if item.get("impact_assessment"):
                    statements[index]["impact_assessment"] = str(item["impact_assessment"])

    def _macro_prompt_payload(self, result: dict[str, object]) -> dict[str, object]:
        symbol = str(result["symbol"])
        base, quote = symbol.split("/")
        timezone_name = self._display_timezone()
        macro = result.get("macro", {}) if isinstance(result.get("macro"), dict) else {}
        driver_context = macro.get("driver_context", {}) if isinstance(macro.get("driver_context"), dict) else {}
        headlines = driver_context.get("latest_headlines", []) if isinstance(driver_context.get("latest_headlines"), list) else []
        latest_statements = driver_context.get("latest_statements", []) if isinstance(driver_context.get("latest_statements"), list) else []
        themes = driver_context.get("macro_themes", []) if isinstance(driver_context.get("macro_themes"), list) else []
        hotspots = driver_context.get("geopolitical_hotspots", []) if isinstance(driver_context.get("geopolitical_hotspots"), list) else []
        lines = [f"- {symbol}: phần vĩ mô dùng headline mới nhất, lịch kinh tế và macro theme do app lấy được."]
        for item in themes[:4]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('currency', '--')}: stance={item.get('stance', 'neutral')}, số headline khớp={item.get('headline_count', 0)}.")
        if headlines:
            lines.append("- Tin mới nhất:")
            for item in headlines[:5]:
                if isinstance(item, dict):
                    lines.append(f"  - {item.get('title', '--')} | {item.get('source', '--')} | {item.get('published_utc', '--')}")
        if hotspots:
            lines.append("- Điểm nóng thế giới:")
            for item in hotspots[:3]:
                if isinstance(item, dict):
                    lines.append(f"  - {item.get('title', '--')} | {item.get('source', '--')}")
        return {
            "symbol": symbol,
            "base_currency": base,
            "quote_currency": quote,
            "macro_summary_lines": lines,
            "base_currency_drivers": self._currency_driver(base),
            "quote_currency_drivers": self._currency_driver(quote),
            "macro_snapshot_from_app": result.get("macro", {}),
            "scenario_macro_alignment_scores": {
                side: values.get("macro_alignment")
                for side, values in (result.get("scenario_scores", {}) or {}).items()
                if isinstance(values, dict)
            },
            "latest_macro_headlines_from_app": driver_context.get("latest_headlines", []),
            "latest_official_statements_from_app": self._localized_news_items(latest_statements),
            "macro_themes_from_app": driver_context.get("macro_themes", []),
            "geopolitical_hotspots_from_app": driver_context.get("geopolitical_hotspots", []),
            "macro_alignment_reasons_from_app": driver_context.get("macro_alignment_reasons", {}),
            "display_timezone": timezone_name,
            "upcoming_economic_events_from_app": self._localized_events(result.get("economic_events", [])),
            "event_instruction": (
                f"Toàn bộ thời gian trong nhận định phải hiển thị theo múi giờ {timezone_name}; "
                "dùng đúng giá trị event_time_local đã cung cấp, không tự đổi sang múi giờ khác. "
                "Mọi lịch kinh tế phải viết theo mẫu: ngày-tháng-năm thời gian: nội dung tiếng Việt -> ảnh hưởng tới đồng tiền đang xét. "
                "Tin mới nhất chỉ thêm phần '-> ảnh hưởng...' khi dữ liệu hoặc nhận định AI cho thấy có tác động cụ thể; không viết câu tác động chung chung. "
                "Nếu upcoming_economic_events_from_app rỗng, nói rõ app chưa có dữ liệu lịch kinh tế sắp tới; "
                "không tự bịa tên tin, giờ công bố hoặc mức độ ảnh hưởng. "
                "Chỉ nêu headline, phát biểu quan chức, Reuters poll, central bank stance, yield differential, intervention risk hoặc điểm nóng thế giới nếu chúng có trong latest_macro_headlines_from_app, latest_official_statements_from_app, macro_themes_from_app hoặc geopolitical_hotspots_from_app."
            ),
        }

    def _behavior_prompt_payload(self, result: dict[str, object]) -> dict[str, object]:
        return {
            "symbol": result.get("symbol"),
            "market_regime": result.get("market_regime"),
            "direction_bias": result.get("direction_bias"),
            "trade_permission": result.get("trade_permission"),
            "decision_summary": result.get("decision_summary"),
            "why_not_opposite": result.get("why_not_opposite"),
            "confidence_reason": result.get("confidence_reason"),
        }

    def _technical_prompt_payload(self, result: dict[str, object]) -> dict[str, object]:
        scenario = self._primary_scenario(result)
        corr_context = scenario.get("correlation_context") if isinstance(scenario, dict) else None
        corr_warnings = scenario.get("correlation_warnings", []) if isinstance(scenario, dict) else []
        return {
            "technical_context": result.get("technical"),
            "scenario_scores": result.get("scenario_scores"),
            "entry_checklist": result.get("entry_checklist"),
            "entry_context": self._entry_context_payload(result),
            "backtest": result.get("backtest"),
            "computed_trade_plan": result.get("scenarios"),
            "data_quality": result.get("data_quality"),
            "risk_management": result.get("risk_management"),
            "correlation_context": corr_context,
            "correlation_warnings": corr_warnings,
            "hard_constraints": [
                "Không tự tạo giá, vùng entry, SL, TP, lot hoặc tin tức ngoài dữ liệu JSON này.",
                "Chỉ chọn, giải thích và diễn đạt lại số liệu do Python đã tính.",
                "Nếu trade_permission là blocked hoặc không có setup sạch, ưu tiên kết luận đứng ngoài.",
                "Nếu correlation_context có warning, đề cập đến cảnh báo phân kỳ trong nhận định.",
            ],
        }

    def _entry_context_payload(self, result: dict[str, object]) -> dict[str, object]:
        scenario = self._primary_scenario(result)
        technical = result.get("technical", {}) if isinstance(result.get("technical"), dict) else {}
        decision = result.get("decision_summary", {}) if isinstance(result.get("decision_summary"), dict) else {}
        price = technical.get("price")
        entry_zone = scenario.get("entry_zone") if scenario else None
        atr_value = technical.get("atr_h4") or technical.get("atr_d1") or 0.0
        return {
            "current_price": price,
            "side": scenario.get("type") if scenario else decision.get("best_scenario"),
            "entry_zone": entry_zone,
            "watch_zone": scenario.get("watch_zone") if scenario else None,
            "stop_loss": scenario.get("stop_loss") if scenario else None,
            "take_profit": scenario.get("take_profit") if scenario else None,
            "risk_reward": scenario.get("risk_reward") if scenario else None,
            "entry_status": scenario.get("entry_status") if scenario else None,
            "trigger_type": scenario.get("trigger_type") if scenario else None,
            "confirmation_score": scenario.get("confirmation_score") if scenario else None,
            "price_vs_zone": self._price_vs_zone(price, entry_zone, atr_value),
        }

    def _primary_scenario(self, result: dict[str, object]) -> dict[str, object]:
        scenarios = result.get("scenarios", []) if isinstance(result.get("scenarios"), list) else []
        scenarios = [item for item in scenarios if isinstance(item, dict)]
        decision = result.get("decision_summary", {}) if isinstance(result.get("decision_summary"), dict) else {}
        best_side = decision.get("best_scenario")
        matched = next((item for item in scenarios if item.get("type") == best_side), None)
        if matched:
            return matched
        return scenarios[0] if scenarios else {}

    def _price_vs_zone(self, price: object, entry_zone: object, atr_value: object) -> str:
        if not isinstance(price, (int, float)) or not isinstance(entry_zone, list) or len(entry_zone) != 2:
            return "unknown"
        try:
            low = float(min(entry_zone))
            high = float(max(entry_zone))
            current = float(price)
            atr = float(atr_value or 0.0)
        except (TypeError, ValueError):
            return "unknown"
        if low <= current <= high:
            return "in_zone"
        distance = low - current if current < low else current - high
        if atr > 0 and distance <= atr * 0.5:
            return "near_zone"
        return "far"

    def _ai_output_schema(self) -> str:
        timezone_name = self._display_timezone()
        return (
            "Trả lời 100% bằng tiếng Việt, rõ ràng, dễ đọc, dùng đúng các tiêu đề sau và bullet ngắn.\n"
            "TUYỆT ĐỐI CẤM: không được viết các từ 'bullet1', 'bullet2', 'Maybe add', 'Note:', 'Also add', 'Consider adding', hoặc bất kỳ ghi chú nội bộ nào vào nội dung bullet. Mỗi bullet phải là một câu hoàn chỉnh, sẵn sàng cho người dùng cuối đọc.\n"
            "Chỉ trả lời phần nhận định cuối cùng; không viết quá trình suy nghĩ, kế hoạch viết bài, câu như 'chúng ta cần', 'trước hết', 'cần kiểm tra' hoặc giải thích cách bạn sẽ trả lời.\n"
            "Bắt đầu ngay bằng dòng '1. Tình hình vĩ mô'. Tổng độ dài tối đa 16 bullet cho cả 4 mục; mỗi bullet tối đa 1 câu ngắn.\n"
            "Quy tắc ngôn ngữ bắt buộc:\n"
            "- Ưu tiên dùng tiếng Việt cho mọi diễn giải; chỉ giữ lại thuật ngữ tiếng Anh khi đó là tên riêng, mã sản phẩm hoặc thuật ngữ trading rất phổ biến.\n"
            "- Mỗi lần thuật ngữ tiếng Anh xuất hiện lần đầu trong câu trả lời, bắt buộc kèm bản dịch tiếng Việt trong ngoặc đơn ngay sau, ví dụ: Direction Bias (thiên hướng giao dịch), Stop Loss (cắt lỗ), Take Profit (chốt lời), Risk/Reward (tỷ lệ rủi ro/lợi nhuận), Buy Score (điểm mua), Sell Score (điểm bán), Trade Permission (quyền giao dịch), BOS (phá cấu trúc), CHOCH (đảo cấu trúc), FVG (khoảng trống giá trị hợp lý), Order Block (khối lệnh tổ chức), Supply Zone (vùng cung), Demand Zone (vùng cầu), Liquidity Pool (vùng thanh khoản), Premium (vùng giá cao), Discount (vùng giá thấp).\n"
            "- Trạng thái thị trường phải dịch: trend_up (xu hướng tăng), trend_down (xu hướng giảm), range (đi ngang), volatile (biến động mạnh), news_sensitive (nhạy tin tức), unknown (chưa rõ).\n"
            "- Quyền giao dịch phải dịch: allowed (được phép), caution (cẩn trọng), blocked (bị chặn).\n"
            "- Hành động phải dịch: ready (sẵn sàng), watch (theo dõi), wait (chờ), wait_for_confirmation (chờ xác nhận), stand_aside (đứng ngoài), skip (bỏ qua).\n"
            "- Thiên hướng phải dịch: buy (mua), sell (bán), neutral (trung lập).\n"
            "- Không viết toàn chữ in hoa BUY/SELL; dùng 'mua' hoặc 'bán' (kèm BUY/SELL trong ngoặc nếu cần).\n"
            f"- Mọi mốc thời gian, giờ công bố tin và thời điểm trong nhận định phải hiển thị theo múi giờ {timezone_name}; không dùng UTC hay múi giờ khác. Nếu dữ liệu chỉ có UTC, phải đổi sang múi giờ trên trước khi viết.\n"
            "Tiêu đề bắt buộc:\n"
            "1. Tình hình vĩ mô\n"
            "- Nêu yếu tố ảnh hưởng chính của đồng tiền cơ sở (base currency) và đồng định giá (quote currency) theo dữ liệu app cung cấp.\n"
            "- Nêu tác động tăng/giảm/trung tính cho cặp tiền; nếu chưa đủ dữ liệu thì nói rõ chưa đủ dữ liệu.\n\n"
            "- Nếu latest_official_statements_from_app có dữ liệu, thêm dòng 'Tin mới nhất:' trong mục này; mỗi phát biểu một bullet theo mẫu ngày-tháng-năm thời gian: nội dung tiếng Việt, chỉ thêm '-> ảnh hưởng...' khi có tác động cụ thể.\n\n"
            "2. Sự kiện kinh tế sắp tới\n"
            f"- Liệt kê sự kiện trong upcoming_economic_events_from_app nếu có; ghi giờ theo múi giờ {timezone_name}.\n"
            "- Mỗi tin lịch kinh tế phải theo mẫu ngày-tháng-năm thời gian: tên tin tiếng Việt -> ảnh hưởng tới đồng tiền đang xét.\n"
            "- Nếu không có dữ liệu lịch kinh tế, ghi rõ: App chưa có dữ liệu lịch kinh tế sắp tới, không xác nhận được sự kiện kích hoạt 24-72 giờ tới.\n\n"
            "3. Nhận định theo số liệu tính toán\n"
            "- Dựa trên trạng thái thị trường, thiên hướng, quyền giao dịch, điểm mua/bán, vùng hỗ trợ/kháng cự và kế hoạch giao dịch.\n"
            "- Khong bia them gia; chi dung entry_context va computed_trade_plan de neu gia hien tai dang trong/gan/xa vung entry, vung vao lenh, cat lo, chot loi, khoi luong.\n\n"
            "4. Lời khuyên hành động\n"
            "- Nêu nên sẵn sàng / theo dõi / chờ / đứng ngoài.\n"
            "- Nêu điều kiện xác nhận, điều kiện vô hiệu, và lưu ý rủi ro.\n"
            "- Nếu không có thiết lập sạch: ghi đúng 'Không có thiết lập giao dịch sạch (No clean setup), nên đứng ngoài'.\n"
            "- Không dùng cụm 'dữ liệu AI nội bộ'; phải gọi đúng là dữ liệu rule engine, dữ liệu vĩ mô/headline của app hoặc nhận định AI.\n"
            "Không dùng Markdown bold/italic, không dùng dấu * trong phản hồi."
        )

    def _currency_driver(self, currency: str) -> dict[str, object]:
        try:
            data = json.loads((CONFIG_DIR / "currency_drivers.json").read_text(encoding="utf-8"))
        except Exception:
            return {"drivers": [], "behavior_questions": []}
        return data.get(currency, {"drivers": [], "behavior_questions": []})

    def _json_block(self, value: object) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    def _fallback_ai_commentary_from_result(self, result: dict[str, object], best_side: str, best_score: int) -> str:
        symbol = str(result.get("symbol", "--"))
        permission = result.get("trade_permission", {}) if isinstance(result.get("trade_permission"), dict) else {}
        scores = result.get("scenario_scores", {}) if isinstance(result.get("scenario_scores"), dict) else {}
        buy_score = scores.get("buy", {}).get("total", "--") if isinstance(scores.get("buy"), dict) else "--"
        sell_score = scores.get("sell", {}).get("total", "--") if isinstance(scores.get("sell"), dict) else "--"
        decision = fallback_ai_commentary(symbol, best_side, best_score, permission)
        permission_text = self._vi_term(str(permission.get("status", "--")))
        return self._normalize_ai_commentary(
            "\n".join(
            [
                "1. Tình hình vĩ mô",
                "- AI (trí tuệ nhân tạo) chưa được cấu hình hoặc chưa có khóa API hợp lệ, nên app chưa thể viết nhận định vĩ mô riêng.",
                "- Macro Alignment (mức độ thuận vĩ mô) đang được giữ ở mức trung tính theo quy tắc dự phòng của hệ thống.",
                "",
                "2. Sự kiện kinh tế sắp tới",
                "- Không có dữ liệu lịch kinh tế sắp tới từ nguồn đã kiểm tra; app không xác nhận được sự kiện kích hoạt trong 24-72 giờ tới.",
                "- Không vào lệnh sát thời điểm tin đỏ (tin có tác động lớn) nếu người dùng chưa tự kiểm tra lịch kinh tế.",
                "",
                "3. Nhận định theo số liệu tính toán",
                f"- {symbol}: Buy Score (điểm mua) / Sell Score (điểm bán) = {buy_score} / {sell_score}; Trade Permission (quyền giao dịch) = {permission_text}.",
                f"- {decision}",
                "",
                "4. Lời khuyên hành động",
                "- Chỉ dùng Entry Zone (vùng vào lệnh), Stop Loss (cắt lỗ), Take Profit (chốt lời) và lot (khối lượng) do hệ thống đã tính ở tab Kế hoạch.",
                "- Nếu thiếu xác nhận trên H1 (nến 1 giờ), Spread (chênh lệch giá mua-bán) bất thường hoặc có tin lớn sát giờ: 'Không có thiết lập giao dịch sạch (No clean setup), nên đứng ngoài'.",
            ]
            ),
            result,
        )

    def _normalize_ai_commentary(self, text: str, result: dict[str, object]) -> str:
        cleaned = str(text or "").strip()
        cleaned = self._CLEAN_MD.sub("", cleaned)
        cleaned = cleaned.replace("dữ liệu AI nội bộ", "dữ liệu rule engine và macro context của app")

        # Compact: parse sections, fill missing, replace section 2 from data
        cleaned = self._compact_ai_commentary(cleaned, result)

        # Annotate English terms with Vietnamese
        cleaned = self._annotate_common_english_terms(cleaned)

        # Localize UTC times
        cleaned = self._localize_times_in_text(cleaned)

        return cleaned.strip()

    def _parse_commentary_sections(self, text: str) -> dict[int, list[str]]:
        """Parse AI commentary text into {section_number: [bullet_lines]}."""
        sections: dict[int, list[str]] = {}
        current: int | None = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            m = self._SECTION_HEADER.match(line)
            if m:
                current = int(m.group(1))
                if current not in sections:
                    sections[current] = []
                continue
            m = self._BULLET_LINE.match(line)
            if m and current is not None:
                raw = m.group(1).strip()
                # Strip AI reasoning leakage: "bullet1: content" → "content"
                raw = self._REASONING_LEAK.sub("", raw).strip()
                if raw:
                    sections[current].append(raw)
        return sections

    def _format_events_section(self, events: list[dict[str, object]]) -> list[str]:
        """Build section 2 bullets from economic_events data."""
        if not events:
            return []
        high: list[dict[str, object]] = []
        low: list[dict[str, object]] = []
        for e in events:
            impact = str(e.get("impact", "")).lower()
            if "high" in impact or "red" in impact or "cao" in impact:
                high.append(e)
            else:
                low.append(e)
        bullets: list[str] = []
        for e in high[:3]:
            time_text = str(e.get("event_time_local") or e.get("time_vn") or "--")
            title = str(e.get("event_vi") or e.get("event", "--"))
            currency = str(e.get("currency", "--"))
            impact_text = str(e.get("impact_assessment") or f"ảnh hưởng {e.get('impact', '')} tới {currency}").strip()
            if impact_text:
                bullets.append(f"{time_text}: {title} -> {impact_text}")
            else:
                bullets.append(f"{time_text}: {title}")
        if low:
            for e in low[:5]:
                time_text = str(e.get("event_time_local") or e.get("time_vn") or "--")
                title = str(e.get("event_vi") or e.get("event", "--"))
                currency = str(e.get("currency", "--"))
                impact_label = str(e.get("impact", "")).capitalize()
                impact_text = str(e.get("impact_assessment") or f"ảnh hưởng {impact_label} tới {currency}").strip()
                if impact_text:
                    bullets.append(f"{time_text}: {title} -> {impact_text} [Thấp]")
                else:
                    bullets.append(f"{time_text}: {title} [Thấp]")
            if len(low) > 5:
                bullets.append(f"Thêm {len(low) - 5} sự kiện tác động thấp khác.")
        return bullets

    def _compact_ai_commentary(self, text: str, result: dict[str, object] | None = None) -> str:
        # Parse sections from AI output
        sections = self._parse_commentary_sections(text)

        # Fill missing sections
        for num in range(1, 5):
            if num not in sections:
                sections[num] = []

        # Replace section 2 with data-driven events
        if result:
            events = result.get("economic_events", [])
            if isinstance(events, list) and events:
                sections[2] = self._format_events_section(events)

        # Build output with limits, blank line between sections
        blocks: list[str] = []
        for num in range(1, 5):
            title = self._SECTION_TITLES[num]
            bullets = sections[num][: self._SECTION_LIMITS[num]]
            block = [title]
            if bullets:
                block.extend(f"- {b}" for b in bullets)
            elif num == 2:
                block.append("- Chưa có dữ liệu sự kiện kinh tế sắp tới.")
            else:
                fallback = self._fallback_section(num, result)
                if fallback:
                    block.extend(f"- {b}" for b in fallback)
                else:
                    block.append("- Chưa có dữ liệu.")
            blocks.append("\n".join(block))
        return "\n\n".join(blocks)

    def _fallback_section(self, num: int, result: dict[str, object] | None) -> list[str]:
        """Return fallback bullets for a section when AI output is missing."""
        if not result:
            return []
        if num == 1:
            return self._fallback_macro_bullets(result)
        if num == 3:
            return self._fallback_calculated_bullets(result)
        if num == 4:
            return self._fallback_advice_bullets(result)
        return []

    def _fallback_macro_bullets(self, result: dict[str, object]) -> list[str]:
        symbol = str(result.get("symbol", "--"))
        macro = result.get("macro", {})
        driver_context = macro.get("driver_context", {}) if isinstance(macro, dict) else {}
        warning = str(driver_context.get("warning", "")) or "Chưa đủ dữ liệu vĩ mô định lượng để kết luận yếu tố ảnh hưởng mới nhất."
        return [
            f"{symbol}: chưa đủ dữ liệu vĩ mô định lượng để kết luận yếu tố ảnh hưởng (driver) mới nhất.",
            f"{warning}",
            "Hệ thống vẫn dùng điểm kỹ thuật, Risk Condition (điều kiện rủi ro) và Macro Alignment (mức độ thuận vĩ mô) hiện có.",
        ]

    def _fallback_calculated_bullets(self, result: dict[str, object]) -> list[str]:
        symbol = str(result.get("symbol", "--"))
        scores = result.get("scenario_scores", {})
        buy_total = scores.get("buy", {}).get("total", "--") if isinstance(scores, dict) else "--"
        sell_total = scores.get("sell", {}).get("total", "--") if isinstance(scores, dict) else "--"
        permission = result.get("trade_permission", {})
        permission_text = str(permission.get("status", "--")) if isinstance(permission, dict) else "--"
        reason = str(permission.get("reason", "")) if isinstance(permission, dict) else ""
        return [
            f"{symbol}: Buy Score (điểm mua) / Sell Score (điểm bán) = {buy_total} / {sell_total}.",
            f"Trade Permission (quyền giao dịch): {permission_text}. {reason}".strip(),
            "Chưa có vùng entry rõ ràng hoặc điều kiện chưa đủ mạnh để vào lệnh.",
        ]

    def _fallback_advice_bullets(self, result: dict[str, object]) -> list[str]:
        scenarios = result.get("scenarios", [])
        scenario = next((s for s in scenarios if isinstance(s, dict) and s.get("type") in {"buy", "sell"}), None)
        if not scenario:
            return ["Không có thiết lập giao dịch sạch (No clean setup), nên đứng ngoài."]
        entry = scenario.get("entry_zone", "--")
        sl = scenario.get("stop_loss", "--")
        tp = scenario.get("take_profit", "--")
        invalidation = scenario.get("invalidation", "")
        return [
            f"Chỉ cân nhắc khi điều kiện xác nhận xuất hiện. Entry Zone (vùng vào lệnh): {entry}; Stop Loss (cắt lỗ): {sl}; Take Profit (chốt lời): {tp}.",
            f"Điều kiện vô hiệu: {invalidation}" if invalidation else "Chờ thêm xác nhận từ H1 và kiểm tra spread trước khi vào lệnh.",
            "Luôn kiểm tra spread (chênh lệch giá mua-bán) và dữ liệu MT5 trước khi vào lệnh thực tế.",
        ]

    def _annotate_common_english_terms(self, text: str) -> str:
        terms = {
            "Market Regime": "trạng thái thị trường",
            "Direction Bias": "thiên hướng giao dịch",
            "Setup Quality Score": "điểm chất lượng kịch bản",
            "Trade Permission": "quyền giao dịch",
            "Buy Score": "điểm mua",
            "Sell Score": "điểm bán",
            "Risk/Reward": "tỷ lệ rủi ro/lợi nhuận",
            "Stop Loss": "cắt lỗ",
            "Take Profit": "chốt lời",
            "Entry Zone": "vùng vào lệnh",
            "Watch Zone": "vùng theo dõi",
            "Position Sizing": "tính khối lượng vào lệnh",
            "Lot": "khối lượng giao dịch",
            "Spread": "chênh lệch giá mua-bán",
            "No clean setup": "không có thiết lập giao dịch sạch",
            "Trend Alignment": "mức độ thuận xu hướng",
            "Momentum Alignment": "mức độ thuận động lượng",
            "Location Quality": "chất lượng vị trí giá",
            "Risk Condition": "điều kiện rủi ro",
            "Macro Alignment": "mức độ thuận vĩ mô",
            "Order Block": "khối lệnh tổ chức",
            "Supply Zone": "vùng cung",
            "Demand Zone": "vùng cầu",
            "Liquidity Pool": "vùng thanh khoản",
            "Timeframe": "khung thời gian",
            "Account Balance": "số dư tài khoản",
            "Risk Percent": "phần trăm rủi ro",
            "Contract Size": "quy mô hợp đồng",
        }
        result = text
        for english, vietnamese in terms.items():
            pattern = re.compile(rf"(?<!\()\b{re.escape(english)}\b(?!\s*\()", re.IGNORECASE)
            result = pattern.sub(f"{english} ({vietnamese})", result)
        return result

    def _display_timezone(self) -> str:
        try:
            return self.settings_service.load().display.timezone or "Asia/Ho_Chi_Minh"
        except Exception:
            return "Asia/Ho_Chi_Minh"

    def _vi_term(self, value: str) -> str:
        return {
            "allowed": "được phép",
            "caution": "cẩn trọng",
            "blocked": "bị chặn",
            "ready": "sẵn sàng",
            "watch": "theo dõi",
            "wait": "chờ",
            "wait_for_confirmation": "chờ xác nhận",
            "stand_aside": "đứng ngoài",
            "skip": "bỏ qua",
            "buy": "mua",
            "sell": "bán",
            "neutral": "trung lập",
            "trend_up": "xu hướng tăng",
            "trend_down": "xu hướng giảm",
            "range": "đi ngang",
            "volatile": "biến động mạnh",
            "news_sensitive": "nhạy tin tức",
            "unknown": "chưa rõ",
        }.get(str(value).strip().lower(), str(value or "--"))

    def _vi_impact(self, value: str) -> str:
        return {
            "high": "cao (tin đỏ)",
            "medium": "trung bình",
            "low": "thấp",
            "holiday": "ngày lễ",
            "": "--",
        }.get(str(value).strip().lower(), str(value or "--"))

    def _localized_events(self, events: object) -> list[dict[str, object]]:
        if not isinstance(events, list):
            return []
        timezone_name = self._display_timezone()
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("Asia/Ho_Chi_Minh")
            timezone_name = "Asia/Ho_Chi_Minh"
        localized: list[dict[str, object]] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            enriched = dict(event)
            local_text = self._format_local_time(event.get("time_utc"), tz)
            if local_text:
                enriched["event_time_local"] = local_text
                enriched["display_timezone"] = timezone_name
            localized.append(enriched)
        return localized

    def _localized_news_items(self, items: object) -> list[dict[str, object]]:
        if not isinstance(items, list):
            return []
        timezone_name = self._display_timezone()
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("Asia/Ho_Chi_Minh")
            timezone_name = "Asia/Ho_Chi_Minh"
        localized: list[dict[str, object]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            enriched = dict(item)
            local_text = self._format_local_time(item.get("published_utc"), tz)
            if local_text:
                enriched["published_local"] = local_text
                enriched["display_timezone"] = timezone_name
            localized.append(enriched)
        return localized

    def _format_event_line(self, event: dict[str, object], timezone_name: str | None = None) -> str:
        time_text = str(event.get("event_time_local") or event.get("time_vn") or event.get("time_utc") or "--")
        title = str(event.get("event_vi") or vi_text(event.get("event", "--")))
        currency = str(event.get("currency", "--"))
        impact = str(event.get("impact_assessment") or f"ảnh hưởng {self._vi_impact(str(event.get('impact', '--')))} tới {currency}")
        return f"{time_text}: {title} -> {impact}"

    def _format_news_line(self, item: dict[str, object]) -> str:
        time_text = str(item.get("published_local") or item.get("published_utc") or "--")
        title = str(item.get("title_vi") or vi_text(item.get("title", "--")))
        impact = str(item.get("impact_assessment") or item.get("impact_note") or "").strip()
        return f"{time_text}: {title} -> {impact}" if impact else f"{time_text}: {title}"

    def _format_local_time(self, utc_value: object, tz: ZoneInfo) -> str:
        if not utc_value:
            return ""
        try:
            parsed = datetime.fromisoformat(str(utc_value).replace("Z", "+00:00"))
        except ValueError:
            return ""
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(tz).strftime("%d-%m-%Y %H:%M")

    def _localize_times_in_text(self, text: str) -> str:
        if not text:
            return text
        timezone_name = self._display_timezone()
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("Asia/Ho_Chi_Minh")
            timezone_name = "Asia/Ho_Chi_Minh"

        def replace_iso(match: re.Match[str]) -> str:
            local = self._format_local_time(match.group(0), tz)
            return f"{local} ({timezone_name})" if local else match.group(0)

        def replace_offset(match: re.Match[str]) -> str:
            local = self._format_local_time(match.group(0), tz)
            return f"{local} ({timezone_name})" if local else match.group(0)

        iso_utc = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?Z\b")
        iso_offset = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?[+\-]\d{2}:?\d{2}\b")
        result = iso_utc.sub(replace_iso, text)
        result = iso_offset.sub(replace_offset, result)
        result = re.sub(r"\b(\d{1,2}:\d{2})\s*UTC\b", lambda m: self._shift_hhmm_to_local(m.group(1), tz, timezone_name), result)
        result = re.sub(r"\b(\d{1,2}:\d{2})\s*GMT\b", lambda m: self._shift_hhmm_to_local(m.group(1), tz, timezone_name), result)
        return result

    def _shift_hhmm_to_local(self, hhmm: str, tz: ZoneInfo, timezone_name: str) -> str:
        try:
            hour, minute = (int(part) for part in hhmm.split(":", 1))
        except ValueError:
            return f"{hhmm} UTC"
        today = datetime.now(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
        local = today.astimezone(tz)
        return f"{local.strftime('%H:%M')} ({timezone_name})"

    def _combined_ai_call(self, result: dict[str, object], active_ai) -> None:
        """1 lan goi AI duy nhat: vua viet commentary vua enrich macro news."""
        from services.ai_service import AIProviderConfig, AIService

        best_side = result["decision_summary"]["best_scenario"]
        best_score = result["decision_summary"]["best_score"]
        symbol = str(result.get("symbol", ""))

        macro_payload = self._json_block(self._macro_prompt_payload(result))
        behavior_payload = self._json_block(self._behavior_prompt_payload(result))
        technical_payload = self._json_block(self._technical_prompt_payload(result))
        output_schema = self._ai_output_schema()

        events = self._localized_events(result.get("economic_events", []))
        macro = result.get("macro", {}) if isinstance(result.get("macro"), dict) else {}
        driver_context = macro.get("driver_context", {}) if isinstance(macro.get("driver_context"), dict) else {}
        statements = self._localized_news_items(driver_context.get("latest_statements", []))

        enrichment_json = "null"
        if events or statements:
            enrichment_json = self._json_block({
                "symbol": symbol,
                "base_currency": str(symbol).split("/")[0] if symbol else "",
                "quote_currency": str(symbol).split("/")[-1] if symbol else "",
                "economic_events": events[:8],
                "latest_official_statements": statements[:10],
            })

        combined_prompt = (
            "Ban la tro ly phan tich cho phan mem giao dich. Thuc hien 2 nhiem vu cung luc:\n\n"
            "NHIEM VU 1: Viet nhan dinh giao dich dua tren du lieu:\n"
            f"- Macro flow: {macro_payload}\n"
            f"- Behavior model: {behavior_payload}\n"
            f"- Technical/SMC: {technical_payload}\n"
            f"- Output schema: {output_schema}\n\n"
            "NHIEM VU 2: Dich va nhan dinh tin tuc (neu co du lieu !== null):\n"
            f"- Du lieu enrichment: {enrichment_json}\n\n"
            'Tra ve CHINH XAC 1 JSON object voi 2 field:\n'
            '- "commentary": string — nhan dinh giao dich theo output_schema\n'
            '- "enrichment": object|null — neu co du lieu enrichment thi tra ve '
            '{"economic_events":[{"index":0,"event_vi":"...","impact_assessment":"..."}],'
            '"latest_official_statements":[{"index":0,"title_vi":"...","impact_assessment":"..."}]}. '
            'Neu khong co du lieu (null) thi tra ve null.\n\n'
            "QUAN TRONG: Chi tra ve JSON hop le, khong markdown, khong giai thich."
        )

        try:
            raw = AIService(
                AIProviderConfig(active_ai.provider, active_ai.model, active_ai.api_key)
            ).analyze(combined_prompt)
            parsed = self._parse_ai_json_object(raw)
        except Exception:
            result["macro"]["ai_summary"] = self._fallback_ai_commentary_from_result(
                result, best_side, best_score
            )
            return

        if not isinstance(parsed, dict):
            result["macro"]["ai_summary"] = self._fallback_ai_commentary_from_result(
                result, best_side, best_score
            )
            return

        commentary = str(parsed.get("commentary", ""))
        if commentary:
            result["macro"]["ai_summary"] = self._normalize_ai_commentary(commentary, result)
        else:
            result["macro"]["ai_summary"] = self._fallback_ai_commentary_from_result(
                result, best_side, best_score
            )

        enrichment = parsed.get("enrichment")
        if isinstance(enrichment, dict):
            self._apply_ai_event_enrichment(result, enrichment.get("economic_events"))
            self._apply_ai_statement_enrichment(driver_context, enrichment.get("latest_official_statements"))
