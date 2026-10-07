# SD-C3 — Phân tích corpus SMC demote

Sinh tự động từ `analysis.json` (số chỉ để đọc; kết luận ở SD-C4).

## Regime

| regime | count | fraction |
|---|---:|---:|
| trending_up | 1235 | 0.618 |
| trending_down | 632 | 0.316 |
| ranging | 130 | 0.065 |
| volatile | 0 | 0.000 |
| unknown | 0 | 0.000 |

## Component discrimination (all)

| component | n | spearman_fwd_8h | spearman_fwd_24h | auc_fwd_24h_pos |
|---|---:|---:|---:|---:|
| trend | 3994 | 0.039 | 0.011 | 0.515 |
| momentum | 3994 | -0.040 | -0.001 | 0.500 |
| location | 3994 | 0.026 | -0.011 | 0.493 |
| smc_raw | 3741 | -0.023 | 0.009 | 0.503 |
| quality_score | 3741 | -0.023 | 0.008 | 0.502 |

## Side selection

| metric | current | no_smc |
|---|---:|---:|
| mean_fwd_24h | -0.091 | -0.091 |
| mean_fwd_8h | 0.035 | 0.040 |
| hit_rate | 0.509 | 0.514 |
| median_gap | 22.000 | 27.000 |
| gap_ok_count | 1598 | 1650 |
| gap_ok_mean_fwd_24h | -0.075 | -0.100 |
| gap_ok_hit_rate | 0.513 | 0.516 |

- Q4(1) diff = -0.000, CI95 = [-0.090, 0.086], pass = False
- changed_side = 91

## SMC TP/SL

| tp_sl | buy | sell | total |
|---|---:|---:|---:|
| tp_first | 42 | 54 | 96 |
| sl_first | 192 | 206 | 398 |
| unresolved | 88 | 117 | 205 |
| not_filled | 327 | 300 | 627 |
| plan_invalid | 0 | 0 | 0 |
| None | 1348 | 1320 | 2668 |

- Q4(2) auc = 0.467, CI95 = [0.407, 0.527], n_resolved = 494, pass = False

## Q6 evidence mapping

| bucket | count |
|---|---:|
| None | 253 |
| 0 | 569 |
| >0 | 3172 |

## Changed-side rows

| symbol | cutoff | regime | side_current | side_no_smc | buy_cur | sell_cur | buy_ns | sell_ns |
|---|---|---|---|---|---:|---:|---:|---:|
| AUD/CAD | 2026-07-23T20:00:00+00:00 | trending_up | buy | sell | 36 | 34 | 28 | 29 |
| AUD/CHF | 2026-09-09T20:00:00+00:00 | trending_up | buy | sell | 48 | 47 | 44 | 47 |
| AUD/JPY | 2026-07-20T20:00:00+00:00 | trending_up | buy | sell | 42 | 41 | 40 | 41 |
| AUD/JPY | 2026-08-24T12:00:00+00:00 | trending_up | sell | buy | 46 | 47 | 50 | 45 |
| AUD/JPY | 2026-09-16T04:00:00+00:00 | trending_up | buy | sell | 41 | 40 | 39 | 43 |
| AUD/JPY | 2026-09-29T12:00:00+00:00 | trending_up | sell | buy | 41 | 47 | 51 | 47 |
| AUD/NZD | 2026-07-09T04:00:00+00:00 | trending_up | sell | buy | 39 | 40 | 49 | 39 |
| AUD/NZD | 2026-07-08T20:00:00+00:00 | trending_up | buy | sell | 37 | 34 | 31 | 33 |
| AUD/NZD | 2026-07-13T12:00:00+00:00 | trending_up | sell | buy | 41 | 46 | 51 | 39 |
| AUD/NZD | 2026-08-06T12:00:00+00:00 | trending_up | sell | buy | 32 | 34 | 30 | 28 |
| AUD/NZD | 2026-08-19T20:00:00+00:00 | trending_up | sell | buy | 40 | 44 | 50 | 39 |
| AUD/NZD | 2026-08-20T04:00:00+00:00 | trending_up | sell | buy | 30 | 40 | 37 | 35 |
| AUD/NZD | 2026-09-21T20:00:00+00:00 | trending_up | buy | sell | 39 | 38 | 36 | 38 |
| AUD/NZD | 2026-09-30T20:00:00+00:00 | trending_up | sell | buy | 32 | 36 | 40 | 35 |
| AUD/USD | 2026-07-31T12:00:00+00:00 | trending_up | buy | sell | 49 | 44 | 40 | 41 |
| AUD/USD | 2026-09-01T04:00:00+00:00 | trending_up | buy | sell | 49 | 48 | 44 | 45 |
| AUD/USD | 2026-09-24T20:00:00+00:00 | trending_up | sell | buy | 26 | 32 | 32 | 28 |
| BTC/USD | 2026-08-07T20:00:00+00:00 | trending_down | buy | sell | 44 | 41 | 39 | 51 |
| BTC/USD | 2026-08-28T20:00:00+00:00 | trending_down | sell | buy | 36 | 43 | 45 | 39 |
| BTC/USD | 2026-08-29T04:00:00+00:00 | trending_down | sell | buy | 36 | 40 | 45 | 39 |
| BTC/USD | 2026-09-10T04:00:00+00:00 | ranging | sell | buy | 18 | 32 | 29 | 17 |
| BTC/USD | 2026-09-16T04:00:00+00:00 | ranging | sell | buy | 21 | 28 | 35 | 17 |
| CAD/CHF | 2026-07-24T04:00:00+00:00 | trending_down | buy | sell | 42 | 36 | 40 | 45 |
| CAD/CHF | 2026-07-27T04:00:00+00:00 | ranging | buy | sell | 23 | 13 | 7 | 22 |
| CHF/JPY | 2026-07-13T12:00:00+00:00 | trending_up | sell | buy | 33 | 40 | 34 | 34 |
| CHF/JPY | 2026-07-20T20:00:00+00:00 | trending_up | sell | buy | 47 | 49 | 51 | 43 |
| CHF/JPY | 2026-08-26T04:00:00+00:00 | ranging | sell | buy | 28 | 30 | 46 | 20 |
| EUR/AUD | 2026-09-08T12:00:00+00:00 | trending_down | sell | buy | 44 | 45 | 45 | 40 |
| EUR/AUD | 2026-09-30T20:00:00+00:00 | trending_down | buy | sell | 37 | 29 | 33 | 36 |
| EUR/CAD | 2026-07-15T04:00:00+00:00 | trending_up | sell | buy | 37 | 38 | 46 | 34 |
| EUR/CAD | 2026-08-03T12:00:00+00:00 | trending_up | buy | sell | 42 | 36 | 40 | 45 |
| EUR/CAD | 2026-08-11T04:00:00+00:00 | trending_up | sell | buy | 39 | 43 | 49 | 40 |
| EUR/CAD | 2026-08-13T20:00:00+00:00 | trending_up | sell | buy | 36 | 39 | 45 | 34 |
| EUR/CAD | 2026-08-28T20:00:00+00:00 | trending_up | buy | sell | 31 | 28 | 26 | 29 |
| EUR/CAD | 2026-09-08T12:00:00+00:00 | ranging | sell | buy | 22 | 33 | 36 | 15 |
| EUR/CHF | 2026-07-28T12:00:00+00:00 | trending_up | buy | sell | 44 | 33 | 40 | 41 |
| EUR/CHF | 2026-08-12T12:00:00+00:00 | trending_up | buy | sell | 42 | 41 | 40 | 51 |
| EUR/GBP | 2026-08-05T04:00:00+00:00 | trending_down | buy | sell | 45 | 41 | 43 | 51 |
| EUR/JPY | 2026-07-17T20:00:00+00:00 | trending_up | buy | sell | 38 | 37 | 36 | 38 |
| EUR/JPY | 2026-09-02T12:00:00+00:00 | trending_up | sell | buy | 32 | 34 | 40 | 29 |
| EUR/NZD | 2026-07-13T12:00:00+00:00 | trending_up | sell | buy | 34 | 38 | 43 | 36 |
| EUR/NZD | 2026-07-27T04:00:00+00:00 | trending_down | buy | sell | 40 | 38 | 34 | 40 |
| EUR/NZD | 2026-07-29T20:00:00+00:00 | trending_down | buy | sell | 39 | 32 | 39 | 40 |
| EUR/USD | 2026-07-24T04:00:00+00:00 | trending_down | sell | buy | 41 | 44 | 41 | 40 |
| EUR/USD | 2026-09-15T20:00:00+00:00 | ranging | sell | buy | 17 | 25 | 29 | 11 |
| GBP/AUD | 2026-07-09T04:00:00+00:00 | trending_down | buy | sell | 38 | 30 | 29 | 37 |
| GBP/AUD | 2026-07-17T20:00:00+00:00 | trending_down | sell | buy | 37 | 41 | 36 | 33 |
| GBP/AUD | 2026-07-29T20:00:00+00:00 | trending_down | buy | sell | 28 | 21 | 25 | 26 |
| GBP/CAD | 2026-07-23T20:00:00+00:00 | trending_up | sell | buy | 29 | 30 | 36 | 23 |
| GBP/CAD | 2026-09-03T20:00:00+00:00 | trending_up | sell | buy | 33 | 39 | 34 | 30 |
| GBP/JPY | 2026-09-18T20:00:00+00:00 | ranging | sell | buy | 27 | 28 | 18 | 12 |
| GBP/NZD | 2026-07-14T20:00:00+00:00 | trending_up | sell | buy | 29 | 31 | 36 | 24 |
| GBP/NZD | 2026-07-29T20:00:00+00:00 | trending_up | sell | buy | 47 | 49 | 59 | 41 |
| GBP/NZD | 2026-07-31T12:00:00+00:00 | trending_up | sell | buy | 37 | 43 | 47 | 40 |
| GBP/NZD | 2026-07-30T04:00:00+00:00 | trending_up | sell | buy | 35 | 51 | 44 | 44 |
| GBP/NZD | 2026-08-04T20:00:00+00:00 | trending_up | sell | buy | 31 | 38 | 39 | 39 |
| GBP/NZD | 2026-08-05T04:00:00+00:00 | trending_up | buy | sell | 44 | 44 | 39 | 40 |
| GBP/NZD | 2026-09-04T04:00:00+00:00 | ranging | sell | buy | 25 | 32 | 24 | 22 |
| GBP/NZD | 2026-09-17T12:00:00+00:00 | trending_up | sell | buy | 37 | 38 | 36 | 33 |
| GBP/USD | 2026-07-08T20:00:00+00:00 | trending_down | buy | sell | 36 | 36 | 34 | 45 |
| GBP/USD | 2026-08-07T20:00:00+00:00 | trending_down | buy | sell | 44 | 38 | 39 | 47 |
| GBP/USD | 2026-09-22T04:00:00+00:00 | trending_up | sell | buy | 32 | 35 | 32 | 31 |
| NZD/CAD | 2026-07-14T20:00:00+00:00 | trending_up | sell | buy | 45 | 46 | 45 | 41 |
| NZD/CAD | 2026-09-09T20:00:00+00:00 | trending_up | buy | sell | 43 | 42 | 39 | 41 |
| NZD/CAD | 2026-09-14T12:00:00+00:00 | trending_up | sell | buy | 39 | 43 | 41 | 39 |
| NZD/CHF | 2026-07-23T20:00:00+00:00 | trending_up | sell | buy | 32 | 34 | 40 | 33 |
| NZD/CHF | 2026-09-02T12:00:00+00:00 | trending_up | sell | buy | 39 | 40 | 36 | 36 |
| NZD/CHF | 2026-09-15T20:00:00+00:00 | trending_up | sell | buy | 39 | 43 | 49 | 35 |
| NZD/JPY | 2026-07-20T20:00:00+00:00 | trending_up | sell | buy | 37 | 38 | 36 | 36 |
| NZD/JPY | 2026-07-31T12:00:00+00:00 | trending_up | sell | buy | 29 | 37 | 36 | 36 |
| NZD/JPY | 2026-08-03T12:00:00+00:00 | trending_up | sell | buy | 36 | 40 | 45 | 36 |
| NZD/JPY | 2026-08-12T12:00:00+00:00 | trending_up | sell | buy | 38 | 40 | 36 | 35 |
| NZD/USD | 2026-07-13T12:00:00+00:00 | trending_down | buy | sell | 32 | 30 | 29 | 37 |
| NZD/USD | 2026-07-15T04:00:00+00:00 | trending_down | buy | sell | 31 | 30 | 25 | 26 |
| NZD/USD | 2026-07-20T20:00:00+00:00 | trending_down | buy | sell | 45 | 41 | 36 | 41 |
| NZD/USD | 2026-07-21T04:00:00+00:00 | trending_down | buy | sell | 39 | 36 | 34 | 45 |
| NZD/USD | 2026-08-03T12:00:00+00:00 | trending_down | buy | sell | 39 | 39 | 34 | 36 |
| NZD/USD | 2026-08-07T20:00:00+00:00 | trending_down | buy | sell | 42 | 41 | 39 | 41 |
| USD/CAD | 2026-07-14T20:00:00+00:00 | trending_up | sell | buy | 29 | 31 | 36 | 25 |
| USD/CAD | 2026-09-04T04:00:00+00:00 | trending_up | sell | buy | 29 | 31 | 36 | 24 |
| USD/CHF | 2026-09-16T04:00:00+00:00 | trending_up | sell | buy | 48 | 50 | 50 | 44 |
| USD/JPY | 2026-07-21T04:00:00+00:00 | trending_up | buy | sell | 40 | 34 | 40 | 42 |
| USD/JPY | 2026-08-12T12:00:00+00:00 | trending_up | buy | sell | 40 | 34 | 40 | 43 |
| USD/JPY | 2026-08-14T04:00:00+00:00 | trending_up | buy | sell | 46 | 46 | 46 | 58 |
| USD/JPY | 2026-09-09T20:00:00+00:00 | ranging | sell | buy | 23 | 25 | 25 | 7 |
| USD/JPY | 2026-09-10T04:00:00+00:00 | ranging | sell | buy | 28 | 35 | 30 | 28 |
| USD/JPY | 2026-09-16T04:00:00+00:00 | ranging | buy | sell | 27 | 10 | 14 | 17 |
| USD/JPY | 2026-09-29T12:00:00+00:00 | ranging | sell | buy | 40 | 41 | 66 | 25 |
| XAG/USD | 2026-08-07T20:00:00+00:00 | trending_down | buy | sell | 39 | 36 | 30 | 34 |
| XAG/USD | 2026-08-10T20:00:00+00:00 | trending_down | buy | sell | 33 | 21 | 25 | 26 |
| XAU/USD | 2026-08-17T04:00:00+00:00 | trending_down | buy | sell | 45 | 44 | 38 | 55 |
