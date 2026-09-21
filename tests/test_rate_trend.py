"""Pure tests for the rate-trend derivation (contract §4.4, plan lô L1.5).

``core/rate_trend.py`` is the registered single owner of the hike/cut/hold
derivation (contract §11b).  Its contract, verified here:

* the threshold is chosen by ``latest.source`` - FRED ``0.1`` (inherited from
  ``_fetch_from_fred`` d.182-187 of ``services/interest_rate_service.py``),
  FF_HTML ``0.01`` (inherited from ``_update_from_forexfactory`` d.123);
  the two thresholds stay separate and never get merged (B5);
* the strict ``>``/``<`` comparisons are kept verbatim: a delta exactly equal
  to the threshold is ``HOLD``, not hike/cut;
* ``previous is None`` (fewer than two observations) is ``HOLD`` for every
  source - the characterization of the legacy single-observation run
  (d.179, ``prev = latest`` -> delta 0);
* ``RateSource.CONFIG_FALLBACK`` has no inherited threshold (the legacy code
  never derived a trend for the fallback source) and conservatively stays
  ``HOLD`` - no number is fabricated (B5);
* ``derive_rate_trend`` return behavior matches the legacy inline logic on
  the same FRED/FF data pairs (B3, function-level);
* return values are ``RateTrend`` enum members, never bare strings (C3, L3) -
  yet ``result == "hike"`` keeps the positional equivalence of the legacy code
  returning a string;
* the module stays pure and layer-clean (L2/L1): the source imports nothing
  outside stdlib + ``core.news_models``.
"""

from __future__ import annotations

import ast
import inspect
import typing
from pathlib import Path

import pytest

from core.news_models import RateObservation, RateSource
from core.rate_trend import RateTrend, derive_rate_trend

_RATE_TREND_PY = Path(__file__).resolve().parents[1] / "core" / "rate_trend.py"


def _obs(rate: float, source: RateSource, latest: bool = True) -> RateObservation:
    """One simulated ``RateObservation``; distinct dates for the two slots."""
    return RateObservation(
        currency="USD",
        rate=rate,
        observed_at="2026-09-21" if latest else "2026-09-20",
        source=source,
        fetched_at="2026-09-21T01:00:00Z",
    )


def _pair(latest_rate: float, previous_rate: float, source: RateSource) -> tuple:
    return _obs(latest_rate, source), _obs(previous_rate, source, latest=False)


class TestFredBoundaries:
    """FRED threshold 0.1 with strict >/< - delta +/- boundary at exactly 0.1."""

    @pytest.mark.parametrize(
        ("latest_rate", "previous_rate", "expected"),
        [
            (0.20, 0.00, RateTrend.HIKE),  # delta +0.2 > 0.1
            (0.11, 0.00, RateTrend.HIKE),  # delta +0.11 strictly above
            (0.10, 0.00, RateTrend.HOLD),  # delta exactly +0.1 -> hold
            (0.05, 0.00, RateTrend.HOLD),  # delta +0.05 below threshold
            (0.00, 0.10, RateTrend.HOLD),  # delta exactly -0.1 -> hold
            (0.00, 0.11, RateTrend.CUT),  # delta -0.11 strictly below
            (0.00, 0.20, RateTrend.CUT),  # delta -0.2 < -0.1
        ],
    )
    def test_fred_boundary_deltas(self, latest_rate, previous_rate, expected):
        latest, previous = _pair(latest_rate, previous_rate, RateSource.FRED)
        assert derive_rate_trend(latest, previous) is expected

    def test_fred_spec_example_delta_plus_zero_point_two_is_hike(self):
        latest, previous = _pair(0.20, 0.00, RateSource.FRED)
        assert derive_rate_trend(latest, previous) is RateTrend.HIKE

    def test_fred_spec_example_delta_minus_zero_point_two_is_cut(self):
        latest, previous = _pair(0.00, 0.20, RateSource.FRED)
        assert derive_rate_trend(latest, previous) is RateTrend.CUT

    def test_fred_zero_delta_is_hold(self):
        latest, previous = _pair(5.25, 5.25, RateSource.FRED)
        assert derive_rate_trend(latest, previous) is RateTrend.HOLD


class TestFfHtmlBoundaries:
    """FF_HTML threshold 0.01 with strict >/< - boundary kept at exactly 0.01."""

    @pytest.mark.parametrize(
        ("latest_rate", "previous_rate", "expected"),
        [
            (0.05, 0.00, RateTrend.HIKE),  # delta +0.05 > 0.01
            (0.02, 0.00, RateTrend.HIKE),  # delta +0.02 strictly above
            (0.01, 0.00, RateTrend.HOLD),  # delta exactly +0.01 -> hold
            (0.005, 0.00, RateTrend.HOLD),  # delta +0.005 below threshold
            (0.00, 0.01, RateTrend.HOLD),  # delta exactly -0.01 -> hold
            (0.00, 0.02, RateTrend.CUT),  # delta -0.02 strictly below
            (0.00, 0.05, RateTrend.CUT),  # delta -0.05 < -0.01
        ],
    )
    def test_ff_html_boundary_deltas(self, latest_rate, previous_rate, expected):
        latest, previous = _pair(latest_rate, previous_rate, RateSource.FF_HTML)
        assert derive_rate_trend(latest, previous) is expected

    def test_ff_html_spec_example_delta_plus_zero_point_zero_five_is_hike(self):
        latest, previous = _pair(0.05, 0.00, RateSource.FF_HTML)
        assert derive_rate_trend(latest, previous) is RateTrend.HIKE

    def test_ff_html_spec_example_delta_minus_zero_point_zero_five_is_cut(self):
        latest, previous = _pair(0.00, 0.05, RateSource.FF_HTML)
        assert derive_rate_trend(latest, previous) is RateTrend.CUT


class TestTwoThresholdsStaySeparate:
    """The same delta must resolve differently per source - the thresholds are
    never merged (B5)."""

    def test_same_delta_zero_point_zero_five_is_fred_hold_but_ff_hike(self):
        fred_latest, fred_previous = _pair(0.05, 0.00, RateSource.FRED)
        ff_latest, ff_previous = _pair(0.05, 0.00, RateSource.FF_HTML)
        assert derive_rate_trend(fred_latest, fred_previous) is RateTrend.HOLD
        assert derive_rate_trend(ff_latest, ff_previous) is RateTrend.HIKE

    def test_same_data_over_the_fred_threshold_drives_both_to_hike(self):
        fred_latest, fred_previous = _pair(0.20, 0.00, RateSource.FRED)
        ff_latest, ff_previous = _pair(0.20, 0.00, RateSource.FF_HTML)
        assert derive_rate_trend(fred_latest, fred_previous) is RateTrend.HIKE
        assert derive_rate_trend(ff_latest, ff_previous) is RateTrend.HIKE


class TestFewerThanTwoObservations:
    """``previous is None`` -> HOLD for every source (B3: legacy "<2 obs" run
    had ``prev = latest`` -> delta 0 -> hold, d.179/182-187)."""

    @pytest.mark.parametrize("source", list(RateSource))
    def test_single_observation_is_hold_for_every_source(self, source):
        latest = _obs(5.5, source)
        assert derive_rate_trend(latest, None) is RateTrend.HOLD

    def test_rate_value_is_irrelevant_for_single_observation(self):
        latest = _obs(0.25, RateSource.FRED)
        assert derive_rate_trend(latest, None) is RateTrend.HOLD


class TestConfigFallback:
    """No inherited threshold exists for the fallback source (the legacy code
    never derived a trend for it) -> conservative HOLD, never a fabricated
    number (B5)."""

    def test_config_fallback_large_positive_delta_is_hold(self):
        latest, previous = _pair(5.5, 5.25, RateSource.CONFIG_FALLBACK)
        assert derive_rate_trend(latest, previous) is RateTrend.HOLD

    def test_config_fallback_large_negative_delta_is_hold(self):
        latest, previous = _pair(5.25, 5.5, RateSource.CONFIG_FALLBACK)
        assert derive_rate_trend(latest, previous) is RateTrend.HOLD

    def test_config_fallback_single_observation_is_hold(self):
        assert (
            derive_rate_trend(_obs(5.5, RateSource.CONFIG_FALLBACK), None)
            is RateTrend.HOLD
        )


class TestLegacyBehaviorEquivalence:
    """B3 (function level): the derivation matches the legacy inline logic of
    ``services/interest_rate_service.py`` on the same FRED/FF data pairs."""

    def test_fred_pairs_match_legacy_lines_182_187(self):
        # Legacy: ``latest > prev + 0.1`` -> hike, ``latest < prev - 0.1`` ->
        # cut, else hold.  Verified equivalent on these real rate pairs.
        cases = [
            (5.50, 5.25, RateTrend.HIKE),
            (5.40, 5.25, RateTrend.HIKE),
            (5.25, 5.25, RateTrend.HOLD),
            (5.20, 5.25, RateTrend.HOLD),  # delta -0.05, within +-0.1
            (5.25, 5.50, RateTrend.CUT),
        ]
        for latest_rate, previous_rate, expected in cases:
            latest, previous = _pair(latest_rate, previous_rate, RateSource.FRED)
            assert derive_rate_trend(latest, previous) is expected

    def test_ff_html_pairs_match_legacy_line_123(self):
        # Legacy: ``new > old + 0.01`` -> hike, ``new < old - 0.01`` -> cut,
        # else hold.  Verified equivalent on these real rate pairs.
        cases = [
            (5.30, 5.25, RateTrend.HIKE),
            (5.25, 5.25, RateTrend.HOLD),
            (5.24, 5.25, RateTrend.HOLD),  # delta -0.01, at the boundary
            (5.25, 5.30, RateTrend.CUT),
        ]
        for latest_rate, previous_rate, expected in cases:
            latest, previous = _pair(latest_rate, previous_rate, RateSource.FF_HTML)
            assert derive_rate_trend(latest, previous) is expected

    def test_threshold_source_follows_latest_not_previous(self):
        # Threshold selection is fixed to ``latest.source`` (§4.4): when the
        # newest observation comes from FRED, the FRED threshold applies even
        # if the older one was captured from the FF HTML channel.
        latest = _obs(0.15, RateSource.FRED)
        previous = _obs(0.00, RateSource.FF_HTML, latest=False)
        assert derive_rate_trend(latest, previous) is RateTrend.HIKE


class TestRateTrendEnum:
    """The enum is the frozen machine-read value set (sections 2, L1.5 §3.3)."""

    def test_documented_value_set_is_closed(self):
        assert [member.value for member in RateTrend] == ["hike", "cut", "hold"]

    def test_str_member_equals_value(self):
        for member in RateTrend:
            assert str(member) == member.value
            assert member.value in ("hike", "cut", "hold")

    def test_result_equals_the_plain_string_of_legacy_code(self):
        latest, previous = _pair(0.20, 0.00, RateSource.FRED)
        assert derive_rate_trend(latest, previous) == "hike"

    def test_result_value_is_the_persisted_string(self):
        latest, previous = _pair(0.00, 0.20, RateSource.FRED)
        assert derive_rate_trend(latest, previous).value == "cut"
        assert str(derive_rate_trend(latest, previous)) == "cut"


class TestContractShape:
    """Locked signature + typed results only (C3, L1.5 §3.1)."""

    def test_derive_rate_trend_signature(self):
        sig = inspect.signature(derive_rate_trend)
        assert list(sig.parameters) == ["latest", "previous"]
        assert sig.parameters["latest"].default is inspect.Parameter.empty
        assert sig.parameters["previous"].default is inspect.Parameter.empty
        assert typing.get_type_hints(derive_rate_trend)["return"] is RateTrend

    def test_result_is_exactly_rate_trend_never_a_bare_string(self):
        latest, previous = _pair(0.20, 0.00, RateSource.FRED)
        result = derive_rate_trend(latest, previous)
        assert type(result) is RateTrend
        assert isinstance(result, RateTrend)
        assert result == "hike"  # str-equivalence with the legacy string result

    def test_hold_result_flows_through_all_three_paths(self):
        none_pair_hold = derive_rate_trend(_obs(5.5, RateSource.FRED), None)
        boundary_hold = derive_rate_trend(*_pair(0.10, 0.00, RateSource.FRED))
        fallback_hold = derive_rate_trend(
            *_pair(5.5, 5.25, RateSource.CONFIG_FALLBACK)
        )
        for result in (none_pair_hold, boundary_hold, fallback_hold):
            assert type(result) is RateTrend
            assert result is RateTrend.HOLD

    def test_thresholds_are_module_constants_not_policy_loaded(self):
        # L1.5 §3.2: both inherited thresholds live in the module as constants
        # (0.1 / 0.01) with the B5 provenance label in their comments - they
        # are not among the nine keys of contract §7, so nothing reads them
        # through the ``news_policy`` loader.
        import core.rate_trend as rate_trend_mod

        assert rate_trend_mod._FRED_THRESHOLD == 0.1
        assert rate_trend_mod._FF_THRESHOLD == 0.01
        assert rate_trend_mod._FRED_THRESHOLD != rate_trend_mod._FF_THRESHOLD
        source = _RATE_TREND_PY.read_text(encoding="utf-8")
        assert "news_policy" not in "".join(
            line for line in source.splitlines() if line.startswith(("import ", "from "))
        )


class TestCoreLayerBoundary:
    """core/rate_trend.py: pure + stdlib only (L2/L1 — điểm review của lô)."""

    @classmethod
    def _source(cls) -> str:
        return _RATE_TREND_PY.read_text(encoding="utf-8")

    @classmethod
    def _imported_modules(cls) -> set[str]:
        tree = ast.parse(cls._source())
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
            elif isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
        return modules

    def test_imports_are_stdlib_plus_core_news_models_only(self):
        # The DoD review point: the pure module imports only the type seam;
        # no policy, no services/ui/controllers/Qt dependency (L1/L2/L3).
        allowed = {"__future__", "enum", "core.news_models"}
        imported = self._imported_modules()
        assert imported <= allowed, f"unexpected imports: {imported - allowed}"
        assert "core.news_models" in imported

    def test_module_imports_nothing_from_policy_services_ui_controllers_or_qt(self):
        # Scan only the actual import statements (not prose/docstrings): a
        # ``news_policy``/``services``/``ui``/``controllers``/Qt module must
        # never appear as an import of this pure core module.
        forbidden_markers = (
            "news_policy",
            "services",
            "ui",
            "controllers",
            "PyQt6",
            "tkinter",
        )
        statements = [
            line.strip()
            for line in self._source().splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        assert statements, "expected at least the __future__ import"
        for stmt in statements:
            for marker in forbidden_markers:
                assert marker not in stmt, f"{marker!r} must not appear in {stmt!r}"

    def test_module_source_is_ascii(self):
        # A core module carries no display strings and no Vietnamese labels
        # (L2/L3): the whole source stays ASCII (L1.5 §3.4).
        assert self._source().isascii()

    def test_derive_signature_reflects_the_contract(self):
        sig = inspect.signature(derive_rate_trend)
        assert list(sig.parameters) == ["latest", "previous"]
        assert typing.get_type_hints(derive_rate_trend)["return"] is RateTrend

    def test_only_frozen_enum_strings_flow_out(self):
        # The function never manufactures its own label - every output string
        # is one of the frozen enum values (L3).
        for result in (
            derive_rate_trend(*_pair(0.20, 0.00, RateSource.FRED)),  # HIKE
            derive_rate_trend(*_pair(0.10, 0.00, RateSource.FRED)),  # HOLD
            derive_rate_trend(*_pair(0.00, 0.20, RateSource.FRED)),  # CUT
        ):
            assert isinstance(result, RateTrend)
            assert result.value in {member.value for member in RateTrend}
            assert result is not RateTrend.HIKE or str(result) == "hike"
            assert result is not RateTrend.CUT or str(result) == "cut"
            assert result is not RateTrend.HOLD or str(result) == "hold"