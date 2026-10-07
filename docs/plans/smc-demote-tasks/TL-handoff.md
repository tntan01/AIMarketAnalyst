# Bàn giao vai Tech Lead — đợt SMC demote

> **Dành cho:** phiên Claude nhận vai Tech Lead (TL) từ 07/10/2026.
> **Người giao:** phiên TL trước (đã lập đề xuất, kế hoạch và SD-C1).
> Đọc hết file này trước khi làm gì khác. Trả lời Owner bằng tiếng Việt.

## 1. Vai trò

| Ai | Vai | Ghi chú |
|---|---|---|
| Owner (người dùng) | Chốt quyết định, chuyển lời giữa TL và Coder | Xưng "tao/mày" là bình thường; giữ giọng chuyên nghiệp, không cần bắt chước |
| **Bạn (Claude Code)** | **Tech Lead**: viết file giao việc, review, chạy lại nghiệm thu, đề xuất quyết định | Không tự viết code task thay Coder, trừ khi Owner yêu cầu |
| Coder | Phiên **opencode, model DeepSeek Flash** | Không có bối cảnh hội thoại; model nhẹ → file giao việc phải tự đủ, rất cụ thể; **luôn tự kiểm chứng** báo cáo của Coder |

## 2. Đọc theo thứ tự

1. [`../smc-demote-entry-quality-plan.md`](../smc-demote-entry-quality-plan.md) — vì sao làm (chẩn đoán SMC, số liệu, phương án A/B).
2. [`../smc-demote-task-plan.md`](../smc-demote-task-plan.md) — kế hoạch: §0 quy trình, §2 quyết định Q1–Q10 **đã chốt**, §3–§5 các task, §8 nhật ký.
3. [`SD-C1.md`](SD-C1.md) — mẫu file giao việc đã dùng (giữ cùng cấu trúc cho task sau).
4. Contract runtime: [`../../scanner/scanner-architecture.md`](../../scanner/scanner-architecture.md) §3–§4, §7.3, §10; [`../smc-bqlc-spec.md`](../smc-bqlc-spec.md).

## 3. Trạng thái tại lúc bàn giao (07/10/2026)

- Commit `5f5cc66` trên `main`: đề xuất + plan + SD-C1. Chưa push.
- **SD-C1/C2/C3 ACCEPT** (code `3d9d4a5`, `f6b4fcf`, `0b699ef`).
  **SD-C4 ACCEPT** (code `8526dfb`). Giai đoạn 1 xong.
- **Đang chờ Owner quyết CP1** (đã trình 07/10/2026). Chưa viết task giai đoạn 2.
  Khi Owner chốt: ghi dòng CP1 vào §8 plan, rồi làm theo lựa chọn.
- Kết quả SD-C3 (để trình CP1): Q4(1) diff −0,0004 ATR, CI [−0,090; 0,086] →
  không đạt (CI rộng, không phải A tệ hơn); Q4(2) AUC 0,467, CI [0,407; 0,527],
  n=494 → không đạt. Bối cảnh TL tự tính: fwd 24h side chọn bởi TechnicalScore
  hiện tại −0,091 ATR, CI cụm ngày [−0,39; 0,20] (chọn ngẫu nhiên = 0 vì
  fwd BUY = −fwd SELL) → chưa thấy edge chọn side ở cả hai biến thể; TP-trước
  96/494 = 19 % so với hòa vốn 33 % ở R:R 2; 204/1997 pair (10 %) bị chặn do
  SMC `data_unavailable` (D7).

## 4. Quy trình mỗi task

```text
TL   viết docs/plans/smc-demote-tasks/SD-xx.md (tự đủ) → commit lên main
Owner  bảo Coder: "Đọc và thực hiện docs/plans/smc-demote-tasks/SD-xx.md"
Coder  làm trên main, commit code; viết SD-xx-report.md (mẫu §7 plan), commit riêng; dừng
Owner  bảo TL: "Review SD-xx"
TL   review → ACCEPT (ghi §8 plan, giao task kế) | REWORK (ghi mục "Rework" cuối SD-xx.md)
```

Quy ước đã chốt với Owner:
- **Commit thẳng lên `main`**, không branch (Owner chốt 07/10/2026). Trước giai
  đoạn 3 (sửa `core/`), nhắc Owner: nếu app Scanner chạy từ thư mục repo này
  thì mỗi commit có hiệu lực ở lần khởi động app kế tiếp.
- Commit message dạng `feat(research): [SD-xx] …`, `docs(smc): …`; cuối message
  có dòng attribution theo hướng dẫn hệ thống của phiên.
- Không push nếu Owner không yêu cầu.
- Checkpoint CP1–CP4 cần **Owner** duyệt, không tự qua.

## 5. Checklist review một task

1. Đọc `SD-xx-report.md`; đối chiếu từng mục "Chấp nhận" trong `SD-xx.md`.
2. `git log` / `git show --stat` — commit chỉ chứa file của task; không đụng
   file bị cấm (mục "Không được làm").
3. **Tự chạy lại** các lệnh nghiệm thu; không tin output dán trong report.
4. Đọc code: đặc biệt mọi chỗ cắt dữ liệu theo cutoff (nguy cơ lookahead),
   chỗ tự viết lại logic đã có sẵn, chỗ nuốt lỗi/điền số bịa (vi phạm fail-closed).
5. Kết luận ACCEPT/REWORK cho Owner, ngắn gọn, kèm bằng chứng file:line.

### 5.1 Khi Owner nói "Review SD-xx" — làm trọn vòng, không hỏi lại

- **ACCEPT:**
  1. Ghi một dòng vào §8 của plan (`ACCEPT SD-xx`, commit code, ghi chú).
  2. Nếu task kế tiếp **không** qua checkpoint: viết `SD-yy.md` (cùng cấu trúc
     SD-C1), commit.
  3. Nếu vừa xong task kết thúc một giai đoạn (SD-C4 → CP1, SD-D2 → CP2,
     SD-I3 → CP3, SD-I7 → CP4): **không** viết task kế; trình Owner nội dung
     cần duyệt và chờ.
  4. Kết thúc câu trả lời bằng **câu Owner dán cho Coder**, đặt trong khối
     trích dẫn, ví dụ: `Đọc và thực hiện docs/plans/smc-demote-tasks/SD-yy.md`.
- **REWORK:**
  1. Ghi yêu cầu sửa vào mục "Rework" cuối `SD-xx.md`: đánh số, mỗi mục nêu
     lỗi + bằng chứng file:line + điều kiện đạt; commit.
  2. Kết thúc bằng câu Owner dán cho Coder:
     `Đọc mục "Rework" cuối docs/plans/smc-demote-tasks/SD-xx.md, sửa theo đó, cập nhật SD-xx-report.md rồi dừng.`
- Lỗi nhỏ, rõ ràng (typo, thiếu dòng .gitignore…) vẫn đi đường REWORK; TL
  không tự sửa code của Coder trừ khi Owner bảo.

## 6. Ghi chú kỹ thuật cho các task tới

**SD-C2 (replay + nhãn):**
- Import `windows_at`/`load_symbol_data` từ `scripts/smc_demote_corpus.py`
  (SD-C1 tạo). Gọi `core.scanner_live_producers.derive_live_analysis` y như
  `scripts/smc_replay_parity.py:_live` (truyền `tick_size`, `tick_size_source`,
  `min_rr`, `m15_candles`, `m15_as_of=cutoff`, `captured_at=cutoff`).
- Đọc kết quả: `analysis["raws"].per_side[side].trend/momentum/location`;
  `analysis["canonical_smc"].side(side).selection` có `quality_raw`,
  `quality_score`, `b/q/l/c`, `state`, `plan_available`, `plan`,
  `zone_low/zone_high`; `analysis["regime"]`.
- Plan entry/SL/TP: xem `core/scanner_scenario_producers.py:plans_from_canonical_selection`.
- Tốc độ: TL đo lại 07/10 trên dữ liệu đóng băng ~1 giây/snapshot (EUR/USD, 1 process); số cũ 5–9 giây đo trên corpus cũ, chưa rõ vì sao chênh — SD-C2 trial sẽ đo lại.
- `reports/scanner/smc_real_snapshots/replay_parity.json` (17/09) đã lỗi thời so với producer 04/10 — không dùng làm expected.
- Phiên TL trước đã chạy thử nghiệm trên corpus 58 snapshot bằng script scratch
  (không commit); kết quả nằm trong đề xuất §3–§4 — dùng để đối chiếu thô.

**SD-C3 — cách tính TechnicalScore "không SMC" để so sánh:** công thức §3.3
scanner-architecture, `raw/raw_max × weight`, trọng số Q5 mặc định
(trending 50/25/25, ranging 17/17/66, volatile 29/14/57, unknown 34/33/33);
hòa → BUY. Áp min score-gap hiện hành từ composition khi so.

**Sự thật đã kiểm chứng (đừng tìm lại):**
- Live chưa truyền `evidence_score`/`execution_quality_score`
  (`core/scanner_release.py:185-200`) → `setup_score` luôn dùng 50 neutral.
- Regime `unknown` gần như không xảy ra (chỉ khi dữ liệu EMA hỏng) —
  `core/technical_context.py:169-256`; ghi ở plan §6 là việc riêng.
- `import-linter` **chưa cài** trên máy dev → `lint-imports` không chạy được.
- Lịch sử Scanner lưu ở `%APPDATA%/ai-market-analyst/scanner_snapshots` chỉ
  ~72 lần quét gần nhất, không có phân rã điểm → không dùng thay corpus.
- `SUPPORTED_SYMBOLS` có 31 symbol (`config/constants.py`).
- Quy tắc kiến trúc: sửa tài liệu contract **trước** code (D1), đổi ngữ nghĩa
  điểm → đổi version, không chỉnh threshold để giữ kết quả cũ
  (`docs/architecture/architecture-rules.md`).
