"""
Test script: Verify section title fix — heading shows only keyword,
not the AI commentary after the colon.
"""
import os
import sys
import re


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
                # Take only the part before the colon (heading keyword only, not AI commentary)
                colon_idx = cleaned.find(":")
                if colon_idx > 0:
                    cleaned = cleaned[:colon_idx]
                cleaned = cleaned.strip().rstrip(":").strip()
                if len(cleaned) > 60:
                    cleaned = cleaned[:60]
                return (cleaned, icon)
        return None

    def looks_like_heading(line: str) -> bool:
        stripped = line.strip()
        if len(stripped) > 80:
            return False
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

    # Fallback: if only 1 default section
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

    # Third fallback
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

    if sections and sections[0]["title"] == "Bản tin":
        first_text = "\n".join(sections[0]["lines"]).lower()
        if any(kw in first_text for kw in ("thị trường hôm nay", "tổng quan", "xu hướng", "phiên")):
            sections[0]["title"] = "TỔNG QUAN PHIÊN"
            sections[0]["icon"] = "🌍"

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
    # TEST 1: Heading title is keyword only (not AI commentary)
    # ================================================================
    print("=" * 70)
    print("TEST 1: Heading titles are keyword-only, no AI commentary")
    print("=" * 70)

    raw = """1. TỔNG QUAN PHIÊN: Thị trường hôm nay USD mạnh, DXY tăng 0.3%

2. NHÓM NÊN ƯU TIÊN: BUY USD với EUR/USD và GBP/USD. Entry đẹp.

3. NHÓM NÊN TRÁNH: JPY yếu nhưng BOJ can thiệp — tránh tất cả JPY

4. MỨC RỦI RO KHUYẾN NGHỊ: Risk 1% hôm nay, CPI lúc 19:30

5. SETUP ĐANG CHỜ: NZD/USD test kháng cự 0.6150, chờ nến H1"""

    sections = parse_market_brief(raw)

    check("1a: 5 sections detected", len(sections) == 5,
          f"Got {len(sections)} sections")

    expected_titles = [
        "TỔNG QUAN PHIÊN",
        "NHÓM NÊN ƯU TIÊN",
        "NHÓM NÊN TRÁNH",
        "MỨC RỦI RO KHUYẾN NGHỊ",
        "SETUP ĐANG CHỜ",
    ]

    for i, (sec, expected) in enumerate(zip(sections, expected_titles)):
        check(f"1b-{i}: Title is '{expected}'",
              sec["title"] == expected,
              f"Got: '{sec['title']}'")

    # Verify commentary is NOT in titles
    check("1c: 'USD mạnh' NOT in any title",
          not any("USD mạnh" in s["title"] for s in sections))
    check("1d: 'BUY USD' NOT in any title",
          not any("BUY USD" in s["title"] for s in sections))
    check("1e: 'BOJ' NOT in any title",
          not any("BOJ" in s["title"] for s in sections))

    # Verify commentary IS in content
    all_content = "\n".join(s["content"] for s in sections)
    check("1f: 'USD mạnh' preserved in content", "USD mạnh" in all_content)
    check("1g: 'BUY USD' preserved in content", "BUY USD" in all_content)
    check("1h: 'BOJ' preserved in content", "BOJ" in all_content)
    check("1i: 'CPI' preserved in content", "CPI" in all_content)
    check("1j: 'NZD/USD' preserved in content", "NZD/USD" in all_content)

    # ================================================================
    # TEST 2: Heading without content after colon (empty or missing)
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 2: Heading with no content after colon")
    print("=" * 70)

    raw2 = """1. TỔNG QUAN PHIÊN:
Thị trường hôm nay sideway, DXY không đổi.

2. NHÓM NÊN TRÁNH:
Tất cả JPY do BOJ can thiệp."""

    sections = parse_market_brief(raw2)

    check("2a: TỔNG QUAN title clean", sections[0]["title"] == "TỔNG QUAN PHIÊN")
    check("2b: TRÁNH title clean", sections[1]["title"] == "NHÓM NÊN TRÁNH")
    check("2c: TỔNG QUAN content preserved", "sideway" in sections[0]["content"])
    check("2d: TRÁNH content preserved", "BOJ" in sections[1]["content"])

    # ================================================================
    # TEST 3: Heading without ANY colon (no inline content)
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 3: Heading without colon at all")
    print("=" * 70)

    raw3 = """1. TỔNG QUAN PHIÊN
Thị trường hôm nay không có biến động lớn.

2. NHÓM NÊN ƯU TIÊN
EUR/USD và GBP/USD đang có setup tốt."""

    sections = parse_market_brief(raw3)

    check("3a: TỔNG QUAN title clean (no colon)", sections[0]["title"] == "TỔNG QUAN PHIÊN")
    check("3b: ƯU TIÊN title clean (no colon)", sections[1]["title"] == "NHÓM NÊN ƯU TIÊN")
    check("3c: Content preserved", "EUR/USD" in sections[1]["content"])

    # ================================================================
    # TEST 4: Heading with colon at end (trailing colon, no content)
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 4: Heading with trailing colon, no inline content")
    print("=" * 70)

    raw4 = """1. TỔNG QUAN PHIÊN:
Thị trường hôm nay USD mạnh.

2. KẾT LUẬN:
Nên đứng ngoài chờ tin CPI."""

    sections = parse_market_brief(raw4)

    check("4a: TỔNG QUAN title clean (trailing colon)", sections[0]["title"] == "TỔNG QUAN PHIÊN")
    check("4b: KẾT LUẬN title clean (trailing colon)", sections[1]["title"] == "KẾT LUẬN")
    check("4c: Content preserved", "đứng ngoài" in sections[1]["content"])

    # ================================================================
    # TEST 5: Short headings match_heading still works
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 5: Various heading formats")
    print("=" * 70)

    format_cases = [
        ("1. TỔNG QUAN PHIÊN: test", "TỔNG QUAN PHIÊN"),
        ("1) NHÓM NÊN ƯU TIÊN: test", "NHÓM NÊN ƯU TIÊN"),
        ("2. NHÓM NÊN TRÁNH: test", "NHÓM NÊN TRÁNH"),
        ("3) MỨC RỦI RO KHUYẾN NGHỊ: test", "MỨC RỦI RO KHUYẾN NGHỊ"),
        ("4. SETUP ĐANG CHỜ: test", "SETUP ĐANG CHỜ"),
        ("5. KẾT LUẬN: test", "KẾT LUẬN"),
    ]

    for inp, expected_title in format_cases:
        sections = parse_market_brief(inp)
        check(f"5: '{inp[:30]}...' → title '{expected_title}'",
              len(sections) > 0 and sections[0]["title"] == expected_title,
              f"Got: '{sections[0]['title'] if sections else 'NO SECTIONS'}'")

    # ================================================================
    # TEST 6: Real-world AI response end-to-end
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 6: Real-world AI response end-to-end")
    print("=" * 70)

    full_ai = """1. TỔNG QUAN PHIÊN: Hôm nay USD mạnh, DXY tăng 0.3%. Thị trường risk-off nhẹ do lo ngại CPI.

2. NHÓM NÊN ƯU TIÊN: Tập trung BUY USD với EUR/USD entry 1.0850, GBP/USD entry 1.2700. Cả hai có M15 strict.

3. NHÓM NÊN TRÁNH: Tuyệt đối tránh USD/JPY — BOJ có thể can thiệp bất kỳ lúc nào. Spread rộng bất thường.

4. MỨC RỦI RO KHUYẾN NGHỊ: Risk 1% toàn hệ thống. Giảm còn 0.5% trước tin CPI 19:30.

5. SETUP ĐANG CHỜ: NZD/USD đang test kháng cự 0.6150. AUD/USD chờ phá vỡ 0.6700. Cần nến H1 xác nhận."""

    sections = parse_market_brief(full_ai)

    check("6a: 5 sections detected", len(sections) == 5,
          f"Got {len(sections)}")

    # All titles should be keyword-only
    for s in sections:
        check(f"6b: Title '{s['title']}' length <= 40 chars",
              len(s["title"]) <= 40,
              f"Title too long: '{s['title']}' ({len(s['title'])} chars)")

    # Critical content preserved
    all_c = "\n".join(s["content"] for s in sections)
    for phrase in ["DXY", "EUR/USD", "1.0850", "BOJ", "CPI", "NZD/USD", "M15 strict"]:
        check(f"6c: '{phrase}' in content", phrase in all_c)

    # No commentary in titles
    for s in sections:
        check(f"6d: Title '{s['title']}' contains no price/currency",
              not any(c in s["title"] for c in ["USD", "EUR", "GBP", "JPY", "1.08", "1.27"]),
              f"Title '{s['title']}' contains price/currency data")

    # ================================================================
    # TEST 7: Edge cases
    # ================================================================
    print("\n" + "=" * 70)
    print("TEST 7: Edge cases")
    print("=" * 70)

    # Colon inside the content part (e.g., DXY: tăng)
    raw_colon = "1. TỔNG QUAN PHIÊN: DXY: tăng 0.3%, VIX: giảm"
    sections = parse_market_brief(raw_colon)
    check("7a: Title stops at first colon", sections[0]["title"] == "TỔNG QUAN PHIÊN")
    check("7b: Content after first colon preserved",
          "DXY: tăng 0.3%, VIX: giảm" in sections[0]["content"])

    # Empty string
    check("7c: Empty input", parse_market_brief("") == [])

    # Heading with very long keyword text (edge case > 60 chars before colon)
    # This is unlikely in practice but should handle gracefully
    long_heading = "1. " + "A" * 50 + " TỔNG QUAN PHIÊN" + ": test content"
    sections = parse_market_brief(long_heading)
    check("7d: Long heading truncated to 60 chars",
          len(sections[0]["title"]) <= 60)

    # Source file check
    test_dir = os.path.dirname(os.path.abspath(__file__))
    source_path = os.path.join(os.path.dirname(test_dir), "ui", "screens", "scanner_screen.py")
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    check("7e: Cleaned[:colon_idx] logic in source",
          "cleaned[:colon_idx]" in source)
    check("7f: 'heading keyword only' comment in source",
          "heading keyword only" in source)

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
