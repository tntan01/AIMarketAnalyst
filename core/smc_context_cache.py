"""Canonical CONTEXT cache for the snapshot seam (Lô B-Ctx, D-LB-01).

**What this caches, and what it deliberately does not.**  The expensive half of
one SMC evaluation is building the canonical CONTEXT — the per-timeframe
structure, zones, lifecycle and confluence that
:func:`core.smc_canonical_context.build_canonical_smc_context` produces.  This
module caches exactly that mapping, keyed by the frozen raw input identity.

It NEVER caches, stores or reconstructs the evaluation: no
``SmcSnapshotEvaluation``, no ``candidate_sets``, no ``SideSelection``, no
``SmcScoringResult``, no plan/order or execution state.  A cache hit skips only
the context build; ``evaluate_smc_snapshot`` → coordinator → finalizer still run
**fresh, exactly once** for the request and produce the typed evaluation.  A hit
here is therefore a *context* hit — it is **not** an evaluator hit, and nothing
in this module may be described as one.

**Identity is pre-context.**  The key is computed from the frozen raw inputs the
builder actually receives — the closed candles, the cutoff, the symbol, the tick
metadata, the scan interval and the identity/versions of the builder itself —
*before* the builder runs.  The un-built context output is never part of the key.

**A hit publishes only what it read.**  The context is stored and returned as
serialised bytes, deserialised verbatim: no zone, evidence, id or timestamp is
created, nothing falls back to the legacy detector, and nothing is recomputed.
Anything short of an exact match — absent, corrupt, another contract version,
another rule identity, another input, an incomplete payload — is a **miss with a
reason**, and the caller rebuilds the context from source.  There is no
last-known-good path: a miss never returns a context.

**The cache never certifies freshness.**  It says nothing about whether a
confirmation is still valid, whether a zone is still usable, or whether a
dispatch may proceed: revalidation and dispatch build a fresh snapshot at their
own cutoff and bypass this cache entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import gzip
import hashlib
import json
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from core.market_models import Candle
from core.smc_persistence import (
    smc_identity_mismatch_codes,
    smc_persistence_identity,
)
from core.smc_snapshot_cache import _canonical_timestamp, smc_snapshot_identity


SMC_CONTEXT_CACHE_VERSION = "smc-context-cache-v1"
SMC_CONTEXT_CACHE_IDENTITY_KEY = "cache_identity"
SMC_CONTEXT_CACHE_KEY_KEY = "context_identity"
SMC_CONTEXT_CACHE_PAYLOAD_KEY = "context"
_CACHE_DIRECTORY = ("cache", "smc_context")

# Absent is a normal, expected miss: this input has not been built yet.
SMC_CONTEXT_MISS_ABSENT = "SMC_CONTEXT_MISS_ABSENT"
# The artifact is unreadable or is not the envelope this seam writes.
SMC_CONTEXT_MISS_RECORD_CORRUPTED = "SMC_CONTEXT_MISS_RECORD_CORRUPTED"
# Written under other rules / another contract version.
SMC_CONTEXT_MISS_IDENTITY_MISMATCH = "SMC_CONTEXT_MISS_IDENTITY_MISMATCH"
SMC_CONTEXT_MISS_VERSION_INVALID = "SMC_CONTEXT_MISS_VERSION_INVALID"
# Readable, current, but written for a different input.
SMC_CONTEXT_MISS_KEY_MISMATCH = "SMC_CONTEXT_MISS_KEY_MISMATCH"
# Readable and current, but the payload is not a complete canonical context.
SMC_CONTEXT_MISS_CONTEXT_INVALID = "SMC_CONTEXT_MISS_CONTEXT_INVALID"

# The three timeframes the context builder is given (data spec §2).
_BUILDER_TIMEFRAMES = ("D1", "H4", "H1")
# Keys a canonical context must carry to be usable by the evaluator.
_REQUIRED_CONTEXT_KEYS = ("domain_version", "contract_version", "symbol", "as_of")

# Counters a caller may pass to observe the seam (hit / miss / built / write_error).
CONTEXT_CACHE_COUNTERS = ("hit", "miss", "built", "write_error")


def _default_context_builder() -> Callable[..., dict[str, Any]]:
    """The canonical context producer — the same one the snapshot seam defaults to."""

    from core.smc_canonical_context import build_canonical_smc_context

    return build_canonical_smc_context


def context_builder_identity(builder: Callable[..., Any] | None = None) -> str:
    """Stable identity of ONE context builder, so two builders never share a key.

    The builder determines the context for the same candles, so its identity —
    module, qualname and the contract version of the context it produces — is
    part of the input identity.  A different builder (or a changed context
    contract) can therefore never reuse another builder's cached context.
    """

    target = builder if builder is not None else _default_context_builder()
    module = getattr(target, "__module__", "") or ""
    qualname = getattr(target, "__qualname__", "") or getattr(target, "__name__", "")
    return f"{module}.{qualname}"


def context_identity(
    *,
    symbol: str,
    as_of: datetime | str,
    candles_by_timeframe: Mapping[str, Sequence[Candle]],
    tick_size: float | None,
    scan_interval_min: int,
    builder: Callable[..., Any] | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> str:
    """The PRE-context identity of one builder invocation.

    Every value here is a frozen raw input the builder really reads.  The
    identity is computed before the builder is called, so the context it is
    about to produce can never take part in identifying its own input.
    """

    metadata: dict[str, Any] = {
        "cache_contract_version": SMC_CONTEXT_CACHE_VERSION,
        "context_builder": context_builder_identity(builder),
        "scan_interval_min": int(scan_interval_min),
        "tick_size": tick_size,
    }
    if extra_metadata:
        # Provenance the snapshot carries beside the builder's own inputs (the
        # tick-size source, say).  Including it keeps the key conservative: a
        # different provenance is a different request, not a reusable one.
        metadata.update({str(key): value for key, value in extra_metadata.items()})
    return smc_snapshot_identity(
        symbol=symbol,
        as_of=as_of,
        candles_by_timeframe=candles_by_timeframe,
        metadata=metadata,
    )


@dataclass(frozen=True, slots=True)
class SmcContextLookup:
    """Outcome of one context-cache read.  A miss never carries a context."""

    hit: bool
    reason_codes: tuple[str, ...] = ()
    context: Mapping[str, Any] | None = None
    identity_mismatch_codes: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Whether the caller may use ``context`` instead of rebuilding it."""

        return self.hit and self.context is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hit": self.hit,
            "reason_codes": list(self.reason_codes),
            "identity_mismatch_codes": list(self.identity_mismatch_codes),
        }


def smc_context_cache_path(root: Path, *, context_identity: str) -> Path:
    """Where one cached context lives.

    The filename is a digest of the input identity, so two different inputs can
    never share a slot and a caller cannot address another input's context.
    """

    normalized = str(context_identity or "").strip()
    if not normalized:
        raise ValueError("SMC context cache requires a context identity")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return Path(root).joinpath(*_CACHE_DIRECTORY, f"{digest}.json.gz")


def write_smc_context_record(
    root: Path,
    *,
    context_identity: str,
    context: Mapping[str, Any],
) -> Path:
    """Atomically store one canonical context under its pre-context identity.

    Writing is unconditional: the caller has just built the context from source,
    so it is by construction the one for this input.  Reading decides trust.
    """

    normalized = str(context_identity or "").strip()
    if not normalized:
        raise ValueError("SMC context cache requires a context identity")
    if not isinstance(context, Mapping) or not context:
        raise ValueError("SMC context cache requires a context payload")

    envelope = {
        "cache_contract_version": SMC_CONTEXT_CACHE_VERSION,
        SMC_CONTEXT_CACHE_IDENTITY_KEY: smc_persistence_identity(),
        SMC_CONTEXT_CACHE_KEY_KEY: normalized,
        SMC_CONTEXT_CACHE_PAYLOAD_KEY: json.loads(json.dumps(dict(context), default=str)),
    }
    path = smc_context_cache_path(root, context_identity=normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(envelope, handle, ensure_ascii=False, indent=None)
    temporary.replace(path)
    return path


def _context_is_complete(context: Any, *, symbol: str, as_of: datetime | str) -> bool:
    """Whether *context* is a whole canonical context for THIS request.

    Only structure is checked — never re-derived.  An incomplete payload (a
    truncated mapping, a missing timeframe, another request's symbol/cutoff) is
    refused so the caller rebuilds instead of evaluating a partial context.
    """

    if not isinstance(context, Mapping):
        return False
    if any(key not in context for key in _REQUIRED_CONTEXT_KEYS):
        return False
    for timeframe in _BUILDER_TIMEFRAMES:
        if not isinstance(context.get(timeframe), Mapping):
            return False
    if str(context.get("symbol") or "") != str(symbol or ""):
        return False
    return _same_instant(context.get("as_of"), as_of)


def _same_instant(left: Any, right: datetime | str) -> bool:
    """Whether two ISO timestamps name the same UTC instant."""

    try:
        return _canonical_timestamp(left, field_name="as_of") == _canonical_timestamp(
            right, field_name="as_of"
        )
    except (TypeError, ValueError):
        return False


def read_smc_context_record(
    root: Path,
    *,
    context_identity: str,
    symbol: str,
    as_of: datetime | str,
) -> SmcContextLookup:
    """Read the cached context for one input, or explain why it cannot be used."""

    path = smc_context_cache_path(root, context_identity=context_identity)
    if not path.is_file():
        return SmcContextLookup(hit=False, reason_codes=(SMC_CONTEXT_MISS_ABSENT,))

    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            envelope = json.load(handle)
    except (OSError, ValueError, EOFError):
        return SmcContextLookup(
            hit=False, reason_codes=(SMC_CONTEXT_MISS_RECORD_CORRUPTED,)
        )
    if not isinstance(envelope, Mapping):
        return SmcContextLookup(
            hit=False, reason_codes=(SMC_CONTEXT_MISS_RECORD_CORRUPTED,)
        )
    if envelope.get("cache_contract_version") != SMC_CONTEXT_CACHE_VERSION:
        return SmcContextLookup(
            hit=False, reason_codes=(SMC_CONTEXT_MISS_VERSION_INVALID,)
        )

    identity_codes = smc_identity_mismatch_codes(
        envelope.get(SMC_CONTEXT_CACHE_IDENTITY_KEY)
    )
    if identity_codes:
        # Another rule identity produced this context (older detector/zone
        # policy) or the identity was tampered with.  It is not this input's
        # current context, and there is no fallback that would make it one.
        return SmcContextLookup(
            hit=False,
            reason_codes=(SMC_CONTEXT_MISS_IDENTITY_MISMATCH,),
            identity_mismatch_codes=identity_codes,
        )

    stored_key = envelope.get(SMC_CONTEXT_CACHE_KEY_KEY)
    if not isinstance(stored_key, str) or stored_key != str(context_identity).strip():
        return SmcContextLookup(
            hit=False, reason_codes=(SMC_CONTEXT_MISS_KEY_MISMATCH,)
        )

    context = envelope.get(SMC_CONTEXT_CACHE_PAYLOAD_KEY)
    if not _context_is_complete(context, symbol=symbol, as_of=as_of):
        return SmcContextLookup(
            hit=False, reason_codes=(SMC_CONTEXT_MISS_CONTEXT_INVALID,)
        )
    return SmcContextLookup(hit=True, context=context)


def caching_context_builder(
    *,
    root: Path,
    builder: Callable[..., dict[str, Any]] | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
    counters: MutableMapping[str, int] | None = None,
) -> Callable[..., dict[str, Any]]:
    """Wrap a context builder so the canonical context is built once per input.

    The returned callable matches the seam's ``ContextBuilder`` signature.  On a
    hit the wrapped builder is **not called**; the deserialised context is
    returned as it was stored.  On any miss it builds from source and stores the
    result.

    A failing write is swallowed on purpose: the request has already built a
    correct context, and a cache problem must never turn it into an error, an
    older context or a different verdict.
    """

    real = builder if builder is not None else _default_context_builder()
    tally = counters if counters is not None else {}

    def _count(name: str) -> None:
        tally[name] = int(tally.get(name, 0)) + 1

    def _builder(
        d1: Sequence[Candle],
        h4: Sequence[Candle],
        h1: Sequence[Candle],
        *,
        scan_interval_min: int = 15,
        symbol: str,
        as_of: Any,
        tick_size: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        candles = {"D1": list(d1), "H4": list(h4), "H1": list(h1)}
        identity = context_identity(
            symbol=symbol,
            as_of=as_of,
            candles_by_timeframe=candles,
            tick_size=tick_size,
            scan_interval_min=scan_interval_min,
            builder=real,
            extra_metadata=extra_metadata,
        )
        lookup = read_smc_context_record(
            root, context_identity=identity, symbol=symbol, as_of=as_of
        )
        if lookup.usable:
            _count("hit")
            return dict(lookup.context or {})
        _count("miss")
        context = real(
            d1,
            h4,
            h1,
            scan_interval_min=scan_interval_min,
            symbol=symbol,
            as_of=as_of,
            tick_size=tick_size,
            **kwargs,
        )
        _count("built")
        try:
            write_smc_context_record(
                root, context_identity=identity, context=context
            )
        except (OSError, ValueError, TypeError):
            _count("write_error")
        return context

    return _builder


__all__ = [
    "CONTEXT_CACHE_COUNTERS",
    "SMC_CONTEXT_CACHE_IDENTITY_KEY",
    "SMC_CONTEXT_CACHE_KEY_KEY",
    "SMC_CONTEXT_CACHE_PAYLOAD_KEY",
    "SMC_CONTEXT_CACHE_VERSION",
    "SMC_CONTEXT_MISS_ABSENT",
    "SMC_CONTEXT_MISS_CONTEXT_INVALID",
    "SMC_CONTEXT_MISS_IDENTITY_MISMATCH",
    "SMC_CONTEXT_MISS_KEY_MISMATCH",
    "SMC_CONTEXT_MISS_RECORD_CORRUPTED",
    "SMC_CONTEXT_MISS_VERSION_INVALID",
    "SmcContextLookup",
    "caching_context_builder",
    "context_builder_identity",
    "context_identity",
    "read_smc_context_record",
    "smc_context_cache_path",
    "write_smc_context_record",
]
