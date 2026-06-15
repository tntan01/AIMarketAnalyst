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
    "Entry Zone": "Vung vao lenh",
    "Stop Loss": "Cat lo",
    "Take Profit": "Chot loi",
    "Direction Bias": "Thien huong",
    "Trade Permission": "Quyen giao dich",
    "Risk/Reward": "Rui ro/loi nhuan",
    "Position Sizing": "Khoi luong vao lenh",
}


def term(label: str) -> str:
    return TERMS.get(label, label)
