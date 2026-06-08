from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
    HAS_WEBENGINE = False
else:
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        HAS_WEBENGINE = True
    except ImportError:
        HAS_WEBENGINE = False


class AnalysisChartView(QWidget):
    """Chart component wrapping QWebEngineView + Lightweight Charts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._payload: dict | None = None
        self._active_tf = "H1"
        self._page_loaded = False
        self._pending_script: str | None = None
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
        self._webview.setMinimumHeight(200)
        layout.addWidget(self._webview)

        # Bat quyen truy cap file local cho WebEngine (bat buoc de load JS local)
        settings = self._webview.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)

        # Load chart HTML voi base path de load duoc JS tu cung thu muc
        chart_html = Path(__file__).parent.parent.parent / "assets" / "chart" / "index.html"
        if chart_html.exists():
            html_content = chart_html.read_text(encoding='utf-8')
            base_url = QUrl.fromLocalFile(str(chart_html.parent.resolve()) + '/')
            self._webview.loadFinished.connect(self._on_load_finished)
            self._webview.setHtml(html_content, base_url)
        else:
            self._webview.setHtml("<p style='color:#888;text-align:center;padding:40px;'>Khong tim thay file bieu do.</p>")

    def set_payload(self, payload: dict) -> None:
        """Set chart data from build_full_chart_payload()."""
        self._payload = payload
        if not HAS_WEBENGINE or not hasattr(self, "_webview"):
            return
        self._active_tf = str(payload.get("active_timeframe", "H1"))
        from ui.chart_bridge import chart_update_script
        self._run_chart_script(chart_update_script(payload))

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
        from ui.chart_bridge import chart_reload_script
        self._run_chart_script(chart_reload_script())

    def show_error(self, message: str) -> None:
        """Show error state."""
        if not HAS_WEBENGINE or not hasattr(self, "_webview"):
            return
        self._payload = None
        self._run_chart_script(f"if(window.showError){{window.showError({__import__('json').dumps(message)});}}")

    def _on_load_finished(self, ok: bool) -> None:
        self._page_loaded = ok
        if ok and self._pending_script:
            script = self._pending_script
            self._pending_script = None
            self._webview.page().runJavaScript(script)

    def _run_chart_script(self, script: str) -> None:
        if not self._page_loaded:
            self._pending_script = script
            return
        self._webview.page().runJavaScript(script)
