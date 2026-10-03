"""NewsMacroProvider — nguồn dữ liệu vĩ mô của Scanner, đọc `news.db` (ca đấu nối b).

Provider **duck-type đúng 5 method** mà `ScannerController` đang gọi trên
`NewsService` (tên + tham số + shape đầu ra giữ nguyên), nhưng nguồn dữ liệu đổi
từ mạng (ForexFactory/FRED/RSS/Yahoo) sang SQLite local qua `NewsRepository`
(contract `docs/macro/macro_score_architecture.md` §0.2):

| Method | Nguồn |
|---|---|
| `preload_macro_contexts` | 1 lượt đọc chung (events/items/rates/yields) → build context từng symbol |
| `latest_macro_context` | cache TTL 5 phút; miss → build từ repository + `core.macro_tiers` |
| `data_quality_flags` | `latest_macro_context` + `news_in_3h`/`high_impact_event_within_30m`/... |
| `macro_freshness_status` | `store_state()` → worst-of 4 scope |
| `execution_news_status` | `events_in_range` cửa sổ blackout, đã lọc currency |

Nguyên tắc:

* **Không HTTP.** Mọi dữ liệu đi qua `NewsRepository` (S1 — một nguồn chân lý);
  module này không mở socket, không đọc cache đĩa của hệ cũ.
* **AI bỏ hẳn.** `ai_service` vẫn nhận (parity chữ ký) nhưng **không dùng** — stance
  tính bằng keyword trong `core.macro_tiers` (verdict AI advisory-only, QĐ owner
  20/09/2026).
* **Fail-closed.** Lỗi đọc DB → không crash scan: context rỗng (công thức tự tụt
  `macro_data_quality`) và `macro_freshness_status()` trả `expired`/0.6.
* **Đổi nguồn có chủ ý đã ghi ở contract §0.2** (không tính là lệch pin B3):
  AI stance bỏ, chuỗi đường cong 10y-5y → 2y/10y, freshness theo `store_state`
  thay cho tuổi lần fetch cuối.

Chưa đấu nối runtime (WI-4/WI-5); `services/news_service.py` vẫn là đường sống
đến WI-7.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any

from config.paths import PROJECT_ROOT
from core.macro_tiers import (
    compute_macro_tiers,
    geopolitical_hotspots,
    macro_data_quality,
    macro_themes,
)
from core.news_models import NewsItemKind, StoreState
from services.calendar_helpers import _event_time, _is_high_impact
from services.news_repository import NewsRepository

__all__ = ["NEWS_STATUS_UNAVAILABLE", "NewsMacroProvider"]

NEWS_STATUS_UNAVAILABLE = "NEWS_STATUS_UNAVAILABLE"

# Nguồn dữ liệu công bố trong context/status (thay chuỗi tên nhà cung cấp mạng cũ).
NEWS_SOURCE = "news_repository"

_EVENTS_LOOKBACK = timedelta(hours=24)
_EVENTS_LOOKAHEAD = timedelta(hours=72)
_HEADLINES_LOOKBACK = timedelta(hours=24)
_MAX_EVENTS = 8
_CONTEXT_CACHE_TTL = timedelta(minutes=5)
_VIX_FLAG_CACHE_TTL = timedelta(seconds=60)
_AGE_UNKNOWN_MINUTES = 9999

_RATE_FALLBACK_PATH = PROJECT_ROOT / "config" / "interest_rates.json"

_STORE_EXPIRED = ("expired", 0.6)
_STORE_STALE = ("stale", 0.85)
_STORE_FRESH = ("fresh", 1.0)


def _utc_iso(moment: datetime) -> str:
    """Khuôn ISO-8601 UTC mà mọi producer ghi (`YYYY-MM-DDTHH:MM:SSZ`).

    `event_time_utc`/`published_utc` được lưu và SO SÁNH dạng chuỗi (§4.1/§4.3),
    nên biên cửa sổ phải nằm đúng khuôn này mới so đúng thứ tự thời gian.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: str | None) -> datetime | None:
    """Đọc chuỗi ISO-8601 (có `Z` hoặc offset); naive coi là UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _symbol_currencies(symbol: str) -> list[str]:
    """Port `NewsService._symbol_currencies`: tách cặp, hoặc cắt `XXXYYY` 6 ký tự."""
    currencies = [part for part in str(symbol).upper().split("/") if part]
    if len(currencies) == 1 and len(currencies[0]) >= 6:
        raw = currencies[0]
        currencies = [raw[:3], raw[3:6]]
    return currencies


def _keep_headline(item: Mapping[str, Any], currencies: Sequence[str]) -> bool:
    """Port `NewsService._filter_by_currencies` (d.1530-1539).

    Nhánh cuối của bản cũ luôn trả `True` ("keep global headline"), nên hàm này
    là **no-op có chủ ý**: headlines KHÔNG bị lọc theo currency. Đổi hành vi này
    = đổi phạm vi headlines = đổi điểm (plan §7) — giữ nguyên đến khi có quyết
    định khác.
    """
    return True


@dataclass(frozen=True, slots=True)
class _NewsSnapshot:
    """Một lượt đọc repository dùng chung cho nhiều symbol trong cùng scan."""

    fetched_at_utc: datetime
    expires_at_utc: datetime
    events: tuple[dict[str, Any], ...]
    headlines: tuple[dict[str, Any], ...]
    statements: tuple[dict[str, Any], ...]
    rates: Mapping[str, Mapping[str, Any]]
    yield_payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _ContextCacheEntry:
    value: dict[str, Any]
    fetched_at_utc: datetime
    expires_at_utc: datetime


class NewsMacroProvider:
    """Đọc `news.db` và dựng `macro_context` cùng shape như `NewsService` cũ.

    ``repository``/``settings_service``/``observability``/``clock`` là seam tiêm
    vào cho test và cho wiring; mặc định `None` nghĩa là dùng bản thật
    (`NewsRepository`, `SettingsService`, `structured_observability`, đồng hồ UTC).
    Repository được tạo **lazy** ở lần đọc đầu tiên (tạo `NewsRepository` sẽ chạy
    migration → chạm đĩa), nên chỉ khởi tạo provider thì chưa đụng DB.
    """

    def __init__(
        self,
        repository: object | None = None,
        *,
        settings_service: object | None = None,
        observability: object | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._settings_service = settings_service
        self._observability = observability
        self._clock = clock
        self._cache: dict[tuple[str, bool], _ContextCacheEntry] = {}
        self._cache_lock = RLock()
        self._vix_flag_cache: tuple[datetime, bool] | None = None

    # ------------------------------------------------------------------
    # Seam nội bộ
    # ------------------------------------------------------------------
    @property
    def repository(self) -> Any:
        if self._repository is None:
            self._repository = NewsRepository()
        return self._repository

    def _now(self) -> datetime:
        moment = self._clock() if self._clock is not None else datetime.now(UTC)
        if moment.tzinfo is None:
            return moment.replace(tzinfo=UTC)
        return moment.astimezone(UTC)

    def _note_read_failure(self, symbol: str, read: str, exc: Exception) -> None:
        """Ghi nhận lỗi đọc qua seam observability sẵn có (không thêm logger mới)."""
        try:
            if self._observability is None:
                from services.observability_service import structured_observability

                self._observability = structured_observability
            self._observability.emit(
                "MACRO_NEWS_READ_FAILED",
                symbol=symbol,
                severity="WARNING",
                payload={"read": read, "error": type(exc).__name__, "message": str(exc)},
            )
        except Exception:
            # Observability không bao giờ được làm gãy đường quét (fail-open ở đây
            # là cố ý: dữ liệu vẫn fail-closed theo công thức).
            pass

    def _read(self, symbol: str, read: str, call: Callable[[], Any], default: Any) -> Any:
        try:
            return call()
        except Exception as exc:
            self._note_read_failure(symbol, read, exc)
            return default

    # ------------------------------------------------------------------
    # 1. preload_macro_contexts
    # ------------------------------------------------------------------
    def preload_macro_contexts(
        self,
        symbols: list[str],
        progress_callback: Callable[[int, str], None] | None = None,
        *,
        ai_service: object | None = None,
        performance_tracker: object | None = None,
    ) -> None:
        """Đọc repository MỘT lượt rồi dựng context cho mọi symbol của scan.

        ``ai_service``/``performance_tracker`` nhận cho parity chữ ký và bị bỏ
        qua (không còn AI, không còn pha fetch mạng để đo).
        """
        if not symbols:
            return
        progress = progress_callback or (lambda _p, _m: None)
        now = self._now()

        progress(15, "Đang tải snapshot vĩ mô toàn cầu...")
        currencies: list[str] = []
        for symbol in symbols:
            for currency in _symbol_currencies(symbol):
                if currency not in currencies:
                    currencies.append(currency)
        snapshot = self._read_snapshot(now=now, currencies=currencies or ["USD"])

        total = max(1, len(symbols))
        for idx, symbol in enumerate(symbols):
            progress(
                17 + int((idx + 1) / total * 2),
                f"Đang phân tích vĩ mô {symbol} ({idx + 1}/{total})...",
            )
            context = self._context_for(
                symbol,
                include_latest_statements=True,
                now=now,
                snapshot=snapshot,
            )
            # Làm ấm cache per-symbol (parity bản cũ): các lượt `data_quality_flags`
            # ngay sau preload trong cùng scan phải trúng cache, không đọc lại DB.
            self._remember(symbol, True, context, now)

    # ------------------------------------------------------------------
    # 2. latest_macro_context
    # ------------------------------------------------------------------
    def latest_macro_context(
        self,
        symbol: str,
        *,
        include_latest_statements: bool = True,
        ai_service: object | None = None,
        performance_tracker: object | None = None,
    ) -> dict[str, Any]:
        """`macro_context` của một symbol, cache in-memory TTL 5 phút.

        ``ai_service`` nhận nhưng **bỏ qua** — stance là keyword (QĐ bỏ AI stance).
        """
        now = self._now()
        cache_key = (symbol, bool(include_latest_statements))
        with self._cache_lock:
            entry = self._cache.get(cache_key)
            if entry is not None and now < entry.expires_at_utc:
                return deepcopy(entry.value)
        context = self._context_for(
            symbol,
            include_latest_statements=bool(include_latest_statements),
            now=now,
            snapshot=None,
        )
        self._remember(symbol, bool(include_latest_statements), context, now)
        return context

    def _remember(
        self,
        symbol: str,
        include_latest_statements: bool,
        context: dict[str, Any],
        now: datetime,
    ) -> None:
        """Ghi context vào cache TTL 5 phút (bản lưu là deepcopy, tách khỏi caller)."""
        with self._cache_lock:
            self._cache[(symbol, bool(include_latest_statements))] = _ContextCacheEntry(
                value=deepcopy(context),
                fetched_at_utc=now,
                expires_at_utc=now + _CONTEXT_CACHE_TTL,
            )

    # ------------------------------------------------------------------
    # 3. data_quality_flags
    # ------------------------------------------------------------------
    def data_quality_flags(
        self,
        symbol: str,
        *,
        buffer_minutes: int = 30,
        include_latest_statements: bool = True,
        ai_service: object | None = None,
        performance_tracker: object | None = None,
    ) -> dict[str, Any]:
        """Port `NewsService.data_quality_flags` (d.419-437) trên context mới."""
        context = self.latest_macro_context(
            symbol,
            include_latest_statements=include_latest_statements,
            ai_service=ai_service,
            performance_tracker=performance_tracker,
        )
        events = context.get("events", [])
        if not isinstance(events, list):
            events = []
        now = self._now()
        high_events = [
            event
            for event in events
            if _is_high_impact(str(event.get("impact", "")))
            and _event_time(event) is not None
            and _event_time(event) >= now
        ]
        next_high = (
            min(high_events, key=lambda event: _event_time(event) or now)
            if high_events
            else None
        )
        event_time = _event_time(next_high) if next_high else None
        hours_until = ((event_time - now).total_seconds() / 3600) if event_time else None
        resume_after = (
            (event_time + timedelta(minutes=buffer_minutes)).isoformat()
            if event_time
            else None
        )
        return {
            "macro_context": context,
            "news_in_3h": bool(hours_until is not None and 0 <= hours_until <= 3),
            "high_impact_event_within_30m": bool(
                hours_until is not None and 0 <= hours_until <= 0.5
            ),
            "next_high_impact_event": next_high,
            "resume_after": resume_after,
            "vix_pair_aware_enabled": self._read_vix_pair_aware_enabled(),
        }

    # ------------------------------------------------------------------
    # 4. macro_freshness_status
    # ------------------------------------------------------------------
    def macro_freshness_status(self) -> dict[str, Any]:
        """Độ tươi dữ liệu vĩ mô suy từ `store_state()` (thay "tuổi lần fetch cuối").

        Worst-of 4 scope: mọi scope `fresh` → fresh/1.0; có `degraded` →
        stale/0.85; có `unavailable` (chưa từng ingest) → expired/0.6.
        `age_minutes` = phút kể từ lượt ingest thành công **mới nhất** trong các
        scope có dữ liệu; không scope nào có → 9999.

        Đọc thẳng mỗi lần gọi (một truy vấn aggregate) thay vì cache: cache sẽ
        đóng băng `confidence_multiplier` mà Scanner dùng làm hệ số confidence.
        """
        try:
            state = self.repository.store_state()
        except Exception as exc:
            self._note_read_failure("", "store_state", exc)
            return {
                "status": _STORE_EXPIRED[0],
                "age_minutes": _AGE_UNKNOWN_MINUTES,
                "confidence_multiplier": _STORE_EXPIRED[1],
            }
        status, multiplier = _freshness_status(state)
        return {
            "status": status,
            "age_minutes": self._freshness_age_minutes(state, self._now()),
            "confidence_multiplier": multiplier,
        }

    @staticmethod
    def _freshness_age_minutes(state: StoreState, now: datetime) -> int:
        stamps = [
            moment
            for moment in (
                _parse_utc(state.events_last_success_at),
                _parse_utc(state.items_last_success_at),
                _parse_utc(state.rates_last_success_at),
                _parse_utc(state.yields_last_success_at),
            )
            if moment is not None
        ]
        if not stamps:
            return _AGE_UNKNOWN_MINUTES
        return int((now - max(stamps)).total_seconds() / 60)

    # ------------------------------------------------------------------
    # 5. execution_news_status
    # ------------------------------------------------------------------
    def execution_news_status(
        self,
        symbol: str,
        *,
        before_minutes: int = 30,
        after_minutes: int = 30,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Trạng thái blackout tin tức lúc gửi lệnh (fail-closed).

        Scope events `unavailable` (chưa từng ingest) → `available=False` +
        `NEWS_STATUS_UNAVAILABLE`; `degraded`/`stale` vẫn `available=True` (dữ
        liệu có thật — độ tươi nằm ở confidence vĩ mô, không chặn ở đây).
        """
        checked_at = (
            now.astimezone(UTC)
            if now is not None and now.tzinfo
            else (now.replace(tzinfo=UTC) if now is not None else self._now())
        )
        unavailable = {
            "available": False,
            "blackout": None,
            "checked_at": checked_at.isoformat(),
            "event": None,
            "source": NEWS_SOURCE,
            "reason_codes": [NEWS_STATUS_UNAVAILABLE],
        }
        try:
            state = self.repository.store_state()
        except Exception as exc:
            self._note_read_failure(symbol, "store_state", exc)
            return dict(unavailable, message=str(exc))
        if state.events_state.value == "unavailable":
            return unavailable

        before = max(0, int(before_minutes))
        after = max(0, int(after_minutes))
        currencies = _symbol_currencies(symbol)
        try:
            events = self.repository.events_in_range(
                _utc_iso(checked_at - timedelta(minutes=after)),
                _utc_iso(checked_at + timedelta(minutes=before)),
                currencies,
            )
        except Exception as exc:
            self._note_read_failure(symbol, "events_in_range", exc)
            return dict(unavailable, message=str(exc))

        blackout_event: dict[str, Any] | None = None
        smallest_distance: float | None = None
        for event in events:
            event_dict = _event_dict(event)
            if not _is_high_impact(str(event_dict.get("impact", ""))):
                continue
            event_time = _event_time(event_dict)
            if event_time is None:
                continue
            event_time = event_time.astimezone(UTC)
            delta_minutes = (event_time - checked_at).total_seconds() / 60.0
            if -after <= delta_minutes <= before:
                distance = abs(delta_minutes)
                if smallest_distance is None or distance < smallest_distance:
                    smallest_distance = distance
                    blackout_event = event_dict

        return {
            "available": True,
            "blackout": blackout_event is not None,
            "checked_at": checked_at.isoformat(),
            "event": blackout_event,
            "source": NEWS_SOURCE,
            "reason_codes": ["NEWS_BLACKOUT"] if blackout_event is not None else [],
        }

    # ------------------------------------------------------------------
    # Đọc repository
    # ------------------------------------------------------------------
    def _read_snapshot(self, *, now: datetime, currencies: Sequence[str]) -> _NewsSnapshot:
        """Một lượt đọc dùng chung. Mọi lỗi đọc → collection rỗng (fail-closed)."""
        wanted = list(dict.fromkeys(str(c).upper() for c in currencies if str(c)))
        events_from = _utc_iso(now - _EVENTS_LOOKBACK)
        events_to = _utc_iso(now + _EVENTS_LOOKAHEAD)
        items_from = _utc_iso(now - _HEADLINES_LOOKBACK)
        items_to = _utc_iso(now)

        raw_events = self._read(
            "",
            "events_in_range",
            lambda: self.repository.events_in_range(events_from, events_to, wanted),
            [],
        )
        # Chỉ kind headline: parity scope cũ (global_headlines = tin RSS, tách khỏi
        # statements). Nếu không lọc kinds, statements bị đếm 2 lần trong hotspots
        # (headlines + statements) và user_note (tin nhập tay) lọt vào công thức.
        raw_headlines = self._read(
            "",
            "items_in_range",
            lambda: self.repository.items_in_range(
                items_from, items_to, [NewsItemKind.HEADLINE.value]
            ),
            [],
        )
        raw_statements = self._read(
            "",
            "items_in_range:statement",
            lambda: self.repository.items_in_range(
                items_from, items_to, [NewsItemKind.STATEMENT.value]
            ),
            [],
        )
        return _NewsSnapshot(
            fetched_at_utc=now,
            expires_at_utc=now + _CONTEXT_CACHE_TTL,
            events=tuple(_event_dict(event) for event in raw_events),
            headlines=tuple(_item_dict(item) for item in raw_headlines),
            statements=tuple(_item_dict(item) for item in raw_statements),
            rates=self._rates_for(wanted),
            yield_payload=self._yield_payload(),
        )

    def _rates_for(self, currencies: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Rate mỗi đồng tiền: news.db trước, thiếu thì fallback `config/interest_rates.json`."""
        rates: dict[str, dict[str, Any]] = {}
        trends = self._read(
            "",
            "latest_rates",
            lambda: self.repository.latest_rates(list(currencies)),
            [],
        )
        for trend in trends:
            rate = float(trend.latest.rate)
            rates[trend.currency] = {
                "rate": rate,
                "trend": str(trend.trend),
                "rate_label": f"{rate:.2f}%",
            }
        fallback = self._load_rate_fallback()
        for currency in currencies:
            if currency in rates:
                continue
            entry = fallback.get(currency)
            if isinstance(entry, Mapping):
                rates[currency] = dict(entry)
        return rates

    def _load_rate_fallback(self) -> dict[str, Any]:
        """Port `interest_rate_service._load_fallback`: `{"currencies": {...}}`, lỗi → {}."""
        try:
            raw = json.loads(_RATE_FALLBACK_PATH.read_text(encoding="utf-8"))
            payload = raw.get("currencies", {})
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _yield_payload(self) -> dict[str, Any]:
        """Đường cong USD từ `latest_bond_yields(["USD"])` (đổi series có chủ ý §0.2)."""
        snapshots = self._read(
            "",
            # Nhãn observability không được chứa chuỗi tên bảng của tín hiệu bond
            # (cổng E2 §9.2(d) cấm string literal chạm `bond_yields` ngoài repository).
            "yield_snapshot",
            lambda: self.repository.latest_bond_yields(["USD"]),
            [],
        )
        context = snapshots[0].context if snapshots else None
        if context is None:
            return _empty_yield_payload()
        delta_6m = getattr(context, "delta_6m", None)
        delta_spread = getattr(delta_6m, "delta_spread", None) if delta_6m else None
        return {
            "spread": context.spread_2y10y,
            "steepening": (delta_spread or 0) > 0,
            "ten_year_yield": context.yield_10y,
            "five_year_yield": None,
            "two_year_yield": context.yield_2y,
            "tnx": context.yield_10y,
            "fvx": None,
        }

    # ------------------------------------------------------------------
    # Dựng context
    # ------------------------------------------------------------------
    def _context_for(
        self,
        symbol: str,
        *,
        include_latest_statements: bool,
        now: datetime,
        snapshot: _NewsSnapshot | None,
    ) -> dict[str, Any]:
        currencies = _symbol_currencies(symbol)
        if snapshot is None:
            snapshot = self._read_snapshot(now=now, currencies=currencies)

        events = _events_for_pair(snapshot.events, currencies)
        headlines = [dict(item) for item in snapshot.headlines if _keep_headline(item, currencies)]
        statements = (
            [dict(item) for item in snapshot.statements]
            if include_latest_statements
            else []
        )
        themes = macro_themes(currencies, headlines)
        hotspots = geopolitical_hotspots(headlines + statements)

        tiers = compute_macro_tiers(
            currencies,
            headlines,
            events,
            hotspots,
            rates=snapshot.rates,
            yield_payload=snapshot.yield_payload,
            now=now,
            vix_level=None,  # VIX thuộc correlation context — ngoài phạm vi ca này
        )
        data_quality = macro_data_quality(headlines, events, now=now)

        return {
            "symbol": symbol,
            "source": NEWS_SOURCE,
            "events": events,
            "latest_headlines": headlines,
            "latest_statements": statements,
            "macro_themes": themes,
            "geopolitical_hotspots": hotspots,
            "macro_alignment_scores": tiers["alignment"],
            "macro_alignment_reasons": tiers["reasons"],
            "macro_tier_detail": {
                "tier1_interest_rate": tiers["tier1"],
                "tier2_calendar": tiers["tier2"],
                "tier3_sentiment": tiers["tier3"],
                "data_confidence": round(data_quality, 2),
                "macro_score_raw": tiers["raw_total"],
            },
            "macro_data_quality": data_quality,
            # Provenance chi tiết của bản cũ mô tả các nguồn fetch mạng (FRED/FF/
            # Yahoo) — không còn tồn tại. Giữ KEY để shape không đổi, giá trị None
            # (không bịa nguồn); provenance mới, nếu cần, dựng từ `store_state()`.
            "macro_data_quality_detail": None,
            "stance_detail": tiers["stance_detail"],
            "macro_cache": {
                "fetched_at_utc": snapshot.fetched_at_utc.isoformat(),
                "expires_at_utc": snapshot.expires_at_utc.isoformat(),
            },
            "warning": (
                ""
                if events
                else "Không có dữ liệu sự kiện kinh tế sắp tới khớp cặp tiền trong nguồn đã kiểm tra."
            ),
        }

    # ------------------------------------------------------------------
    # Cờ Bước 7 (vix_pair_aware_enabled)
    # ------------------------------------------------------------------
    def _read_vix_pair_aware_enabled(self) -> bool:
        """Port `_read_vix_pair_aware_enabled` (d.172): cache 60s, lỗi đọc → False."""
        now = self._now()
        cached = self._vix_flag_cache
        if cached is not None and (now - cached[0]) < _VIX_FLAG_CACHE_TTL:
            return cached[1]
        try:
            service = self._settings_service
            if service is None:
                from services.settings_service import SettingsService

                service = SettingsService()
            settings = service.load()
            vix_pair_aware = bool(
                getattr(getattr(settings, "advanced", None), "vix_pair_aware_enabled", False)
            )
        except Exception:
            vix_pair_aware = False
        self._vix_flag_cache = (now, vix_pair_aware)
        return vix_pair_aware


# ---------------------------------------------------------------------------
# Mapping model → dict (đúng key mà công thức port đang đọc)
# ---------------------------------------------------------------------------


def _event_dict(event: Any) -> dict[str, Any]:
    """`CalendarEvent` → dict Tier 2 / news gate đọc (`time_utc`, `event`, `impact`)."""
    return {
        "currency": str(getattr(event, "currency", "")),
        "event": str(getattr(event, "title", "")),
        "impact": _enum_value(getattr(event, "impact", "")),
        "forecast": getattr(event, "forecast", None),
        "previous": getattr(event, "previous", None),
        "actual": getattr(event, "actual", None),
        "time_utc": str(getattr(event, "event_time_utc", "")),
    }


def _item_dict(item: Any) -> dict[str, Any]:
    """`NewsItem` → dict headline (`title`, `published_utc`, `currencies`)."""
    currencies = getattr(item, "currencies", None)
    return {
        "title": str(getattr(item, "title", "")),
        "published_utc": str(getattr(item, "published_utc", "")),
        "currencies": [str(code) for code in currencies] if currencies else [],
    }


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _events_for_pair(
    events: Sequence[Mapping[str, Any]], currencies: Sequence[str]
) -> list[dict[str, Any]]:
    """Sự kiện của 2 currency trong cặp, giữ thứ tự ASC của repository, cap 8."""
    wanted = {currency.upper() for currency in currencies}
    matched = [
        dict(event)
        for event in events
        if str(event.get("currency", "")).upper() in wanted
    ]
    return matched[:_MAX_EVENTS]


def _empty_yield_payload() -> dict[str, Any]:
    return {
        "spread": None,
        "tnx": None,
        "fvx": None,
        "steepening": None,
        "ten_year_yield": None,
        "five_year_yield": None,
    }


def _freshness_status(state: StoreState) -> tuple[str, float]:
    """Worst-of 4 scope → (status, multiplier). Unavailable thắng degraded."""
    scopes = (
        state.events_state.value,
        state.items_state.value,
        state.rates_state.value,
        state.yields_state.value,
    )
    if "unavailable" in scopes:
        return _STORE_EXPIRED
    if "degraded" in scopes:
        return _STORE_STALE
    return _STORE_FRESH
