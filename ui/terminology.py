from __future__ import annotations

TERMS = {
    "Dashboard": "Bảng điều khiển",
    "Scanner": "Quét thị trường",
    "Backtest": "Kiểm thử",
    "Journal": "Nhật ký",
    "Settings": "Cài đặt",
    "AI Provider": "Nhà cung cấp AI",
    "Model": "Mô hình",
    "API Key": "Khóa API",
    "Entry Zone": "Vùng vào lệnh",
    "Stop Loss": "Cắt lỗ",
    "Take Profit": "Chốt lời",
    "Direction Bias": "Thiên hướng",
    "Trade Permission": "Quyền giao dịch",
    "Risk/Reward": "Rủi ro/Lợi nhuận",
    "Position Sizing": "Khối lượng vào lệnh",
}


def term(label: str) -> str:
    return TERMS.get(label, label)
