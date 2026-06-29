from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
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

    # ------------------------------------------------------------------
    # Order alerts (ready + waiting + watch — same gates as "Hiển thị lệnh")
    # ------------------------------------------------------------------

    def send_order_alerts(
        self,
        candidates: list[dict[str, object]],
        *,
        bot_token: str,
        chat_ids: list[str],
    ) -> TelegramAlertResult:
        token = bot_token.strip()
        recipients = [item.strip() for item in chat_ids if item.strip()]
        if not token or not recipients:
            return TelegramAlertResult(attempted=0, sent=0, errors=[])

        attempted = len(candidates) * len(recipients)
        sent = 0
        errors: list[str] = []
        for cand in candidates:
            message = self.format_order_alert(cand)
            for chat_id in recipients:
                try:
                    self._send_message(token, chat_id, message)
                    sent += 1
                except Exception as exc:
                    errors.append(f"{cand.get('symbol', '--')} -> {chat_id}: {exc}")
        return TelegramAlertResult(attempted=attempted, sent=sent, errors=errors)

    def format_order_alert(self, cand: dict[str, object]) -> str:
        action = str(cand.get("scanner_action", ""))
        symbol = str(cand.get("symbol") or "--")
        broker_symbol = str(cand.get("broker_symbol") or "").strip()
        symbol_text = f"{symbol} ({broker_symbol})" if broker_symbol else symbol
        side_text = self._format_side(cand.get("side"))
        score = cand.get("best_score", "--")

        entry_zone = cand.get("entry_zone")
        entry_text = self._format_entry(entry_zone)
        sl = cand.get("stop_loss", "--")
        tp = self._format_take_profit(cand.get("take_profit"))
        rr = cand.get("risk_reward", "--")
        vol = cand.get("volume", "--")
        reason = str(cand.get("short_reason") or "")

        if action == "ready":
            header = "🔔 AI Market Analyst - TÍN HIỆU VÀO LỆNH"
        else:
            header = "👀 AI Market Analyst - TÍN HIỆU THEO DÕI"

        lines = [
            header,
            f"• Mã: {symbol_text}",
            f"• Hướng: {side_text}",
            f"• Entry: {entry_text}",
            f"• Stop loss: {sl}",
            f"• Take profit: {tp}",
            f"• Lot gợi ý: {vol}",
            f"• R:R: {rr}",
            f"• Điểm setup: {score}/100",
        ]
        if reason:
            lines.append(f"• Lý do: {reason}")
        if action != "ready":
            status_label = {"watch": "Theo dõi", "wait": "Đang chờ"}.get(action, action.capitalize())
            lines.append(f"• Trạng thái: {status_label}")
        lines.append("• Nguồn: scanner")

        return "\n".join(line for line in lines if line).strip()

    # ------------------------------------------------------------------
    # Summary alert
    # ------------------------------------------------------------------

    def send_summary_alert(
        self,
        rows: list[dict[str, object]],
        *,
        candidates: list[dict[str, object]] | None = None,
        bot_token: str,
        chat_ids: list[str],
        timestamp: str,
    ) -> int:
        token = bot_token.strip()
        recipients = [item.strip() for item in chat_ids if item.strip()]
        if not token or not recipients:
            return 0
        if candidates is None:
            candidates = []
        message = self.format_summary_alert(rows, candidates, timestamp)
        sent = 0
        for chat_id in recipients:
            try:
                self._send_message(token, chat_id, message)
                sent += 1
            except Exception:
                pass
        return sent

    def format_summary_alert(
        self,
        rows: list[dict[str, object]],
        candidates: list[dict[str, object]],
        timestamp: str,
    ) -> str:
        total = len(rows)
        ready = [c for c in candidates if c.get("scanner_action") == "ready"]
        waiting = [c for c in candidates if c.get("scanner_action") != "ready"]

        lines = [
            "✨ AI Market Analyst - Tổng kết quét thị trường",
            f"🕒 Thời gian: {self._format_timestamp(timestamp)}",
            f"🔎 Đã quét: {total} mã",
            f"📋 Lệnh đủ điều kiện: {len(candidates)} mã",
            f"✅ Sẵn sàng vào lệnh: {len(ready)} mã",
            f"👀 Đang theo dõi: {len(waiting)} mã",
        ]

        if ready:
            lines.append("")
            lines.append("🎯 SẴN SÀNG VÀO LỆNH:")
            lines.extend(self._format_candidate_line(c) for c in ready)
        elif candidates:
            lines.append("• Chưa có mã nào sẵn sàng vào lệnh ngay.")

        if waiting:
            lines.append("")
            lines.append("👀 ĐANG THEO DÕI:")
            lines.extend(self._format_candidate_line(c) for c in waiting[:6])

        return "\n".join(lines)

    def _format_candidate_line(self, cand: dict[str, object]) -> str:
        symbol = str(cand.get("symbol") or "--")
        broker = str(cand.get("broker_symbol") or "").strip()
        symbol_text = f"{symbol} ({broker})" if broker else symbol
        side = self._format_side(cand.get("side"))
        entry = self._format_entry(cand.get("entry_zone"))
        sl = cand.get("stop_loss", "--")
        score = cand.get("best_score", "--")
        action = str(cand.get("scanner_action", ""))
        status = {"ready": "✓", "watch": "△", "wait": "⏳"}.get(action, "•")
        return f"{status} {symbol_text} | {side} | Điểm: {score}/100 | Entry: {entry} | SL: {sl}"

    # ------------------------------------------------------------------
    # Messaging helpers
    # ------------------------------------------------------------------

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

    def _format_symbol(self, row: dict[str, object]) -> str:
        symbol = str(row.get("symbol") or "--")
        broker_symbol = str(row.get("broker_symbol") or "").strip()
        return f"{symbol} ({broker_symbol})" if broker_symbol else symbol

    def _format_side(self, value: object) -> str:
        side = str(value or "").strip().lower()
        if side == "buy":
            return "MUA"
        if side == "sell":
            return "BÁN"
        return "--"

    def _format_entry(self, value: object) -> str:
        if isinstance(value, list) and len(value) == 2:
            return f"{value[0]} - {value[1]}"
        return str(value or "--")

    def _format_take_profit(self, value: object) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value) or "--"
        return str(value or "--")

    def _format_timestamp(self, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            return "--"
        try:
            return datetime.fromisoformat(cleaned).strftime("%d-%m-%Y %H:%M:%S")
        except ValueError:
            return cleaned
