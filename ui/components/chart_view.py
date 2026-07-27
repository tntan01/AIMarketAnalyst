from __future__ import annotations

import json
import os
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget
from ui.rich_text import empty_state_html
from ui.theme import ThemePalette, chart_palette
from ui.theme_manager import current_palette

if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
    HAS_WEBENGINE = False
else:
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        HAS_WEBENGINE = True
    except ImportError:
        HAS_WEBENGINE = False


def chart_bootstrap_html(source: str, palette: ThemePalette) -> str:
    """Inject the active theme before WebEngine performs its first paint."""

    colors = chart_palette(palette)
    theme_class = "light-theme" if palette.name == "light" else "dark-theme"
    themed = source.replace(
        '<html lang="vi">',
        f'<html lang="vi" class="{theme_class}">',
        1,
    ).replace("<body>", f'<body class="{theme_class}">', 1)
    bootstrap = (
        '<style id="ama-chart-bootstrap">'
        ":root{"
        f"--chart-background:{colors['background']};"
        f"--chart-text:{colors['text']};"
        f"--chart-muted:{colors['neutral']};"
        f"--chart-subtle:{colors['neutral']};"
        f"--chart-surface:{colors['surface']};"
        f"--chart-surface-hover:{colors['surfaceRaised']};"
        f"--chart-border:{colors['border']};"
        f"--chart-accent:{colors['accent']};"
        f"--chart-selection-text:{colors['selectionText']};"
        "}"
        "html,body,#chart-wrapper,#chart-container{"
        "background:var(--chart-background)!important;"
        "}"
        "</style>"
    )
    return themed.replace("</head>", bootstrap + "</head>", 1)


class AnalysisChartView(QWidget):
    """Chart component wrapping QWebEngineView + Lightweight Charts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AnalysisChartSurface")
        self._payload: dict | None = None
        self._active_tf = "D1"
        self._page_loaded = False
        self._pending_scripts: list[str] = []
        self._palette = current_palette()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        if not HAS_WEBENGINE:
            fallback = QLabel("Bieu do yeu cau PyQt6-WebEngine.\nCai: pip install PyQt6-WebEngine")
            fallback.setObjectName("EmptyText")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setWordWrap(True)
            layout.addWidget(fallback)
            return

        from PyQt6.QtWebEngineCore import QWebEngineSettings

        self._webview = QWebEngineView()
        self._webview.setObjectName("AnalysisChartWebView")
        self._webview.setMinimumHeight(200)
        self._set_page_background()
        layout.addWidget(self._webview)

        # Bat quyen truy cap file local cho WebEngine (bat buoc de load JS local)
        settings = self._webview.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

        # Load chart HTML voi base path de load duoc JS tu cung thu muc
        chart_html = Path(__file__).parent.parent.parent / "assets" / "chart" / "index.html"
        if chart_html.exists():
            html_content = chart_bootstrap_html(
                chart_html.read_text(encoding="utf-8"),
                self._palette,
            )
            base_url = QUrl.fromLocalFile(str(chart_html.parent.resolve()) + '/')
            self._webview.loadFinished.connect(self._on_load_finished)
            self._webview.setHtml(html_content, base_url)
        else:
            self._webview.setHtml(
                empty_state_html(
                    "Không tìm thấy file biểu đồ.",
                    tone="danger",
                )
            )

    def set_payload(self, payload: dict) -> None:
        """Set chart data from build_full_chart_payload()."""
        themed_payload = dict(payload)
        themed_payload["theme"] = self._palette.name
        themed_payload["palette"] = chart_palette(self._palette)
        self._payload = themed_payload
        if not HAS_WEBENGINE or not hasattr(self, "_webview"):
            return
        self._active_tf = str(themed_payload.get("active_timeframe", "D1"))
        from ui.chart_bridge import chart_update_script
        self._run_chart_script(chart_update_script(themed_payload))

    def switch_timeframe(self, tf: str) -> None:
        """Switch active timeframe."""
        self._active_tf = tf
        if not HAS_WEBENGINE or not hasattr(self, "_webview") or not self._payload:
            return
        from ui.chart_bridge import chart_switch_tf_script
        self._run_chart_script(chart_switch_tf_script(tf))

    def show_empty(self) -> None:
        """Show empty state."""
        if not HAS_WEBENGINE or not hasattr(self, "_webview"):
            return
        self._payload = None
        self._run_chart_script("if(window.showEmpty){window.showEmpty();}")

    def show_error(self, message: str) -> None:
        """Show error state."""
        if not HAS_WEBENGINE or not hasattr(self, "_webview"):
            return
        self._payload = None
        self._run_chart_script(
            f"if(window.showError){{window.showError({json.dumps(message)});}}"
        )

    def refresh_theme(self, palette: ThemePalette | None = None) -> None:
        """Refresh page chrome and chart colors without recreating the view."""

        self._palette = palette or current_palette()
        if not HAS_WEBENGINE or not hasattr(self, "_webview"):
            return
        self._set_page_background()
        from ui.chart_bridge import chart_theme_script

        palette_payload = chart_palette(self._palette)
        if self._payload is not None:
            self._payload["theme"] = self._palette.name
            self._payload["palette"] = palette_payload
        self._run_chart_script(
            chart_theme_script(self._palette.name, palette_payload)
        )
        if self._payload is not None:
            from ui.chart_bridge import chart_reload_script

            self._run_chart_script(chart_reload_script())

    def _set_page_background(self) -> None:
        if not hasattr(self, "_webview"):
            return
        self._webview.page().setBackgroundColor(
            QColor(self._palette.background)
        )

    def _on_load_finished(self, ok: bool) -> None:
        self._page_loaded = ok
        if ok and self._pending_scripts:
            scripts = list(self._pending_scripts)
            self._pending_scripts.clear()
            for script in scripts:
                self._webview.page().runJavaScript(script)

    def _run_chart_script(self, script: str) -> None:
        if not self._page_loaded:
            self._pending_scripts.append(script)
            return
        self._webview.page().runJavaScript(script)
