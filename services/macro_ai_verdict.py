"""Bước 6 — AI Macro Verdict: trọng tài AI nhìn toàn bộ tín hiệu macro cùng lúc.

Phát hiện mâu thuẫn giữa các tầng macro (Tier 1 lãi suất, Tier 2 calendar,
Tier 3 sentiment, correlation, stance, sự kiện) và có quyền phủ quyết — nhưng
CHỈ được phép làm khó setup, không được phép làm dễ (bất đối xứng).

Quyền bất đối xứng:
- veto=true → giáng READY xuống WATCH (qua gate engine)
- adjustment: CHỈ từ -5 đến 0 (luôn âm hoặc 0)
- conviction < 0.7 → bỏ qua toàn bộ verdict

Không thay đổi điểm deterministic — chỉ hiệu chỉnh đè lên trên.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ngưỡng macro score tối thiểu để gọi AI verdict (top ~33%).
MIN_MACRO_SCORE_FOR_VERDICT = 20

# Conviction tối thiểu để áp dụng verdict.
MIN_AI_CONVICTION = 0.7

# Adjustment range: chỉ âm hoặc 0.
ADJUSTMENT_MIN = -5
ADJUSTMENT_MAX = 0

# AI call timeout (seconds).
AI_TIMEOUT_S = 15.0

# Negative cache: khi AI hỏng, không gọi lại trong cửa sổ này (Minor 9).
NEGATIVE_CACHE_TTL = timedelta(minutes=30)

# Thread pool dùng chung cho AI call — timeout tạo thread zombie được chấp nhận
# (Major 7); pool có 2 workers để lần gọi sau không nghẽn bởi zombie.
_AI_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="macro-verdict-ai")

# Valid enum values for bias field.
BIAS_VALUES = frozenset({"aligned", "conflict", "unclear"})

# Fallback verdict when AI fails.
FALLBACK_VERDICT = {
    "bias": "unclear",
    "conviction": 0.0,
    "conflicts": [],
    "veto": False,
    "adjustment": 0,
    "evidence": [],
}

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class MacroVerdict:
    """AI referee's holistic macro assessment for a single pair on one day.

    Đây là kết quả đầu ra duy nhất của toàn bộ module. Pipeline đọc verdict
    và áp dụng veto + adjustment.
    """

    pair: str
    date: str  # "YYYY-MM-DD"
    bias: str  # "aligned" | "conflict" | "unclear"
    conviction: float  # 0.0-1.0, AI's confidence in its verdict
    conflicts: list[str]  # Human-readable contradiction descriptions
    veto: bool  # True → gate engine caps decision to WATCH_ONLY
    adjustment: int  # -5..0, amount to subtract from macro_confidence
    evidence: list[str]  # Short justifications from AI
    source: str  # "ai" | "fallback" | "skip_low_conviction" | "skip_below_threshold" | "skip_disabled"
    ai_blocking_time_s: float = 0.0
    best_side: str = "buy"  # Hướng đang xét khi verdict được tạo (Major 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "date": self.date,
            "bias": self.bias,
            "conviction": self.conviction,
            "conflicts": list(self.conflicts),
            "veto": self.veto,
            "adjustment": self.adjustment,
            "evidence": list(self.evidence),
            "source": self.source,
            "ai_blocking_time_s": self.ai_blocking_time_s,
            "best_side": self.best_side,
        }

    @classmethod
    def skip(cls, pair: str, date: str, reason: str, *, best_side: str = "buy") -> MacroVerdict:
        """Factory for skipped verdicts (below threshold, disabled, etc.)."""
        return cls(
            pair=pair,
            date=date,
            bias="unclear",
            conviction=0.0,
            conflicts=[],
            veto=False,
            adjustment=0,
            evidence=[],
            source=reason,
            ai_blocking_time_s=0.0,
            best_side=best_side,
        )

    @classmethod
    def fallback(cls, pair: str, date: str, *, best_side: str = "buy") -> MacroVerdict:
        """Factory for AI-failure fallback verdict."""
        return cls(
            pair=pair,
            date=date,
            bias=FALLBACK_VERDICT["bias"],
            conviction=FALLBACK_VERDICT["conviction"],
            conflicts=list(FALLBACK_VERDICT["conflicts"]),
            veto=FALLBACK_VERDICT["veto"],
            adjustment=FALLBACK_VERDICT["adjustment"],
            evidence=list(FALLBACK_VERDICT["evidence"]),
            source="fallback",
            ai_blocking_time_s=0.0,
            best_side=best_side,
        )


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def _ai_fingerprint(ai_service: object | None) -> str:
    """Fingerprint ổn định của AI service (không đọc secret — chỉ provider + model).

    Copy logic từ event_impact_assessor.py và news_service.py. Cache miss
    khi đổi model hoặc tắt AI.
    """
    if ai_service is None:
        payload = {"enabled": False, "provider": "", "model": ""}
    else:
        config = getattr(ai_service, "config", None)
        provider = getattr(config, "provider", "")
        model = getattr(config, "model", "")
        payload = {
            "enabled": True,
            "provider": provider if isinstance(provider, str) else "unknown",
            "model": model if isinstance(model, str) else "unknown",
        }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _repo_data_dir() -> Path:
    """Thư mục dữ liệu trong repo (thống nhất với Bước 5 — Minor 10)."""
    return Path(__file__).resolve().parents[1] / "data"


def verdict_cache_key(pair: str, date_str: str, fingerprint: str, best_side: str = "buy") -> str:
    """Cache key: sha1(pair|date|side|fingerprint)."""
    raw = f"{pair.strip().upper()}|{date_str}|{best_side.strip().lower()}|{fingerprint}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_verdict_prompt(
    pair: str,
    macro_context: dict[str, Any] | None,
    best_side: str,
) -> str:
    """Dựng prompt tiếng Việt yêu cầu AI đánh giá toàn bộ tín hiệu macro.

    Parameters
    ----------
    pair : str
        Cặp tiền (EUR/USD, GBP/JPY, ...).
    macro_context : dict | None
        Toàn bộ tín hiệu macro: tier scores, correlation, stance, events, V2.
    best_side : str
        Hướng giao dịch đang được hệ thống xem xét ("buy" hoặc "sell").
    """
    ctx = macro_context or {}

    # Extract tier scores
    tier1 = ctx.get("tier1", {})
    tier2 = ctx.get("tier2", {})
    tier3 = ctx.get("tier3", {})
    alignment = ctx.get("alignment", {})
    macro_v2 = ctx.get("macro_v2", {})
    data_quality = ctx.get("data_quality", {})
    events = ctx.get("upcoming_event_assessments", [])
    correlation = ctx.get("correlation", {})
    stance = ctx.get("stance", {})

    lines = [
        "Bạn là trọng tài phân tích vĩ mô cho trading forex. Nhiệm vụ của bạn là NHÌN TOÀN BỘ tín hiệu macro",
        "cùng lúc và phát hiện MÂU THUẪN giữa các tầng — thứ mà từng tầng riêng lẻ không thấy được.",
        "",
        f"CẶP TIỀN: {pair}",
        f"HƯỚNG ĐANG XÉT: {best_side.upper()}",
        "",
        "=== TẦNG 1: LÃI SUẤT & CHÍNH SÁCH TIỀN TỆ ===",
        f"  Buy={tier1.get('buy', '?')}, Sell={tier1.get('sell', '?')}",
        f"  Chi tiết: {json.dumps(tier1.get('detail', {}), ensure_ascii=False)}",
        "",
        "=== TẦNG 2: LỊCH KINH TẾ ===",
        f"  Buy={tier2.get('buy', '?')}, Sell={tier2.get('sell', '?')}",
        f"  Event risk level: {tier2.get('event_risk_level', '?')}",
        "",
        "=== TẦNG 3: TÂM LÝ RỦI RO & ĐỊA CHÍNH TRỊ ===",
        f"  Buy={tier3.get('buy', '?')}, Sell={tier3.get('sell', '?')}",
        "",
        "=== ĐIỂM TỔNG HỢP ===",
        f"  Macro Alignment: Buy={alignment.get('buy', '?')}, Sell={alignment.get('sell', '?')}",
        f"  Macro V2 (shadow): Buy={macro_v2.get('buy', '?')}, Sell={macro_v2.get('sell', '?')}",
        f"  Data Quality: {data_quality}",
        "",
        "=== CORRELATION & STANCE ===",
        f"  Correlation: {json.dumps(correlation, ensure_ascii=False)}",
        f"  Stance: {json.dumps(stance, ensure_ascii=False)}",
        "",
    ]

    # V6: dữ liệu chuyển động DXY thực tế — nguyên liệu cho phát hiện mâu thuẫn
    # "Tier 1 nói USD mạnh nhưng DXY đang giảm" (Critical 2 fix).
    dxy = correlation.get("dxy") if isinstance(correlation, dict) else None
    if isinstance(dxy, dict) and dxy.get("has_data"):
        lines.append(
            f"  DXY (2 nến gần nhất): {dxy.get('direction', '?').upper()} "
            f"({dxy.get('change_pct', '?')}%, close={dxy.get('last_close', '?')})"
        )
    else:
        lines.append("  DXY: không có dữ liệu")

    lines.append("")

    if events:
        for ev in (events or [])[:5]:
            if isinstance(ev, dict):
                lines.append(
                    f"  - {ev.get('currency', '?')}: {ev.get('event_name', '?')} "
                    f"(còn {ev.get('hours_until', '?')}h, "
                    f"magnitude={ev.get('magnitude', '?')}, "
                    f"priced_in={ev.get('priced_in', '?')})"
                )
    else:
        lines.append("  (không có sự kiện high-impact trong 4-48h tới)")

    lines.extend([
        "",
        "=== CÂU HỎI CẦN TRẢ LỜI ===",
        f"1. Các tầng macro có ĐỒNG THUẬN ủng hộ hướng {best_side.upper()} không? Hay có mâu thuẫn?",
        "2. Có tín hiệu nào ở tầng này MÂU THUẪN với tầng khác không?",
        "   Ví dụ: Tier 1 nói USD hawkish (lợi suất tăng) nhưng DXY thực tế đang giảm → mâu thuẫn.",
        "3. Nếu có mâu thuẫn, mức độ nghiêm trọng thế nào? Có đủ lớn để PHỦ QUYẾT (veto) không?",
        "",
        "=== QUY TẮC BẮT BUỘC ===",
        "- veto=true CHỈ khi phát hiện mâu thuẫn NGHIÊM TRỌNG giữa các tầng khiến setup đáng ngờ.",
        "- adjustment CHỈ từ -5 đến 0 (không bao giờ dương — bạn chỉ được làm khó, không được làm dễ).",
        "- adjustment=-5: mâu thuẫn rất rõ, nên giảm mạnh điểm macro.",
        "- adjustment=0: không có vấn đề gì đáng kể.",
        "- conviction là độ tự tin của bạn (0-1). Nếu không chắc chắn, trả conviction < 0.7.",
        "- conflicts: mô tả ngắn gọn từng mâu thuẫn phát hiện được (mảng rỗng nếu không có).",
        "- evidence: căn cứ ngắn gọn cho kết luận của bạn.",
        "",
        "TRẢ VỀ DUY NHẤT MỘT JSON HỢP LỆ, KHÔNG THÊM VĂN BẢN KHÁC:",
        '{"bias": "aligned"|"conflict"|"unclear", "conviction": <0.0-1.0>,',
        '"conflicts": ["mô tả mâu thuẫn 1", "mô tả mâu thuẫn 2"],',
        '"veto": true|false, "adjustment": <-5 đến 0>,',
        '"evidence": ["căn cứ 1", "căn cứ 2"]}',
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parser + Validator
# ---------------------------------------------------------------------------


def _normalize_enum(value: object, allowed: frozenset[str]) -> str | None:
    """Chuẩn hóa giá trị enum, trả về None nếu không hợp lệ."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in allowed else None


def parse_verdict_json(response: object) -> dict | None:
    """Parse và validate phản hồi JSON của AI cho macro verdict.

    Trả về dict đã chuẩn hóa {bias, conviction, conflicts, veto, adjustment,
    evidence} hoặc None nếu không thể trích JSON hợp lệ. Trích được JSON kể
    cả khi response bị bọc trong markdown fence hoặc có rác bao quanh.
    """
    if not isinstance(response, str):
        return None
    text = response.strip()
    if not text:
        return None

    # Try direct parse first, then bracket extraction
    candidates = []
    # Strip markdown fences
    cleaned = text
    if cleaned.startswith("```"):
        newline_idx = cleaned.find("\n")
        if newline_idx != -1:
            cleaned = cleaned[newline_idx + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    candidates.append(cleaned)

    # Extract JSON object via bracket matching
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        parsed = _validate_verdict(data)
        if parsed is not None:
            return parsed
    return None


def _validate_verdict(data: dict) -> dict | None:
    """Validate dict từ AI response, thực thi các ràng buộc bất đối xứng.

    Trả về dict đã chuẩn hóa hoặc None nếu không hợp lệ.
    """
    # bias
    bias = _normalize_enum(data.get("bias"), BIAS_VALUES)
    if bias is None:
        return None

    # conviction
    conviction = data.get("conviction")
    if isinstance(conviction, bool) or not isinstance(conviction, (int, float)):
        return None
    conviction = float(conviction)
    if not (0.0 <= conviction <= 1.0):
        return None

    # conflicts
    conflicts = data.get("conflicts")
    if not isinstance(conflicts, list):
        return None
    conflicts = [str(c) for c in conflicts if isinstance(c, str) and c.strip()]

    # veto
    veto = data.get("veto")
    if not isinstance(veto, bool):
        return None

    # adjustment: MUST be -5..0
    adjustment = data.get("adjustment")
    if isinstance(adjustment, bool) or not isinstance(adjustment, (int, float)):
        return None
    adjustment = int(adjustment)
    if adjustment < ADJUSTMENT_MIN or adjustment > ADJUSTMENT_MAX:
        return None

    # evidence
    evidence = data.get("evidence")
    if not isinstance(evidence, list):
        return None
    evidence = [str(e) for e in evidence if isinstance(e, str) and e.strip()]

    # Nếu veto=true mà không có conflicts → vô hiệu hóa veto
    if veto and not conflicts:
        veto = False

    # Nếu conflicts rỗng mà bias=conflict → sửa thành unclear
    if not conflicts and bias == "conflict":
        bias = "unclear"

    return {
        "bias": bias,
        "conviction": conviction,
        "conflicts": conflicts,
        "veto": veto,
        "adjustment": adjustment,
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Cache — disk-backed, per (pair, date)
# ---------------------------------------------------------------------------


class MacroVerdictCache:
    """Disk cache cho MacroVerdict, keyed by (pair, date, best_side).

    Lưu tại ``data/macro_verdict_cache/``, mỗi file JSON chứa 1 verdict.
    TTL = đến cuối ngày giao dịch (date_str != today → stale); entry negative
    cache có ``expires_at_utc`` hết hạn trong 30 phút.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        if cache_dir is None:
            cache_dir = _repo_data_dir() / "macro_verdict_cache"
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, pair: str, date_str: str, best_side: str = "buy") -> Path:
        safe_pair = pair.replace("/", "_").replace("\\", "_")
        side = str(best_side or "buy").strip().lower() or "buy"
        return self._dir / f"{safe_pair}_{date_str}_{side}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        pair: str,
        date_str: str,
        fingerprint: str,
        *,
        best_side: str = "buy",
        match_fingerprint: bool = True,
        now: datetime | None = None,
    ) -> MacroVerdict | None:
        """Đọc verdict từ cache. None nếu miss, khác fingerprint, hoặc khác ngày.

        ``match_fingerprint=False`` (backtest read-cache-only) bỏ qua kiểm tra
        fingerprint — đọc lại verdict mà hệ thống live đã ghi cho (pair, date, side).
        Entry negative cache hết hạn (``expires_at_utc`` trong quá khứ) → miss.
        """
        if now is None:
            now = datetime.now(UTC)
        filepath = self._file_path(pair, date_str, best_side)
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None

        # Fingerprint mismatch → cache miss (backtest có thể bỏ qua — Major 5)
        if match_fingerprint:
            cached_fp = data.get("fingerprint", "")
            if cached_fp != fingerprint:
                return None

        # Date mismatch → stale
        if data.get("date") != date_str:
            return None

        # Negative cache hết hạn → miss
        expires_at = data.get("expires_at_utc")
        if isinstance(expires_at, str) and expires_at:
            try:
                parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                # Không parse được → coi như hết hạn, không dùng.
                return None
            if parsed <= now:
                return None

        return MacroVerdict(
            pair=data.get("pair", pair),
            date=data.get("date", date_str),
            bias=data.get("bias", "unclear"),
            conviction=float(data.get("conviction", 0.0)),
            conflicts=list(data.get("conflicts", [])),
            veto=bool(data.get("veto", False)),
            adjustment=int(data.get("adjustment", 0)),
            evidence=list(data.get("evidence", [])),
            source=data.get("source", "unknown"),
            ai_blocking_time_s=float(data.get("ai_blocking_time_s", 0.0)),
            best_side=str(data.get("best_side", best_side)),
        )

    def put(
        self,
        verdict: MacroVerdict,
        fingerprint: str,
        *,
        negative_ttl: timedelta | None = None,
    ) -> None:
        """Ghi verdict vào disk cache.

        ``negative_ttl`` (vd 30 phút) đánh dấu entry là negative cache: khi đọc
        quá hạn sẽ miss để thử lại AI (Minor 9).
        """
        filepath = self._file_path(verdict.pair, verdict.date, verdict.best_side)
        payload = {
            **verdict.to_dict(),
            "fingerprint": fingerprint,
            "cached_at_utc": datetime.now(UTC).isoformat(),
        }
        if negative_ttl is not None:
            payload["expires_at_utc"] = (datetime.now(UTC) + negative_ttl).isoformat()
        try:
            filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        except OSError:
            pass  # Fail silently — cache is best-effort.


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


def _journal_verdict(
    verdict: MacroVerdict,
    journal_path: Path | None = None,
) -> None:
    """Ghi 1 dòng JSONL vào macro_verdict_journal.jsonl.

    Journal dùng để sau này đối chiếu verdict với kết quả lệnh thực tế.
    """
    if journal_path is None:
        journal_path = _repo_data_dir() / "macro_verdict_journal.jsonl"
    try:
        record = {
            **verdict.to_dict(),
            "trade_result_r": None,
            "trade_outcome": None,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
        }
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # Fail silently — journal is best-effort.


# ---------------------------------------------------------------------------
# Assessor
# ---------------------------------------------------------------------------


class MacroVerdictAssessor:
    """Đánh giá toàn bộ tín hiệu macro bằng AI, có cache + journal.

    Fail-closed: mọi lỗi → fallback verdict (veto=False, adjustment=0).
    Không bao giờ ném exception ra ngoài assess().
    """

    def __init__(
        self,
        cache: MacroVerdictCache | None = None,
        journal_path: Path | None = None,
        timeout_s: float = AI_TIMEOUT_S,
    ) -> None:
        self.cache = cache if cache is not None else MacroVerdictCache()
        self._journal_path = journal_path
        self._timeout_s = timeout_s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        pair: str,
        macro_context: dict[str, Any] | None,
        ai_service: object | None,
        *,
        date_str: str | None = None,
        best_side: str = "buy",
        verdict_enabled: bool = False,
        now: datetime | None = None,
        is_backtest: bool = False,
    ) -> MacroVerdict:
        """Đánh giá macro verdict cho 1 cặp trong 1 ngày.

        Parameters
        ----------
        pair : str
            Cặp tiền (EUR/USD, ...).
        macro_context : dict | None
            Toàn bộ tín hiệu macro từ NewsService.
        ai_service : object | None
            AIService instance (có method analyze(prompt, max_tokens)).
        date_str : str | None
            Ngày dạng "YYYY-MM-DD". None → dùng hôm nay (UTC).
        best_side : str
            Hướng đang được xem xét ("buy"/"sell").
        verdict_enabled : bool
            Feature flag từ settings.
        now : datetime | None
            Thời điểm hiện tại (test injection).
        is_backtest : bool
            True → chế độ read-cache-only (Major 5): chỉ đọc cache theo
            (pair, date, best_side), không kiểm tra fingerprint; miss → skip
            trung tính, TUYỆT ĐỐI không gọi AI. Đảm bảo backtest reproducible.

        Returns
        -------
        MacroVerdict
            Không bao giờ None. Không bao giờ ném exception.
        """
        try:
            if now is None:
                now = datetime.now(UTC)
            if date_str is None:
                date_str = now.strftime("%Y-%m-%d")

            # ---- Guard 1: feature flag ----
            if not verdict_enabled:
                return MacroVerdict.skip(pair, date_str, "skip_disabled", best_side=best_side)

            # ---- Guard 2: top candidate threshold ----
            alignment = (macro_context or {}).get("alignment", {})
            macro_buy = alignment.get("buy", 15) if isinstance(alignment, dict) else 15
            macro_sell = alignment.get("sell", 15) if isinstance(alignment, dict) else 15
            if max(macro_buy, macro_sell) < MIN_MACRO_SCORE_FOR_VERDICT:
                return MacroVerdict.skip(pair, date_str, "skip_below_threshold", best_side=best_side)

            # ---- Cache check ----
            fingerprint = _ai_fingerprint(ai_service)
            cached = self.cache.get(
                pair, date_str, fingerprint,
                best_side=best_side,
                # Backtest read-cache-only: đọc lại verdict live đã ghi, không
                # cần khớp fingerprint (Major 5).
                match_fingerprint=not is_backtest,
                now=now,
            )
            if cached is not None:
                return cached

            # ---- Backtest: read-cache-only — miss thì skip trung tính ----
            if is_backtest:
                return MacroVerdict.skip(
                    pair, date_str, "skip_backtest_no_cache", best_side=best_side,
                )

            # ---- AI call ----
            if ai_service is None:
                failure = MacroVerdict.fallback(pair, date_str, best_side=best_side)
                self.cache.put(failure, fingerprint, negative_ttl=NEGATIVE_CACHE_TTL)
                _journal_verdict(failure, self._journal_path)
                return failure

            t0 = time.monotonic()
            try:
                prompt = build_verdict_prompt(pair, macro_context, best_side)
                # Major 7: thực thi budget timeout — chạy AI trong thread riêng,
                # chờ tối đa self._timeout_s. Thread zombie được chấp nhận.
                future = _AI_EXECUTOR.submit(ai_service.analyze, prompt, max_tokens=300)
                response = future.result(timeout=self._timeout_s)
                elapsed = time.monotonic() - t0
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "macro_ai_verdict timeout sau %.1fs (pair=%s, side=%s) — fallback",
                    self._timeout_s, pair, best_side,
                )
                failure = MacroVerdict.fallback(pair, date_str, best_side=best_side)
                failure.ai_blocking_time_s = round(self._timeout_s, 3)
                self.cache.put(failure, fingerprint, negative_ttl=NEGATIVE_CACHE_TTL)
                _journal_verdict(failure, self._journal_path)
                return failure
            except Exception:
                failure = MacroVerdict.fallback(pair, date_str, best_side=best_side)
                self.cache.put(failure, fingerprint, negative_ttl=NEGATIVE_CACHE_TTL)
                _journal_verdict(failure, self._journal_path)
                return failure

            parsed = parse_verdict_json(response)
            if parsed is None:
                failure = MacroVerdict.fallback(pair, date_str, best_side=best_side)
                self.cache.put(failure, fingerprint, negative_ttl=NEGATIVE_CACHE_TTL)
                _journal_verdict(failure, self._journal_path)
                return failure

            verdict = MacroVerdict(
                pair=pair,
                date=date_str,
                bias=parsed["bias"],
                conviction=parsed["conviction"],
                conflicts=list(parsed["conflicts"]),
                veto=parsed["veto"],
                adjustment=parsed["adjustment"],
                evidence=list(parsed["evidence"]),
                source="ai",
                ai_blocking_time_s=round(elapsed, 3),
                best_side=best_side,
            )

            # ---- Cache + journal ----
            self.cache.put(verdict, fingerprint)
            _journal_verdict(verdict, self._journal_path)

            return verdict

        except Exception:
            # Ultimate fail-closed
            try:
                return MacroVerdict.fallback(pair, date_str or datetime.now(UTC).strftime("%Y-%m-%d"))
            except Exception:
                return MacroVerdict.skip(pair, "unknown", "skip_fatal_error")
