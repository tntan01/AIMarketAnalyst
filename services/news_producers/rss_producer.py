"""rss_producer — collection of public text news (headlines + statements)
into ``NewsItem`` (plan batch L2.5).

Sole owner of "thu thập tin văn bản công khai thành ``NewsItem``" (contract
§6.2 / §11b, identity M5).  This batch ports from ``news_service.py`` the 3
broad Google News queries (d.1207-1211), the 6 official-statement queries
(d.2621-2628), the ``EXTRA_RSS_FEEDS`` (FXStreet/Investing, d.521-524), the
``ElementTree`` parsers ``_rss_items``/``_rss_items_with_status``
(d.2696-2736), ``_fetch_extra_rss`` (d.1264-1296), ``parse_rss_time``
(d.3042-3053), ``_rss_collection_result`` status semantics (d.1449-1468),
``CURRENCY_KEYWORDS`` (d.105-117) and ``_matches_currency`` (d.2766-2768) —
transport (UA ``AI Market Analyst/1.0``, Google timeout=5, extra timeout=8),
caps (``[:8]`` per Google query, ``[:15]`` extra feed, 10 statements total)
and query/feed lists verbatim (inherited runtime — evidence label B5, no new
source invented).  The XML-to-``NewsItem`` converter sits at the boundary
(R8/C2): the raw row shape (``{"title","url","published_utc","query",...}``)
never leaves this module's public API.

One entry point, ``fetch_round`` = ONE collection round = one ``ingest_runs``
row (producer ``rss``, contract §4.6/§10).  Status follows the inherited
``_rss_collection_result`` mapping: every source unit fresh → ``ok``, some
dead → ``partial``, all dead → ``failed`` (contract §4.6).  The collection
window comes from policy ``rss_window_hours`` (R4 — nothing hard-coded; the
old ``now - 24h`` cutoff is replaced by the policy value).

Governance:

* **No timer/scheduler/poll.**  The ``rss_poll_interval_minutes`` cadence is
  owned by the L2.7 worker; this module never hard-codes it.
* **No disk cache** — the ``news_service`` disk-cache merge branch
  (d.1243-1255) is deliberately NOT ported (B7 §3.1.2).
* **No display strings, no headline tags, no impact notes** — ``_headline_tags``
  and ``_headline_impact_note`` (Vietnamese user-facing strings) are not ported
  (L3); ``impact_hint`` is reserved for ``user_note`` items (§4.3).
* **Deliberate deviations, plan-sanctioned (V2):** (a) an extra-feed transport
  error propagates to the caller instead of being silently swallowed, so the
  round status can reach ``failed`` (plan L2.5 test "nguồn chết"); (b) an item
  with an unparseable/empty time is skipped instead of persisted — §4.3 makes
  ``published_utc`` mandatory; (c) the in-round dedupe is the inherited
  title-lowercased first-wins (runtime behavior) while the persisted
  ``dedupe_key`` follows the §4.3 formula (hash of url, else title +
  published_utc) — the contract wins (D1).
* Within-round dedupe is a round-local set; duplicate titles across sources
  collapse to the first item seen (d.1195-1203).
"""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from core.news_models import (
    IngestProducer,
    IngestRun,
    IngestRunStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
)
from core.news_policy import NewsPolicy, load_news_policy
from services.calendar_helpers import clean_text, parse_event_time
from services.news_repository import NewsRepository

__all__ = [
    "RssCollectionResult",
    "RssProducer",
    "RssSourceError",
    "parse_rss_time",
]


# ---------------------------------------------------------------------------
# Inherited runtime data (B5: kế thừa runtime hiện hành — không bịa)
# ---------------------------------------------------------------------------

# news_service.py:105-117 — currency code -> keywords matched case-insensitively
# against an item title to derive its ``currencies``.
CURRENCY_KEYWORDS: dict[str, list[str]] = {
    "USD": ["Fed", "FOMC", "Powell", "Treasury yields", "US yields", "dollar"],
    "JPY": ["BOJ", "BoJ", "Ueda", "Japan", "Tokyo CPI", "Tankan", "intervention", "yen"],
    "EUR": ["ECB", "Lagarde", "Eurozone", "Bund yields", "euro"],
    "GBP": ["BOE", "Bailey", "UK", "sterling", "pound"],
    "CHF": ["SNB", "Swiss CPI", "franc", "safe haven"],
    "AUD": ["RBA", "Australia CPI", "China data", "iron ore", "Aussie"],
    "NZD": ["RBNZ", "New Zealand CPI", "kiwi"],
    "CAD": ["BOC", "Canada CPI", "WTI", "oil", "loonie"],
    "XAU": ["gold", "real yields", "safe haven", "geopolitics", "central banks"],
    "XAG": ["silver", "gold/silver ratio", "industrial metals", "real yields", "PMI"],
    "BTC": ["Bitcoin", "BTC", "crypto", "spot ETF", "on-chain", "digital assets"],
}

# news_service.py:1207-1211 (broad headline queries, kind=headline).
BROAD_QUERIES: tuple[str, ...] = (
    "forex central bank Fed ECB BOJ BOE rate decision macro latest",
    "global macro risk sentiment dollar yen euro pound forex markets",
    "forex geopolitical oil gold safe haven latest",
)

# news_service.py:2621-2628 (official-statement queries, kind=statement) with
# the ``speaker_role`` (contract §4.3 — free TEXT, not an enum).
STATEMENT_SOURCES: tuple[tuple[str, str], ...] = (
    ('Trump Truth Social tariffs dollar Fed "Truth Social"', "US President"),
    ("Trump remarks dollar tariffs Fed markets latest", "US President"),
    ("Fed officials speech Powell Waller Bowman dollar yields latest", "Fed official"),
    ("Japan Prime Minister remarks yen BOJ latest", "JP PM"),
    ("UK Prime Minister remarks pound BOE latest", "UK PM"),
    ("European Union officials Lagarde von der Leyen euro latest", "EU official"),
)

# news_service.py:521-524 — extra free feeds, each fixing its frozen enum.
EXTRA_RSS_FEEDS: tuple[tuple[str, NewsItemSource], ...] = (
    ("https://www.fxstreet.com/rss/news", NewsItemSource.FXSTREET_RSS),
    ("https://www.investing.com/rss/news_301.rss", NewsItemSource.INVESTING_RSS),
)


# ---------------------------------------------------------------------------
# Typed results (C3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RssSourceError:
    """One failed source unit of a collection round (contract §4.6 style:
    inherited classification — ``type(exc).__name__`` or ``InvalidRSSStructure``)."""

    source: str
    kind: NewsItemKind
    error_type: str
    detail: str


@dataclass(frozen=True, slots=True)
class RssCollectionResult:
    """Typed outcome of one RSS collection round (contract §6.2/§4.6).

    Carries the repository upsert summary, the single ``ingest_runs`` row id
    (producer ``rss``), the source-unit accounting of the inherited
    ``_rss_collection_result`` and the per-source errors.  Raw rows never
    cross this boundary (C3/R8)."""

    inserted: int
    updated: int
    run_status: IngestRunStatus
    run_id: int
    attempted_sources: int
    successful_sources: int
    source_errors: tuple[RssSourceError, ...]


# ---------------------------------------------------------------------------
# Module helpers (ported verbatim from news_service, B3)
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    """Current UTC time in the khuôn ISO-8601 form: ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_rss_time(value: str) -> datetime | None:
    """Port of ``news_service.parse_rss_time`` (d.3042-3053): RFC-2822 first,
    ISO-8601 fallback, a naive result is treated as UTC."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return parse_event_time(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _google_news_url(query: str) -> str:
    """Inherited Google News RSS search URL (news_service.py:1216/2635)."""
    return "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"


def _matches_currency(title: str, currency: str) -> bool:
    """Port of ``news_service._matches_currency`` (d.2766-2768): the currency
    code or any inherited keyword appears in the title (case-insensitive)."""
    text = str(title).lower()
    return currency.lower() in text or any(
        keyword.lower() in text for keyword in CURRENCY_KEYWORDS.get(currency, [])
    )


def _collection_status(successful_sources: int, attempted_sources: int) -> IngestRunStatus:
    """Map the inherited ``_rss_collection_result`` (d.1449-1468) status onto
    ``IngestRunStatus``: all → ``ok`` (fresh), some → ``partial`` (degraded),
    none → ``failed`` (unavailable)."""
    if successful_sources <= 0:
        return IngestRunStatus.FAILED
    if successful_sources < attempted_sources:
        return IngestRunStatus.PARTIAL
    return IngestRunStatus.OK


def _dedupe_key(*, url: str | None, title: str, published_utc: str) -> str:
    """Persisted ``NewsItem.dedupe_key`` per contract §4.3: hash of the url,
    else hash of ``title + published_utc`` (stable sha256 hex — same khuôn as
    the calendar producer)."""
    seed = url if url else f"{title}|{published_utc}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


class RssProducer:
    """Sole owner of collecting public text news into ``NewsItem`` (M5)."""

    def __init__(self, repo: NewsRepository, policy: NewsPolicy | None = None) -> None:
        self._repo = repo
        # Injected for testability of the window (R4 — the cadence key
        # rss_poll_interval_minutes belongs to the L2.7 worker).
        self._policy = policy if policy is not None else load_news_policy()

    # --- transport (ported verbatim from news_service; one shot, no retry) ------

    def _fetch_rss_items(
        self,
        url: str,
        *,
        query: str,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        """Google News RSS parser (port of ``_rss_items_with_status``,
        news_service.py:2700-2736): UA ``AI Market Analyst/1.0``, timeout=5,
        ``[:8]`` items, root must be ``rss`` with a ``channel`` else
        ``InvalidRSSStructure``; transport/parse errors → ``type(exc).__name__``.
        An empty feed is ``fresh``."""
        request = Request(url, headers={"User-Agent": "AI Market Analyst/1.0"})
        try:
            with urlopen(request, timeout=5) as response:
                payload = response.read()
        except Exception as exc:
            return [], {"status": "unavailable", "error_type": type(exc).__name__}
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            return [], {"status": "unavailable", "error_type": type(exc).__name__}
        root_name = str(root.tag).rsplit("}", 1)[-1].lower()
        if root_name != "rss" or root.find(".//channel") is None:
            return [], {"status": "unavailable", "error_type": "InvalidRSSStructure"}
        rows: list[dict[str, object]] = []
        for item in root.findall(".//item")[:8]:
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            source = clean_text(item.findtext("source") or "")
            published = parse_rss_time(item.findtext("pubDate") or "")
            rows.append(
                {
                    "source": source or "Google News RSS",
                    "query": query,
                    "title": title,
                    "url": link,
                    "published_utc": published.isoformat(timespec="minutes").replace("+00:00", "Z") if published else "",
                }
            )
        return rows, {"status": "fresh", "error_type": ""}

    def _fetch_extra_rss(self, url: str, cutoff: datetime) -> list[dict[str, object]]:
        """Standard-RSS feed parser (port of ``_fetch_extra_rss``,
        news_service.py:1264-1296): UA ``AI Market Analyst/1.0``, timeout=8,
        ``[:15]`` items, source-name fallback = bare host of the feed URL when
        the XML has no ``<source>``.  Unlike the original, a transport/parse
        error PROPAGATES so the round status can record a dead feed (B3 parity
        holds on the successful path; plan L2.5 "nguồn chết")."""
        request = Request(url, headers={"User-Agent": "AI Market Analyst/1.0"})
        with urlopen(request, timeout=8) as response:
            payload = response.read()
        root = ElementTree.fromstring(payload)
        items: list[dict[str, object]] = []
        for item in root.findall(".//item")[:15]:
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            source_name = clean_text(item.findtext("source") or "")
            pub_str = item.findtext("pubDate") or ""
            published = parse_rss_time(pub_str)
            if not title:
                continue
            if published and published < cutoff:
                continue
            if not source_name:
                source_name = url.split("/")[2].replace("www.", "")
            items.append(
                {
                    "source": source_name,
                    "title": title,
                    "url": link,
                    "published_utc": published.isoformat(timespec="minutes").replace("+00:00", "Z") if published else "",
                }
            )
        return items

    # --- one collection round ---------------------------------------------------

    def fetch_round(self, now: datetime | None = None) -> RssCollectionResult:
        """Collect one round of headlines + statements, upsert them (never
        "skip if exists" — §6.1 lượt 2 spirit for RSS) and log exactly one
        ``ingest_runs`` row (producer ``rss``, §4.6/§10).

        Source units: 3 broad queries + 2 extra feeds + 6 statement queries
        (11).  A dead source never blocks the others (``as_completed`` khuôn
        cũ); the round status follows ``_rss_collection_result`` semantics.
        ``now`` is injectable for deterministic tests; the window is
        ``now - policy.rss_window_hours`` (R4)."""
        started_at = _utc_now()
        now_dt = now if now is not None else datetime.now(UTC)
        cutoff = now_dt - timedelta(hours=self._policy.rss_window_hours)
        fetched_at = _utc_now()

        seen: set[str] = set()
        source_errors: list[RssSourceError] = []
        successful_sources = 0
        attempted_sources = len(BROAD_QUERIES) + len(EXTRA_RSS_FEEDS) + len(STATEMENT_SOURCES)
        headline_items: list[NewsItem] = []
        statement_rows: list[dict[str, object]] = []

        # --- kind=headline: 3 broad Google queries (parallel, 3 workers) --------
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self._fetch_google_batch, query, cutoff): query
                for query in BROAD_QUERIES
            }
            for future in as_completed(futures):
                query = futures[future]
                try:
                    rows, status = future.result()
                except Exception as exc:
                    source_errors.append(
                        RssSourceError(
                            source=query,
                            kind=NewsItemKind.HEADLINE,
                            error_type=type(exc).__name__,
                            detail=str(exc),
                        )
                    )
                    continue
                if status.get("status") != "fresh":
                    error_type = str(status.get("error_type", "")).strip() or "Unknown"
                    source_errors.append(
                        RssSourceError(source=query, kind=NewsItemKind.HEADLINE, error_type=error_type, detail=str(status))
                    )
                else:
                    successful_sources += 1
                for row in rows:
                    if self._first_seen(row, seen):
                        item = self._to_news_item(
                            row,
                            kind=NewsItemKind.HEADLINE,
                            source=NewsItemSource.GOOGLE_NEWS_RSS,
                            speaker_role=None,
                            fetched_at=fetched_at,
                        )
                        if item is not None:
                            headline_items.append(item)

        # --- kind=headline: extra free feeds (sequential, khuôn cũ) -------------
        for feed_url, source in EXTRA_RSS_FEEDS:
            try:
                rows = self._fetch_extra_rss(feed_url, cutoff)
            except Exception as exc:
                source_errors.append(
                    RssSourceError(
                        source=feed_url,
                        kind=NewsItemKind.HEADLINE,
                        error_type=type(exc).__name__,
                        detail=str(exc),
                    )
                )
                continue
            successful_sources += 1
            for row in rows:
                if self._first_seen(row, seen):
                    item = self._to_news_item(
                        row,
                        kind=NewsItemKind.HEADLINE,
                        source=source,
                        speaker_role=None,
                        fetched_at=fetched_at,
                    )
                    if item is not None:
                        headline_items.append(item)

        # --- kind=statement: 6 official-statement queries (parallel, 6 workers) --
        statement_roles = dict(STATEMENT_SOURCES)
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(self._fetch_google_batch, query, cutoff): query
                for query, _role in STATEMENT_SOURCES
            }
            for future in as_completed(futures):
                query = futures[future]
                try:
                    rows, status = future.result()
                except Exception as exc:
                    source_errors.append(
                        RssSourceError(
                            source=query,
                            kind=NewsItemKind.STATEMENT,
                            error_type=type(exc).__name__,
                            detail=str(exc),
                        )
                    )
                    continue
                if status.get("status") != "fresh":
                    error_type = str(status.get("error_type", "")).strip() or "Unknown"
                    source_errors.append(
                        RssSourceError(
                            source=query, kind=NewsItemKind.STATEMENT, error_type=error_type, detail=str(status)
                        )
                    )
                else:
                    successful_sources += 1
                for row in rows:
                    if self._first_seen(row, seen):
                        row["speaker_role"] = statement_roles[query]
                        statement_rows.append(row)

        # Inherited cap: at most 10 statements total (d.2674-2675).  Items that
        # cannot be converted (missing title / unparseable time, §4.3) are
        # dropped at this boundary — never handed to ``upsert_items``.
        statement_items = [
            item
            for row in statement_rows[:10]
            if (item := self._to_news_item(
                row,
                kind=NewsItemKind.STATEMENT,
                source=NewsItemSource.GOOGLE_NEWS_RSS,
                speaker_role=str(row.get("speaker_role") or None),
                fetched_at=fetched_at,
            )) is not None
        ]

        upsert = self._repo.upsert_items(headline_items + statement_items)
        first_error = source_errors[0] if source_errors else None
        run_status = _collection_status(successful_sources, attempted_sources)
        run_id = self._repo.record_run(
            IngestRun(
                producer=IngestProducer.RSS,
                started_at=started_at,
                finished_at=_utc_now(),
                status=run_status,
                items_written=upsert.inserted + upsert.updated,
                error_type=first_error.error_type if first_error else None,
                error_detail=first_error.detail if first_error else None,
            )
        )
        return RssCollectionResult(
            inserted=upsert.inserted,
            updated=upsert.updated,
            run_status=run_status,
            run_id=run_id,
            attempted_sources=attempted_sources,
            successful_sources=successful_sources,
            source_errors=tuple(source_errors),
        )

    # --- round helpers ----------------------------------------------------------

    def _fetch_google_batch(
        self,
        query: str,
        cutoff: datetime,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        """One Google query: parse the feed then drop items published before the
        cutoff (khuôn ``_fetch_one``, d.1214-1222/2633-2649)."""
        url = _google_news_url(query)
        rows, status = self._fetch_rss_items(url, query=query)
        kept: list[dict[str, object]] = []
        for row in rows:
            published = parse_rss_time(str(row.get("published_utc", "")))
            if not published or published < cutoff:
                continue
            kept.append(row)
        return kept, status

    def _first_seen(self, row: dict[str, object], seen: set[str]) -> bool:
        """In-round dedupe inherited from d.1195-1203: title lowercased +
        stripped, first-wins across every source of the round."""
        title_key = str(row.get("title", "")).lower().strip()
        if not title_key or title_key in seen:
            return False
        seen.add(title_key)
        return True

    def _to_news_item(
        self,
        row: dict[str, object],
        *,
        kind: NewsItemKind,
        source: NewsItemSource,
        speaker_role: str | None,
        fetched_at: str,
    ) -> NewsItem | None:
        """Raw RSS row → ``NewsItem`` at the boundary (R8/C2, contract §4.3).

        A missing title or an unparseable/empty ``published_utc`` is skipped
        (the column is mandatory); ``currencies`` is derived from the title via
        the inherited ``CURRENCY_KEYWORDS``/``_matches_currency``; ``url``
        empty → ``None``; ``content`` stays ``None`` (this channel has no body);
        ``dedupe_key`` follows the §4.3 formula."""
        title = str(row.get("title", "")).strip()
        if not title:
            return None
        published_utc = str(row.get("published_utc", "")).strip()
        if not published_utc:
            return None
        url = str(row.get("url", "")).strip()
        currencies = [currency for currency in CURRENCY_KEYWORDS if _matches_currency(title, currency)]
        return NewsItem(
            kind=kind,
            source=source,
            title=title,
            published_utc=published_utc,
            currencies=currencies,
            dedupe_key=_dedupe_key(url=url or None, title=title, published_utc=published_utc),
            fetched_at=fetched_at,
            content=None,
            url=url or None,
            speaker_role=speaker_role,
        )