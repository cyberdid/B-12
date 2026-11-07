"""Background jobs for HTTP work; Qt widgets stay on the GUI thread."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from b12.desktop.client import DesktopApiError


class JobSignals(QObject):
    event = Signal(str, object)
    result = Signal(str, object)
    error = Signal(str, str)
    finished = Signal(object)


class ApiJob(QRunnable):
    """Run one synchronous API operation on Qt's thread pool."""

    def __init__(
        self,
        tag: str,
        operation: Callable[..., object],
        *,
        streaming: bool = False,
    ):
        super().__init__()
        self.tag = tag
        self.operation = operation
        self.streaming = streaming
        self.signals = JobSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            if self.streaming:
                result = self.operation(lambda event: self.signals.event.emit(self.tag, event))
            else:
                result = self.operation()
            self.signals.result.emit(self.tag, result)
        except DesktopApiError as exc:
            self.signals.error.emit(self.tag, exc.code)
        except Exception:
            self.signals.error.emit(self.tag, "internal_error")
        finally:
            self.signals.finished.emit(self)
