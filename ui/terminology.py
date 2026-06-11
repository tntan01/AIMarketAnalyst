from __future__ import annotations

TERMS = {
    "Dashboard": "Bang dieu khien",
    "Scanner": "Quet thi truong",
    "Backtest": "Backtest",
    "Journal": "Nhat ky",
    "Settings": "Cai dat",
    "AI Provider": "Nha cung cap AI",
    "Model": "Mo hinh",
    "API Key": "Khoa API",
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
