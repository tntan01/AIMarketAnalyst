# Kế hoạch giao việc: rút SMC khỏi TechnicalScore (Tech Lead → Coder)

> **Trạng thái:** Q1–Q10 ĐÃ CHỐT 07/10/2026 (xem §2 và §8); Giai đoạn 1 dùng
> corpus **nhỏ**, không tối ưu trọng số. **SD-C1, SD-C2 ACCEPT; SD-C3 đã giao:**
> [`smc-demote-tasks/SD-C3.md`](smc-demote-tasks/SD-C3.md).  
> **Ngày lập:** 07/10/2026.  
> **Đề xuất gốc (lý do, số liệu, phương án A/B):**
> [`smc-demote-entry-quality-plan.md`](smc-demote-entry-quality-plan.md) — đọc
> trước khi nhận việc.  
> **Contract runtime liên quan:** [`scanner-architecture.md`](../scanner/scanner-architecture.md)
> §3 (TechnicalScore), §4 (SetupScore), §7.3 (version), §10 (kiểm thử);
> [`smc-bqlc-spec.md`](smc-bqlc-spec.md); quy tắc chung
> [`architecture-rules.md`](../architecture/architecture-rules.md).

## 0. Cách làm việc

### 0.1 Vai trò

| Vai trò | Trách nhiệm |
|---|---|
| **Tech Lead (TL)** | Giao từng task theo ID; chốt các quyết định `Q*` ở §2; review và duyệt tại mỗi checkpoint `CP*`; quyết định có chuyển giai đoạn hay không |
| **Coder** | Thực hiện đúng phạm vi task được giao; không tự mở rộng phạm vi; dừng ở checkpoint và báo cáo theo mẫu §7; gặp điểm mơ hồ thì hỏi TL, không tự chọn |

### 0.2 Quy tắc bắt buộc cho Coder

1. **Một task = một commit** (hoặc một nhóm commit nhỏ cùng ID task trong message,
   ví dụ `feat(scanner): [SD-I1] …`). Không trộn hai task trong một commit.
2. **Tài liệu trước code** (rule D1): không sửa code runtime Scanner ở Giai đoạn 3
   khi Giai đoạn 2 chưa được TL duyệt.
3. **Không chỉnh threshold** (`ready/watch/wait`, min score-gap, min R:R) để giữ
   kết quả cũ. Phân bố điểm đổi là kết quả dự kiến; TL/Owner đánh giá riêng.
4. **Không dual/shadow scorer trên live**; không relabel snapshot/journal cũ.
5. **Fail-closed giữ nguyên**: thiếu dữ liệu không bao giờ thành điểm bịa.
6. Mọi lệnh kiểm tra chạy được trên máy dev: `python -X utf8 -m pytest …`,
   `lint-imports` (`.importlinter`) nếu môi trường đã cài `import-linter` (hiện máy dev chưa cài — ghi rõ trong báo cáo). Báo cáo phải dán output thật, không tóm tắt
   "đã pass" nếu chưa chạy.
7. Không gửi lệnh MT5 thật trong bất kỳ task nào.

### 0.3 Các giai đoạn và checkpoint

```text
Giai đoạn 1: Hiệu chỉnh offline (SD-C1..C4)        → CP1: TL/Owner chọn A/B/giữ nguyên + trọng số
Giai đoạn 2: Cập nhật tài liệu contract (SD-D1..D2) → CP2: TL duyệt contract mới
Giai đoạn 3: Triển khai phương án A (SD-I1..I7)     → CP3 (sau I1–I3), CP4 (hoàn tất)
```

### 0.4 Quy trình chuyển giao TL ↔ Coder

```text
TL viết  docs/plans/smc-demote-tasks/SD-xx.md         (file giao việc tự đủ)
Owner    bảo Coder (opencode): "Đọc và thực hiện docs/plans/smc-demote-tasks/SD-xx.md"
Coder    làm trực tiếp trên main, commit code của task, rồi viết
         docs/plans/smc-demote-tasks/SD-xx-report.md   (mẫu §7, ghi hash commit code)
         và commit riêng file report → DỪNG
Owner    bảo TL: "Review SD-xx"
TL       đọc report + git diff + tự chạy lại lệnh nghiệm thu
         → ACCEPT (giao task kế) hoặc REWORK (ghi yêu cầu sửa vào cuối SD-xx.md, mục "Rework")
```

- File giao việc là **nguồn duy nhất** cho Coder; Coder không cần đọc hội thoại
  của TL. Mâu thuẫn giữa file giao việc và file này → Coder dừng và hỏi.
- Làm thẳng trên `main` (Owner chốt 07/10/2026, không dùng branch riêng).
  Trước khi commit: `git status` sạch ngoài các file của task; mọi test
  liên quan phải pass — `main` không được ở trạng thái đỏ.
- Coder **không** tự bắt đầu task tiếp theo, không sửa file giao việc, không
  sửa plan này.

Nếu tại CP1 chọn **giữ nguyên** → dừng sau Giai đoạn 1, lưu báo cáo. Nếu chọn
**B** → TL lập plan riêng cho B; Giai đoạn 2–3 của file này không áp dụng.

## 1. Bối cảnh ngắn cho Coder

- `TechnicalSignalScore` hiện = Trend/Momentum/Location/SMC theo trọng số regime
  (`core/technical_signal_scorer.py:61-95`), dùng để **chọn side**.
- SMC raw = `quality_raw` (0–15) của zone tốt nhất mỗi side, đọc qua
  `project_smc_quality_raw` (`core/technical_signal_scorer.py:935`). Điểm này
  không phụ thuộc vị trí giá → ít phân biệt BUY/SELL và tạo "vách" khi một side
  không có zone (xem đề xuất §2–§4).
- **Phát hiện khi lập plan:** trên đường live, `build_side_snapshot` trong
  `core/scanner_release.py:185-200` **không truyền** `evidence_score` /
  `execution_quality_score` → `setup_score` luôn dùng 50 neutral cho cả hai
  (`core/final_score.py`, `FINAL_SCORE_NEUTRAL_FALLBACK`). Tức Evidence đang là
  slot trống — phương án A đặt SMC vào đây.
- Phương án A: Technical chỉ còn Trend/Momentum/Location; SMC quality →
  `evidence_score`; gate READY (zone + plan) giữ nguyên.

## 2. Quyết định đã chốt (Owner, 07/10/2026)

Coder thực hiện theo cột "Đã chốt". Q4 là **quy tắc quyết định** đã chốt; kết
quả được áp tại CP1 dựa trên báo cáo SD-C4.

**Quy mô Giai đoạn 1 (chốt 07/10/2026):** corpus **nhỏ** — mục tiêu chỉ là trả
lời "phương án A có làm việc chọn side tệ đi rõ rệt không" và "Q6 có hợp lý
không". **Không tối ưu trọng số** trong đợt này (xem Q5, §6).

| ID | Câu hỏi | Đã chốt | Lý do |
|---|---|---|---|
| Q1 | Nguồn dữ liệu cho corpus (SD-C1) | Lấy lịch sử MT5 **một lần**, đóng băng vào file; mọi phân tích sau chỉ đọc file, không cần terminal | Corpus 58 snapshot chỉ có 24 H1 tương lai, không trượt cutoff được; lịch sử Scanner đã lưu (`%APPDATA%/ai-market-analyst/scanner_snapshots`) chỉ có 72 lần quét 04–07/10 và không có phân rã điểm → không thay được; dữ liệu đóng băng → tái lập được |
| Q2 | Phạm vi corpus | `SUPPORTED_SYMBOLS` (31 cặp), **3 tháng** gần nhất có đủ 48 H1 tương lai, **1 cutoff/ngày**, giờ cutoff **xoay vòng 04:00 → 12:00 → 20:00 UTC** theo ngày (đóng nến H4; lần lượt phiên Á/Âu/Mỹ). Bỏ ngày không có nến (cuối tuần forex). Ước tính ~2.000 snapshot, ~15–30 phút chạy song song | Mốc cách nhau vài giờ gần như trùng nhau (499/500 nến H4, cùng D1), số mẫu độc lập do số (cặp × ngày) quyết định; xoay vòng giờ để không lệch theo một phiên; chi phí thấp → chạy lại khi sửa lỗi được |
| Q3 | Outcome | **Chính:** TP-trước/SL-trước theo plan của hệ thống, cùng bar chạm cả hai → SL (STOP_FIRST), trong tối đa 48 H1; chưa chạm cả hai → `unresolved`, loại khỏi phép đo chính và đếm riêng. **Phụ:** MFE/MAE theo R; fwd 8h/24h theo ATR H1 | TP/SL sát giao dịch thật nhưng chỉ có ở side có plan; outcome phụ dùng để đánh giá chọn side cho mọi side |
| Q4 | Chọn A / B / giữ nguyên | **Chọn A** nếu báo cáo SD-C4 cho thấy đồng thời: **(1)** chọn side: chênh lệch fwd 24h (ATR H1) trung bình của side được chọn, **A − hiện tại**, có cận dưới khoảng tin cậy 95% (bootstrap theo cụm) **≥ −0,05 ATR**; **(2)** SMC `quality_score` phân biệt TP-trước/SL-trước trên side có plan: **AUC ≥ 0,55** và khoảng tin cậy 95% không chứa 0,5; nếu số side có kết quả TP/SL < 200 thì ghi "không đủ mẫu" và coi (2) là **không đạt**. Không đạt (1) → giữ nguyên, TL cân nhắc B. Đạt (1), không đạt (2) → vẫn A, TL quyết định lại Q6 | Bằng chứng hiện tại chỉ 50 pair / 4 lần đổi side; ngưỡng cụ thể để đọc báo cáo không cần đoán |
| Q5 | Trọng số regime 3 thành phần | **Dùng mặc định chia lại tỷ lệ**, không tối ưu trong đợt này: trending **50/25/25**, ranging **17/17/66**, volatile **29/14/57**, unknown **34/33/33** (Trend/Momentum/Location, tổng 100). Tối ưu trọng số để đợt sau, gộp với việc sửa phân loại regime (§6) | Chia lại tỷ lệ là thay đổi tối thiểu, không thêm giả định; corpus nhỏ và gần như toàn trending không đủ để tối ưu mà không overfit |
| Q6 | Ánh xạ SMC → `evidence_score` | Có zone → `round_half_up(quality_score)` (0–100); không có zone sau khi đánh giá đủ → `0`; `DATA_UNAVAILABLE` → `None` (50 neutral + warning `FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK`) | Khớp contract §4 (thiếu dữ liệu = neutral, không có zone = kết quả hợp lệ); side đã chọn xong nên 0 chỉ hạ thứ hạng, không lật hướng; slot Evidence live đang trống |
| Q7 | Bỏ B khỏi SMC quality trong đợt này? | **Không** — để đợt sau | Tránh hai thay đổi chồng nhau (spec B/Q/L/C + TechnicalScore); khi SMC rời Technical, B không còn đếm trùng Trend trong chọn side |
| Q8 | Lưu trữ dữ liệu corpus | Lưu **chuỗi nến gốc mỗi symbol một lần**, cắt cửa sổ theo cutoff khi replay; không lưu sẵn cửa sổ từng snapshot. File nến gốc nằm trong `reports/scanner/smc_demote/data/` và **không commit** (thêm `.gitignore`); chỉ commit manifest (kèm hash) và kết quả phân tích | Lưu sẵn cửa sổ: 58 snapshot đã 1,9 MB → hàng nghìn snapshot thành hàng trăm MB; manifest + hash đủ để kiểm chứng tái lập |
| Q9 | Có tính spread/chi phí khi xác định TP/SL? | **Không**; báo cáo ghi rõ giới hạn này | So sánh tương đối giữa hai phương án; chi phí như nhau cho cả hai nên không đổi kết luận |
| Q10 | Ai đóng vai TL/Coder; MT5 cho SD-C1 | **TL = Claude Code** (phiên Claude của Owner); **Coder = phiên opencode, model DeepSeek Flash**; Owner chuyển giao giữa hai phiên và duyệt checkpoint. MT5 sẵn sàng trên máy dev (terminal mở, đăng nhập khi chạy `fetch`). Symbol thiếu lịch sử → loại, ghi trong manifest. Quy trình: §0.4 | Coder không có bối cảnh hội thoại → mỗi task có file giao việc tự đủ |

## 3. Giai đoạn 1 — Hiệu chỉnh offline

Toàn bộ code ở `scripts/`, output ở `reports/scanner/smc_demote/`. **Không sửa
`core/`, `controllers/`, `ui/`, `services/`** trong giai đoạn này.

### SD-C1 — Dựng corpus mở rộng

- **Đầu vào:** quyết định Q1, Q2, Q8, Q10.
- **Việc:** script `scripts/smc_demote_corpus.py`:
  - `fetch`: đọc lịch sử D1/H4/H1/M15 qua `services/mt5_service.py`
    (`copy_rates_range`), lưu **chuỗi nến gốc mỗi symbol một lần** (gzip
    JSONL) vào `reports/scanner/smc_demote/data/`, kèm `tick_size`,
    `tick_size_source`, `min_rr` từ `config/scanner_order_policy.json`. Thêm
    thư mục `data/` vào `.gitignore`.
  - `plan`: sinh danh sách cutoff theo Q2 (1/ngày, xoay vòng 04/12/20 UTC, chỉ
    ngày có nến, đủ 48 H1 sau cutoff) → `cutoffs.json` (commit được, nhỏ).
  - Không lưu sẵn cửa sổ từng snapshot; SD-C2 cắt cửa sổ khi replay bằng hàm
    dùng chung (500 nến D1/H4/H1, 100 nến M15 đã đóng tại cutoff; future tail
    48 H1 / 192 M15), dùng lại `_candle`/recipe của
    `scripts/smc_replay_parity.py`, không viết lại logic lọc nến đóng.
- **Chấp nhận:**
  - Có lệnh `verify`: với mọi cutoff, cửa sổ không chứa nến sau cutoff; future
    tail bắt đầu sau cutoff và đủ độ dài; đếm cutoff theo symbol/tháng/giờ.
  - Ghi `reports/scanner/smc_demote/corpus_manifest.json` (symbol có/không đủ
    lịch sử và lý do, số cutoff, khoảng thời gian, hash từng file nến gốc).
- **Không làm:** không sửa corpus 58 snapshot hiện có.

### SD-C2 — Replay và gắn nhãn outcome

- **Việc:** `scripts/smc_demote_replay.py` chạy mỗi cutoff qua
  `core.scanner_live_producers.derive_live_analysis` (song song nhiều
  process), ghi mỗi side: regime, raw trend/momentum/location, SMC
  `quality_raw`/B/Q/L/C/state/plan, entry/SL/TP của plan; rồi gắn nhãn theo Q3
  từ future tail (M15 cho TP/SL, H1 cho fwd/MFE/MAE).
  - **Chạy thử trước:** 1 symbol × 1 tháng; báo thời gian/snapshot và RAM mỗi
    process; từ đó chọn số process và ước tổng thời gian trước khi chạy cả lô.
  - **Chạy tiếp được:** ghi kết quả từng snapshot ngay khi xong (append), khi
    chạy lại bỏ qua snapshot đã có; có tùy chọn chỉ chạy lại theo symbol hoặc
    khoảng ngày.
- **Chấp nhận:**
  - Replay lại 58 snapshot corpus cũ qua đường SD-C2 cho kết quả SMC khớp
    `scripts/smc_replay_parity.py` chạy **với code hiện tại** (trạng thái side).
    Không so với `replay_parity.json` đã lưu (tạo 17/09, trước khi producer
    đổi ngày 04/10 — lỗi thời).
  - Lỗi từng row ghi vào file lỗi, không làm dừng cả lô; báo tỷ lệ lỗi.
  - Không có nhãn nào dùng dữ liệu ≤ cutoff (test nhỏ trong script).

### SD-C3 — Phân tích

- **Việc:** `scripts/smc_demote_analyze.py` tính:
  1. Phân bố raw từng thành phần theo regime.
  2. Khả năng phân biệt từng thành phần với outcome: hit-rate theo bucket,
     AUC, tương quan Spearman.
  3. So sánh chọn side: (a) hiện tại 4 thành phần; (b) 3 thành phần với trọng
     số Q5 mặc định. Mỗi biến thể: số side đổi, outcome của side được chọn, áp
     min score-gap hiện hành. Tính đúng chỉ số của **Q4 điều kiện (1)**.
     Không grid search/tối ưu trọng số (Q5).
  4. Với side có plan: AUC của SMC `quality_score` đối với TP-trước/SL-trước,
     số side resolved/unresolved — đúng chỉ số của **Q4 điều kiện (2)**.
  5. Khoảng tin cậy bootstrap **theo cụm ngày UTC của cutoff** (TL sửa
     07/10/2026: mỗi symbol 1 cutoff/ngày nên cụm (symbol, ngày) trùng từng row),
     không bootstrap từng row.
  6. **Phân bố regime** của corpus (số/tỷ lệ trending_up, trending_down,
     ranging, volatile, unknown) theo symbol và theo tháng; kết quả mục 2–3
     tách theo regime (mang tính mô tả; regime ít mẫu ghi rõ). Số liệu này là
     đầu vào cho việc riêng về regime ở §6.
- **Chấp nhận:** script chạy lại cho cùng kết quả (seed cố định); output JSON
  máy đọc + bảng markdown.

### SD-C4 — Báo cáo cho CP1

- **Việc:** `reports/scanner/smc_demote/report.md`: tóm tắt 1 trang, bảng
  ablation, phân bố regime, kết quả đánh giá **từng điều kiện của quy tắc Q4**
  (đạt/không đạt + số liệu + khoảng tin cậy), xác nhận Q6 còn hợp lệ, các giới
  hạn của dữ liệu (quy mô nhỏ, không tính spread, tỷ lệ unresolved).
- **CP1 — TL/Owner:** áp quy tắc Q4 lên báo cáo, xác nhận kết quả. Ghi vào §8
  của file này.

## 4. Giai đoạn 2 — Tài liệu contract (chỉ khi CP1 chọn A)

### SD-D1 — Sửa `scanner-architecture.md`

- §1, §3.1–3.3: TechnicalScore 3 thành phần; bảng trọng số theo Q5; ghi rõ SMC
  không còn tham gia chọn side.
- §3.4/§3.5: bỏ câu "Không đổi Trend/Momentum/SMC…" hoặc cập nhật cho đúng.
- §4: Evidence = SMC quality theo Q6, source `smc-quality-evidence-v1`;
  Execution vẫn neutral (không thuộc phạm vi).
- §5/§6: SMC `DATA_UNAVAILABLE` không còn làm Technical fail-closed; READY vẫn
  cần zone + plan (selection/readiness không đổi).
- §7.3: version mới — tối thiểu `Scoring`, `Technical weights`, `FinalScore`
  (vì Evidence đổi nguồn), `Feature` nếu shape raws đổi. TL chốt chuỗi version.
- §10: liệt kê test bắt buộc mới (xem SD-I7).

### SD-D2 — Tài liệu liên quan

- [`scanner-features-spec.md`](../scanner/scanner-features-spec.md) §0:
  `smc` không còn là raw của TechnicalScore.
- [`smc-bqlc-spec.md`](smc-bqlc-spec.md): thêm ghi chú consumer — quality được
  đọc làm Evidence; công thức không đổi.
- [`technical-scoring-architecture.md`](../scanner/technical-scoring-architecture.md)
  §13: cập nhật trỏ tới contract mới.
- [`docs/README.md`](../README.md) và
  [`architecture.md`](../architecture/architecture.md) (dòng "TechnicalSignalScore
  chỉ gồm Trend, Momentum, Location và SMC").
- **CP2 — TL:** duyệt diff tài liệu. Chưa duyệt thì không bắt đầu Giai đoạn 3.

## 5. Giai đoạn 3 — Triển khai phương án A

Thứ tự bắt buộc I1 → I7. Sau I3 dừng ở **CP3**.

### SD-I1 — Scorer 3 thành phần

- **File:** `core/technical_signal_scorer.py`.
- **Việc:**
  - `TECHNICAL_COMPONENT_RAW_MAX`/`TECHNICAL_REGIME_WEIGHTS` live bỏ `smc`,
    trọng số theo Q5; đổi `TECHNICAL_WEIGHT_POLICY_VERSION`.
  - `score_technical_signal` không còn nhận/đòi `canonical_smc` để tính điểm;
    SMC unavailable không còn raise `TechnicalScoreDataError`.
  - `TechnicalSignalScoreResult`: quyết định giữ `smc_evidence` như provenance
    (không cộng điểm) hay chuyển ra ngoài — theo contract SD-D1.
  - Giữ reader lịch sử: payload cũ 4 thành phần vẫn đọc được với nghĩa cũ
    (theo compatibility contract; `TECHNICAL_WEIGHT_POLICY_LEGACY_VERSION`).
- **Chấp nhận:** test scorer mới pass; payload cũ trong fixture vẫn parse.

### SD-I2 — Model, composition, version

- **File:** `core/scanner_v4_models.py` (`TechnicalBreakdown` ~:701-752,
  :828; version :33-50), `core/scanner_composition.py` (:290, :1569 và mọi chỗ
  gọi `score_technical_signal`), `core/scanner_v4_observability.py` (:169).
- **Việc:** breakdown live 3 thành phần; reader chấp nhận cả shape cũ (4) theo
  version; bump version theo §7.3 mới; composition truyền đúng input mới.
- **Chấp nhận:** `tests/test_scanner_composition.py`,
  `tests/test_scanner_contract.py`, `tests/test_scanner_v4_observability.py`
  pass sau khi cập nhật expected có giải thích.

### SD-I3 — SMC quality → Evidence

- **File:** `core/scanner_release.py:185-200`,
  `core/scanner_live_producers.py:build_side_snapshot`.
- **Việc:** tính `evidence_score` từng side theo Q6 từ `analysis["canonical_smc"]`
  (dùng `project_smc_quality_raw`/selection đã có, không tính lại B/Q/L/C), truyền
  `evidence_source` theo SD-D1. Execution giữ nguyên `None`.
- **Chấp nhận:**
  - Test: side `DATA_UNAVAILABLE` → evidence `None` + reason
    `FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK`; no-zone → 0; có zone → đúng
    `quality_score` làm tròn.
  - Test: đổi SMC của một side **không** đổi `selected_side` khi Trend/
    Momentum/Location giữ nguyên.
- **CP3 — TL:** review I1–I3 cùng kết quả replay corpus 58 snapshot (số side
  đổi, phân bố technical/setup_score trước–sau).

### SD-I4 — Row, UI, persistence

- **File:** `core/scanner_ui_adapter.py`, `ui/scanner_v4_presentation.py`,
  `core/scanner_row.py`, tab Chẩn đoán/Detail (`ui/screens/scanner_detail_screen.py`).
- **Việc:** phân rã Technical hiển thị 3 thành phần; SMC hiển thị ở khối
  Evidence/chất lượng entry (giữ B/Q/L/C chi tiết như hiện có); row/snapshot cũ
  vẫn hiển thị được nhãn cũ.
- **Chấp nhận:** test UI adapter/row pass; chạy app (skill `run`) chụp màn hình
  Scanner + Detail một pair có zone và một pair không zone, đính vào báo cáo.

### SD-I5 — Journal, replay, backtest contract

- **Việc:** kiểm tra `services/scanner_persistence_service.py`, journal, replay
  reader nhận version mới và vẫn đọc version cũ; backtest config cũ fail-closed
  theo §9 của contract.
- **Chấp nhận:** test replay/journal hiện có pass; thêm test đọc snapshot cũ.

### SD-I6 — Oracle và fixture

- **File:** `reports/scanner/oracle_fixture.json`, `tests/test_scanner_oracle.py`,
  `tests/test_scanner_invariants.py`.
- **Việc:** sinh lại oracle bằng đúng script hiện hành; mọi expected đổi phải
  liệt kê trong báo cáo kèm lý do (do SMC rời Technical / Evidence có nguồn).
- **Không làm:** sửa tay expected cho khớp mà không giải thích.

### SD-I7 — Kiểm thử tổng và nghiệm thu

- **Việc:**
  - Toàn bộ `python -X utf8 -m pytest` + `lint-imports`.
  - Test bắt buộc mới (đưa vào §10 contract): (1) side selection độc lập SMC;
    (2) SMC unavailable không chặn Technical; (3) Evidence provenance đúng;
    (4) payload cũ đọc được; (5) READY vẫn cần zone + plan.
  - Chạy lại `scripts/smc_demote_analyze.py` trên corpus với code mới, xác nhận
    khớp biến thể đã chọn ở CP1.
  - Smoke Scanner trên fixture/environment, intent-only, không dispatch lệnh.
- **CP4 — TL:** duyệt toàn bộ; cập nhật trạng thái các tài liệu thành "ĐÃ
  TRIỂN KHAI"; Owner quyết định threshold có cần đánh giá lại không (việc riêng).

## 6. Ngoài phạm vi

- Đổi công thức B/Q/L/C hoặc trọng số 4/7/2/2 (Q7).
- Nối `execution_quality_score` thật.
- Chỉnh threshold READY/WATCH/WAIT, min R:R, gate Macro/Safety.
- Phương án B.
- **Tối ưu trọng số regime 3 thành phần** (Q5): để đợt sau, gộp với việc
  regime bên dưới; khi đó mở rộng corpus bằng chính công cụ SD-C1/C2 (nhiều
  cutoff/ngày, 12 tháng, chia train/test theo thời gian).
- **Lỗi pipeline SMC trên dữ liệu thật** (ghi nhận 07/10/2026 từ SD-C2):
  13/2010 cutoff `derive_live_analysis` raise `ValueError: SMC M15 expires_at
  must follow confirmed_at` (ví dụ `CHF/JPY@2026-07-27T04:00`,
  `EUR/GBP@2026-08-03T12:00`, `XAU/USD@2026-08-03T12:00`; đủ danh sách trong
  `reports/scanner/smc_demote/data/replay_errors.jsonl`). Trên live, pair gặp
  lỗi này có thể không được chấm. Cần plan riêng để điều tra; không sửa trong
  đợt này.
- **Regime `unknown` và độ nhạy phân loại regime** (ghi nhận 07/10/2026, việc
  riêng sau đợt này): theo `detect_market_regime`
  (`core/technical_context.py:169-256`), khi EMA50/EMA200 D1 tách ≥ 1 ATR H4 thì
  tổng điểm luôn ≥ 35 → luôn trending; `unknown` chỉ xảy ra khi dữ liệu hỏng
  (vd. EMA NaN làm mọi phép so sánh sai). Hai việc cần plan riêng:
  (1) dữ liệu EMA/ATR không hợp lệ phải fail-closed thay vì chấm với trọng số
  `unknown`; (2) đánh giá lại ngưỡng phân loại vì gần như mọi snapshot là
  trending (corpus cũ 56/58), khiến trọng số ranging/volatile hiếm khi được
  dùng. Số liệu đầu vào lấy từ SD-C3 mục 6.

## 7. Mẫu báo cáo của Coder tại mỗi task/checkpoint

```text
Task: SD-xx — <tên>
Commit: <hash> (<số file> file)
Đã làm: <gạch đầu dòng ngắn>
Kiểm tra đã chạy: <lệnh> → <output thật, tóm tắt pass/fail + số test>
Thay đổi hành vi/expected: <liệt kê + lý do> | Không có
Câu hỏi cho TL / điểm mơ hồ: <…> | Không có
Rủi ro còn lại: <…> | Không có
```

## 8. Nhật ký quyết định (TL điền)

| Ngày | Quyết định | Người chốt | Ghi chú |
|---|---|---|---|
| 07/10/2026 | Q1: lịch sử MT5 đóng băng vào file | Owner | Theo đề xuất §2 |
| 07/10/2026 | Q2: `SUPPORTED_SYMBOLS`, 12 tháng, cutoff mỗi 4h | Owner | **Thay thế** bởi dòng sửa đổi bên dưới |
| 07/10/2026 | Q3: TP/SL-trước (STOP_FIRST) + MFE/MAE + fwd 8h/24h | Owner | Theo đề xuất §2 |
| 07/10/2026 | Q4: quy tắc chọn A theo 2 điều kiện tại SD-C4 | Owner | Kết quả áp tại CP1 |
| 07/10/2026 | Q5: trọng số tối ưu nếu giữ được trên test, ngược lại mặc định chia tỷ lệ | Owner | **Thay thế** bởi dòng sửa đổi bên dưới |
| 07/10/2026 | Q6: evidence = quality_score / 0 khi no-zone / neutral khi unavailable | Owner | Theo đề xuất §2 |
| 07/10/2026 | Q7: không bỏ B trong đợt này | Owner | Theo đề xuất §2 |
| 07/10/2026 | Thêm yêu cầu báo cáo phân bố regime (SD-C3 mục 6); ghi nhận việc riêng về regime `unknown` (§6) | Owner | |
| 07/10/2026 | **Sửa đổi** — quy mô corpus nhỏ: Q2 = 31 cặp × 3 tháng × 1 cutoff/ngày xoay vòng 04/12/20 UTC (~2.000 snapshot); Q5 = mặc định chia tỷ lệ, không tối ưu (để đợt sau) | Owner | Lý do: chi phí ~65–120 giờ CPU của quy mô cũ; mốc liền kề trùng thông tin |
| 07/10/2026 | Q4 thêm ngưỡng đo: (1) cận dưới CI95 của chênh lệch fwd 24h ≥ −0,05 ATR; (2) AUC ≥ 0,55, CI không chứa 0,5, cần ≥ 200 side resolved | Owner | |
| 07/10/2026 | Q8: lưu nến gốc một lần, không commit `data/`; Q9: không tính spread | Owner | |
| 07/10/2026 | SD-C2 thêm chạy thử 1 symbol × 1 tháng và cơ chế chạy tiếp | Owner | |
| 07/10/2026 | Q10: TL = Claude Code; Coder = opencode (DeepSeek Flash); MT5 sẵn sàng | Owner | Quy trình §0.4 |
| 07/10/2026 | **ACCEPT SD-C1** — commit code `3d9d4a5`, report `5094e04` | TL | 31/31 symbol ok, 2010 cutoff; TL chạy lại `plan` (ra đúng `cutoffs.json` đã commit), `verify` 0 problems, 3 test pass. Câu hỏi của Coder về đếm lý do bỏ: giữ đếm độc lập theo lý do (dữ liệu không trùng: 2010 + 780 + 93 = 31 × 93). Ghi nhận nhỏ, không rework: `verify` đòi tail M15 đúng 192 (chặt hơn spec "> 0"); test 1 dùng chuỗi H1 cho mọi TF |
| 07/10/2026 | SD-C2: tiêu chí parity đổi sang so với `smc_replay_parity.py` chạy bằng code hiện tại | TL | TL đo: 4/6 row đầu lệch `replay_parity.json` (quality_raw/zone) do producer SMC Ca 1–4 (04/10) — file lưu đã lỗi thời |
| 07/10/2026 | Làm rõ Q3 cho SD-C2: entry của plan là lệnh limit tại mép zone → phải khớp trước (M15 chạm E) rồi mới xét TP/SL; giá khớp = E; nến khớp chỉ xét SL; không khớp trong 48h → `not_filled` (đếm riêng như `unresolved`) | TL | Plan có cả ở side `WATCH_ZONE` với E cách giá; không có luật khớp thì TP/SL-trước vô nghĩa. Owner có thể bác tại CP1 |
| 07/10/2026 | **ACCEPT SD-C2** — commit code `f6b4fcf`, report `a0e4556` | TL | 1997 row + 13 lỗi (0,65 %), missing 0. TL chạy lại: parity 58/0, summary ra đúng file đã commit, `rows_sha256` khớp; bộ gắn nhãn độc lập của TL khớp 3994/3994 side; 30 cutoff ngẫu nhiên chạy lại giống hệt. Resolved TP/SL = 494 side (≥ 200). Trả lời Coder: `error_rate` = errors/cutoffs giữ nguyên; 13 lỗi loại khỏi SD-C3, ghi số lượng, mở việc riêng (§6) |
| 07/10/2026 | SD-C3: cụm bootstrap = ngày UTC; chỉ số Q4(1) tính trên tập pair cả hai biến thể chọn được side (không lọc gap), pair chỉ biến thể 3 thành phần chọn được báo riêng; biến thể (a) phải khớp `score_technical_signal` thật trên 50 row (`check-scorer`) | TL | 204/1997 pair (10 %) biến thể hiện tại fail-closed vì SMC `data_unavailable` một side — số liệu cho D7 |
| | CP1 | | |
| | CP2 | | |
| | CP3 | | |
| | CP4 | | |
