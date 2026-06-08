from __future__ import annotations

from pathlib import Path

from config.paths import PROMPTS_DIR

_MANDATORY_QUESTIONS = (
    "\n\n## Phan 5 - Cau hoi bat buoc\n\n"
    "Tra loi ngan gon, cu the, khong chung chung. "
    "Khong duoc tra loi 'can nhac ky' hay 'tuy thi truong'.\n\n"
    "1. Voi vung entry hien tai, yeu to ky thuat/SMC nao UNG HO va yeu to nao CANH BAO? "
    "Tra loi dang bullet 2 cot: 'Ung ho:' va 'Canh bao:'.\n\n"
    "2. Neu gia khong cham vung entry ma bat len som (FOMO), "
    "trader nen DUOI THEO hay DOI RETEST? Tra loi kem ly do cu the "
    "dua tren SMC context (BOS/CHOCH, premium/discount, liquidity sweep).\n\n"
    "3. Dieu gi se khien setup nay bi VO HIEU TRUOC KHI gia cham SL? "
    "Liet ke dieu kien cu the. Neu khong co dieu kien ro rang, ghi dung: "
    "'Khong co dieu kien vo hieu ro rang.'"
)


def render_template(template: str, values: dict[str, object]) -> str:
    output = template
    for key, value in values.items():
        output = output.replace("{{" + key + "}}", str(value))
    return output


def build_full_analysis_prompt(values: dict[str, object], template_path: Path | None = None) -> str:
    path = template_path or PROMPTS_DIR / "full_analysis_prompt.md"
    rendered = render_template(path.read_text(encoding="utf-8"), values)
    return rendered + _MANDATORY_QUESTIONS
