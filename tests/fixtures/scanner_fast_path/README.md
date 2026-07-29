# Scanner fast-path offline corpus

`corpus.json` holds deterministic candle recipes and `full-oracles.json` holds
the normalized baseline result from the unmodified full analysis route. The
corpus never contacts MT5, a news provider, an AI provider, or an order API.

The oracle intentionally excludes volatile values such as result timestamps
and scan IDs. It retains the values needed by later fast-path A/B checks:

- raw SMC candidate counts for H4/H1 and all four families;
- selected canonical zone IDs by side;
- scenario type and entry status;
- scanner candidate status and selected side;
- requested/effective SMC policy mode; and
- baseline elapsed milliseconds, recorded for diagnostics only (never a timing assertion).

Refreshes must be deliberate: regenerate the normalized result from the same
recipe/request/config, review the diff, and update the oracle only when the
full-route behavior change is intended.
