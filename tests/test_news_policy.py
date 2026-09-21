"""Contract tests for the News domain policy seam (contract §7, plan lô L1.1).

``core/news_policy.py`` is the ONLY runtime seam that reads
``config/news_policy.json``. Its contract:

* the committed file pins, key for key, the values the Owner decided at
  ``docs/news/news-architecture.md`` §7 — including the two values inherited
  from the current runtime, which must carry their evidence label;
* ANY load failure (missing file, bad JSON, missing key, wrong type, wrong
  ``policy_version``) raises ``NewsPolicyLoadError`` — there is no fallback
  policy and no implicit default, so a broken config can never be read as a
  working one (B4, fail-closed);
* no test here accepts an optimistic read (a policy that loads while a
  mandatory key is absent would be a defect, not a convenience).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from core.news_policy import (
    DEFAULT_NEWS_POLICY_FILENAME,
    HORIZON_KEYS,
    MANDATORY_KEYS,
    NEWS_POLICY_VERSION,
    HorizonDefinition,
    NewsPolicy,
    NewsPolicyError,
    NewsPolicyLoadError,
    load_news_policy,
)
from services import interest_rate_service

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "news_policy.json"

# Values of the Owner-decided table (contract §7, Owner chốt 20/09/2026).
# ``fred_refresh_hours`` is inherited from the running interest-rate service —
# pinned separately against that service's live cadence (see
# TestInheritedRuntimeValues).
OWNER_DECIDED_VALUES = {
    "rss_poll_interval_minutes": 15,
    "rss_window_hours": 24,
    "fred_refresh_hours": 6,
    "event_stale_grace_minutes": 15,
    "ingest_freshness_hours": 2,
    "ingest_runs_retention_days": 30,
    "ai_window_days": 7,
    "ai_min_items": 3,
}


def _config_data() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _probe(tmp_path: Path, data: object, name: str = "probe.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestCommittedConfigValues:
    """The committed policy file itself — the runtime source of the numbers."""

    def test_default_path_resolves_to_the_committed_config(self):
        assert DEFAULT_NEWS_POLICY_FILENAME == "news_policy.json"
        assert load_news_policy() == load_news_policy(CONFIG_PATH)

    def test_default_path_is_repo_root_anchored(self, tmp_path, monkeypatch):
        # The default path must never depend on the process CWD.
        monkeypatch.chdir(tmp_path)
        assert load_news_policy() == load_news_policy(CONFIG_PATH)

    @pytest.mark.parametrize(
        ("key", "expected"), sorted(OWNER_DECIDED_VALUES.items())
    )
    def test_file_and_loader_pin_the_owner_decided_value(self, key, expected):
        assert _config_data()[key] == expected
        assert getattr(load_news_policy(), key) == expected

    def test_policy_version_is_the_locked_machine_read_key(self):
        assert _config_data()["policy_version"] == NEWS_POLICY_VERSION
        assert load_news_policy().policy_version == NEWS_POLICY_VERSION

    def test_every_contract_key_is_present(self):
        data = _config_data()
        for key in MANDATORY_KEYS:
            assert key in data, f"contract §7 key {key!r} must be in the policy file"

    def test_ai_horizons_pin_the_three_owner_definitions(self):
        # §7: ngắn = trong ngày–3 ngày; trung = 1–4 tuần; dài = 1–6 tháng.
        # Each span keeps the unit the Owner wrote it in (no day conversion).
        horizons = load_news_policy().ai_horizons
        assert set(horizons) == set(HORIZON_KEYS)
        assert horizons["short"] == HorizonDefinition(
            unit="day", min_value=0, max_value=3
        )
        assert horizons["mid"] == HorizonDefinition(
            unit="week", min_value=1, max_value=4
        )
        assert horizons["long"] == HorizonDefinition(
            unit="month", min_value=1, max_value=6
        )

    def test_mandatory_key_set_matches_the_contract_table(self):
        # Guard against a §7 key being dropped from the loader's mandatory set:
        # the file's non-marker keys are exactly the mandatory set.
        file_keys = {key for key in _config_data() if not key.startswith("_")}
        assert MANDATORY_KEYS == file_keys


class TestInheritedRuntimeValues:
    """Values inherited from the current runtime carry an evidence label (B5/R4)."""

    def test_fred_refresh_hours_matches_the_running_service_cadence(self):
        # Evidence: services/interest_rate_service.py:42
        # ``_CACHE_TTL = timedelta(hours=6)  # cập nhật tối đa 4 lần/ngày``
        # (confirmed in docs/macro/macro_score_architecture.md §12: TTL 6 giờ).
        inherited_hours = int(
            interest_rate_service._CACHE_TTL.total_seconds() // 3600
        )
        assert load_news_policy().fred_refresh_hours == inherited_hours

    @pytest.mark.parametrize("key", ("rss_window_hours", "fred_refresh_hours"))
    def test_inherited_values_carry_the_evidence_label(self, key):
        provenance = _config_data()["_provenance"]
        assert "kế thừa runtime hiện hành (bằng chứng: đang chạy)" in provenance[key]


class TestFailClosedLoad:
    """Every broken config raises a typed error — never a silent default (B4)."""

    def test_missing_file_raises_load_error(self, tmp_path):
        missing = tmp_path / "does-not-exist.json"
        with pytest.raises(NewsPolicyLoadError) as excinfo:
            load_news_policy(missing)
        assert str(missing) in excinfo.value.path

    def test_invalid_json_raises_load_error(self, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{ not json", encoding="utf-8")
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(broken)

    def test_non_object_root_raises_load_error(self, tmp_path):
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, [1, 2, 3]))

    def test_wrong_policy_version_raises_load_error(self, tmp_path):
        data = _config_data()
        data["policy_version"] = "news-policy-v2"
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    @pytest.mark.parametrize("key", sorted(MANDATORY_KEYS))
    def test_missing_key_raises_load_error(self, tmp_path, key):
        data = _config_data()
        del data[key]
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    @pytest.mark.parametrize("key", sorted(MANDATORY_KEYS))
    def test_null_value_raises_load_error(self, tmp_path, key):
        data = _config_data()
        data[key] = None
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_empty_object_raises_load_error(self, tmp_path):
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, {}))

    def test_load_error_is_a_news_policy_error(self):
        assert issubclass(NewsPolicyLoadError, NewsPolicyError)

    def test_wrong_type_value_raises_load_error(self, tmp_path):
        data = _config_data()
        data["rss_poll_interval_minutes"] = "15"
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    @pytest.mark.parametrize("value", [0, -1, 1.5, True])
    def test_non_positive_or_non_integer_raises_load_error(self, tmp_path, value):
        data = _config_data()
        data["ai_min_items"] = value
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_unknown_key_raises_load_error(self, tmp_path):
        data = _config_data()
        data["rss_poll_interval_minute"] = 15  # typo of a real key
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_governance_markers_are_ignored(self, tmp_path):
        data = _config_data()
        data["_accepted_by_owner"] = "ignored marker"
        data["_provenance"] = {"note": "ignored marker"}
        policy = load_news_policy(_probe(tmp_path, data))
        assert policy == load_news_policy()


class TestHorizonFailClosed:
    """``ai_horizons`` must be exactly the three typed spans of the contract."""

    @pytest.mark.parametrize("key", sorted(HORIZON_KEYS))
    def test_missing_horizon_raises_load_error(self, tmp_path, key):
        data = _config_data()
        del data["ai_horizons"][key]
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_extra_horizon_raises_load_error(self, tmp_path):
        data = _config_data()
        data["ai_horizons"]["extra"] = {"unit": "day", "min": 1, "max": 2}
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    @pytest.mark.parametrize("key", ["unit", "min", "max"])
    def test_missing_horizon_field_raises_load_error(self, tmp_path, key):
        data = _config_data()
        del data["ai_horizons"]["mid"][key]
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_extra_horizon_field_raises_load_error(self, tmp_path):
        data = _config_data()
        data["ai_horizons"]["mid"]["note"] = "extra"
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_unknown_unit_raises_load_error(self, tmp_path):
        data = _config_data()
        data["ai_horizons"]["long"]["unit"] = "quarter"
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    @pytest.mark.parametrize(
        ("low", "high"), [(3, 3), (4, 3), (-1, 3), (1.5, 3)]
    )
    def test_invalid_span_bounds_raise_load_error(self, tmp_path, low, high):
        data = _config_data()
        data["ai_horizons"]["short"]["min"] = low
        data["ai_horizons"]["short"]["max"] = high
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))


class TestNoImplicitDefaults:
    """A policy cannot exist in a half-decided state (B4)."""

    def test_no_dataclass_field_carries_a_default(self):
        for field in dataclasses.fields(NewsPolicy):
            assert field.default is dataclasses.MISSING
            assert field.default_factory is dataclasses.MISSING  # type: ignore[misc]
        assert len(dataclasses.fields(NewsPolicy)) == len(MANDATORY_KEYS)

    def test_policy_instance_is_immutable(self):
        policy = load_news_policy()
        with pytest.raises(dataclasses.FrozenInstanceError):
            policy.ai_min_items = 5  # type: ignore[misc]

    def test_horizons_mapping_is_read_only(self):
        policy = load_news_policy()
        with pytest.raises(TypeError):
            policy.ai_horizons["short"] = HorizonDefinition("day", 0, 1)  # type: ignore[index]

    def test_direct_construction_needs_every_field(self):
        with pytest.raises(TypeError):
            NewsPolicy(policy_version=NEWS_POLICY_VERSION)  # type: ignore[call-arg]


class TestCoreLayerBoundary:
    """`core/` carries pure logic: no IO framework, no upstream layer (L1)."""

    def test_module_imports_nothing_from_services_or_qt(self):
        source = (
            Path(__file__).resolve().parents[1] / "core" / "news_policy.py"
        ).read_text(encoding="utf-8")
        assert "PyQt6" not in source
        assert "import services" not in source
        assert "from services" not in source
