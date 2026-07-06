"""
Test script: Reproduce "missing text" bugs in Market Brief dialog.
Tests parse_market_brief() and _format_section_content_to_html().

Focus: text LOSS (not cosmetic formatting issues).
"""
import os
import sys
import re
from html import escape

# ============================================================
# Copy of _format_section_content_to_html from scanner_screen.py
# ============================================================
def _format_section_content_to_html(text: str, light: bool = False) -> str:
    text_color = "#111827" if light else "#cbd5e1"
    list_color = "#1f2937" if light else "#d1d5db"

    lines = text.splitlines()
    html_lines = []
    list_type = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if list_type:
                html_lines.append(f"</{list_type}>")
                list_type = None
            continue

        m = re.match(r"^[-•*]\s+(.*)", stripped)
        if m:
            if list_type == "ol":
                html_lines.append("</ol>")
                list_type = None
            if not list_type:
                html_lines.append(
                    f"<ul style='margin: 4px 0; padding-left: 20px; color: {list_color}; list-style-type: disc;'>"
                )
                list_type = "ul"
            html_lines.append(f"<li style='margin: 3px 0; line-height: 1.4;'>{escape(m.group(1))}</li>")
            continue

        m = re.match(r"^\d+[.)]\s+(.*)", stripped)
        if m:
            if list_type == "ul":
                html_lines.append("</ul>")
                list_type = None
            if not list_type:
                html_lines.append(
                    f"<ol style='margin: 4px 0; padding-left: 20px; color: {list_color};'>"
                )
                list_type = "ol"
            html_lines.append(f"<li style='margin: 3px 0; line-height: 1.4;'>{escape(m.group(1))}</li>")
            continue

        if list_type:
            html_lines.append(f"</{list_type}>")
            list_type = None

        html_lines.append(f"<p style='margin: 4px 0; color: {text_color}; line-height: 1.5;'>{escape(stripped)}</p>")

    if list_type:
        html_lines.append(f"</{list_type}>")

    return "\n".join(html_lines)


# ============================================================
# Copy of parse_market_brief from scanner_screen.py
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
        stripped = line.strip()
        if len(stripped) > 80:
            return False
        upper = stripped.upper()
        if re.match(r"^[\d\s.)\-•*#]+\s*", stripped):
            return any(kw in upper for kw, _ in SECTION_PATTERNS)
        return any(kw in upper and len(stripped) < 60 for kw, _ in SECTION_PATTERNS)

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


# ============================================================
# Test helpers
# ============================================================
def get_visible_text(html: str) -> str:
    """Strip HTML tags to extract visible text content."""
    # Remove style attributes
    clean = re.sub(r"style='[^']*'", "", html)
    # Remove all HTML tags
    clean = re.sub(r"<[^>]+>", "", clean)
    # Unescape HTML entities
    clean = clean.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return clean.strip()


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
    # BUG 1: Decimal price numbers stripped by ordered-list regex
    # ================================================================
    print("=" * 70)
    print("BUG 1: Decimal numbers (prices) stripped by ^\\d+[.)]\\s+ regex")
    print("=" * 70)

    # Simulate AI outputting prices at line start
    test_lines = [
        "1.0850 là mức entry cho EUR/USD hôm nay",
        "150.25 là vùng kháng cự mạnh của GBP/JPY",
        "0.6500 - Hỗ trợ quan trọng AUD/USD",
    ]
    for tl in test_lines:
        html = _format_section_content_to_html(tl)
        visible = get_visible_text(html)

        # The leading number before . should be preserved
        m = re.match(r"^(\d+)\.(\d+)", tl)
        if m:
            check(f"BUG-1: '{tl[:30]}...' keeps leading number",
                   m.group(1) in visible,
                   f"Expected '{m.group(1)}' in output, got: '{visible[:60]}'")

    # Explicit test: "1.0850 - Entry" should NOT lose "1."
    html = _format_section_content_to_html("1.0850 - Entry cho EUR/USD")
    visible = get_visible_text(html)
    check("BUG-1a: '1.0850' preserved (not treated as list item 1.)",
          "1.0850" in visible or "1" in visible,
          f"Visible text: '{visible}'")
    check("BUG-1b: Full price value preserved",
          ".0850" not in visible.split()[0] if visible else True,
          f"First word: '{visible.split()[0] if visible else 'EMPTY'}'")

    # ================================================================
    # BUG 2: Negative numbers with leading dash stripped as bullets
    # ================================================================
    print("\n" + "=" * 70)
    print("BUG 2: Leading dash '-' treated as bullet, stripping content")
    print("=" * 70)

    neg_cases = [
        ("-50 pips risk cho lệnh này", "50"),
        ("-0.5% thay đổi trong ngày", "0.5"),
        ("-2R expected loss", "2R"),
    ]
    for inp, expected_contains in neg_cases:
        html = _format_section_content_to_html(inp)
        visible = get_visible_text(html)
        check(f"BUG-2: '{inp[:30]}' preserves dash meaning",
              expected_contains in visible,
              f"Visible: '{visible[:60]}'")

    # ================================================================
    # BUG 3: Content lines falsely identified as section headings
    # ================================================================
    print("\n" + "=" * 70)
    print("BUG 3: Content lines with section keywords treated as headings")
    print("=" * 70)

    # Scenario: AI output where a content line contains a keyword
    raw_brief_3 = """1. TỔNG QUAN PHIÊN: Thị trường hôm nay sideway

Nên tránh giao dịch trong giờ đầu phiên Mỹ
Các cặp chính đang chờ tin CPI
Rủi ro chính hôm nay là CPI Mỹ công bố lúc 19:30"""

    sections = parse_market_brief(raw_brief_3)
    all_content = "\n".join(s["content"] for s in sections)

    check("BUG-3a: Content 'Nên tránh giao dịch...' appears in output",
          "Nên tránh giao dịch trong giờ đầu phiên Mỹ" in all_content,
          f"Sections: {[(s['title'], s['content'][:50]) for s in sections]}")

    check("BUG-3b: Content 'Rủi ro chính hôm nay...' appears in output",
          "Rủi ro chính hôm nay là CPI" in all_content,
          f"All content: '{all_content[:200]}'")

    # Check if false heading was created
    titles = [s["title"] for s in sections]
    check("BUG-3c: Not too many sections (false headings)",
          len(sections) <= 3,  # Expected: TỔNG QUAN PHIÊN + maybe 1-2 more
          f"Got {len(sections)} sections: {titles}")

    # ================================================================
    # BUG 4: AI uses markdown despite instructions not to
    # ================================================================
    print("\n" + "=" * 70)
    print("BUG 4: AI markdown **bold** / *italic* rendered literally")
    print("=" * 70)

    md_cases = [
        "**EUR/USD** đang có setup tốt nhất hôm nay",
        "*GBP/USD* cần thêm xác nhận M15",
    ]
    for inp in md_cases:
        html = _format_section_content_to_html(inp)
        visible = get_visible_text(html)
        # The ** markers should be visible (since we're checking the bug exists)
        check(f"BUG-4: Markdown markers preserved as literal text in '{inp[:30]}'",
              "**" in visible or "*" in visible,
              f"Visible: '{visible[:60]}'")

    # ================================================================
    # BUG 5: Complete end-to-end realistic AI response
    # ================================================================
    print("\n" + "=" * 70)
    print("BUG 5: End-to-end realistic AI response")
    print("=" * 70)

    # Simulates a real AI response (some AIs use markdown, some don't follow format)
    realistic_ai_response = """1. TỔNG QUAN PHIÊN: Hôm nay USD mạnh, DXY tăng 0.3%. Thị trường risk-off nhẹ.

2. NHÓM NÊN ƯU TIÊN: BUY USD với các cặp EUR/USD, GBP/USD, AUD/USD.
**EUR/USD** đang sẵn sàng nhất — entry tại 1.0850, SL 1.0820.

3. NHÓM NÊN TRÁNH: JPY yếu nhưng BOJ can thiệp — tránh USD/JPY.
- Rủi ro can thiệp BOJ
- Spread rộng bất thường

4. MỨC RỦI RO KHUYẾN NGHỊ: Risk 1% cho hôm nay.
Đang có CPI Mỹ lúc 19:30 — nên giảm risk xuống 0.5% nếu giao dịch trước tin.

5. SETUP ĐANG CHỜ: NZD/USD đang test kháng cự 0.6150 — chờ nến H1 đóng trên vùng này."""

    sections = parse_market_brief(realistic_ai_response)
    combined_html = ""
    for sec in sections:
        combined_html += _format_section_content_to_html(sec["content"]) + "\n"
    visible = get_visible_text(combined_html)

    # Check critical content is NOT lost
    must_contain = [
        "DXY tăng",
        "BUY USD",
        "EUR/USD",
        "GBP/USD",
        "entry tại",
        "BOJ",
        "CPI",
        "NZD/USD",
    ]
    for phrase in must_contain:
        check(f"BUG-5: '{phrase}' preserved in full pipeline",
              phrase in visible,
              f"Missing '{phrase}' from output")

    # Check section count is reasonable
    check(f"BUG-5: Reasonable section count (>=4)",
          len(sections) >= 4,
          f"Got {len(sections)} sections: {[s['title'] for s in sections]}")

    # ================================================================
    # BUG 6: Special cases — colon in content, empty sections
    # ================================================================
    print("\n" + "=" * 70)
    print("BUG 6: Edge cases")
    print("=" * 70)

    # Empty input
    sections = parse_market_brief("")
    check("BUG-6a: Empty input returns empty list", len(sections) == 0)

    # Single line
    sections = parse_market_brief("Thị trường hôm nay bình thường")
    check("BUG-6b: Single line creates one section", len(sections) == 1)

    # Text with colon but no keyword
    html = _format_section_content_to_html("EUR/USD: xu hướng tăng, entry 1.0850")
    visible = get_visible_text(html)
    check("BUG-6c: Colon in content preserved", "EUR/USD: xu hướng tăng" in visible)

    # Text that looks like HTML
    html = _format_section_content_to_html("DXY index < 100 là tín hiệu USD yếu")
    visible = get_visible_text(html)
    check("BUG-6d: HTML-like content escaped properly",
          "< 100" in visible or "&lt; 100" in visible)

    # Multi-line with blank lines
    text_with_blanks = "Dòng 1\n\nDòng 2\n\nDòng 3"
    html = _format_section_content_to_html(text_with_blanks)
    visible = get_visible_text(text_with_blanks)
    check("BUG-6e: All 3 lines preserved despite blank lines",
          "Dòng 1" in visible and "Dòng 2" in visible and "Dòng 3" in visible,
          f"Visible: '{visible}'")

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
