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
- **SD-C1 đã giao**, chờ Coder làm. Chưa có `SD-C1-report.md`.
- Việc kế tiếp của TL: khi Owner nói "Review SD-C1" → review (§5); ACCEPT thì
  viết `SD-C2.md`.

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
- Tốc độ đo được ~5 giây/snapshot (1 process); tài liệu replay parity ghi ~9 giây.
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
