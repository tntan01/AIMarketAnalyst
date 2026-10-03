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
    HorizonWindow,
    NewsPolicy,
    NewsPolicyError,
    NewsPolicyLoadError,
    load_news_policy,
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "news_policy.json"

# Values of the Owner-decided table (contract §7, Owner chốt 20/09/2026).
# ``fred_refresh_hours`` được kế thừa từ interest-rate service lúc chốt; service
# đó đã xóa ở ca đấu nối (b) — 6h nay là giá trị Owner-decided đứng độc lập,
# provenance lịch sử nằm ở ``_provenance`` của config.
OWNER_DECIDED_VALUES = {
    "rss_poll_interval_minutes": 15,
    "rss_window_hours": 24,
    "fred_refresh_hours": 6,
    "bond_yield_refresh_hours": 6,
    "event_stale_grace_minutes": 15,
    "ingest_freshness_hours": 2,
    "event_freshness_hours": 24,
    "event_coverage_hours": 24,
    "ingest_runs_retention_days": 30,
    "ai_window_days": 7,
    "ai_long_window_max_rows": 50,
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

    def test_ai_horizon_windows_pin_the_three_owner_day_spans(self):
        # §7 (đợt 6): short 7 / mid 42 / long 180 ngày (Owner chốt 29/09/2026).
        windows = load_news_policy().ai_horizon_windows
        assert set(windows) == set(HORIZON_KEYS)
        assert windows["short"] == HorizonWindow(days=7)
        assert windows["mid"] == HorizonWindow(days=42)
        assert windows["long"] == HorizonWindow(days=180)

    def test_horizon_windows_and_max_rows_carry_their_owner_provenance(self):
        provenance = _config_data()["_provenance"]
        assert "Owner chốt đợt 6" in provenance["ai_horizon_windows"]
        assert "mid 42" in provenance["ai_horizon_windows"]
        assert "long 180" in provenance["ai_horizon_windows"]
        assert "Owner chốt đợt 6" in provenance["ai_long_window_max_rows"]

    def test_mandatory_key_set_matches_the_contract_table(self):
        # Guard against a §7 key being dropped from the loader's mandatory set:
        # the file's non-marker keys are exactly the mandatory set.
        file_keys = {key for key in _config_data() if not key.startswith("_")}
        assert MANDATORY_KEYS == file_keys


class TestInheritedRuntimeValues:
    """Values inherited from the current runtime carry an evidence label (B5/R4)."""

    @pytest.mark.parametrize("key", ("rss_window_hours", "fred_refresh_hours"))
    def test_inherited_values_carry_the_evidence_label(self, key):
        provenance = _config_data()["_provenance"]
        assert "kế thừa runtime hiện hành (bằng chứng: đang chạy)" in provenance[key]

    def test_bond_yield_refresh_hours_equals_fred_refresh_hours(self):
        # B5 (đợt 5): the new key is the value of ``fred_refresh_hours`` --
        # no new number is fabricated (Owner chốt 28/09/2026, contract §7).
        policy = load_news_policy()
        assert policy.bond_yield_refresh_hours == policy.fred_refresh_hours

    def test_bond_yield_refresh_hours_carries_its_provenance_note(self):
        provenance = _config_data()["_provenance"]
        assert "fred_refresh_hours" in provenance["bond_yield_refresh_hours"]
        assert "Owner chốt đợt 5" in provenance["bond_yield_refresh_hours"]

    @pytest.mark.parametrize("key", ("event_freshness_hours", "event_coverage_hours"))
    def test_event_freshness_keys_carry_the_owner_provenance(self, key):
        # Phương án 3 (tuổi HOẶC độ phủ) — Owner chốt 03/10/2026.
        provenance = _config_data()["_provenance"]
        assert "Owner chốt 03/10/2026" in provenance[key]
        assert "phương án 3" in provenance[key]
        assert "dán tay" in provenance[key]

    def test_event_freshness_keys_are_loaded_as_positive_int_hours(self):
        policy = load_news_policy()

        assert policy.event_freshness_hours == 24
        assert policy.event_coverage_hours == 24
        # Không dùng chung nhịp RSS (2h) — lý do tồn tại của 2 khóa này.
        assert policy.event_freshness_hours != policy.ingest_freshness_hours


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


class TestHorizonWindowFailClosed:
    """``ai_horizon_windows`` must be exactly the three positive day spans of the
    contract, and ``ai_long_window_max_rows`` a positive int (đợt 6, fail-closed)."""

    @pytest.mark.parametrize("key", sorted(HORIZON_KEYS))
    def test_missing_window_raises_load_error(self, tmp_path, key):
        data = _config_data()
        del data["ai_horizon_windows"][key]
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_extra_window_raises_load_error(self, tmp_path):
        data = _config_data()
        data["ai_horizon_windows"]["extra"] = {"days": 1}
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    @pytest.mark.parametrize("key", sorted(HORIZON_KEYS))
    def test_missing_days_raises_load_error(self, tmp_path, key):
        data = _config_data()
        del data["ai_horizon_windows"][key]["days"]
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_extra_window_field_raises_load_error(self, tmp_path):
        data = _config_data()
        data["ai_horizon_windows"]["mid"]["note"] = "extra"
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    @pytest.mark.parametrize("value", [0, -1, 1.5, True, "7", None])
    def test_invalid_days_raise_load_error(self, tmp_path, value):
        data = _config_data()
        data["ai_horizon_windows"]["short"]["days"] = value
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    def test_non_object_window_raises_load_error(self, tmp_path):
        data = _config_data()
        data["ai_horizon_windows"]["short"] = 7
        with pytest.raises(NewsPolicyLoadError):
            load_news_policy(_probe(tmp_path, data))

    @pytest.mark.parametrize("value", [0, -1, 1.5, True, "50", None])
    def test_non_positive_long_window_max_rows_raises_load_error(self, tmp_path, value):
        data = _config_data()
        data["ai_long_window_max_rows"] = value
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

    def test_horizon_windows_mapping_is_read_only(self):
        policy = load_news_policy()
        with pytest.raises(TypeError):
            policy.ai_horizon_windows["short"] = HorizonWindow(1)  # type: ignore[index]

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
