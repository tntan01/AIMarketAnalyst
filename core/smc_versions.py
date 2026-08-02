"""Version constants shared by SMC domain and rollout modules."""

SMC_SCORER_VERSION = "smc-v2"
# Legacy zone provenance label for raw/candidate zones that have not been
# scored by the canonical scorer.  Removed in the domain cleanup step when raw
# candidates stop carrying a scorer version.
SMC_RAW_ZONE_VERSION = "smc-v1"
SMC_CONFLUENCE_VERSION = "smc-confluence-v1"
