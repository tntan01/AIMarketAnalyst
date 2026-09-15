"""Version constants shared by SMC domain modules."""

SMC_SCORER_VERSION = "smc-v2"
SMC_CONFLUENCE_VERSION = "smc-confluence-v1"

# Candidate-selection rule identity (coordinator + plan seam, tasks 92–99).  It
# is part of the cache/rule identity of compatibility spec §4.1: a change here
# invalidates a cached result instead of silently reusing the old selection.
SMC_SELECTION_VERSION = "smc-selection-v1"

# Target-only Scanner projection contract.  This does not replace or alter
# the executable canonical SMC scorer identity above.
SMC_TECHNICAL_RAW_VERSION = "smc-technical-raw-v1"
