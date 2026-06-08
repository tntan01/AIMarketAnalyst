from core.signal_engine import DYNAMIC_WEIGHTS


def test_macro_weight_reduced():
    """Phase 4 Prompt 1: macro weight khong vuot qua 20 o moi regime."""
    for regime, weights in DYNAMIC_WEIGHTS.items():
        assert weights.get("macro", 0) <= 20, f"{regime}: macro={weights.get('macro', 0)} > 20"


def test_dynamic_weights_total_reasonable():
    """Tong trong so moi regime nam trong khoang 95-105."""
    for regime, weights in DYNAMIC_WEIGHTS.items():
        total = sum(weights.values())
        assert 95 <= total <= 105, f"{regime}: total={total} nam ngoai [95, 105]"


def test_required_keys_present():
    """Cac key chinh trend/momentum/location/smc/risk/macro van ton tai."""
    required = {"trend", "momentum", "location", "smc", "risk", "macro"}
    for regime, weights in DYNAMIC_WEIGHTS.items():
        assert required.issubset(weights.keys()), f"{regime}: thieu key, hien co {set(weights.keys())}"


def test_no_extra_keys():
    """Khong co key la trong DYNAMIC_WEIGHTS."""
    allowed = {"trend", "momentum", "location", "smc", "risk", "macro"}
    for regime, weights in DYNAMIC_WEIGHTS.items():
        extra = set(weights.keys()) - allowed
        assert not extra, f"{regime}: key du thua {extra}"


def test_all_regimes_present():
    """Nam regime co ban deu ton tai."""
    assert "trending_up" in DYNAMIC_WEIGHTS
    assert "trending_down" in DYNAMIC_WEIGHTS
    assert "ranging" in DYNAMIC_WEIGHTS
    assert "volatile" in DYNAMIC_WEIGHTS
    assert "unknown" in DYNAMIC_WEIGHTS
