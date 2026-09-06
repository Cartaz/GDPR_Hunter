from __future__ import annotations

import threading
from enum import StrEnum

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.application.app_controller import AppController
from ui.operation_errors import operation_error


class _ResearchMode(StrEnum):
    LOCAL_ANALYSIS = "LOCAL_ANALYSIS"
    ARTIFACT_URLS = "ARTIFACT_URLS"
    MODEL_EVIDENCE = "MODEL_EVIDENCE"


class _ResearchWorker(QObject):
    succeeded = Signal(str, int, int, object)
    failed = Signal(str, int, int, str, str)
    completed = Signal()

    def __init__(
        self,
        controller: AppController,
        mode: _ResearchMode,
        investigation_id: int,
        target_id: int,
        approved_by_user: bool,
        cancel_event: threading.Event | None = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._mode = mode
        self._investigation_id = investigation_id
        self._target_id = target_id
        self._approved_by_user = approved_by_user
        self._cancel_event = cancel_event if cancel_event is not None else threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            if self._mode is _ResearchMode.LOCAL_ANALYSIS:
                result = self._controller.analyze_artifact(
                    self._investigation_id, self._target_id,
                    cancel_requested=self._cancel_event.is_set,
                )
            elif self._mode is _ResearchMode.ARTIFACT_URLS:
                result = self._controller.research_artifact_urls(
                    self._investigation_id,
                    self._target_id,
                    approved_by_user=self._approved_by_user,
                    cancel_requested=self._cancel_event.is_set,
                )
            else:
                result = self._controller.research_model_evidence(
                    self._investigation_id,
                    self._target_id,
                    approved_by_user=self._approved_by_user,
                    cancel_requested=self._cancel_event.is_set,
                )
        except Exception as exc:  # noqa: BLE001 -- UI boundary must always return a terminal error
            code, message = operation_error(exc)
            self.failed.emit(self._mode.value, self._investigation_id, self._target_id, code, message)
        else:
            self.succeeded.emit(
                self._mode.value,
                self._investigation_id,
                self._target_id,
                result,
            )
        finally:
            self.completed.emit()


class ResearchRunner(QObject):
    """Own one Qt worker thread for bounded research without blocking the GUI thread."""

    artifactAnalysisStarted = Signal(int, int)
    artifactAnalysisSucceeded = Signal(int, int, object)
    artifactAnalysisFailed = Signal(int, int, str, str)
    researchStarted = Signal(int, int)
    researchSucceeded = Signal(int, int, object)
    researchFailed = Signal(int, int, str, str)
    modelResearchStarted = Signal(int, int)
    modelResearchSucceeded = Signal(int, int, object)
    modelResearchFailed = Signal(int, int, str, str)

    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self._controller = controller
        self._stopping = False
        self._cancel_event = threading.Event()
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
        return self._start(
            _ResearchMode.ARTIFACT_URLS,
            investigation_id,
            artifact_id,
            approved_by_user=approved_by_user,
        )

    def start_analysis(self, investigation_id: int, artifact_id: int) -> bool:
        return self._start(_ResearchMode.LOCAL_ANALYSIS, investigation_id, artifact_id, approved_by_user=False)

    def start_model_evidence(
        self,
        investigation_id: int,
        evidence_id: int,
        *,
        approved_by_user: bool,
    ) -> bool:
        return self._start(
            _ResearchMode.MODEL_EVIDENCE,
            investigation_id,
            evidence_id,
            approved_by_user=approved_by_user,
        )

    def _start(
        self,
        mode: _ResearchMode,
        investigation_id: int,
        target_id: int,
        *,
        approved_by_user: bool,
    ) -> bool:
        if self.is_busy or self._stopping:
            return False

        self._cancel_event.clear()
        thread = QThread(self)
        worker = _ResearchWorker(
            self._controller,
            mode,
            investigation_id,
            target_id,
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
        if mode is _ResearchMode.LOCAL_ANALYSIS:
            self.artifactAnalysisStarted.emit(investigation_id, target_id)
        elif mode is _ResearchMode.ARTIFACT_URLS:
            self.researchStarted.emit(investigation_id, target_id)
        else:
            self.modelResearchStarted.emit(investigation_id, target_id)
        thread.start()
        return True

    @Slot(str, int, int, object)
    def _relay_succeeded(
        self,
        mode: str,
        investigation_id: int,
        target_id: int,
        result: object,
    ) -> None:
        if mode == _ResearchMode.LOCAL_ANALYSIS.value:
            self.artifactAnalysisSucceeded.emit(investigation_id, target_id, result)
        elif mode == _ResearchMode.ARTIFACT_URLS.value:
            self.researchSucceeded.emit(investigation_id, target_id, result)
        else:
            self.modelResearchSucceeded.emit(investigation_id, target_id, result)

    @Slot(str, int, int, str, str)
    def _relay_failed(
        self,
        mode: str,
        investigation_id: int,
        target_id: int,
        code: str,
        message: str,
    ) -> None:
        if mode == _ResearchMode.LOCAL_ANALYSIS.value:
            self.artifactAnalysisFailed.emit(investigation_id, target_id, code, message)
        elif mode == _ResearchMode.ARTIFACT_URLS.value:
            self.researchFailed.emit(investigation_id, target_id, code, message)
        else:
            self.modelResearchFailed.emit(investigation_id, target_id, code, message)

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
