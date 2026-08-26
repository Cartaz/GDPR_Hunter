from __future__ import annotations

import threading

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from ui.research_runner import ResearchRunner


class FakeResearchController:
    def __init__(self) -> None:
        self.worker_thread_id: int | None = None

    def research_artifact_urls(
        self,
        investigation_id: int,
        artifact_id: int,
        *,
        approved_by_user: bool,
    ) -> dict[str, object]:
        assert investigation_id == 7
        assert artifact_id == 11
        assert approved_by_user is True
        self.worker_thread_id = threading.get_ident()
        return {"createdCount": 2, "evidence": []}


def test_research_runner_executes_use_case_off_calling_thread_and_returns_signal():
    application = QCoreApplication.instance() or QCoreApplication([])
    assert application is not None
    controller = FakeResearchController()
    runner = ResearchRunner(controller)  # type: ignore[arg-type]
    succeeded = QSignalSpy(runner.researchSucceeded)
    caller_thread_id = threading.get_ident()

    assert runner.start(7, 11) is True
    assert succeeded.wait(2_000)
    runner.shutdown()

    assert controller.worker_thread_id is not None
    assert controller.worker_thread_id != caller_thread_id
    assert succeeded.count() == 1
    arguments = succeeded.at(0)
    assert arguments[0] == 7
    assert arguments[1] == 11
    assert arguments[2]["createdCount"] == 2
