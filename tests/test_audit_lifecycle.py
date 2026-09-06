from __future__ import annotations

import contextlib
import http.server
import sqlite3
import subprocess
import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from core.application.bounded_network import NetworkDeadline, OperationCancelled
from core.application.inference_endpoint import InferenceEndpoint, InferenceLocation
from core.application.inference_service import InferenceService
from core.storage.sensitive_store import StorageIntegrityError
from ui.bridge import Bridge
from ui.model_analysis_runner import ModelAnalysisRunner, _ModelAnalysisWorker
from ui.research_runner import ResearchRunner, _ResearchMode, _ResearchWorker


@pytest.mark.parametrize("error", [sqlite3.OperationalError("private detail"), StorageIntegrityError("Integrity failure"), RuntimeError("private detail"), ValueError("Invalid input")])
@pytest.mark.parametrize("mode", ["model", "research", "local"])
def test_every_worker_failure_emits_one_failure_and_one_terminal_signal(error, mode):
    application = QCoreApplication.instance() or QCoreApplication([])
    assert application is not None

    class FailingService:
        def propose(self, *_args, **_kwargs):
            raise error

        research_artifact_urls = propose
        analyze_artifact = propose

    if mode == "model":
        worker = _ModelAnalysisWorker(FailingService(), 1, True)
    else:
        worker = _ResearchWorker(FailingService(), _ResearchMode.ARTIFACT_URLS if mode == "research" else _ResearchMode.LOCAL_ANALYSIS, 1, 2, True)
    failed = QSignalSpy(worker.failed)
    succeeded = QSignalSpy(worker.succeeded)
    completed = QSignalSpy(worker.completed)
    worker.run()
    assert failed.count() == completed.count() == 1
    assert succeeded.count() == 0
    assert "private detail" not in str(failed.at(0))


def test_refresh_failure_does_not_report_committed_mutation_as_failed():
    class Controller:
        writes = 0

        def set_display_name(self, value):
            self.writes += 1
            return {"displayName": value}

        def get_bootstrap_state(self):
            raise StorageIntegrityError("Check original archive key")

    controller = Controller()
    bridge = Bridge(controller, ResearchRunner(controller))
    assert bridge.getBootstrapState()["error"]["code"] == "STORAGE_INTEGRITY"
    result = bridge.setDisplayName("Name")
    assert result["ok"] is True
    assert "Do not repeat" in result["warning"]
    assert controller.writes == 1


@pytest.mark.parametrize("kind", ["model", "local"])
def test_cancel_retains_worker_ownership_until_finished(kind):
    application = QCoreApplication.instance() or QCoreApplication([])
    entered = threading.Event()
    release = threading.Event()

    class BlockingService:
        def propose(self, *_args, **_kwargs):
            entered.set()
            assert release.wait(2)
            return ()

        analyze_artifact = propose

    runner = ModelAnalysisRunner(BlockingService()) if kind == "model" else ResearchRunner(BlockingService())
    thread = None
    try:
        if kind == "model":
            assert runner.start(1, approved_by_user=True)
        else:
            assert runner.start_analysis(1, 2)
        assert entered.wait(1)
        thread = runner._thread
        start = time.monotonic()
        runner.request_stop()
        assert time.monotonic() - start < 0.1
        assert thread.isRunning()
        assert runner.is_busy
        release.set()
        runner.shutdown()
        assert not thread.isRunning()
        application.processEvents()
        assert not runner.is_busy
    finally:
        release.set()
        runner.shutdown()


def test_dns_deadline_terminates_and_reaps_resolver_process(monkeypatch):
    monkeypatch.setattr("core.application.bounded_network._DNS_SCRIPT", "import time; time.sleep(5)")
    processes = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr("core.application.bounded_network.subprocess.Popen", popen)
    start = time.monotonic()
    with NetworkDeadline(0.15) as deadline, pytest.raises(TimeoutError):
        deadline.resolve("example.test", 443)
    assert time.monotonic() - start < 1.5
    assert processes and processes[0].poll() is not None


@contextlib.contextmanager
def slow_server(*, trickle_headers=False, on_request=None):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            if on_request is not None:
                on_request.set()
            payload = b'{"choices":[{"message":{"content":"{}"}}]}'
            headers = f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n".encode()
            try:
                if trickle_headers:
                    for value in headers:
                        self.connection.sendall(bytes([value]))
                        time.sleep(0.025)
                else:
                    self.connection.sendall(headers)
                for value in payload:
                    self.connection.sendall(bytes([value]))
                    time.sleep(0.025)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.025))
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("trickle_headers", [False, True])
def test_inference_total_deadline_interrupts_trickling_response(trickle_headers):
    with slow_server(trickle_headers=trickle_headers) as port:
        service = InferenceService(InferenceEndpoint(f"http://127.0.0.1:{port}", InferenceLocation.LOCAL_PROCESS), timeout_seconds=0.15)
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            service.complete_json(model="m", system_prompt="system", user_prompt="synthetic")
        assert time.monotonic() - start < 1.0


def test_inference_cancellation_interrupts_socket_read():
    cancelled = threading.Event()
    with slow_server() as port:
        service = InferenceService(InferenceEndpoint(f"http://127.0.0.1:{port}", InferenceLocation.LOCAL_PROCESS), timeout_seconds=5)
        timer = threading.Timer(0.1, cancelled.set)
        timer.start()
        start = time.monotonic()
        try:
            with pytest.raises(OperationCancelled):
                service.complete_json(model="m", system_prompt="system", user_prompt="synthetic", cancel_requested=cancelled.is_set)
            assert time.monotonic() - start < 1.0
        finally:
            timer.cancel()
            timer.join()


def test_runner_cancellation_reaches_active_network_watchdog():
    application = QCoreApplication.instance() or QCoreApplication([])
    received = threading.Event()
    with slow_server(on_request=received) as port:
        inference = InferenceService(InferenceEndpoint(f"http://127.0.0.1:{port}", InferenceLocation.LOCAL_PROCESS), timeout_seconds=5)

        class Service:
            def propose(self, _id, *, approved_by_user, cancel_requested):
                inference.complete_json(model="m", system_prompt="system", user_prompt="synthetic", cancel_requested=cancel_requested)
                return ()

        runner = ModelAnalysisRunner(Service())
        failed = QSignalSpy(runner.analysisFailed)
        try:
            runner.start(1, approved_by_user=True)
            assert received.wait(1)
            start = time.monotonic()
            runner.request_stop()
            while runner.is_busy and time.monotonic() - start < 1:
                application.processEvents()
                time.sleep(0.005)
            assert not runner.is_busy
            assert failed.count() == 1
            assert failed.at(0)[1] == "CANCELLED"
        finally:
            runner.shutdown()
