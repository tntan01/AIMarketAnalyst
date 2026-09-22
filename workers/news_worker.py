"""NewsWorker — background wrapper for the two periodic News rounds (plan batch L2.7).

Contract §3 puts the workers of this domain at "bao bọc concurrency, không logic
nghiệp vụ" (wrap concurrency, no business logic): every slot here calls exactly
one ``NewsController`` method and turns its outcome into a signal, exactly like
``workers/ai_test_worker.py``.  It holds a ``QObject`` (no new ``QThread``
subclass — plan L2.7), and it owns the schedule: one ``QTimer`` per cadence,
whose intervals come from the controller's policy-derived properties (R4 — no
operational number in this file; only the milliseconds-per-minute/hour unit
conversion is local).

Two rounds exist in this layer — the ones §13 keeps on a timer:

* ``run_news_round`` → ``NewsController.poll_news`` (RSS poll,
  ``rss_poll_interval_minutes``).
* ``run_rates_round`` → ``NewsController.refresh_rates`` (FRED refresh,
  ``fred_refresh_hours``).

ForexFactory has no poll (Owner decision, contract §6.1/§13): its four turns are
event-driven and belong to the news screen (L3.3) and the app-startup turn
(L3.6) — so no FF timer and no startup turn is created here.  Nothing in this
batch calls ``start()`` either: the cadences are wired by the batches that own
those entry points (L3.2 screen / L3.6 boot), which keeps the current boot
behavior untouched (plan L2.7: "chưa bật lượt khởi động").

The caller follows the inherited thread khuôn (``ui/screens/settings_screen.py``
for ``AITestWorker``): build the worker, ``moveToThread(thread)``, connect
``thread.started`` to ``start`` (or to a one-shot round slot) and
``thread.finished`` to ``deleteLater``.  Because a round runs in the worker's
thread, a slow fetch never blocks the GUI.

Name note (deliberate): ``ui/screens/dashboard_screen.py`` still declares a
legacy ``NewsWorker`` (a QThread subclass on the old Dashboard news path).  The
collision is temporary and planned — contract §12 lists that class among the old
code removed at connect-time (a), while ``workers/news_worker.py`` is the
mandated file name of this layer (plan L2.7), keeping file name and class name
aligned as ``ai_test_worker.py`` does for ``AITestWorker``.  This batch touches
neither the old class nor its screen.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from controllers.news_controller import NewsController
from workers.base_worker import WorkerState

__all__ = ["NewsWorker"]

# Unit conversion only (the cadences themselves are policy values, R4).
_MINUTE_MS = 60_000
_HOUR_MS = 60 * _MINUTE_MS


class NewsWorker(QObject):
    """Runs the periodic News rounds in a background thread and owns their timers."""

    news_succeeded = pyqtSignal(object)  # RssCollectionResult
    news_failed = pyqtSignal(str)
    rates_succeeded = pyqtSignal(object)  # RateFetchResult
    rates_failed = pyqtSignal(str)

    def __init__(self, controller: NewsController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.state = WorkerState.IDLE

        # Timers are children of this worker, so they move with it to its thread
        # when the caller calls ``moveToThread`` (interval khuôn: minutes/hours
        # from the controller, converted to the milliseconds QTimer expects).
        self._news_timer = QTimer(self)
        self._news_timer.setInterval(controller.rss_poll_interval_minutes * _MINUTE_MS)
        self._news_timer.timeout.connect(self.run_news_round)

        self._rates_timer = QTimer(self)
        self._rates_timer.setInterval(controller.rates_refresh_hours * _HOUR_MS)
        self._rates_timer.timeout.connect(self.run_rates_round)

    # --- schedule (owned here; started by the batches that own the entry points) ---

    @property
    def news_interval_minutes(self) -> int:
        """RSS poll cadence actually programmed into the timer (policy key)."""
        return self._news_timer.interval() // _MINUTE_MS

    @property
    def rates_interval_hours(self) -> int:
        """FRED refresh cadence actually programmed into the timer (policy key)."""
        return self._rates_timer.interval() // _HOUR_MS

    @pyqtSlot()
    def start(self) -> None:
        """Start both periodic rounds (must be called from the worker's thread)."""
        self._news_timer.start()
        self._rates_timer.start()

    @pyqtSlot()
    def stop(self) -> None:
        """Stop both periodic rounds."""
        self._news_timer.stop()
        self._rates_timer.stop()

    # --- rounds (one controller call each, outcome broadcast as a signal) ---------

    @pyqtSlot()
    def run_news_round(self) -> None:
        """One text-news round; emits the typed result or the failure reason."""
        self.state = WorkerState.RUNNING
        try:
            result = self._controller.poll_news()
        except Exception as exc:
            self.state = WorkerState.FAILED
            self.news_failed.emit(str(exc))
            return
        self.state = WorkerState.FINISHED
        self.news_succeeded.emit(result)

    @pyqtSlot()
    def run_rates_round(self) -> None:
        """One policy-rate round; emits the typed result or the failure reason."""
        self.state = WorkerState.RUNNING
        try:
            result = self._controller.refresh_rates()
        except Exception as exc:
            self.state = WorkerState.FAILED
            self.rates_failed.emit(str(exc))
            return
        self.state = WorkerState.FINISHED
        self.rates_succeeded.emit(result)
