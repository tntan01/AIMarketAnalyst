"""Shared semantic renderer for QTextDocument and QLabel rich text.

Screen code may assemble content with legacy inline declarations while it is
being migrated.  The renderer removes those declarations from the delivered
HTML, maps legacy colors to the active semantic palette, and emits deterministic
CSS classes in one document-level stylesheet.
"""

from __future__ import annotations

from html import escape
import re
from typing import Protocol

from ui.theme import (
    ThemePalette,
    color_for_role,
    palette_for,
    semantic_role_for_color,
)
from ui.theme.fonts import QSS_BODY, QSS_NUMBER, QSS_SMALL, QSS_SUBTITLE, QSS_TITLE
from ui.theme_manager import current_palette


class _HtmlTarget(Protocol):
    def setHtml(self, html: str) -> None: ...


_TAG_RE = re.compile(
    r"<(?P<closing>/)?(?P<name>[A-Za-z][\w:-]*)(?P<attrs>[^<>]*)>",
    re.DOTALL,
)
_STYLE_ATTR_RE = re.compile(
    r"\s+style\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_CLASS_ATTR_RE = re.compile(
    r"\s+class\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_HEX_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
_RICH_MARKER = 'data-ama-rich-text="1"'


def _resolve_palette(
    *,
    theme: object | None = None,
    palette: ThemePalette | None = None,
) -> ThemePalette:
    if palette is not None:
        return palette
    if theme is not None:
        return palette_for(theme)
    return current_palette()


def _semanticize_css(css: str, palette: ThemePalette) -> str:
    def replace_color(match: re.Match[str]) -> str:
        literal = match.group(0)
        role = semantic_role_for_color(literal, default="")
        if not role:
            return literal
        return color_for_role(palette, role)

    return _HEX_RE.sub(replace_color, css)


def _extract_inline_classes(
    html: str,
    palette: ThemePalette,
) -> tuple[str, list[tuple[str, str]]]:
    styles: dict[str, str] = {}

    def replace_tag(match: re.Match[str]) -> str:
        if match.group("closing"):
            return match.group(0)
        name = match.group("name")
        attrs = match.group("attrs")
        style_match = _STYLE_ATTR_RE.search(attrs)
        if style_match is None:
            return match.group(0)

        declaration = _semanticize_css(
            " ".join(style_match.group("value").split()),
            palette,
        )
        class_name = styles.get(declaration)
        if class_name is None:
            class_name = f"rt-rule-{len(styles) + 1}"
            styles[declaration] = class_name

        attrs = _STYLE_ATTR_RE.sub("", attrs, count=1)
        class_match = _CLASS_ATTR_RE.search(attrs)
        if class_match is None:
            attrs = f'{attrs} class="{class_name}"'
        else:
            current = class_match.group("value").strip()
            combined = f"{current} {class_name}".strip()
            attrs = (
                attrs[: class_match.start()]
                + f' class="{combined}"'
                + attrs[class_match.end() :]
            )
        return f"<{name}{attrs}>"

    converted = _TAG_RE.sub(replace_tag, html)
    ordered = [(class_name, css) for css, class_name in styles.items()]
    return converted, ordered


def rich_text_css(
    palette: ThemePalette,
    generated_rules: list[tuple[str, str]] | None = None,
) -> str:
    """Build the common QTextDocument stylesheet for one active palette."""

    qss_body_bold = QSS_BODY.replace("font-weight: normal;", "font-weight: bold;")
    rules = [
        (
            ".rt-root",
            f"{QSS_BODY}"
            f"color:{palette.text};background:transparent;"
            "line-height:1.45;margin:0;",
        ),
        ("h1,h2,h3,h4", f"color:{palette.text};font-weight:700;"),
        ("h1", f"{QSS_TITLE}margin:0 0 12px;"),
        ("h2", f"{QSS_SUBTITLE}margin:16px 0 10px;"),
        ("h3", f"{qss_body_bold}margin:12px 0 8px;"),
        ("p", "margin:5px 0;"),
        ("ul,ol", "margin:5px 0;padding-left:22px;"),
        ("li", "margin:3px 0;"),
        (
            "table",
            f"{QSS_SMALL}width:100%;border-collapse:collapse;"
            "margin:0 0 14px;",
        ),
        (
            "th",
            f"color:{palette.text_muted};border-bottom:2px solid {palette.border};"
            "padding:7px 9px;text-align:left;font-weight:700;",
        ),
        (
            "td",
            f"color:{palette.text};border-bottom:1px solid {palette.border};"
            "padding:6px 9px;vertical-align:top;",
        ),
        ("code", f"{QSS_NUMBER}color:{palette.info};"),
        ("a", f"color:{palette.info};text-decoration:none;"),
        (".rt-muted", f"color:{palette.text_muted};"),
        (".rt-success", f"color:{palette.success};"),
        (".rt-warning", f"color:{palette.warning};"),
        (".rt-danger", f"color:{palette.danger};"),
        (".rt-info", f"color:{palette.info};"),
        (".rt-accent", f"color:{palette.accent};"),
        (
            ".rt-empty",
            f"color:{palette.text_muted};text-align:center;padding:32px;",
        ),
        (
            ".rt-warning-block",
            f"color:{palette.warning};background:{palette.surface_raised};"
            f"border:1px solid {palette.warning};padding:10px 12px;",
        ),
        (
            ".rt-danger-block",
            f"color:{palette.danger};background:{palette.surface_raised};"
            f"border:1px solid {palette.danger};padding:10px 12px;",
        ),
    ]
    rules.extend(
        (f".{class_name}", declaration)
        for class_name, declaration in generated_rules or []
    )
    return "\n".join(f"{selector}{{{declaration}}}" for selector, declaration in rules)


def compile_rich_html(
    fragment: object,
    *,
    theme: object | None = None,
    palette: ThemePalette | None = None,
) -> str:
    """Return a self-contained, class-based rich-text document.

    The function is idempotent so screen code can safely compile a formatter
    result before passing it through :func:`set_rich_html`.
    """

    raw = str(fragment or "")
    if _RICH_MARKER in raw:
        return raw
    resolved = _resolve_palette(theme=theme, palette=palette)
    converted, generated = _extract_inline_classes(raw, resolved)
    css = rich_text_css(resolved, generated)

    body_match = re.search(r"<body\b([^>]*)>", converted, re.IGNORECASE)
    if body_match is not None:
        body_attrs = body_match.group(1)
        class_match = _CLASS_ATTR_RE.search(body_attrs)
        if class_match is None:
            replacement = f'<body{body_attrs} class="rt-root">'
        else:
            existing = class_match.group("value").strip()
            updated = f"{existing} rt-root".strip()
            updated_attrs = (
                body_attrs[: class_match.start()]
                + f' class="{updated}"'
                + body_attrs[class_match.end() :]
            )
            replacement = f"<body{updated_attrs}>"
        converted = (
            converted[: body_match.start()]
            + replacement
            + converted[body_match.end() :]
        )
        style_block = f"<style>{css}</style>"
        if re.search(r"</head\s*>", converted, re.IGNORECASE):
            converted = re.sub(
                r"</head\s*>",
                style_block + "</head>",
                converted,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            converted = style_block + converted
        return converted.replace(
            "<html",
            f"<html {_RICH_MARKER}",
            1,
        )

    return (
        f'<!DOCTYPE html><html {_RICH_MARKER}><head><meta charset="utf-8">'
        f"<style>{css}</style></head><body class=\"rt-root\">"
        f"{converted}</body></html>"
    )


def set_rich_html(
    target: _HtmlTarget,
    fragment: object,
    *,
    theme: object | None = None,
    palette: ThemePalette | None = None,
) -> str:
    """Compile and apply rich text, returning the delivered HTML for tests."""

    document = compile_rich_html(fragment, theme=theme, palette=palette)
    target.setHtml(document)
    return document


def empty_state_html(
    message: object,
    *,
    tone: str = "muted",
    theme: object | None = None,
    palette: ThemePalette | None = None,
) -> str:
    """Build a common empty/error/waiting message without inline attributes."""

    role = str(tone or "muted").strip().lower()
    class_name = {
        "danger": "rt-danger-block",
        "error": "rt-danger-block",
        "warning": "rt-warning-block",
    }.get(role, "rt-empty")
    return compile_rich_html(
        f'<p class="{class_name}">{escape(str(message or ""))}</p>',
        theme=theme,
        palette=palette,
    )
