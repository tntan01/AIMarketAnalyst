# Báo cáo CP1 — SMC demote (Giai đoạn 1)

> Báo cáo sinh tự động bởi `scripts/smc_demote_report.py` từ `analysis.json` (rows_sha256 `sha256:0c41acbcece0ce3c61776986c37cf3975f31fd494db369f7cb4b68a03990f5e2`). Không chứa khuyến nghị; quyết định thuộc TL/Owner tại CP1.

## 1. Kết quả quy tắc Q4

| Điều kiện | Chỉ số | Giá trị | CI95 | Ngưỡng | Kết quả |
|---|---|---:|---|---|---|
| (1) Chọn side | mean fwd 24h (ATR) side chọn bởi 3 thành phần − 4 thành phần, trên pair cả hai chọn được | -0.000 | [-0.090, 0.086] | cận dưới ≥ −0,05 | KHÔNG ĐẠT |
| (2) SMC phân biệt TP/SL | AUC `quality_score`, n resolved = 494 (TP 96 / SL 398) | 0.467 | [0.407, 0.527] | AUC ≥ 0,55 và cận dưới > 0,5; n ≥ 200 | KHÔNG ĐẠT |

**Kết quả cơ học của quy tắc Q4:** Không đạt điều kiện (1) → giữ nguyên TechnicalScore 4 thành phần; TL cân nhắc phương án B.

**Độ rộng khoảng tin cậy (1):** half_width = 0.088, need = 0.050, factor = 3.2. Ước tính thô: nếu chênh lệch giữ nguyên, cần khoảng 3.2 lần số pair hiện tại để cận dưới CI95 đạt −0,05 (giả định độ rộng CI tỷ lệ 1/√n).

## 2. Dữ liệu

- `fetched_at`: 2026-10-07T06:44:42.334894+00:00
- Symbol: 31 ok / 31 tổng (manifest)
- `min_rr`: 2.000
- Tổng cutoff: 2010
- Cutoff theo giờ (UTC): 4h = 660, 12h = 690, 20h = 660
- Cutoff theo tháng: 2026-07 = 595, 2026-08 = 661, 2026-09 = 690, 2026-10 = 64
- Cutoff bị bỏ theo lý do: insufficient_history = 0, insufficient_tail = 93, market_closed = 780
- Rows: 1997
- Errors: 13 (ValueError: 13)
- Số cụm ngày: 90
- `bootstrap_n`: 2000, `seed`: 20261007
- check-scorer: 100 side, 0 mismatch

| regime | rows | fraction |
|---|---:|---:|
| trending_up | 1235 | 61.8% |
| trending_down | 632 | 31.6% |
| ranging | 130 | 6.5% |
| volatile | 0 | 0.0% |
| unknown | 0 | 0.0% |

## 3. Chọn side: 4 thành phần (hiện tại) vs 3 thành phần (Q5)

- Số pair: both = 1793, only_no_smc = 204, neither = 0, changed_side = 91

| metric | current | no_smc |
|---|---:|---:|
| mean_fwd_24h | -0.091 | -0.091 |
| mean_fwd_8h | 0.035 | 0.040 |
| hit_rate | 0.509 | 0.514 |
| median_gap | 22.000 | 27.000 |
| gap_ok_count | 1598 | 1650 |
| gap_ok_mean_fwd_24h | -0.075 | -0.100 |
| gap_ok_hit_rate | 0.513 | 0.516 |

- `gap_ok` chỉ ở current: 63; chỉ ở no_smc: 115
- Chênh lệch fwd 8h (mô tả, không thuộc Q4): diff = 0.005, CI95 = [-0.029, 0.039]
- `only_no_smc_mean_fwd_24h` = -0.250. Pair mà biến thể hiện tại không chấm được vì SMC data_unavailable ở ít nhất một side (fail-closed).

| regime | both | changed | mean_diff_fwd_24h |
|---|---:|---:|---:|
| trending_up | 1130 | 55 | -0.011 |
| trending_down | 549 | 24 | 0.050 |
| ranging | 114 | 12 | -0.142 |
| volatile | 0 | 0 | — |
| unknown | 0 | 0 | — |

## 4. Khả năng phân biệt từng thành phần

| component | n | spearman_fwd_8h | spearman_fwd_24h | auc_fwd_24h_pos |
|---|---:|---:|---:|---:|
| trend | 3994 | 0.039 | 0.011 | 0.515 |
| momentum | 3994 | -0.040 | -0.001 | 0.500 |
| location | 3994 | 0.026 | -0.011 | 0.493 |
| smc_raw | 3741 | -0.023 | 0.009 | 0.503 |
| quality_score | 3741 | -0.023 | 0.008 | 0.502 |

### Bucket `trend` (`fwd_24h_atr`)

| bucket | n | hit_rate | mean_fwd_24h |
|---|---:|---:|---:|
| 0-8 | 1603 | 48.7% | 0.131 |
| 17-25 | 1449 | 50.7% | -0.222 |
| 9-16 | 942 | 50.6% | 0.118 |

### Bucket `momentum` (`fwd_24h_atr`)

| bucket | n | hit_rate | mean_fwd_24h |
|---|---:|---:|---:|
| 0-6 | 1992 | 49.1% | -0.087 |
| 14-20 | 775 | 48.4% | -0.143 |
| 7-13 | 1227 | 52.1% | 0.231 |

### Bucket `location` (`fwd_24h_atr`)

| bucket | n | hit_rate | mean_fwd_24h |
|---|---:|---:|---:|
| 0 | 2301 | 50.0% | 0.015 |
| 1-8 | 499 | 53.1% | 0.263 |
| 17-25 | 829 | 47.8% | -0.139 |
| 9-16 | 365 | 49.6% | -0.139 |

### Bucket `smc_raw` (`fwd_24h_atr`)

| bucket | n | hit_rate | mean_fwd_24h |
|---|---:|---:|---:|
| 0 | 569 | 50.1% | 0.057 |
| 1-5 | 260 | 45.0% | -0.405 |
| 6-7 | 1058 | 50.0% | -0.048 |
| 8 | 847 | 51.0% | 0.002 |
| 9-15 | 1007 | 50.4% | 0.108 |

Chi tiết theo regime: xem `reports/scanner/smc_demote/analysis.md`.

## 5. SMC trên side có plan (TP/SL)

| tp_sl | count |
|---|---:|
| tp_first | 96 |
| sl_first | 398 |
| unresolved | 205 |
| not_filled | 627 |
| plan_invalid | 0 |
| None | 2668 |

| component | AUC | CI95 |
|---|---:|---|
| quality_score | 0.467 | [0.407, 0.527] |
| quality_raw | 0.462 | [0.401, 0.523] |
| b | 0.494 | [0.438, 0.547] |
| q | 0.474 | [0.422, 0.535] |
| l | 0.491 | [0.450, 0.535] |
| c | 0.477 | [0.419, 0.532] |

### Tỷ lệ `tp_first` theo bucket `quality_raw`

| bucket | n | tp_first_rate |
|---|---:|---:|
| 0 | 0 | — |
| 1-5 | 74 | 24.3% |
| 6-7 | 190 | 20.0% |
| 8 | 130 | 20.0% |
| 9-15 | 100 | 14.0% |

### Tỷ lệ `tp_first` theo `readiness_status`

| readiness_status | n | tp_first_rate |
|---|---:|---:|
| READY_NOW | 4 | 25.0% |
| WAITING_CONFIRMATION | 215 | 18.1% |
| WATCH_ZONE | 275 | 20.4% |

- Tỷ lệ `tp_first` chung = 19.4%
- Với R:R tối thiểu 2.000, tỷ lệ TP-trước hòa vốn (bỏ qua chi phí) là 1/(1+R:R) = 33.3%.

| nhãn | mean_mfe_r | mean_mae_r |
|---|---:|---:|
| tp_first | 2.604 | 0.414 |
| sl_first | 0.774 | 1.260 |

## 6. Ánh xạ Q6 (SMC → evidence_score) — dữ kiện

| bucket | count |
|---|---:|
| None | 253 |
| 0 | 569 |
| >0 | 3172 |

- Phân phối giá trị >0: min = 18.000, p25 = 45.000, median = 52.000, p75 = 59.000, max = 89.000

| smc_state | count |
|---|---:|
| data_unavailable | 253 |
| evaluated | 1326 |
| out_of_strategy | 569 |
| watch_zone | 1846 |

## 7. Giới hạn

1. Quy mô nhỏ: 1997 snapshot, 90 ngày, ~3 tháng; regime gần như chỉ có trending (ranging 130, volatile 0).
2. Không tính spread/chi phí (Q9).
3. fwd 8h/24h tính theo số nến H1 (nến thứ 8/24 sau cutoff), không theo giờ đồng hồ; qua cuối tuần thì dài hơn 24 giờ.
4. TP/SL: entry là lệnh limit tại mép zone, giá khớp coi là đúng entry; nến khớp chỉ xét SL; cùng nến chạm TP và SL tính SL (STOP_FIRST); không khớp trong 48 H1 → not_filled.
5. Tỷ lệ chưa có kết quả: unresolved 205, not_filled 627 trên 1326 side có plan.
6. 13 cutoff (0.6%) lỗi pipeline SMC (ValueError: 13) bị loại khỏi phân tích.
7. Trọng số 3 thành phần là mặc định chia lại tỷ lệ (Q5), chưa tối ưu.
8. Không có bằng chứng lợi nhuận; mọi chỉ số chỉ mang tính so sánh tương đối.

## 8. Pair đổi side

| symbol | cutoff | regime | side hiện tại → mới | buy/sell (current) | buy/sell (no_smc) | smc_raw buy/sell | fwd 24h hiện tại → mới |
|---|---|---|---|---:|---:|---|---|
| AUD/CAD | 2026-07-23T20:00:00+00:00 | trending_up | buy → sell | 36/34 | 28/29 | 10/8 | 3.455 → -3.455 |
| AUD/CHF | 2026-09-09T20:00:00+00:00 | trending_up | buy → sell | 48/47 | 44/47 | 10/7 | -5.034 → 5.034 |
| AUD/JPY | 2026-07-20T20:00:00+00:00 | trending_up | buy → sell | 42/41 | 40/41 | 8/6 | 4.637 → -4.637 |
| AUD/JPY | 2026-08-24T12:00:00+00:00 | trending_up | sell → buy | 46/47 | 50/45 | 5/8 | 0.381 → -0.381 |
| AUD/JPY | 2026-09-16T04:00:00+00:00 | trending_up | buy → sell | 41/40 | 39/43 | 8/4 | 1.938 → -1.938 |
| AUD/JPY | 2026-09-29T12:00:00+00:00 | trending_up | sell → buy | 41/47 | 51/47 | 0/7 | 3.010 → -3.010 |
| AUD/NZD | 2026-07-08T20:00:00+00:00 | trending_up | buy → sell | 37/34 | 31/33 | 9/6 | -11.615 → 11.615 |
| AUD/NZD | 2026-07-09T04:00:00+00:00 | trending_up | sell → buy | 39/40 | 49/39 | 0/7 | 8.284 → -8.284 |
| AUD/NZD | 2026-07-13T12:00:00+00:00 | trending_up | sell → buy | 41/46 | 51/39 | 0/11 | 4.148 → -4.148 |
| AUD/NZD | 2026-08-06T12:00:00+00:00 | trending_up | sell → buy | 32/34 | 30/28 | 6/9 | -2.154 → 2.154 |
| AUD/NZD | 2026-08-19T20:00:00+00:00 | trending_up | sell → buy | 40/44 | 50/39 | 0/10 | 3.633 → -3.633 |
| AUD/NZD | 2026-08-20T04:00:00+00:00 | trending_up | sell → buy | 30/40 | 37/35 | 0/9 | -0.200 → 0.200 |
| AUD/NZD | 2026-09-21T20:00:00+00:00 | trending_up | buy → sell | 39/38 | 36/38 | 8/6 | -3.687 → 3.687 |
| AUD/NZD | 2026-09-30T20:00:00+00:00 | trending_up | sell → buy | 32/36 | 40/35 | 0/6 | -2.690 → 2.690 |
| AUD/USD | 2026-07-31T12:00:00+00:00 | trending_up | buy → sell | 49/44 | 40/41 | 13/8 | -1.010 → 1.010 |
| AUD/USD | 2026-09-01T04:00:00+00:00 | trending_up | buy → sell | 49/48 | 44/45 | 11/9 | -4.004 → 4.004 |
| AUD/USD | 2026-09-24T20:00:00+00:00 | trending_up | sell → buy | 26/32 | 32/28 | 0/7 | -1.090 → 1.090 |
| BTC/USD | 2026-08-07T20:00:00+00:00 | trending_down | buy → sell | 44/41 | 39/51 | 10/0 | 0.392 → -0.392 |
| BTC/USD | 2026-08-28T20:00:00+00:00 | trending_down | sell → buy | 36/43 | 45/39 | 0/9 | -0.958 → 0.958 |
| BTC/USD | 2026-08-29T04:00:00+00:00 | trending_down | sell → buy | 36/40 | 45/39 | 0/7 | -1.325 → 1.325 |
| BTC/USD | 2026-09-10T04:00:00+00:00 | ranging | sell → buy | 18/32 | 29/17 | 0/8 | 3.245 → -3.245 |
| BTC/USD | 2026-09-16T04:00:00+00:00 | ranging | sell → buy | 21/28 | 35/17 | 0/7 | -1.061 → 1.061 |
| CAD/CHF | 2026-07-24T04:00:00+00:00 | trending_down | buy → sell | 42/36 | 40/45 | 7/0 | -4.180 → 4.180 |
| CAD/CHF | 2026-07-27T04:00:00+00:00 | ranging | buy → sell | 23/13 | 7/22 | 7/0 | 2.349 → -2.349 |
| CHF/JPY | 2026-07-13T12:00:00+00:00 | trending_up | sell → buy | 33/40 | 34/34 | 5/10 | 1.883 → -1.883 |
| CHF/JPY | 2026-07-20T20:00:00+00:00 | trending_up | sell → buy | 47/49 | 51/43 | 5/11 | -1.262 → 1.262 |
| CHF/JPY | 2026-08-26T04:00:00+00:00 | ranging | sell → buy | 28/30 | 46/20 | 0/7 | 0.665 → -0.665 |
| EUR/AUD | 2026-09-08T12:00:00+00:00 | trending_down | sell → buy | 44/45 | 45/40 | 6/10 | -2.579 → 2.579 |
| EUR/AUD | 2026-09-30T20:00:00+00:00 | trending_down | buy → sell | 37/29 | 33/36 | 8/0 | -4.919 → 4.919 |
| EUR/CAD | 2026-07-15T04:00:00+00:00 | trending_up | sell → buy | 37/38 | 46/34 | 0/8 | -3.499 → 3.499 |
| EUR/CAD | 2026-08-03T12:00:00+00:00 | trending_up | buy → sell | 42/36 | 40/45 | 8/0 | 0.755 → -0.755 |
| EUR/CAD | 2026-08-11T04:00:00+00:00 | trending_up | sell → buy | 39/43 | 49/40 | 0/8 | 1.847 → -1.847 |
| EUR/CAD | 2026-08-13T20:00:00+00:00 | trending_up | sell → buy | 36/39 | 45/34 | 0/9 | 0.387 → -0.387 |
| EUR/CAD | 2026-08-28T20:00:00+00:00 | trending_up | buy → sell | 31/28 | 26/29 | 8/4 | -0.856 → 0.856 |
| EUR/CAD | 2026-09-08T12:00:00+00:00 | ranging | sell → buy | 22/33 | 36/15 | 0/9 | -0.774 → 0.774 |
| EUR/CHF | 2026-07-28T12:00:00+00:00 | trending_up | buy → sell | 44/33 | 40/41 | 9/0 | 2.843 → -2.843 |
| EUR/CHF | 2026-08-12T12:00:00+00:00 | trending_up | buy → sell | 42/41 | 40/51 | 8/0 | 0.966 → -0.966 |
| EUR/GBP | 2026-08-05T04:00:00+00:00 | trending_down | buy → sell | 45/41 | 43/51 | 8/0 | 1.800 → -1.800 |
| EUR/JPY | 2026-07-17T20:00:00+00:00 | trending_up | buy → sell | 38/37 | 36/38 | 7/5 | -2.272 → 2.272 |
| EUR/JPY | 2026-09-02T12:00:00+00:00 | trending_up | sell → buy | 32/34 | 40/29 | 0/8 | 21.268 → -21.268 |
| EUR/NZD | 2026-07-13T12:00:00+00:00 | trending_up | sell → buy | 34/38 | 43/36 | 0/7 | 4.700 → -4.700 |
| EUR/NZD | 2026-07-27T04:00:00+00:00 | trending_down | buy → sell | 40/38 | 34/40 | 10/5 | 1.299 → -1.299 |
| EUR/NZD | 2026-07-29T20:00:00+00:00 | trending_down | buy → sell | 39/32 | 39/40 | 6/0 | -5.524 → 5.524 |
| EUR/USD | 2026-07-24T04:00:00+00:00 | trending_down | sell → buy | 41/44 | 41/40 | 6/9 | -2.787 → 2.787 |
| EUR/USD | 2026-09-15T20:00:00+00:00 | ranging | sell → buy | 17/25 | 29/11 | 0/7 | 9.030 → -9.030 |
| GBP/AUD | 2026-07-09T04:00:00+00:00 | trending_down | buy → sell | 38/30 | 29/37 | 11/0 | -0.598 → 0.598 |
| GBP/AUD | 2026-07-17T20:00:00+00:00 | trending_down | sell → buy | 37/41 | 36/33 | 6/11 | 4.671 → -4.671 |
| GBP/AUD | 2026-07-29T20:00:00+00:00 | trending_down | buy → sell | 28/21 | 25/26 | 6/0 | -1.882 → 1.882 |
| GBP/CAD | 2026-07-23T20:00:00+00:00 | trending_up | sell → buy | 29/30 | 36/23 | 0/9 | -2.077 → 2.077 |
| GBP/CAD | 2026-09-03T20:00:00+00:00 | trending_up | sell → buy | 33/39 | 34/30 | 5/11 | -3.143 → 3.143 |
| GBP/JPY | 2026-09-18T20:00:00+00:00 | ranging | sell → buy | 27/28 | 18/12 | 6/8 | -1.176 → 1.176 |
| GBP/NZD | 2026-07-14T20:00:00+00:00 | trending_up | sell → buy | 29/31 | 36/24 | 0/9 | -2.975 → 2.975 |
| GBP/NZD | 2026-07-29T20:00:00+00:00 | trending_up | sell → buy | 47/49 | 59/41 | 0/12 | 4.182 → -4.182 |
| GBP/NZD | 2026-07-30T04:00:00+00:00 | trending_up | sell → buy | 35/51 | 44/44 | 0/12 | 2.327 → -2.327 |
| GBP/NZD | 2026-07-31T12:00:00+00:00 | trending_up | sell → buy | 37/43 | 47/40 | 0/8 | -1.529 → 1.529 |
| GBP/NZD | 2026-08-04T20:00:00+00:00 | trending_up | sell → buy | 31/38 | 39/39 | 0/5 | -2.607 → 2.607 |
| GBP/NZD | 2026-08-05T04:00:00+00:00 | trending_up | buy → sell | 44/44 | 39/40 | 10/9 | -1.580 → 1.580 |
| GBP/NZD | 2026-09-04T04:00:00+00:00 | ranging | sell → buy | 25/32 | 24/22 | 4/7 | -2.542 → 2.542 |
| GBP/NZD | 2026-09-17T12:00:00+00:00 | trending_up | sell → buy | 37/38 | 36/33 | 6/9 | -2.015 → 2.015 |
| GBP/USD | 2026-07-08T20:00:00+00:00 | trending_down | buy → sell | 36/36 | 34/45 | 7/0 | 0.348 → -0.348 |
| GBP/USD | 2026-08-07T20:00:00+00:00 | trending_down | buy → sell | 44/38 | 39/47 | 10/0 | 0.827 → -0.827 |
| GBP/USD | 2026-09-22T04:00:00+00:00 | trending_up | sell → buy | 32/35 | 32/31 | 5/8 | 7.254 → -7.254 |
| NZD/CAD | 2026-07-14T20:00:00+00:00 | trending_up | sell → buy | 45/46 | 45/41 | 7/10 | -4.065 → 4.065 |
| NZD/CAD | 2026-09-09T20:00:00+00:00 | trending_up | buy → sell | 43/42 | 39/41 | 9/7 | -5.262 → 5.262 |
| NZD/CAD | 2026-09-14T12:00:00+00:00 | trending_up | sell → buy | 39/43 | 41/39 | 5/9 | -0.612 → 0.612 |
| NZD/CHF | 2026-07-23T20:00:00+00:00 | trending_up | sell → buy | 32/34 | 40/33 | 0/6 | -5.115 → 5.115 |
| NZD/CHF | 2026-09-02T12:00:00+00:00 | trending_up | sell → buy | 39/40 | 36/36 | 8/8 | -0.411 → 0.411 |
| NZD/CHF | 2026-09-15T20:00:00+00:00 | trending_up | sell → buy | 39/43 | 49/35 | 0/11 | 0.428 → -0.428 |
| NZD/JPY | 2026-07-20T20:00:00+00:00 | trending_up | sell → buy | 37/38 | 36/36 | 6/7 | -1.943 → 1.943 |
| NZD/JPY | 2026-07-31T12:00:00+00:00 | trending_up | sell → buy | 29/37 | 36/36 | 0/6 | 6.399 → -6.399 |
| NZD/JPY | 2026-08-03T12:00:00+00:00 | trending_up | sell → buy | 36/40 | 45/36 | 0/8 | -1.988 → 1.988 |
| NZD/JPY | 2026-08-12T12:00:00+00:00 | trending_up | sell → buy | 38/40 | 36/35 | 7/9 | 2.304 → -2.304 |
| NZD/USD | 2026-07-13T12:00:00+00:00 | trending_down | buy → sell | 32/30 | 29/37 | 7/0 | 2.393 → -2.393 |
| NZD/USD | 2026-07-15T04:00:00+00:00 | trending_down | buy → sell | 31/30 | 25/26 | 8/7 | 3.928 → -3.928 |
| NZD/USD | 2026-07-20T20:00:00+00:00 | trending_down | buy → sell | 45/41 | 36/41 | 12/6 | -1.601 → 1.601 |
| NZD/USD | 2026-07-21T04:00:00+00:00 | trending_down | buy → sell | 39/36 | 34/45 | 9/0 | -4.310 → 4.310 |
| NZD/USD | 2026-08-03T12:00:00+00:00 | trending_down | buy → sell | 39/39 | 34/36 | 9/8 | 1.207 → -1.207 |
| NZD/USD | 2026-08-07T20:00:00+00:00 | trending_down | buy → sell | 42/41 | 39/41 | 8/6 | -1.754 → 1.754 |
| USD/CAD | 2026-07-14T20:00:00+00:00 | trending_up | sell → buy | 29/31 | 36/25 | 0/8 | 1.703 → -1.703 |
| USD/CAD | 2026-09-04T04:00:00+00:00 | trending_up | sell → buy | 29/31 | 36/24 | 0/9 | -4.876 → 4.876 |
| USD/CHF | 2026-09-16T04:00:00+00:00 | trending_up | sell → buy | 48/50 | 50/44 | 6/11 | -10.858 → 10.858 |
| USD/JPY | 2026-07-21T04:00:00+00:00 | trending_up | buy → sell | 40/34 | 40/42 | 6/0 | 8.398 → -8.398 |
| USD/JPY | 2026-08-12T12:00:00+00:00 | trending_up | buy → sell | 40/34 | 40/43 | 6/0 | 1.608 → -1.608 |
| USD/JPY | 2026-08-14T04:00:00+00:00 | trending_up | buy → sell | 46/46 | 46/58 | 7/0 | -2.305 → 2.305 |
| USD/JPY | 2026-09-09T20:00:00+00:00 | ranging | sell → buy | 23/25 | 25/7 | 3/8 | -2.323 → 2.323 |
| USD/JPY | 2026-09-10T04:00:00+00:00 | ranging | sell → buy | 28/35 | 30/28 | 4/7 | -3.690 → 3.690 |
| USD/JPY | 2026-09-16T04:00:00+00:00 | ranging | buy → sell | 27/10 | 14/17 | 7/0 | 3.850 → -3.850 |
| USD/JPY | 2026-09-29T12:00:00+00:00 | ranging | sell → buy | 40/41 | 66/25 | 0/10 | 0.537 → -0.537 |
| XAG/USD | 2026-08-07T20:00:00+00:00 | trending_down | buy → sell | 39/36 | 30/34 | 11/7 | 4.120 → -4.120 |
| XAG/USD | 2026-08-10T20:00:00+00:00 | trending_down | buy → sell | 33/21 | 25/26 | 10/0 | -2.125 → 2.125 |
| XAU/USD | 2026-08-17T04:00:00+00:00 | trending_down | buy → sell | 45/44 | 38/55 | 11/0 | -0.211 → 0.211 |
