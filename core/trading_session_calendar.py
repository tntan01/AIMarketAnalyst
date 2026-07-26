"""Deterministic trading-session policy used by Backtest data validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


TRADING_SESSION_POLICY_VERSION = "trading-session-calendar-v1"
HOLIDAY_CALENDAR_VERSION = "backtest-market-holidays-v1"

SESSION_OPEN = "SESSION_OPEN"
EXPECTED_SESSION_CLOSE = "EXPECTED_SESSION_CLOSE"
BROKER_MAINTENANCE = "BROKER_MAINTENANCE"
MARKET_HOLIDAY = "MARKET_HOLIDAY"
UNEXPECTED_DATA_GAP = "UNEXPECTED_DATA_GAP"

ASSET_FOREX = "FOREX"
ASSET_METAL = "METAL"
ASSET_CRYPTO = "CRYPTO"

_NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True, slots=True)
class TradingSessionPolicy:
    version: str
    holiday_calendar_version: str
    asset_class: str
    timezone_name: str
    weekly_open: str
    weekly_close: str
    daily_maintenance: str
    weekly_open_grace_minutes: int


@dataclass(frozen=True, slots=True)
class SlotClassification:
    expected_candle: bool
    classification: str
    detail: str


class TradingSessionCalendar:
    """Classify whether a missing candle belongs to an expected closure.

    Forex and metals are defined in New York local time so the UTC boundary
    follows US daylight saving time without a hard-coded UTC month table.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = _normalize_symbol(symbol)
        self.policy = _policy_for_symbol(self.symbol)

    @property
    def fingerprint(self) -> str:
        payload = {
            "symbol": self.symbol,
            "policy": asdict(self.policy),
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            **asdict(self.policy),
            "fingerprint": self.fingerprint,
        }

    def classify_missing_slot(
        self,
        opened_at: datetime,
        duration: timedelta,
        *,
        timeframe: str,
    ) -> SlotClassification:
        opened_utc = _utc(opened_at)
        if self.policy.asset_class == ASSET_CRYPTO:
            return SlotClassification(
                True,
                UNEXPECTED_DATA_GAP,
                "Thị trường crypto được kỳ vọng giao dịch 24/7.",
            )

        if str(timeframe or "").upper() == "D1":
            return self._classify_daily_slot(opened_utc)

        statuses = {
            self._instant_status(sample)
            for sample in _slot_samples(opened_utc, duration)
        }
        if SESSION_OPEN in statuses:
            return SlotClassification(
                True,
                UNEXPECTED_DATA_GAP,
                "Khoảng thời gian có ít nhất một phần nằm trong phiên giao dịch.",
            )
        if MARKET_HOLIDAY in statuses:
            return SlotClassification(
                False,
                MARKET_HOLIDAY,
                "Thị trường đóng cửa theo lịch nghỉ có version.",
            )
        if BROKER_MAINTENANCE in statuses:
            return SlotClassification(
                False,
                BROKER_MAINTENANCE,
                "Khoảng nghỉ bảo trì hằng ngày của nhóm kim loại.",
            )
        return SlotClassification(
            False,
            EXPECTED_SESSION_CLOSE,
            "Thị trường đóng cửa theo lịch phiên cuối tuần.",
        )

    def _classify_daily_slot(self, opened_utc: datetime) -> SlotClassification:
        day = opened_utc.date()
        holiday = _holiday_name(day, self.policy.asset_class)
        if holiday:
            return SlotClassification(False, MARKET_HOLIDAY, holiday)
        if opened_utc.weekday() >= 5:
            return SlotClassification(
                False,
                EXPECTED_SESSION_CLOSE,
                "Nến D1 cuối tuần không được kỳ vọng tồn tại.",
            )
        return SlotClassification(
            True,
            UNEXPECTED_DATA_GAP,
            "Nến D1 thuộc một ngày giao dịch trong tuần.",
        )

    def _instant_status(self, value: datetime) -> str:
        local = _utc(value).astimezone(_NEW_YORK)
        local_time = local.time().replace(tzinfo=None)
        trading_day = (
            local.date() + timedelta(days=1)
            if local_time >= time(17, 0)
            else local.date()
        )
        holiday = _holiday_name(trading_day, self.policy.asset_class)
        if holiday:
            return MARKET_HOLIDAY

        weekday = local.weekday()
        if weekday == 5:
            return EXPECTED_SESSION_CLOSE

        if self.policy.asset_class == ASSET_METAL:
            early_close = _metal_early_close(local.date())
            if early_close is not None and early_close <= local_time < time(18, 0):
                return MARKET_HOLIDAY
            if weekday == 6:
                if local_time < time(18, 0):
                    return EXPECTED_SESSION_CLOSE
                if local_time < time(18, self.policy.weekly_open_grace_minutes):
                    return BROKER_MAINTENANCE
                return SESSION_OPEN
            if weekday == 4 and local_time >= time(17, 0):
                return EXPECTED_SESSION_CLOSE
            if weekday < 4 and time(17, 0) <= local_time < time(18, 0):
                return BROKER_MAINTENANCE
            if weekday < 4 and time(18, 0) <= local_time < time(18, 15):
                return BROKER_MAINTENANCE
            return SESSION_OPEN

        if weekday == 6:
            if local_time < time(17, 0):
                return EXPECTED_SESSION_CLOSE
            if local_time < time(17, self.policy.weekly_open_grace_minutes):
                return BROKER_MAINTENANCE
            return SESSION_OPEN
        if weekday == 4 and local_time >= time(17, 0):
            return EXPECTED_SESSION_CLOSE
        return SESSION_OPEN


def trading_session_calendar(symbol: str) -> TradingSessionCalendar:
    return TradingSessionCalendar(symbol)


def _normalize_symbol(symbol: str) -> str:
    normalized = "".join(character for character in str(symbol or "").upper() if character.isalpha())
    return normalized or "GENERICFX"


def _policy_for_symbol(symbol: str) -> TradingSessionPolicy:
    if symbol.startswith(("BTC", "ETH")):
        asset_class = ASSET_CRYPTO
        weekly_open = "ALWAYS"
        weekly_close = "NEVER"
        maintenance = "NONE"
        open_grace = 0
    elif symbol.startswith(("XAU", "XAG")):
        asset_class = ASSET_METAL
        weekly_open = "SUNDAY 18:00 America/New_York"
        weekly_close = "FRIDAY 17:00 America/New_York"
        maintenance = "MONDAY-THURSDAY 17:00-18:00 America/New_York"
        open_grace = 15
    else:
        asset_class = ASSET_FOREX
        weekly_open = "SUNDAY 17:00 America/New_York"
        weekly_close = "FRIDAY 17:00 America/New_York"
        maintenance = "NONE"
        open_grace = 15
    return TradingSessionPolicy(
        version=TRADING_SESSION_POLICY_VERSION,
        holiday_calendar_version=HOLIDAY_CALENDAR_VERSION,
        asset_class=asset_class,
        timezone_name="America/New_York",
        weekly_open=weekly_open,
        weekly_close=weekly_close,
        daily_maintenance=maintenance,
        weekly_open_grace_minutes=open_grace,
    )


def _slot_samples(opened_at: datetime, duration: timedelta) -> tuple[datetime, ...]:
    if duration <= timedelta(0):
        return (opened_at,)
    end_inside = opened_at + duration - timedelta(microseconds=1)
    midpoint = opened_at + duration / 2
    return (opened_at, midpoint, end_inside)


def _holiday_name(day: date, asset_class: str) -> str | None:
    if asset_class == ASSET_CRYPTO:
        return None
    if (day.month, day.day) == (1, 1):
        return "New Year's Day"
    if (day.month, day.day) == (12, 25):
        return "Christmas Day"
    if asset_class == ASSET_METAL and day == _western_easter(day.year) - timedelta(days=2):
        return "Good Friday"
    return None


def _metal_early_close(day: date) -> time | None:
    """Return the deterministic New York close time for major metal holidays."""

    if day == _nth_weekday(day.year, 1, 0, 3):  # Martin Luther King Jr. Day
        return time(14, 30)
    if day == _nth_weekday(day.year, 2, 0, 3):  # Presidents Day
        return time(14, 30)
    if day == _last_weekday(day.year, 5, 0):  # Memorial Day
        return time(14, 30)
    if day == _observed_date(date(day.year, 6, 19)):  # Juneteenth
        return time(13, 0)
    if day == _observed_date(date(day.year, 7, 4)):  # Independence Day
        return time(13, 0)
    thanksgiving = _nth_weekday(day.year, 11, 3, 4)
    if day == thanksgiving:
        return time(14, 30)
    if day == thanksgiving + timedelta(days=1):
        return time(13, 0)
    if day.month == 12 and day.day == 24 and day.weekday() < 5:
        return time(13, 0)
    return None


def _nth_weekday(
    year: int,
    month: int,
    weekday: int,
    occurrence: int,
) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (occurrence - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    return cursor - timedelta(days=(cursor.weekday() - weekday) % 7)


def _observed_date(value: date) -> date:
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def _western_easter(year: int) -> date:
    """Return Gregorian Easter Sunday using the Meeus/Jones/Butcher rule."""

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
