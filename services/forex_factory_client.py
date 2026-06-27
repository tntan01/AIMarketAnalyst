"""Forex Factory client — fetch, parse, and cache economic calendar data.

Pure data-access layer with no dependency on NewsService business logic.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from config.paths import app_data_dir


# ---------------------------------------------------------------------------
# Module-level helpers (stateless, used by NewsService too)
# ---------------------------------------------------------------------------


def parse_event_time(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _event_time(event: object) -> datetime | None:
    if not isinstance(event, dict):
        return None
    return parse_event_time(str(event.get("time_utc") or ""))


def clean_text(value: str) -> str:
    return " ".join(unescape(value or "").split())


HIGH_IMPACT_VALUES: frozenset[str] = frozenset({"high", "red", "cao"})


def _is_high_impact(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in HIGH_IMPACT_VALUES or "high" in normalized or "red" in normalized


# ---------------------------------------------------------------------------
# ForexFactoryClient
# ---------------------------------------------------------------------------


class ForexFactoryClient:
    """Fetch, parse, cache, and filter Forex Factory economic calendar events."""

    FOREX_FACTORY_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    FOREX_FACTORY_NEXTWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"
    FOREX_FACTORY_HTML_URL = "https://www.forexfactory.com/calendar?week=this"
    FOREX_FACTORY_NEXTWEEK_HTML_URL = "https://www.forexfactory.com/calendar?week=next"
    CALENDAR_CACHE_MAX_AGE = timedelta(hours=12)
    CALENDAR_CACHE_FILE: Path | None = None

    def __init__(self) -> None:
        self._calendar_cache: dict[str, tuple[datetime, list[dict[str, object]]]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calendar_events(self, currencies: list[str]) -> dict[str, object]:
        """Return economic calendar events for *currencies* (JSON → HTML fallback)."""
        cached = self._cached_calendar_events()
        if cached:
            return {
                "source": "Calendar file cache",
                "events": self._select_calendar_events(currencies, cached),
                "warning": "",
            }

        errors: list[str] = []
        for source, fetcher in (
            ("Forex Factory", self._fetch_json_events),
            ("Forex Factory HTML", self._fetch_html_events),
        ):
            try:
                rows = fetcher()
            except Exception as exc:
                errors.append(f"{source}: {exc}")
                continue

            if source == "Forex Factory":
                try:
                    html_rows = self._fetch_html_events()
                    self._merge_actual_from_html(rows, html_rows)
                except Exception:
                    pass

            self._store_calendar_cache(rows)
            return {
                "source": source,
                "events": self._select_calendar_events(currencies, rows),
                "warning": "",
            }

        return {
            "source": "Calendar unavailable",
            "events": [],
            "warning": "Không lấy được lịch kinh tế từ Forex Factory: " + "; ".join(errors),
        }

    def calendar_events_window(
        self, currencies: list[str], from_date: datetime, to_date: datetime
    ) -> dict[str, object]:
        """Return economic calendar events in [from_date, to_date] range.

        Fetches thisweek + nextweek JSON (with HTML fallback) and merges
        with disk cache. Filters to the requested date window.
        """
        all_rows: list[dict[str, object]] = []
        sources: list[str] = []
        errors: list[str] = []

        # Try thisweek JSON
        for label, fetcher in (
            ("Forex Factory (thisweek)", self._fetch_json_events),
            ("Forex Factory (nextweek)", self._fetch_json_events_nextweek),
        ):
            try:
                rows = fetcher()
                if rows:
                    sources.append(label)
                    all_rows.extend(rows)
            except Exception as exc:
                errors.append(f"{label}: {exc}")

        # HTML fallback for thisweek
        if not any("thisweek" in s for s in sources):
            try:
                rows = self._fetch_html_events()
                if rows:
                    sources.append("Forex Factory HTML (thisweek)")
                    all_rows.extend(rows)
            except Exception as exc:
                errors.append(f"HTML thisweek: {exc}")

        # HTML fallback for nextweek
        if not any("nextweek" in s for s in sources):
            try:
                rows = self._fetch_html_events_nextweek()
                if rows:
                    sources.append("Forex Factory HTML (nextweek)")
                    all_rows.extend(rows)
            except Exception as exc:
                errors.append(f"HTML nextweek: {exc}")

        # Merge with disk cache for extra coverage
        try:
            cached = self._cached_calendar_events()
            if cached:
                existing_keys = set()
                for ev in all_rows:
                    existing_keys.add((
                        str(ev.get("time_utc", "")),
                        str(ev.get("currency", "")),
                        str(ev.get("event", "")),
                    ))
                for cev in cached:
                    k = (str(cev.get("time_utc", "")), str(cev.get("currency", "")), str(cev.get("event", "")))
                    if k not in existing_keys:
                        all_rows.append(cev)
                if not sources:
                    sources.append("Disk cache")
        except Exception:
            pass

        # Deduplicate
        seen = set()
        deduped: list[dict[str, object]] = []
        for ev in all_rows:
            k = (str(ev.get("time_utc", "")), str(ev.get("currency", "")), str(ev.get("event", "")))
            if k not in seen:
                seen.add(k)
                deduped.append(ev)

        # Store combined results to cache for future fallback
        if deduped and sources and "Disk cache" not in sources:
            try:
                self._store_calendar_cache(deduped)
            except Exception:
                pass

        # Filter by date window AND currencies
        filtered = self._select_calendar_events_window(currencies, deduped, from_date, to_date)

        return {
            "source": ", ".join(sources) if sources else "Calendar unavailable",
            "events": filtered,
            "warning": "" if filtered else ("Không có sự kiện trong khoảng ngày. " + "; ".join(errors)).strip(),
        }

    def _select_calendar_events_window(
        self,
        currencies: list[str],
        rows: list[dict[str, object]],
        from_date: datetime,
        to_date: datetime,
    ) -> list[dict[str, object]]:
        wanted = {currency.upper() for currency in currencies} if currencies else set()
        relevant: list[dict[str, object]] = []
        for row in rows:
            currency = str(row.get("currency", "")).upper()
            if wanted and currency not in wanted:
                continue
            ev_time = _event_time(row)
            if ev_time is None:
                # Keep events without time if they might be relevant
                if wanted and currency in wanted:
                    relevant.append(dict(row))
                continue
            if from_date <= ev_time <= to_date:
                relevant.append(dict(row))
        return sorted(relevant, key=lambda row: str(row.get("time_utc", "")))

    # ------------------------------------------------------------------
    # HTTP fetch
    # ------------------------------------------------------------------

    def _fetch_json_events(self) -> list[dict[str, object]]:
        last_error = None
        for attempt in range(3):
            try:
                request = Request(
                    self.FOREX_FACTORY_CALENDAR_URL,
                    headers={"User-Agent": "AI Market Analyst/1.0"},
                )
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return self._normalize_calendar_items(
                    payload if isinstance(payload, list) else [], source="Forex Factory"
                )
            except HTTPError as exc:
                last_error = RuntimeError(f"HTTP {exc.code}")
                if exc.code == 429 and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_error from exc
            except URLError as exc:
                last_error = RuntimeError(str(exc.reason))
                if attempt < 2:
                    time.sleep(1)
                    continue
                raise last_error from exc

    def _fetch_html_events(self) -> list[dict[str, object]]:
        request = Request(
            self.FOREX_FACTORY_HTML_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AI Market Analyst/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc
        rows = self._parse_html(html)
        if not rows:
            raise RuntimeError("không đọc được bảng HTML")
        return rows

    def _fetch_json_events_nextweek(self) -> list[dict[str, object]]:
        last_error = None
        for attempt in range(3):
            try:
                request = Request(
                    self.FOREX_FACTORY_NEXTWEEK_URL,
                    headers={"User-Agent": "AI Market Analyst/1.0"},
                )
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return self._normalize_calendar_items(
                    payload if isinstance(payload, list) else [], source="Forex Factory (nextweek)"
                )
            except HTTPError as exc:
                last_error = RuntimeError(f"HTTP {exc.code}")
                if exc.code == 429 and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_error from exc
            except URLError as exc:
                last_error = RuntimeError(str(exc.reason))
                if attempt < 2:
                    time.sleep(1)
                    continue
                raise last_error from exc

    def _fetch_html_events_nextweek(self) -> list[dict[str, object]]:
        request = Request(
            self.FOREX_FACTORY_NEXTWEEK_HTML_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AI Market Analyst/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc
        rows = self._parse_html(html)
        if not rows:
            raise RuntimeError("không đọc được bảng HTML nextweek")
        return rows

    # ------------------------------------------------------------------
    # Normalizer
    # ------------------------------------------------------------------

    def _normalize_calendar_items(self, payload: list[object], *, source: str) -> list[dict[str, object]]:
        now = datetime.now(UTC)
        rows: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            currency = str(item.get("country") or item.get("currency") or "")
            if not currency:
                continue
            event_time = parse_event_time(str(item.get("date") or ""))
            hours_until = ((event_time - now).total_seconds() / 3600) if event_time else None
            rows.append(
                {
                    "source": source,
                    "currency": currency,
                    "event": item.get("title", ""),
                    "impact": item.get("impact", ""),
                    "time_utc": event_time.isoformat(timespec="minutes").replace("+00:00", "Z") if event_time else "",
                    "hours_until": round(hours_until, 2) if hours_until is not None else None,
                    "forecast": item.get("forecast", ""),
                    "previous": item.get("previous", ""),
                    "actual": item.get("actual", ""),
                }
            )
        return rows

    # ------------------------------------------------------------------
    # HTML parser
    # ------------------------------------------------------------------

    def _parse_html(self, html: str) -> list[dict[str, object]]:
        now = datetime.now(UTC)
        rows: list[dict[str, object]] = []
        current_date: str | None = None

        html_tz = self._detect_html_timezone(html)

        row_blocks = re.findall(r"<tr[^>]*calendar__row[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
        for block in row_blocks:
            date_text = self._html_cell_text(block, "calendar__date")
            if not date_text:
                date_text = self._html_cell_text(block, "calendar__cell")
            if date_text:
                date_clean = re.sub(r"<[^>]+>", "", date_text).strip()
                date_clean = re.sub(r"\s+", " ", date_clean)
                if re.search(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}", date_clean, re.IGNORECASE):
                    current_date = date_clean

            currency = self._html_cell_text(block, "calendar__currency")
            event = self._html_cell_text(block, "calendar__event-title") or self._html_cell_text(block, "calendar__event")
            if not currency or not event:
                continue

            time_text = self._html_raw_cell(block, "calendar__time")
            time_text = re.sub(r"<[^>]+>", " ", time_text).strip() if time_text else ""
            event_time = self._parse_html_time(time_text, current_date, html_tz)

            hours_until = ((event_time - now).total_seconds() / 3600) if event_time else None
            rows.append(
                {
                    "source": "Forex Factory HTML",
                    "currency": currency,
                    "event": event,
                    "impact": self._html_impact(block),
                    "time_utc": event_time.isoformat(timespec="minutes").replace("+00:00", "Z") if event_time else "",
                    "hours_until": round(hours_until, 2) if hours_until is not None else None,
                    "forecast": self._html_cell_text(block, "calendar__forecast"),
                    "previous": self._html_cell_text(block, "calendar__previous"),
                    "actual": self._html_cell_text(block, "calendar__actual"),
                }
            )
        return rows

    def _detect_html_timezone(self, html: str) -> str:
        tz_match = re.search(r"Calendar Time Zone:\s*([^<]+)", html)
        if tz_match:
            tz_text = tz_match.group(1).strip()
            tz_name = re.search(r"([A-Z][a-z]+/[A-Z][a-z_]+)", tz_text)
            if tz_name:
                return tz_name.group(1)
        tz_match = re.search(r"'User Timezone':\s*'([^']+)'", html)
        if tz_match:
            return tz_match.group(1)
        return str(datetime.now().astimezone().tzinfo)

    def _parse_html_time(self, time_text: str, date_text: str | None, html_tz: str = "UTC") -> datetime | None:
        if not time_text or not date_text:
            return None
        time_text = time_text.strip().lower()
        if time_text in ("all day", "tentative", ""):
            return None

        match = re.match(r"(\d{1,2}):(\d{2})(am|pm)", time_text)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))
        ampm = match.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        try:
            parsed_date = datetime.strptime(date_text + f" {datetime.now(UTC).year}", "%a %b %d %Y")
        except ValueError:
            return None

        try:
            tz = ZoneInfo(html_tz)
        except Exception:
            tz = None
        dt_local = parsed_date.replace(hour=hour, minute=minute, tzinfo=tz)
        if tz:
            return dt_local.astimezone(UTC)
        return dt_local.replace(tzinfo=UTC)

    def _html_raw_cell(self, row_html: str, class_name: str) -> str:
        match = re.search(
            rf'<(?:td|span|div)[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>(.*?)</(?:td|span|div)>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return match.group(1) if match else ""

    def _html_cell_text(self, row_html: str, class_name: str) -> str:
        match = re.search(
            rf'<(?:td|span|div)[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>(.*?)</(?:td|span|div)>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))

    def _html_event_time(self, row_html: str) -> datetime | None:
        for pattern in (
            r'data-event-datetime="([^"]+)"',
            r'data-event-time="([^"]+)"',
            r'datetime="([^"]+)"',
        ):
            match = re.search(pattern, row_html, flags=re.IGNORECASE)
            if match:
                parsed = parse_event_time(match.group(1))
                if parsed:
                    return parsed
        return None

    def _html_impact(self, row_html: str) -> str:
        lowered = row_html.lower()
        if "high impact" in lowered or "calendar__impact-icon--red" in lowered or "ff-impact-red" in lowered:
            return "High"
        if "medium impact" in lowered or "calendar__impact-icon--orange" in lowered or "ff-impact-orange" in lowered:
            return "Medium"
        if "low impact" in lowered or "calendar__impact-icon--yellow" in lowered or "ff-impact-yellow" in lowered:
            return "Low"
        return ""

    # ------------------------------------------------------------------
    # Event selection / merge
    # ------------------------------------------------------------------

    def _select_calendar_events(self, currencies: list[str], rows: list[dict[str, object]]) -> list[dict[str, object]]:
        wanted = {currency.upper() for currency in currencies}
        relevant = [dict(row) for row in rows if str(row.get("currency", "")).upper() in wanted]
        if relevant:
            return sorted(relevant, key=lambda row: str(row.get("time_utc", "")))[:8]
        important = [
            dict(row)
            for row in rows
            if _is_high_impact(str(row.get("impact", ""))) or str(row.get("impact", "")).lower() == "medium"
        ]
        return sorted(important, key=lambda row: str(row.get("time_utc", "")))[:8]

    def _merge_actual_from_html(self, json_rows: list[dict[str, object]], html_rows: list[dict[str, object]]) -> None:
        if not html_rows:
            return
        now = datetime.now(UTC)
        html_lookup: dict[tuple[str, str, str], str] = {}
        for row in html_rows:
            currency = str(row.get("currency", "")).upper()
            event = str(row.get("event", "")).strip().lower()
            actual = str(row.get("actual", "")).strip()
            ev_time = _event_time(row)
            date_key = ev_time.strftime("%Y%m%d") if ev_time else ""
            if actual and currency and event:
                html_lookup[(currency, event, date_key)] = actual

        if not html_lookup:
            return

        for row in json_rows:
            ev_time = _event_time(row)
            if not ev_time or ev_time >= now:
                continue
            currency = str(row.get("currency", "")).upper()
            event = str(row.get("event", "")).strip().lower()
            date_key = ev_time.strftime("%Y%m%d")
            key = (currency, event, date_key)
            if key in html_lookup and not str(row.get("actual", "")).strip():
                row["actual"] = html_lookup[key]

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def _store_calendar_cache(self, rows: list[dict[str, object]]) -> None:
        if not rows:
            return
        now = datetime.now(UTC)
        today_key = now.strftime("%Y%m%d")
        snapshot = [dict(row) for row in rows]

        existing = self._read_calendar_cache_file()
        if existing and existing.get("date") == today_key:
            old_rows = existing.get("rows", [])
            existing_keys = set()
            for r in old_rows:
                t = str(r.get("time_utc", ""))
                c = str(r.get("currency", ""))
                e = str(r.get("event", ""))
                existing_keys.add((t, c, e))
            for r in snapshot:
                t = str(r.get("time_utc", ""))
                c = str(r.get("currency", ""))
                e = str(r.get("event", ""))
                if (t, c, e) not in existing_keys:
                    old_rows.append(r)
            snapshot = old_rows

        self._calendar_cache["global"] = (now, snapshot)
        try:
            cache_file = self._calendar_cache_file()
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({"date": today_key, "stored_utc": now.isoformat(), "rows": snapshot}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _read_calendar_cache_file(self) -> dict | None:
        try:
            cache_file = self._calendar_cache_file()
            if cache_file.exists():
                return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    def _cached_calendar_events(self) -> list[dict[str, object]]:
        cached = self._calendar_cache.get("global")
        if cached:
            timestamp, rows = cached
            if datetime.now(UTC) - timestamp <= self.CALENDAR_CACHE_MAX_AGE:
                return [dict(row) for row in rows]

        raw = self._read_calendar_cache_file()
        if raw and isinstance(raw, dict):
            stored = parse_event_time(str(raw.get("stored_utc", "")))
            rows = raw.get("rows", [])
            if stored and datetime.now(UTC) - stored <= self.CALENDAR_CACHE_MAX_AGE and isinstance(rows, list):
                clean_rows = [dict(row) for row in rows if isinstance(row, dict)]
                if clean_rows:
                    self._calendar_cache["global"] = (stored, clean_rows)
                    return clean_rows
        return []

    def _calendar_cache_file(self) -> Path:
        if self.CALENDAR_CACHE_FILE is not None:
            return self.CALENDAR_CACHE_FILE
        return app_data_dir() / "cache" / "economic_calendar_thisweek.json"
