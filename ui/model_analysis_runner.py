from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.application.model_analysis_service import ModelAnalysisService

_LOG = logging.getLogger(__name__)


class _ModelAnalysisWorker(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str, str)
    completed = Signal()

    def __init__(
        self,
        service: ModelAnalysisService,
        investigation_id: int,
        approved_by_user: bool,
    ) -> None:
        super().__init__()
        self._service = service
        self._investigation_id = investigation_id
        self._approved_by_user = approved_by_user

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.propose(
                self._investigation_id,
                approved_by_user=self._approved_by_user,
            )
        except (ValueError, LookupError) as exc:
            self.failed.emit(self._investigation_id, "INVALID_INPUT", str(exc))
        except PermissionError as exc:
            self.failed.emit(self._investigation_id, "APPROVAL_REQUIRED", str(exc))
        except (ConnectionError, RuntimeError) as exc:
            _LOG.warning("Model analysis operation failed")
            self.failed.emit(self._investigation_id, "MODEL_ANALYSIS_FAILED", str(exc))
        except OSError:
            _LOG.exception("Model analysis I/O operation failed")
            self.failed.emit(
                self._investigation_id,
                "MODEL_ANALYSIS_FAILED",
                "Model analysis failed. Check the logs for details.",
            )
        else:
            self.succeeded.emit(self._investigation_id, result)
        finally:
            self.completed.emit()


class ModelAnalysisRunner(QObject):
    """Own one Qt worker thread for model analysis without blocking the GUI thread."""

    analysisStarted = Signal(int)
    analysisSucceeded = Signal(int, object)
    analysisFailed = Signal(int, str, str)

    SHUTDOWN_WAIT_MS = 180_000

    def __init__(self, service: ModelAnalysisService) -> None:
        super().__init__()
        self._service = service
        self._thread: QThread | None = None
        self._worker: _ModelAnalysisWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def start(self, investigation_id: int, *, approved_by_user: bool) -> bool:
        if self.is_busy:
            return False

        thread = QThread(self)
        worker = _ModelAnalysisWorker(
            self._service,
            investigation_id,
            approved_by_user,
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

    def shutdown(self) -> None:
        thread = self._thread
        if thread is None:
            return
        thread.requestInterruption()
        thread.quit()
        if not thread.wait(self.SHUTDOWN_WAIT_MS):
            _LOG.error("Model analysis worker did not stop within the bounded shutdown window")
