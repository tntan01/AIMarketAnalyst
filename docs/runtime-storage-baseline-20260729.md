# Runtime storage baseline — 2026-07-29

Captured before runtime-storage remediation. No scanner artifacts were moved or
deleted during this baseline capture.

## Reproduce

```powershell
python tools/runtime_storage_report.py --dry-run --top-files 10 --recent-days 7
```

## Result

Collected at `2026-07-29T11:59:56Z` from `%APPDATA%\ai-market-analyst`:

| Category | Size | Files |
| --- | ---: | ---: |
| scanner_analysis | 33.81 GiB | 14,560 |
| scanner_snapshots | 5.26 GiB | 563 |
| logs | 2.86 GiB | 2 |
| backtests | 154.70 MiB | 11 |
| other runtime data | 3.67 MiB | 10 |
| **Total** | **42.08 GiB** | **15,146** |

The report found no unreadable entries. The baseline is intentionally measured
before the auto-scan, retention, and log-rotation changes planned in later
phases.
