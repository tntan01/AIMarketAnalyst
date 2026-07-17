#!/usr/bin/env python
"""Kiểm tra chất lượng chuỗi tiếng Việt trong source code.

Phát hiện:
- Chuỗi tiếng Việt không dấu
- Lỗi chính tả phổ biến
- Thuật ngữ không thống nhất

Usage:
    python tools/check_ui_strings.py          # Quét toàn bộ project
    python tools/check_ui_strings.py --fix    # Tự động sửa (khi có thể)

Exit code:
    0 = Không phát hiện lỗi
    1 = Có lỗi (CI/CD sẽ fail)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


# ── Project root ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── File extensions to scan ───────────────────────────────────────────────
SCAN_EXTENSIONS = {".py", ".qss", ".css", ".json", ".yaml", ".yml", ".xml", ".ini", ".toml", ".md", ".html"}

# ── Directories to skip ───────────────────────────────────────────────────
SKIP_DIRS = {
    "__pycache__", ".git", ".pytest_cache", ".vscode", "node_modules",
    "venv", ".venv", "env", ".env", "dist", "build", "packaging",
    ".claude",
}

# ── Files to skip ─────────────────────────────────────────────────────────
SKIP_FILES = {
    "ai_providers.json",  # external catalog
}

# ═══════════════════════════════════════════════════════════════════════════
# Rule definitions
# ═══════════════════════════════════════════════════════════════════════════


class Rule(NamedTuple):
    """A check rule: finds `pattern` regex and suggests `fix`."""
    id: str
    category: str  # "diacritic" | "spelling" | "terminology"
    pattern: str   # regex
    fix: str       # suggested replacement (or "" if manual fix needed)
    description: str


# ── Non-diacritic Vietnamese detection ──────────────────────────────────
# These regexes match Vietnamese words written WITHOUT diacritics in UI strings.
# We look for common patterns that should have tone marks.

NON_DIACRITIC_RULES: list[Rule] = [
    # ── Single words ──
    Rule("D001", "diacritic", r'"Cai dat\b', '"Cài đặt', '"Cai dat" → "Cài đặt"'),
    Rule("D002", "diacritic", r'"Khoang cach\b', '"Khoảng cách', '"Khoang cach" → "Khoảng cách"'),
    Rule("D003", "diacritic", r'"Khong the\b', '"Không thể', '"Khong the" → "Không thể"'),
    Rule("D004", "diacritic", r'"Khong tim thay\b', '"Không tìm thấy', '"Khong tim thay" → "Không tìm thấy"'),
    Rule("D005", "diacritic", r'"Khong co\b', '"Không có', '"Khong co" → "Không có"'),
    Rule("D006", "diacritic", r'"Khong doc duoc\b', '"Không đọc được', '"Khong doc duoc" → "Không đọc được"'),
    Rule("D007", "diacritic", r'"Khong lay duoc\b', '"Không lấy được', '"Khong lay duoc" → "Không lấy được"'),
    Rule("D008", "diacritic", r'"Khong ho tro\b', '"Không hỗ trợ', '"Khong ho tro" → "Không hỗ trợ"'),
    Rule("D009", "diacritic", r'"Khong khoi tao\b', '"Không khởi tạo', '"Khong khoi tao" → "Không khởi tạo"'),
    Rule("D010", "diacritic", r'"Khong du dieu kien\b', '"Không đủ điều kiện', '"Khong du dieu kien" → "Không đủ điều kiện"'),
    Rule("D011", "diacritic", r'"Chua co du lieu\b', '"Chưa có dữ liệu', '"Chua co du lieu" → "Chưa có dữ liệu"'),
    Rule("D012", "diacritic", r'"Chua co du\b', '"Chưa có đủ', '"Chua co du" → "Chưa có đủ"'),
    Rule("D013", "diacritic", r'"Chua co\b', '"Chưa có', '"Chua co" → "Chưa có"'),
    Rule("D014", "diacritic", r'"Dang tai\b', '"Đang tải', '"Dang tai" → "Đang tải"'),
    Rule("D015", "diacritic", r'"Dang quet\b', '"Đang quét', '"Dang quet" → "Đang quét"'),
    Rule("D016", "diacritic", r'"Dang chay\b', '"Đang chạy', '"Dang chay" → "Đang chạy"'),
    Rule("D017", "diacritic", r'"Dang xu ly\b', '"Đang xử lý', '"Dang xu ly" → "Đang xử lý"'),
    Rule("D018", "diacritic", r'"Dang phan tich\b', '"Đang phân tích', '"Dang phan tich" → "Đang phân tích"'),
    Rule("D019", "diacritic", r'"Dang dong bo\b', '"Đang đồng bộ', '"Dang dong bo" → "Đang đồng bộ"'),
    Rule("D020", "diacritic", r'"Dang kiem tra\b', '"Đang kiểm tra', '"Dang kiem tra" → "Đang kiểm tra"'),
    Rule("D021", "diacritic", r'"Dang mo\b', '"Đang mở', '"Dang mo" → "Đang mở"'),
    Rule("D022", "diacritic", r'"Dang dat\b', '"Đang đặt', '"Dang dat" → "Đang đặt"'),
    Rule("D023", "diacritic", r'"Dang bat\b', '"Đang bật', '"Dang bat" → "Đang bật"'),
    Rule("D024", "diacritic", r'"Dang tat\b', '"Đang tắt', '"Dang tat" → "Đang tắt"'),
    Rule("D025", "diacritic", r'"Dang cap nhat\b', '"Đang cập nhật', '"Dang cap nhat" → "Đang cập nhật"'),
    Rule("D026", "diacritic", r'"Dang tom tat\b', '"Đang tóm tắt', '"Dang tom tat" → "Đang tóm tắt"'),
    Rule("D027", "diacritic", r'"Lenh da dong\b', '"Lệnh đã đóng', '"Lenh da dong" → "Lệnh đã đóng"'),
    Rule("D028", "diacritic", r'"Du lieu khong hop le\b', '"Dữ liệu không hợp lệ', '"Du lieu khong hop le" → "Dữ liệu không hợp lệ"'),
    Rule("D029", "diacritic", r'"Quan ly lenh\b', '"Quản lý lệnh', '"Quan ly lenh" → "Quản lý lệnh"'),
    Rule("D030", "diacritic", r'"Vao lenh\b', '"Vào lệnh', '"Vao lenh" → "Vào lệnh"'),
    Rule("D031", "diacritic", r'"Khong vao lenh\b', '"Không vào lệnh', '"Khong vao lenh" → "Không vào lệnh"'),
    Rule("D032", "diacritic", r'"Thanh cong\b', '"Thành công', '"Thanh cong" → "Thành công"'),
    Rule("D033", "diacritic", r'"That bai\b', '"Thất bại', '"That bai" → "Thất bại"'),
    Rule("D034", "diacritic", r'"Kiem thu\b', '"Kiểm thử', '"Kiem thu" → "Kiểm thử"'),
    Rule("D035", "diacritic", r'"Giao dich\b', '"Giao dịch', '"Giao dich" → "Giao dịch"'),
    Rule("D036", "diacritic", r'"Thi truong\b', '"Thị trường', '"Thi truong" → "Thị trường"'),
    Rule("D037", "diacritic", r'"Theo doi\b', '"Theo dõi', '"Theo doi" → "Theo dõi"'),
    Rule("D038", "diacritic", r'"Tai khoan\b', '"Tài khoản', '"Tai khoan" → "Tài khoản"'),
    Rule("D039", "diacritic", r'"Ket noi\b', '"Kết nối', '"Ket noi" → "Kết nối"'),
    Rule("D040", "diacritic", r'"Xu huong\b', '"Xu hướng', '"Xu huong" → "Xu hướng"'),
    Rule("D041", "diacritic", r'"San sang\b', '"Sẵn sàng', '"San sang" → "Sẵn sàng"'),
    Rule("D042", "diacritic", r'"Dung ngoai\b', '"Đứng ngoài', '"Dung ngoai" → "Đứng ngoài"'),
    Rule("D043", "diacritic", r'"Cho xac nhan\b', '"Chờ xác nhận', '"Cho xac nhan" → "Chờ xác nhận"'),
    Rule("D044", "diacritic", r'"Bi chan\b', '"Bị chặn', '"Bi chan" → "Bị chặn"'),
    Rule("D045", "diacritic", r'"Loi nhuan\b', '"Lợi nhuận', '"Loi nhuan" → "Lợi nhuận"'),
    Rule("D046", "diacritic", r'"Rui ro\b', '"Rủi ro', '"Rui ro" → "Rủi ro"'),
    Rule("D047", "diacritic", r'"Thua lo\b', '"Thua lỗ', '"Thua lo" → "Thua lỗ"'),
    Rule("D048", "diacritic", r'"Chien luoc\b', '"Chiến lược', '"Chien luoc" → "Chiến lược"'),
    Rule("D049", "diacritic", r'"Dieu kien\b', '"Điều kiện', '"Dieu kien" → "Điều kiện"'),
    Rule("D050", "diacritic", r'"Cong cu\b', '"Công cụ', '"Cong cu" → "Công cụ"'),
    Rule("D051", "diacritic", r'"Tro giup\b', '"Trợ giúp', '"Tro giup" → "Trợ giúp"'),
    Rule("D052", "diacritic", r'"Huong dan\b', '"Hướng dẫn', '"Huong dan" → "Hướng dẫn"'),
    Rule("D053", "diacritic", r'"Giai thich\b', '"Giải thích', '"Giai thich" → "Giải thích"'),
    Rule("D054", "diacritic", r'"Canh bao\b', '"Cảnh báo', '"Canh bao" → "Cảnh báo"'),
    Rule("D055", "diacritic", r'"Thong bao\b', '"Thông báo', '"Thong bao" → "Thông báo"'),
    Rule("D056", "diacritic", r'"Xac nhan\b', '"Xác nhận', '"Xac nhan" → "Xác nhận"'),
    Rule("D057", "diacritic", r'"Hoan tat\b', '"Hoàn tất', '"Hoan tat" → "Hoàn tất"'),
    Rule("D058", "diacritic", r'"Ket qua\b', '"Kết quả', '"Ket qua" → "Kết quả"'),
    Rule("D059", "diacritic", r'"Che do\b', '"Chế độ', '"Che do" → "Chế độ"'),
    Rule("D060", "diacritic", r'"Co dinh\b', '"Cố định', '"Co dinh" → "Cố định"'),
    Rule("D061", "diacritic", r'"Khoi dong\b', '"Khởi động', '"Khoi dong" → "Khởi động"'),
    Rule("D062", "diacritic", r'"Man hinh\b', '"Màn hình', '"Man hinh" → "Màn hình"'),
    Rule("D063", "diacritic", r'"Chi tiet\b', '"Chi tiết', '"Chi tiet" → "Chi tiết"'),
    Rule("D064", "diacritic", r'"Tong quan\b', '"Tổng quan', '"Tong quan" → "Tổng quan"'),
    Rule("D065", "diacritic", r'"Phan tich\b', '"Phân tích', '"Phan tich" → "Phân tích"'),
    Rule("D066", "diacritic", r'"Thong so\b', '"Thông số', '"Thong so" → "Thông số"'),
    Rule("D067", "diacritic", r'"Thoi gian\b', '"Thời gian', '"Thoi gian" → "Thời gian"'),
    Rule("D068", "diacritic", r'"Hien tai\b', '"Hiện tại', '"Hien tai" → "Hiện tại"'),
    Rule("D069", "diacritic", r'"Quet thi truong\b', '"Quét thị trường', '"Quet thi truong" → "Quét thị trường"'),
    Rule("D070", "diacritic", r'"Khoi luong\b', '"Khối lượng', '"Khoi luong" → "Khối lượng"'),
    Rule("D071", "diacritic", r'"Cap nhat\b', '"Cập nhật', '"Cap nhat" → "Cập nhật"'),
    Rule("D072", "diacritic", r'"So du\b', '"Số dư', '"So du" → "Số dư"'),
    Rule("D073", "diacritic", r'"Ky vong\b', '"Kỳ vọng', '"Ky vong" → "Kỳ vọng"'),
    Rule("D074", "diacritic", r'"Do lech\b', '"Độ lệch', '"Do lech" → "Độ lệch"'),
    Rule("D075", "diacritic", r'"Ty le\b', '"Tỷ lệ', '"Ty le" → "Tỷ lệ"'),
    Rule("D076", "diacritic", r'"Gioi han\b', '"Giới hạn', '"Gioi han" → "Giới hạn"'),
    Rule("D077", "diacritic", r'"Nguong\b', '"Ngưỡng', '"Nguong" → "Ngưỡng"'),
    Rule("D078", "diacritic", r'"Don gia\b', '"Đơn giá', '"Don gia" → "Đơn giá"'),
    Rule("D079", "diacritic", r'"Dong cua so\b', '"Đóng cửa sổ', '"Dong cua so" → "Đóng cửa sổ"'),
    Rule("D080", "diacritic", r'"Sao chep\b', '"Sao chép', '"Sao chep" → "Sao chép"'),
    Rule("D081", "diacritic", r'"Dan vao\b', '"Dán vào', '"Dan vao" → "Dán vào"'),
    Rule("D082", "diacritic", r'"Quay lai\b', '"Quay lại', '"Quay lai" → "Quay lại"'),
    Rule("D083", "diacritic", r'"Tiep tuc\b', '"Tiếp tục', '"Tiep tuc" → "Tiếp tục"'),
    Rule("D084", "diacritic", r'"Bat dau\b', '"Bắt đầu', '"Bat dau" → "Bắt đầu"'),
    Rule("D085", "diacritic", r'"Ket thuc\b', '"Kết thúc', '"Ket thuc" → "Kết thúc"'),
    Rule("D086", "diacritic", r'"Da luu\b', '"Đã lưu', '"Da luu" → "Đã lưu"'),
    Rule("D087", "diacritic", r'"Da xoa\b', '"Đã xóa', '"Da xoa" → "Đã xóa"'),
    Rule("D088", "diacritic", r'"Da them\b', '"Đã thêm', '"Da them" → "Đã thêm"'),
    Rule("D089", "diacritic", r'"Da cap nhat\b', '"Đã cập nhật', '"Da cap nhat" → "Đã cập nhật"'),
    Rule("D090", "diacritic", r'"Da gui\b', '"Đã gửi', '"Da gui" → "Đã gửi"'),
    Rule("D091", "diacritic", r'"Da dong\b', '"Đã đóng', '"Da dong" → "Đã đóng"'),
    Rule("D092", "diacritic", r'"Da huy\b', '"Đã hủy', '"Da huy" → "Đã hủy"'),
    Rule("D093", "diacritic", r'"Da chon\b', '"Đã chọn', '"Da chon" → "Đã chọn"'),
    Rule("D094", "diacritic", r'"Da ap dung\b', '"Đã áp dụng', '"Da ap dung" → "Đã áp dụng"'),
    Rule("D095", "diacritic", r'"Da xuat\b', '"Đã xuất', '"Da xuat" → "Đã xuất"'),
    Rule("D096", "diacritic", r'"Da sao chep\b', '"Đã sao chép', '"Da sao chep" → "Đã sao chép"'),
    Rule("D097", "diacritic", r'"Da dan\b', '"Đã dán', '"Da dan" → "Đã dán"'),
    Rule("D098", "diacritic", r'"Huy bo\b', '"Hủy bỏ', '"Huy bo" → "Hủy bỏ"'),
    Rule("D099", "diacritic", r'"Luu lai\b', '"Lưu lại', '"Luu lai" → "Lưu lại"'),
    Rule("D100", "diacritic", r'"Xoa bo\b', '"Xóa bỏ', '"Xoa bo" → "Xóa bỏ"'),
    Rule("D101", "diacritic", r'"Chon ma\b', '"Chọn mã', '"Chon ma" → "Chọn mã"'),
    Rule("D102", "diacritic", r'"Chon file\b', '"Chọn file', '"Chon file" → "Chọn file"'),
    Rule("D103", "diacritic", r'"Chon tat ca\b', '"Chọn tất cả', '"Chon tat ca" → "Chọn tất cả"'),
    Rule("D104", "diacritic", r'"Bo chon\b', '"Bỏ chọn', '"Bo chon" → "Bỏ chọn"'),
    Rule("D105", "diacritic", r'"Mo rong\b', '"Mở rộng', '"Mo rong" → "Mở rộng"'),
    Rule("D106", "diacritic", r'"Thu nho\b', '"Thu nhỏ', '"Thu nho" → "Thu nhỏ"'),
    Rule("D107", "diacritic", r'"Dong y\b', '"Đồng ý', '"Dong y" → "Đồng ý"'),
    Rule("D108", "diacritic", r'"Tu choi\b', '"Từ chối', '"Tu choi" → "Từ chối"'),
    Rule("D109", "diacritic", r'"Phong to\b', '"Phóng to', '"Phong to" → "Phóng to"'),
    Rule("D110", "diacritic", r'"Tim kiem\b', '"Tìm kiếm', '"Tim kiem" → "Tìm kiếm"'),
    Rule("D111", "diacritic", r'\bduoc ket noi\b', 'được kết nối', '"duoc ket noi" → "được kết nối"'),
    Rule("D112", "diacritic", r'\btao du lieu\b', 'tạo dữ liệu', '"tao du lieu" → "tạo dữ liệu"'),
    Rule("D113", "diacritic", r'\bbieu do\b', 'biểu đồ', '"bieu do" → "biểu đồ"'),
    Rule("D114", "diacritic", r'\btu ket qua\b', 'từ kết quả', '"tu ket qua" → "từ kết quả"'),
    Rule("D115", "diacritic", r'\bket qua quet\b', 'kết quả quét', '"ket qua quet" → "kết quả quét"'),
    Rule("D116", "diacritic", r'\bkhong crash\b', 'không crash', '"khong crash" → "không crash"'),
]

# ── Spelling errors ────────────────────────────────────────────────────
SPELLING_RULES: list[Rule] = [
    Rule("S001", "spelling", r"Trailling", "Trailing", '"Trailling" → "Trailing"'),
    Rule("S002", "spelling", r"Walk-Foward", "Walk-Forward", '"Walk-Foward" → "Walk-Forward"'),
    Rule("S003", "spelling", r"Reccomend", "Recommend", '"Reccomend" → "Recommend"'),
    Rule("S004", "spelling", r"occured", "occurred", '"occured" → "occurred"'),
    Rule("S005", "spelling", r"seperator", "separator", '"seperator" → "separator"'),
    Rule("S006", "spelling", r"liqudity", "liquidity", '"liqudity" → "liquidity"'),
    Rule("S007", "spelling", r"liquidty", "liquidity", '"liquidty" → "liquidity"'),
]

# ── All rules ──────────────────────────────────────────────────────────
ALL_RULES = NON_DIACRITIC_RULES + SPELLING_RULES


# ═══════════════════════════════════════════════════════════════════════════
# Scanner
# ═══════════════════════════════════════════════════════════════════════════


class Finding(NamedTuple):
    file: str
    line: int
    column: int
    rule: Rule
    matched_text: str


def scan_file(filepath: Path) -> list[Finding]:
    """Scan a single file for string quality issues."""
    findings: list[Finding] = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError, OSError):
        return findings

    for rule in ALL_RULES:
        # Pattern v1: inside double/single quotes (Python/JS strings)
        quoted_pattern = rf"""["'>(]\s*{rule.pattern}"""
        for match in re.finditer(quoted_pattern, content):
            if "Rule(" in content[max(0, match.start() - 20):match.start() + 20]:
                continue
            line_no = content[:match.start()].count("\n") + 1
            col = match.start() - (content[:match.start()].rfind("\n") + 1) + 1
            # Extract the actual matched text without the leading quote/bracket
            actual = match.group().lstrip("\"'>( ")
            findings.append(Finding(
                file=str(filepath.relative_to(PROJECT_ROOT)),
                line=line_no,
                column=col,
                rule=rule,
                matched_text=actual,
            ))

    return findings


def scan_project() -> list[Finding]:
    """Scan entire project for string quality issues."""
    all_findings: list[Finding] = []

    for filepath in PROJECT_ROOT.rglob("*"):
        # Skip directories
        if any(part in SKIP_DIRS for part in filepath.parts):
            continue
        # Skip non-matching extensions
        if filepath.suffix not in SCAN_EXTENSIONS and filepath.suffix:
            continue
        # Skip specific files
        if filepath.name in SKIP_FILES:
            continue
        # Skip self
        if filepath.resolve() == Path(__file__).resolve():
            continue

        all_findings.extend(scan_file(filepath))

    return sorted(all_findings, key=lambda f: (f.file, f.line))


def apply_fix(filepath: Path, finding: Finding) -> bool:
    """Attempt to auto-fix a finding. Returns True if fix was applied."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError, OSError):
        return False

    if finding.rule.fix:
        new_content = content.replace(finding.matched_text, finding.rule.fix)
        if new_content != content:
            filepath.write_text(new_content, encoding="utf-8")
            return True
    return False


def format_finding(f: Finding) -> str:
    return (
        f"  {f.file}:{f.line}:{f.column}  [{f.rule.id}] {f.rule.category}\n"
        f"    Found   : {f.matched_text}\n"
        f"    Expected: {f.rule.fix}\n"
        f"    Detail  : {f.rule.description}"
    )


def main() -> int:
    # Fix Windows console encoding
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Kiểm tra chất lượng chuỗi tiếng Việt")
    parser.add_argument("--fix", action="store_true", help="Tự động sửa các lỗi có thể sửa")
    parser.add_argument("--json", action="store_true", help="Xuất kết quả dạng JSON")
    parser.add_argument("--stats", action="store_true", help="Chỉ hiển thị thống kê")
    args = parser.parse_args()

    findings = scan_project()

    if args.stats:
        by_category: dict[str, int] = {}
        for f in findings:
            by_category[f.rule.category] = by_category.get(f.rule.category, 0) + 1
        by_file: dict[str, int] = {}
        for f in findings:
            by_file[f.file] = by_file.get(f.file, 0) + 1

        print(f"Tổng số lỗi: {len(findings)}")
        print(f"\nTheo danh mục:")
        for cat, count in sorted(by_category.items()):
            print(f"  {cat}: {count}")
        print(f"\nTheo file (top 10):")
        for fname, count in sorted(by_file.items(), key=lambda x: -x[1])[:10]:
            print(f"  {fname}: {count}")
        return 0 if not findings else 1

    if args.json:
        import json
        result = []
        for f in findings:
            result.append({
                "file": f.file,
                "line": f.line,
                "column": f.column,
                "rule_id": f.rule.id,
                "category": f.rule.category,
                "matched": f.matched_text,
                "expected": f.rule.fix,
                "description": f.rule.description,
            })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not findings else 1

    if not findings:
        print("✅ Không phát hiện lỗi chuỗi tiếng Việt nào.")
        return 0

    print(f"🔍 Phát hiện {len(findings)} lỗi chuỗi:\n")

    if args.fix:
        fixed = 0
        for f in findings:
            filepath = PROJECT_ROOT / f.file
            if apply_fix(filepath, f):
                print(f"  ✅ Đã sửa: {f.file}:{f.line} — {f.rule.id}")
                fixed += 1
            else:
                print(f"  ⚠️  Cần sửa thủ công: {f.file}:{f.line} — {f.rule.id}")
                print(f"      {f.matched_text} → {f.rule.fix}")
        print(f"\nĐã tự động sửa: {fixed}/{len(findings)} lỗi.")
        return 0 if fixed == len(findings) else 1

    for f in findings:
        print(format_finding(f))
        print()

    print(f"Tổng: {len(findings)} lỗi.")
    print(f"Chạy với --fix để tự động sửa, hoặc --stats để xem thống kê.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
