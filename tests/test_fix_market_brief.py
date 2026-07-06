"""
Test script: Verify Option A fix for market brief missing text bug.
Tests parse_market_brief() with the fixed looks_like_heading().
"""
import os
import sys
import re
from html import escape

# ============================================================
# Copy of FIXED parse_market_brief from scanner_screen.py
# ============================================================
def parse_market_brief(raw: str) -> list[dict]:
    SECTION_PATTERNS: list[tuple[str, str]] = [
        ("TỔNG QUAN", "🌍"),
        ("ƯU TIÊN", "⭐"),
        ("TRÁNH", "🚫"),
        ("RỦI RO", "🛡️"),
        ("CHỜ", "⏳"),
        ("KẾT LUẬN", "📌"),
    ]

    def match_heading(line: str) -> tuple[str, str] | None:
        upper = line.upper()
        for keyword, icon in SECTION_PATTERNS:
            if keyword in upper:
                cleaned = re.sub(r"^[\d\s.)\-•*#]+\s*", "", line)
                cleaned = cleaned.strip().rstrip(":").strip()
                if len(cleaned) > 60:
                    cleaned = cleaned[:60]
                return (cleaned, icon)
        return None

    def looks_like_heading(line: str) -> bool:
        """Quick check if a line is likely a heading (starts with number prefix like 1. or 2))."""
        stripped = line.strip()
        if len(stripped) > 80:
            return False
        # Must start with a number prefix: "1.", "2)", "3." etc.
        if not re.match(r"^\d+[.)]\s+", stripped):
            return False
        upper = stripped.upper()
        return any(kw in upper for kw, _ in SECTION_PATTERNS)

    lines = raw.splitlines()
    sections: list[dict] = []
    current_section: dict | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        cleaned = re.sub(r"^(\*{1,3}\s*|#{1,3}\s*)", "", stripped)

        heading_match = match_heading(cleaned)
        is_heading = heading_match is not None and looks_like_heading(cleaned)

        if is_heading:
            heading, icon = heading_match  # type: ignore[misc]
            current_section = {"title": heading, "icon": icon, "lines": []}
            sections.append(current_section)
            rest = re.sub(r"^[\d\s.)\-•#]+\s*", "", stripped)
            colon_idx = rest.find(":")
            if colon_idx > 0:
                after_colon = rest[colon_idx + 1:].strip()
                if after_colon:
                    current_section["lines"].append(after_colon)
        else:
            if current_section is not None:
                current_section["lines"].append(stripped)
            else:
                current_section = {
                    "title": "Bản tin",
                    "icon": "📊",
                    "lines": [stripped],
                }
                sections.append(current_section)

    # Fallback: if only 1 default "Bản tin" section, try harder to split
    if len(sections) == 1 and sections[0]["title"] == "Bản tin":
        content = "\n".join(sections[0]["lines"])
        parts = re.split(r"\n(?=\d+[.)]\s*[A-Za-zÀ-ỸĐ])", content)
        if len(parts) > 1:
            sections = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                hm = match_heading(part.split("\n")[0])
                if hm:
                    heading, icon = hm
                    body_lines = part.split("\n")
                    first = body_lines[0]
                    rest_first = re.sub(r"^[\d\s.)\-•#]+\s*", "", first)
                    colon_idx = rest_first.find(":")
                    if colon_idx > 0:
                        after = rest_first[colon_idx + 1:].strip()
                        if after:
                            body_lines = [after] + body_lines[1:]
                        else:
                            body_lines = body_lines[1:]
                    else:
                        body_lines = body_lines[1:]
                    body = "\n".join(line.strip() for line in body_lines if line.strip())
                    sections.append({"title": heading, "icon": icon, "lines": [body] if body else []})
                else:
                    sections.append({"title": "Bản tin", "icon": "📊", "lines": [part]})

    # Third fallback: continuous narrative without headings
    if len(sections) == 1:
        content = "\n".join(sections[0]["lines"])
        TRANSITIONS: list[tuple[str, str, str]] = [
            (r"(?:tuyệt\s*đối\s*)?(?:nên|hãy|cần|phải)\s*tránh", "NHÓM NÊN TRÁNH", "🚫"),
            (r"tránh\s*giao\s*dịch", "NHÓM NÊN TRÁNH", "🚫"),
            (r"rủi\s*ro\s*toàn\s*hệ\s*thống", "MỨC RỦI RO KHUYẾN NGHỊ", "🛡️"),
            (r"(?:mức|quản\s*trị)\s*rủi\s*ro", "MỨC RỦI RO KHUYẾN NGHỊ", "🛡️"),
            (r"(?:đang|còn)\s*chờ\s*(?:tín\s*hiệu|xác\s*nhận)", "SETUP ĐANG CHỜ", "⏳"),
            (r"các\s*mã\s*đang\s*chờ", "SETUP ĐANG CHỜ", "⏳"),
            (r"(?:nhóm|tập\s*trung)\s*(?:nên|đáng|cần)\s*(?:ưu\s*tiên|tập\s*trung|chú\s*ý)", "NHÓM NÊN ƯU TIÊN", "⭐"),
            (r"nên\s*tập\s*trung", "NHÓM NÊN ƯU TIÊN", "⭐"),
            (r"kết\s*luận", "KẾT LUẬN", "📌"),
        ]
        sentences = re.split(r"(?<=[.!?])\s+", content)
        if len(sentences) > 1:
            new_sections: list[dict] = []
            cur_title = sections[0]["title"]
            cur_icon = sections[0]["icon"]
            cur_lines: list[str] = []
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                matched = False
                for pattern, title, icon in TRANSITIONS:
                    if re.search(pattern, sent, re.IGNORECASE):
                        if cur_lines:
                            new_sections.append({"title": cur_title, "icon": cur_icon, "lines": list(cur_lines)})
                        cur_title = title
                        cur_icon = icon
                        cur_lines = [sent]
                        matched = True
                        break
                if not matched:
                    cur_lines.append(sent)
            if cur_lines:
                new_sections.append({"title": cur_title, "icon": cur_icon, "lines": cur_lines})
            if len(new_sections) > 1:
                sections = new_sections

    # Rename default first section
    if sections and sections[0]["title"] == "Bản tin":
        first_text = "\n".join(sections[0]["lines"]).lower()
        if any(kw in first_text for kw in ("thị trường hôm nay", "tổng quan", "xu hướng", "phiên")):
            sections[0]["title"] = "TỔNG QUAN PHIÊN"
            sections[0]["icon"] = "🌍"

    # Deduplicate consecutive sections with same title
    merged: list[dict] = []
    for s in sections:
        s_title = s["title"]
        if merged and merged[-1]["title"] == s_title:
            merged[-1]["lines"].extend(s["lines"])
        else:
            merged.append(s)

    formatted_sections = []
    for s in merged:
        content = "\n".join(s["lines"])
        formatted_sections.append({
            "title": s["title"],
            "icon": s["icon"],
            "content": content,
        })
    return formatted_sections


def run_tests():
    results = []
    passed = 0
    failed = 0

    def check(test_name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            passed += 1
            results.append(f"  PASS: {test_name}")
        else:
            failed += 1
            results.append(f"  FAIL: {test_name} — {detail}")

    # ================================================================
    # TEST 1: THE BUG IS FIXED — content lines with keywords NOT headings
    # ================================================================
    print("=" * 70)
    print("TEST 1: Content lines with keywords no longer treated as headings")
    print("=" * 70)

    raw = """1. TỔNG QUAN PHIÊN: Thị trường hôm nay sideway

Nên tránh giao dịch trong giờ đầu phiên Mỹ
Các cặp chính đang chờ tin CPI
Rủi ro chính hôm nay là CPI Mỹ công bố lúc 19:30"""

    sections = parse_market_brief(raw)
    all_content = "\n".join(s["content"] for s in sections)
    titles = [s["title"] for s in sections]

    check("1a: 'Nên tránh giao dịch...' appears in content (not lost)",
          "Nên tránh giao dịch trong giờ đầu phiên Mỹ" in all_content)
    check("1b: 'Các cặp chính đang chờ tin CPI' appears in content",
          "Các cặp chính đang chờ tin CPI" in all_content)
    check("1c: 'Rủi ro chính hôm nay...' appears in content",
          "Rủi ro chính hôm nay là CPI Mỹ" in all_content)
    check("1d: CPI đầy đủ preserved",
          "CPI Mỹ công bố lúc 19:30" in all_content)
    check("1e: Only proper headings create sections (not content lines)",
          len(sections) <= 2,
          f"Got {len(sections)} sections: {titles}")

    # ================================================================
    # TEST 2: Properly formatted headings still work
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 2: Properly formatted headings (1. HEADING:) still detected")
    print("=" * 70)

    proper_format = """1. TỔNG QUAN PHIÊN: Thị trường hôm nay USD mạnh

2. NHÓM NÊN ƯU TIÊN: BUY USD với EUR/USD và GBP/USD

3. NHÓM NÊN TRÁNH: JPY yếu nhưng BOJ can thiệp

4. MỨC RỦI RO KHUYẾN NGHỊ: Risk 1%, CPI lúc 19:30

5. SETUP ĐANG CHỜ: NZD/USD test kháng cự 0.6150"""

    sections = parse_market_brief(proper_format)

    check("2a: At least 4 sections detected", len(sections) >= 4,
          f"Got {len(sections)} sections")
    check("2b: TỔNG QUAN section exists",
          any("TỔNG QUAN" in s["title"].upper() for s in sections))
    check("2c: ƯU TIÊN section exists",
          any("ƯU TIÊN" in s["title"].upper() for s in sections))
    check("2d: TRÁNH section exists",
          any("TRÁNH" in s["title"].upper() for s in sections))

    all_content = "\n".join(s["content"] for s in sections)
    check("2e: Content for TỔNG QUAN preserved", "USD mạnh" in all_content)
    check("2f: Content for TRÁNH preserved", "BOJ" in all_content)
    check("2g: Content for CHỜ preserved", "NZD/USD" in all_content)

    # ================================================================
    # TEST 3: Keyword in content WITHOUT number prefix → NOT heading
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 3: Keyword in content without number prefix → stays content")
    print("=" * 70)

    keyword_in_content_cases = [
        "Hôm nay nên ưu tiên các cặp USD",           # "ƯU TIÊN" keyword
        "Tuyệt đối tránh GBP do tin Brexit",          # "TRÁNH" keyword
        "Rủi ro: CPI Mỹ lúc 19:30, cần cẩn trọng",   # "RỦI RO" keyword
        "Đang chờ tín hiệu từ H1 cho EUR/USD",        # "CHỜ" keyword
        "Kết luận: thị trường sideway, nên đứng ngoài", # "KẾT LUẬN" keyword
        "Tổng quan: 3 cặp ready, 5 cặp waiting",      # "TỔNG QUAN" keyword
    ]

    for case in keyword_in_content_cases:
        sections = parse_market_brief(f"1. TỔNG QUAN PHIÊN: Mở đầu\n\n{case}")
        all_content = "\n".join(s["content"] for s in sections)
        check(f"3: '{case[:40]}...' stays in content",
              case in all_content,
              f"Not found in: '{all_content[:100]}'")

    # ================================================================
    # TEST 4: Lines that look like headings but no keyword → not heading
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 4: Number prefix without keyword → not a heading")
    print("=" * 70)

    raw_no_keyword = """1. TỔNG QUAN PHIÊN: Mở đầu

1. đây là dòng bắt đầu bằng số nhưng không có keyword
2. dòng này cũng bắt đầu bằng số nhưng không có keyword
3. tiếp tục nội dung bình thường"""

    sections = parse_market_brief(raw_no_keyword)
    all_content = "\n".join(s["content"] for s in sections)

    check("4a: '1. đây là dòng...' preserved in content",
          "đây là dòng bắt đầu bằng số nhưng không có keyword" in all_content)
    check("4b: '2. dòng này...' preserved in content",
          "dòng này cũng bắt đầu bằng số nhưng không có keyword" in all_content)
    check("4c: '3. tiếp tục...' preserved in content",
          "tiếp tục nội dung bình thường" in all_content)

    # ================================================================
    # TEST 5: Edge cases
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 5: Edge cases")
    print("=" * 70)

    # Empty
    check("5a: Empty input → empty list", parse_market_brief("") == [])

    # Single line with keyword but no number prefix
    sections = parse_market_brief("Nên tránh tất cả các cặp JPY hôm nay")
    check("5b: Single content line → 1 section (not lost)",
          len(sections) == 1 and "Nên tránh tất cả các cặp JPY hôm nay" in sections[0]["content"])

    # Number prefix with format "1) HEADING:" (paren instead of dot)
    sections = parse_market_brief("1) TỔNG QUAN PHIÊN: USD tăng\nNội dung sau heading")
    check("5c: '1) HEADING:' format works",
          any("TỔNG QUAN" in s["title"].upper() for s in sections))
    all_c = "\n".join(s["content"] for s in sections)
    check("5d: Content after '1) HEADING:' preserved",
          "Nội dung sau heading" in all_c)

    # Very long line with keyword ( > 80 chars)
    long_line = "A" * 70 + " tránh " + "B" * 10  # > 80 chars, contains TRÁNH
    assert len(long_line) > 80
    sections = parse_market_brief(f"1. TỔNG QUAN PHIÊN: test\n{long_line}")
    all_c = "\n".join(s["content"] for s in sections)
    check("5e: Very long line with keyword stays content",
          long_line in all_c)

    # ================================================================
    # TEST 6: Realistic full AI responses (end-to-end)
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 6: End-to-end realistic AI responses")
    print("=" * 70)

    # Scenario A: AI follows format perfectly
    ai_good = """1. TỔNG QUAN PHIÊN: Hôm nay USD mạnh, DXY tăng 0.3%. Thị trường risk-off.

2. NHÓM NÊN ƯU TIÊN: BUY USD với EUR/USD, GBP/USD. EUR/USD entry 1.0850.

3. NHÓM NÊN TRÁNH: USD/JPY — BOJ có thể can thiệp. Spread rộng bất thường.

4. MỨC RỦI RO KHUYẾN NGHỊ: Risk 1% hôm nay. CPI lúc 19:30 — giảm 0.5% trước tin.

5. SETUP ĐANG CHỜ: NZD/USD test 0.6150 — chờ H1 đóng trên vùng này."""

    sections = parse_market_brief(ai_good)
    all_c = "\n".join(s["content"] for s in sections)
    must_have = ["DXY", "EUR/USD", "BOJ", "CPI", "NZD/USD", "risk-off", "1.0850"]
    for phrase in must_have:
        check(f"6a: '{phrase}' preserved (good format)",
              phrase in all_c, f"Missing '{phrase}'")

    # Scenario B: AI outputs free-form narrative (NO number prefixes)
    ai_narrative = """Thị trường hôm nay nghiêng về USD mạnh, DXY tăng nhẹ.
Các cặp EUR/USD và GBP/USD đang có xu hướng giảm tốt.

Hôm nay nên ưu tiên BUY USD, tập trung vào EUR/USD và GBP/USD.
Nên tránh USD/JPY vì có rủi ro can thiệp từ BOJ.

Mức rủi ro khuyến nghị: 1%, giảm còn 0.5% trước tin CPI lúc 19:30.
Các mã đang chờ: NZD/USD cần thêm xác nhận H1, AUD/USD chờ phá vỡ kháng cự."""

    sections = parse_market_brief(ai_narrative)
    all_c = "\n".join(s["content"] for s in sections)

    check("6b: Narrative: 'EUR/USD' preserved", "EUR/USD" in all_c)
    check("6c: Narrative: 'BOJ' preserved", "BOJ" in all_c)
    check("6d: Narrative: 'CPI' preserved", "CPI" in all_c)
    check("6e: Narrative: 'NZD/USD' preserved", "NZD/USD" in all_c)
    check("6f: Narrative: 'nên ưu tiên' stays content (not heading)",
          "nên ưu tiên BUY USD" in all_c)
    check("6g: Narrative: 'Nên tránh' stays content (not heading)",
          "Nên tránh USD/JPY" in all_c)
    check("6h: Narrative: 'rủi ro' stays content (not heading)",
          "rủi ro can thiệp" in all_c)

    # ================================================================
    # TEST 7: Verify source file has the fix applied
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 7: Source file verification")
    print("=" * 70)

    test_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(os.path.dirname(test_dir), "ui", "screens", "scanner_screen.py")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    # Extract looks_like_heading from source
    check("7a: Old len(stripped) < 60 check removed",
          "len(stripped) < 60" not in source)

    check("7b: New number prefix check present",
          r"^\d+[.)]\s+" in source)

    check("7c: Must start with number prefix logic present",
          'Must start with a number prefix' in source)

    # ================================================================
    # Summary
    # ================================================================
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} PASSED, {failed} FAILED out of {passed + failed} tests")
    print("=" * 70)
    for r in results:
        print(r)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
