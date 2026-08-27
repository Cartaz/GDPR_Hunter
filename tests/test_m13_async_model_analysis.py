from __future__ import annotations

import threading
import time

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.domain.model_proposal import ClaimProposal, ResearchEvidenceProposal
from ui.bridge import Bridge
from ui.model_analysis_runner import ModelAnalysisRunner
from ui.research_runner import ResearchRunner


class FakeModelAnalysisService:
    def __init__(self) -> None:
        self.worker_thread_id: int | None = None

    def propose(self, investigation_id: int, *, approved_by_user: bool):
        assert investigation_id == 7
        assert approved_by_user is True
        self.worker_thread_id = threading.get_ident()
        return (
            ClaimProposal("Example Ltd may control the campaign", (1, 2), 0.8),
            ResearchEvidenceProposal(2, "Review the cited evidence for further research."),
        )


class FakeController:
    def get_bootstrap_state(self):
        return {"milestone": "M13"}


class BusyModelRunner(QObject):
    analysisStarted = Signal(int)
    analysisSucceeded = Signal(int, object)
    analysisFailed = Signal(int, str, str)

    def start(self, _investigation_id: int, *, approved_by_user: bool) -> bool:
        assert approved_by_user is True
        return False


class SignalModelRunner(QObject):
    analysisStarted = Signal(int)
    analysisSucceeded = Signal(int, object)
    analysisFailed = Signal(int, str, str)

    def start(self, _investigation_id: int, *, approved_by_user: bool) -> bool:
        assert approved_by_user is True
        return True


def test_model_analysis_runner_executes_off_calling_thread_and_returns_proposals() -> None:
    application = QCoreApplication.instance() or QCoreApplication([])
    assert application is not None
    service = FakeModelAnalysisService()
    runner = ModelAnalysisRunner(service)  # type: ignore[arg-type]
    succeeded = QSignalSpy(runner.analysisSucceeded)
    caller_thread_id = threading.get_ident()

    try:
        assert runner.start(7, approved_by_user=True) is True
        assert runner.start(7, approved_by_user=True) is False
        deadline = time.monotonic() + 2.0
        while succeeded.count() == 0 and time.monotonic() < deadline:
            application.processEvents()
            time.sleep(0.01)

        assert service.worker_thread_id is not None
        assert service.worker_thread_id != caller_thread_id
        assert succeeded.count() == 1
        arguments = succeeded.at(0)
        assert arguments[0] == 7
        assert isinstance(arguments[1][0], ClaimProposal)
        assert isinstance(arguments[1][1], ResearchEvidenceProposal)
    finally:
        runner.shutdown()


def test_bridge_rejects_unapproved_or_busy_model_analysis() -> None:
    controller = FakeController()
    research_runner = ResearchRunner(controller)  # type: ignore[arg-type]
    bridge_without_model = Bridge(controller, research_runner)  # type: ignore[arg-type]

    unapproved = bridge_without_model.analyzeInvestigationWithModel(7, False)
    unavailable = bridge_without_model.analyzeInvestigationWithModel(7, True)

    assert unapproved["ok"] is False
    assert unapproved["error"]["code"] == "APPROVAL_REQUIRED"
    assert unavailable["ok"] is False
    assert unavailable["error"]["code"] == "CAPABILITY_UNAVAILABLE"

    bridge_busy = Bridge(
        controller,
        research_runner,
        BusyModelRunner(),  # type: ignore[arg-type]
    )
    busy = bridge_busy.analyzeInvestigationWithModel(7, True)
    assert busy["ok"] is False
    assert busy["error"]["code"] == "BUSY"


def test_bridge_serializes_typed_model_proposals_without_mutation() -> None:
    application = QCoreApplication.instance() or QCoreApplication([])
    assert application is not None
    controller = FakeController()
    research_runner = ResearchRunner(controller)  # type: ignore[arg-type]
    model_runner = SignalModelRunner()
    bridge = Bridge(
        controller,
        research_runner,
        model_runner,  # type: ignore[arg-type]
    )
    completed = QSignalSpy(bridge.modelAnalysisCompleted)

    model_runner.analysisSucceeded.emit(
        7,
        (
            ClaimProposal("Example Ltd may control the campaign", (1, 2), 0.8),
            ResearchEvidenceProposal(2, "Review evidence two."),
        ),
    )

    assert completed.count() == 1
    arguments = completed.at(0)
    assert arguments[0] == 7
    proposals = arguments[1]["proposals"]
    assert proposals == [
        {
            "kind": "CLAIM",
            "statement": "Example Ltd may control the campaign",
            "evidenceIds": [1, 2],
            "confidence": 0.8,
        },
        {
            "kind": "RESEARCH_EVIDENCE",
            "evidenceId": 2,
            "rationale": "Review evidence two.",
        },
    ]
