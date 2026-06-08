from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class TelegramAlertResult:
    attempted: int
    sent: int
    errors: list[str]


class TelegramAlertService:
    API_BASE = "https://api.telegram.org"

    def send_ready_trade_alerts(
        self,
        rows: list[dict[str, object]],
        *,
        bot_token: str,
        chat_ids: list[str],
    ) -> TelegramAlertResult:
        token = bot_token.strip()
        recipients = [item.strip() for item in chat_ids if item.strip()]
        if not token or not recipients:
            return TelegramAlertResult(attempted=0, sent=0, errors=[])

        ready_rows = [row for row in rows if self._is_ready_trade(row)]
        attempted = len(ready_rows) * len(recipients)
        sent = 0
        errors: list[str] = []
        for row in ready_rows:
            message = self.format_trade_alert(row)
            for chat_id in recipients:
                try:
                    self._send_message(token, chat_id, message)
                    sent += 1
                except Exception as exc:
                    errors.append(f"{row.get('symbol', '--')} -> {chat_id}: {exc}")
        return TelegramAlertResult(attempted=attempted, sent=sent, errors=errors)

    def format_trade_alert(self, row: dict[str, object]) -> str:
        analysis = row.get("analysis_result", {})
        scenario = self._best_scenario(row)
        sizing = scenario.get("position_sizing", {}) if isinstance(scenario.get("position_sizing"), dict) else {}
        entry = self._format_entry(scenario.get("entry_zone"))
        tp = self._format_take_profit(scenario.get("take_profit"))
        side = "BUY" if str(row.get("best_side")) == "buy" else "SELL"
        balance = sizing.get("account_balance")
        balance_text = f"Vốn MT5: {balance}" if balance not in (None, "") else ""
        reason = row.get("short_reason") or row.get("permission_reason") or ""
        lines = [
                "AI Market Analyst - Tín hiệu vào lệnh",
                f"Mã: {row.get('symbol', '--')} ({row.get('broker_symbol', '--')})",
                f"Hướng: {side}",
                f"Entry: {entry}",
                f"Stop loss: {scenario.get('stop_loss', '--')}",
                f"Take profit: {tp}",
                f"Lot: {sizing.get('suggested_lot', '--')}",
                f"R:R: {scenario.get('risk_reward', row.get('risk_reward', '--'))}",
                f"Điểm: {row.get('best_score', '--')}/100",
                f"Lý do: {reason}",
                balance_text,
                f"Nguồn: {analysis.get('mode', 'scanner') if isinstance(analysis, dict) else 'scanner'}",
        ]
        return "\n".join(line for line in lines if line).strip()

    def _send_message(self, bot_token: str, chat_id: str, text: str) -> None:
        url = f"{self.API_BASE}/bot{bot_token}/sendMessage"
        payload = urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        request = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            raise RuntimeError(f"Telegram HTTP {exc.code}: {detail[:200]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Không kết nối được Telegram: {exc.reason}") from exc
        if not data.get("ok"):
            raise RuntimeError(str(data.get("description") or "Telegram không chấp nhận tin nhắn."))

    def _is_ready_trade(self, row: dict[str, object]) -> bool:
        return (
            row.get("scanner_action") == "ready"
            and row.get("trade_permission") == "allowed"
            and isinstance(row.get("analysis_result"), dict)
            and bool(self._best_scenario(row))
        )

    def _best_scenario(self, row: dict[str, object]) -> dict[str, object]:
        analysis = row.get("analysis_result", {})
        if not isinstance(analysis, dict):
            return {}
        scenarios = analysis.get("scenarios", [])
        if not isinstance(scenarios, list):
            return {}
        side = row.get("best_side")
        for scenario in scenarios:
            if isinstance(scenario, dict) and scenario.get("type") == side:
                return scenario
        return {}

    def _format_entry(self, value: object) -> str:
        if isinstance(value, list) and len(value) == 2:
            return f"{value[0]} - {value[1]}"
        return str(value or "--")

    def _format_take_profit(self, value: object) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) or "--"
        return str(value or "--")

    def format_summary_alert(self, rows: list[dict[str, object]], timestamp: str) -> str:
        total = len(rows)
        ready_rows = [row for row in rows if self._is_ready_trade(row)]
        ready_count = len(ready_rows)
        watching = sum(1 for row in rows if row.get("scanner_action") in ("watch", "ready"))

        buy_list = [str(row.get("symbol", "")) for row in ready_rows if str(row.get("best_side")) == "buy"]
        sell_list = [str(row.get("symbol", "")) for row in ready_rows if str(row.get("best_side")) == "sell"]

        lines = [
            "AI Market Analyst - Tong ket quet thi truong",
            f"Thoi gian: {timestamp}",
            f"Tong so ma da quet: {total}",
            f"San sang vao lenh: {ready_count} ma",
        ]

        if ready_count > 0:
            if buy_list:
                lines.append(f"[MUA] {', '.join(buy_list)}")
            if sell_list:
                lines.append(f"[BAN] {', '.join(sell_list)}")

        lines.append(f"Dang theo doi: {watching} ma")
        return "\n".join(lines)

    def send_summary_alert(
        self,
        rows: list[dict[str, object]],
        *,
        bot_token: str,
        chat_ids: list[str],
        timestamp: str,
    ) -> int:
        token = bot_token.strip()
        recipients = [item.strip() for item in chat_ids if item.strip()]
        if not token or not recipients:
            return 0
        message = self.format_summary_alert(rows, timestamp)
        sent = 0
        for chat_id in recipients:
            try:
                self._send_message(token, chat_id, message)
                sent += 1
            except Exception:
                pass
        return sent
