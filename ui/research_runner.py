from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.application.app_controller import AppController

_LOG = logging.getLogger(__name__)


class _ResearchWorker(QObject):
    succeeded = Signal(int, int, object)
    failed = Signal(int, int, str, str)
    completed = Signal()

    def __init__(
        self,
        controller: AppController,
        investigation_id: int,
        artifact_id: int,
        approved_by_user: bool,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._investigation_id = investigation_id
        self._artifact_id = artifact_id
        self._approved_by_user = approved_by_user

    @Slot()
    def run(self) -> None:
        try:
            result = self._controller.research_artifact_urls(
                self._investigation_id,
                self._artifact_id,
                approved_by_user=self._approved_by_user,
            )
        except (ValueError, LookupError) as exc:
            self.failed.emit(
                self._investigation_id,
                self._artifact_id,
                "INVALID_INPUT",
                str(exc),
            )
        except (RuntimeError, PermissionError) as exc:
            _LOG.warning("Research operation failed")
            self.failed.emit(
                self._investigation_id,
                self._artifact_id,
                "RESEARCH_FAILED",
                str(exc),
            )
        except (OSError, sqlite3.Error):
            _LOG.exception("Research persistence or I/O operation failed")
            self.failed.emit(
                self._investigation_id,
                self._artifact_id,
                "RESEARCH_FAILED",
                "Research failed. Check the logs for details.",
            )
        else:
            self.succeeded.emit(self._investigation_id, self._artifact_id, result)
        finally:
            self.completed.emit()


class ResearchRunner(QObject):
    """Own one Qt worker thread for bounded research without blocking the GUI thread."""

    researchStarted = Signal(int, int)
    researchSucceeded = Signal(int, int, object)
    researchFailed = Signal(int, int, str, str)

    SHUTDOWN_WAIT_MS = 60_000

    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self._controller = controller
        self._thread: QThread | None = None
        self._worker: _ResearchWorker | None = None

    @property
    def is_busy(self) -> bool:
        return self._thread is not None

    def start(
        self,
        investigation_id: int,
        artifact_id: int,
        *,
        approved_by_user: bool,
    ) -> bool:
        if self.is_busy:
            return False

        thread = QThread(self)
        worker = _ResearchWorker(
            self._controller,
            investigation_id,
            artifact_id,
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
        self.researchStarted.emit(investigation_id, artifact_id)
        thread.start()
        return True

    @Slot(int, int, object)
    def _relay_succeeded(
        self,
        investigation_id: int,
        artifact_id: int,
        result: object,
    ) -> None:
        self.researchSucceeded.emit(investigation_id, artifact_id, result)

    @Slot(int, int, str, str)
    def _relay_failed(
        self,
        investigation_id: int,
        artifact_id: int,
        code: str,
        message: str,
    ) -> None:
        self.researchFailed.emit(investigation_id, artifact_id, code, message)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        thread = self._thread
        if thread is None:
            return
        thread.requestInterruption()
        # QThread lives in the GUI thread, so a worker->quit auto-connection may still
        # be queued when shutdown starts. Calling quit here before wait avoids blocking
        # the event loop that would otherwise have to deliver that queued call.
        thread.quit()
        if not thread.wait(self.SHUTDOWN_WAIT_MS):
            _LOG.error("Research worker did not stop within the bounded shutdown window")
