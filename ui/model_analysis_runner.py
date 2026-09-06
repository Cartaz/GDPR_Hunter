from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.application.model_analysis_service import ModelAnalysisService
from ui.operation_errors import operation_error


class _ModelAnalysisWorker(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str, str)
    completed = Signal()

    def __init__(
        self,
        service: ModelAnalysisService,
        investigation_id: int,
        approved_by_user: bool,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._investigation_id = investigation_id
        self._approved_by_user = approved_by_user
        self._cancel_event = cancel_event if cancel_event is not None else threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.propose(
                self._investigation_id,
                approved_by_user=self._approved_by_user,
                cancel_requested=self._cancel_event.is_set,
            )
        except Exception as exc:  # noqa: BLE001 -- UI boundary must always return a terminal error
            code, message = operation_error(exc)
            self.failed.emit(self._investigation_id, code, message)
        else:
            self.succeeded.emit(self._investigation_id, result)
        finally:
            self.completed.emit()


class ModelAnalysisRunner(QObject):
    """Own one Qt worker thread for model analysis without blocking the GUI thread."""

    analysisStarted = Signal(int)
    analysisSucceeded = Signal(int, object)
    analysisFailed = Signal(int, str, str)

    def __init__(self, service: ModelAnalysisService) -> None:
        super().__init__()
        self._service = service
        self._stopping = False
        self._cancel_event = threading.Event()
        self._thread: QThread | None = None
        self._worker: _ModelAnalysisWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def start(self, investigation_id: int, *, approved_by_user: bool) -> bool:
        if self.is_busy or self._stopping:
            return False

        self._cancel_event.clear()
        thread = QThread(self)
        worker = _ModelAnalysisWorker(
            self._service,
            investigation_id,
            approved_by_user,
            self._cancel_event,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.succeeded.connect(self._relay_succeeded)
        worker.failed.connect(self._relay_failed)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        self.analysisStarted.emit(investigation_id)
        thread.start()
        return True

    @Slot(int, object)
    def _relay_succeeded(self, investigation_id: int, result: object) -> None:
        self.analysisSucceeded.emit(investigation_id, result)

    @Slot(int, str, str)
    def _relay_failed(
        self,
        investigation_id: int,
        code: str,
        message: str,
    ) -> None:
        self.analysisFailed.emit(investigation_id, code, message)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def request_stop(self) -> None:
        self._stopping = True
        self._cancel_event.set()
        if self._thread is not None:
            self._thread.requestInterruption()
            self._thread.quit()

    def shutdown(self) -> None:
        # Final safety net for application.quit/session teardown. Normal window
        # close uses nonblocking request_stop and waits for finished in the GUI.
        self.request_stop()
        if self._thread is not None:
            self._thread.wait()
