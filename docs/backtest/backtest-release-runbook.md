# Backtest Release Runbook

## Mục đích

Phase 7 không tự coi một backtest tốt là đủ để phát hành. Một config chỉ được
Scanner Router chấp nhận khi có release report đã khóa với đúng dataset và
provenance của lần validation.

Release report phải đồng thời đạt:

- golden replay cố định `passed=true`;
- ít nhất 20 lệnh forward demo được đối soát;
- fill rate tối thiểu 80%, rejection rate tối đa 20%;
- adverse slippage trung bình tối đa 5 bps;
- suy giảm hiệu suất tối đa 25%;
- ít nhất 20 mẫu shadow, tỷ lệ khác biệt tối đa 10%;
- một người review xác nhận `approved=true`.

## Dữ liệu đầu vào

Chuẩn bị bốn file JSON:

1. Snapshot `VALIDATION` từ engine hiện tại, có `validation_replay` hoàn chỉnh.
2. Snapshot forward của engine hiện tại, chạy frozen config trên đúng khoảng
   thời gian tài khoản demo hoạt động.
3. Snapshot engine cũ chạy trên cùng khoảng forward để so shadow. File này được giữ
   làm audit và tự gắn `LEGACY_RESEARCH`.
4. Danh sách lệnh đóng trên tài khoản demo. Mỗi dòng phải có `candidate_id`;
   nếu thiếu, hệ thống ghép theo symbol, side và thời gian trong sai số 240
   phút để chẩn đoán nhưng release vẫn bị chặn bởi
   `FORWARD_CORRELATION_MISSING`. Các field hữu ích là `actual_entry`,
   `result_amount` hoặc `result_r`, `mt5_deal_id`.

Lệnh Scanner mới tự ghi correlation ID dạng `AMA-FWD:*` vào comment MT5. Xuất
lịch sử đã đóng từ tài khoản demo bằng:

```powershell
python scripts/export_mt5_forward_demo.py `
  --days 90 `
  --output data/backtests/forward-demo.json
```

Exporter từ chối tài khoản thật và chỉ xuất các lệnh có correlation ID; không
dùng lệnh tay hoặc lịch sử không truy được về Scanner làm bằng chứng.

## Tạo báo cáo

Chạy lần đầu không có `--approve` để xem các block code:

```powershell
python scripts/backtest_release_report.py `
  --snapshot data/backtests/current-validation.json `
  --forward-snapshot data/backtests/current-forward.json `
  --legacy-snapshot data/backtests/legacy-shadow.json `
  --demo-trades data/backtests/forward-demo.json `
  --reviewer "ten-nguoi-review"
```

Sau khi kiểm tra số liệu và xác nhận các file đầu vào đúng, chạy lại với
`--approve` và chỉ định output mới:

```powershell
python scripts/backtest_release_report.py `
  --snapshot data/backtests/current-validation.json `
  --forward-snapshot data/backtests/current-forward.json `
  --legacy-snapshot data/backtests/legacy-shadow.json `
  --demo-trades data/backtests/forward-demo.json `
  --reviewer "ten-nguoi-review" `
  --approve `
  --output data/backtests/current-validation-reviewed.json
```

Mã thoát `0` nghĩa là `ready=true`; mã `2` nghĩa là report đã tạo nhưng còn
block. Không sửa tay report vì fingerprint sẽ không còn hợp lệ.

## Phát hành vào Scanner

Tải file `*-reviewed.json` trong màn hình Backtest, mở “Áp dụng cấu hình” và
kiểm tra trạng thái `VALIDATED` trước khi lưu. Snapshot legacy chỉ được xem và
phân tích; nút áp dụng bị ẩn. Settings sẽ tự hạ config cũ/thiếu report về
`VERSION_MISMATCH` hoặc `DRAFT`, và Router tiếp tục dùng nhánh mặc định.

## Khi chưa đủ dữ liệu

Không hạ ngưỡng và không sửa `ready` thủ công. Tiếp tục thu thập demo/shadow,
tạo lại report, rồi review lại. Đây là trạng thái chờ bằng chứng, không phải lỗi
Scanner hay MT5.

Trình tự để đóng hai điều kiện vận hành còn lại:

1. Đăng nhập MT5 bằng tài khoản **demo**; exporter cố ý từ chối server/tài khoản
   thật.
2. Từ Scanner, đặt và đóng ít nhất 20 lệnh đủ điều kiện. Comment MT5 phải giữ
   correlation `AMA-FWD:*`; lệnh tay ngoài Scanner không được tính.
3. Chạy current engine và legacy engine trên cùng khoảng thời gian demo để tạo
   `current-forward.json` và `legacy-shadow.json`; chạy một snapshot
   `VALIDATION` hiện hành riêng.
4. Chạy exporter, sau đó tạo report không `--approve`. Xử lý mọi `block_codes`
   cho đến khi các ngưỡng sample, fill, rejection, slippage, degradation và
   shadow đều đạt.
5. Người review kiểm tra evidence rồi chạy lại với `--approve`. Chỉ khi CLI trả
   mã `0` và report có `ready=true` mới áp dụng config vào Scanner.

Trạng thái kiểm tra ngày 25/07/2026: full test suite đã đạt **1550 passed,
12 skipped, 17 xfailed, 0 failed**. MT5 đang kết nối `Exness-MT5Real36`, nên
exporter đã từ chối đúng thiết kế và chưa có forward-demo evidence hợp lệ.
