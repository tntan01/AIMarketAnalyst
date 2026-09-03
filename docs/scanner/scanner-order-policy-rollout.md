# Scanner order policy — vận hành và rollback

## Trạng thái nghiệm thu

Policy live duy nhất là `config/scanner_order_policy.json`. Threshold hiện tại:

| Khóa | Giá trị |
|---|---:|
| `technical_floor` | `40` |
| `setup_floor` | `35` |
| `min_score_gap` | `5` |
| `min_risk_reward` | `2/1` |

Controller đọc policy trước mỗi scan qua `load_runtime_order_policy()` và truyền
cùng một `RuntimeOrderPolicy` qua composition, router, scenario producer và UI.

## Kiểm tra trước khi chạy live

```powershell
python -c "from core.scanner_order_policy import load_runtime_order_policy; p=load_runtime_order_policy(); assert p.certified() and p.order_enabled; print(p.threshold.to_dict())"
python -m pytest -q tests -k "scanner or market_safety"
```

Config hợp lệ phải có đủ 4 trường threshold, đúng policy version và R:R dương.
Config thiếu, hỏng JSON, sai version hoặc sai kiểu sẽ phát `ORDER_POLICY_FAULT`,
dùng fallback mở `DEFAULT_RUNTIME_ORDER_POLICY`, và giữ `order_enabled=False`.

## Quy tắc thay đổi

1. Sao lưu `config/scanner_order_policy.json` trước khi sửa.
2. Chỉ sửa block `threshold` nếu thay đổi ngưỡng Scanner.
3. Chạy lệnh kiểm tra loader và test Scanner ở trên.
4. Khởi động scan mới để controller nạp policy mới; không sửa hardcode trong code.

## Rollback

Khôi phục bản đã kiểm chứng:

```powershell
Copy-Item config/scanner_order_policy.json.bak config/scanner_order_policy.json -Force
python -c "from core.scanner_order_policy import load_runtime_order_policy; p=load_runtime_order_policy(); print(p.threshold.to_dict())"
```

Nếu config không thể đọc, hệ thống phải giữ trạng thái fail-closed và không được
tự thay bằng threshold khác.

## Phạm vi

`DEFAULT_MIN_*` trong router legacy/backtest và fixture
`make_default_threshold_policy()` chỉ phục vụ test/replay; chúng không được dùng
trong Scanner V4/live release path.
