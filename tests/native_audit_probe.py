"""Run in an isolated QApplication process, with real HTML, bridge and temporary DB."""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.application.proposal_review_controller import ProposalReviewController
from core.storage.secret_store import SecretStore
from main import build_controller
from ui.bridge import Bridge
from ui.model_analysis_runner import ModelAnalysisRunner
from ui.research_runner import ResearchRunner
from ui.window import MainWindow


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    temporary = TemporaryDirectory()
    os.environ["XDG_DATA_HOME"] = temporary.name + "/data"
    os.environ["XDG_CONFIG_HOME"] = temporary.name + "/config"
    with patch.object(SecretStore, "get_or_create_master_key", return_value=b"a" * 32):
        controller, model, review, _settings = build_controller()
    controller.set_display_name("Original identity")
    approvals = []
    for number in (1, 2):
        target = controller.create_target(f"Example {number}", f"example{number}.test", f"privacy@example{number}.test")
        case = controller.create_case(target["id"], "ACCESS_PROVENANCE")
        approval = controller.approve_case_request(case["id"], None, (), approved_by_user=True)
        approvals.append(approval)
        if number == 1:
            controller.set_display_name("Changed identity")
            controller.approve_case_request(case["id"], None, (), approved_by_user=True)
        controller.submit_case(case["id"], approval["id"], "2026-09-01", "IT", confirmed_by_user=True)
    controller.record_case_response(1, "EMAIL", "2026-09-02", "sender", "Case ONE", "Response belonging to Case ONE", confirmed_by_user=True)
    research = ResearchRunner(controller)
    model_runner = ModelAnalysisRunner(model)
    bridge = Bridge(controller, research, model_runner, ProposalReviewController(review))
    window = MainWindow(bridge, Path(__file__).resolve().parents[1] / "ui" / "web", 1280, 820, runners=(research, model_runner))
    window.show()
    page = window._page
    steps = []

    def fail():
        traceback.print_exc()
        app.exit(1)

    def evaluate(code, callback):
        def checked(value):
            try:
                callback(value)
            except Exception:  # noqa: BLE001 -- test process must report callback failures
                fail()
        page.runJavaScript(code, checked)

    def wait_for(condition, callback, expires=None):
        expires = expires or time.monotonic() + 5

        def check(value):
            assert time.monotonic() < expires, f"UI timed out: {condition}"
            if value:
                callback()
            else:
                QTimer.singleShot(25, lambda: wait_for(condition, callback, expires))
        evaluate(condition, check)

    def click_case(case_id, label):
        return f"[...document.querySelectorAll('.case-record')].find(n=>n.textContent.includes('Case #{case_id} ·')).querySelectorAll('button').forEach(b=>{{if(b.textContent==={json.dumps(label)})b.click()}});"

    def next_step():
        if steps:
            steps.pop(0)()
        else:
            print("NATIVE_AUDIT_OK", flush=True)
            window.close()
            app.exit(0)

    def assert_js(condition):
        def checked(value):
            assert value, condition
            next_step()
        evaluate(condition, checked)

    def action(code, condition):
        evaluate(code, lambda _: wait_for(condition, next_step))

    steps.extend([
        lambda: assert_js("[...document.querySelectorAll('[hidden]')].every(n=>getComputedStyle(n).display==='none')"),
        lambda: action(click_case(1, "Responses"), "document.querySelector('#response-list button') !== null"),
        lambda: action("document.querySelector('#response-list button').click(); document.getElementById('response-body').value='DRAFT FOR CASE ONE';", "document.getElementById('response-detail-body').value==='Response belonging to Case ONE'"),
        lambda: action(click_case(2, "Responses"), "document.getElementById('response-panel-title').textContent.includes('Case #2')"),
        lambda: assert_js("document.getElementById('response-body').value==='' && document.getElementById('response-detail-body').value==='' && getComputedStyle(document.getElementById('response-detail')).display==='none'"),
        lambda: action(click_case(1, "Responses"), "document.getElementById('response-body').value==='DRAFT FOR CASE ONE'"),
        lambda: action(click_case(1, f"View payload #{approvals[0]['id']}"), "document.getElementById('approved-history-dialog').open"),
        lambda: assert_js(f"document.getElementById('approved-history-body').value==={json.dumps(approvals[0]['body'])} && document.getElementById('approved-history-body').readOnly"),
        lambda: action("document.getElementById('approved-history-dialog').close();", "!document.getElementById('approved-history-dialog').open"),
    ])

    def stale_responses():
        code = """
        import(new URL('./js/responses.js', location.href).href).then(({createResponsePanel})=>{
          const lists=[], details=[];
          const fake={listCaseResponses:(id,cb)=>lists.push([id,cb]), getCaseResponse:(id,cb)=>details.push([id,cb])};
          const panel=createResponsePanel({getBackend:()=>fake,getState:()=>({cases:[1,2].map(id=>({id,receivedOn:'2026-09-01',status:'AWAITING_RESPONSE',targetId:id}))}),targetName:()=>'',setStatus:()=>{},handleMutation:()=>{},localDateString:()=> '2026-09-02',makeButton:(label,fn)=>{const b=document.createElement('button');b.textContent=label;b.onclick=fn;return b;},clearNode:n=>n.replaceChildren()});
          panel.open(1); panel.open(2);
          lists[0][1]([{id:99,caseId:1,channel:'EMAIL'}]);
          const oldListIgnored=document.querySelector('#response-list button')===null;
          panel.open(1); lists[2][1]([{id:99,caseId:1,channel:'EMAIL'}]);
          document.querySelector('#response-list button').click();
          panel.open(2); details[0][1]({id:99,caseId:1,body:'STALE SECRET',channel:'EMAIL'});
          window.auditStaleResult=oldListIgnored && document.getElementById('response-detail-body').value==='' && document.getElementById('response-detail').hidden;
        });
        """
        evaluate(code, lambda _: wait_for("window.auditStaleResult===true", next_step))

    steps.append(stale_responses)

    def close_while_busy():
        class BusyRunner:
            is_busy = True
            stopped = False

            def request_stop(self):
                self.stopped = True

        busy = BusyRunner()
        window._runners = (busy,)
        window.close()
        assert busy.stopped and window.isVisible()
        busy.is_busy = False
        QTimer.singleShot(150, lambda: evaluate("true", lambda _: finish_close()))

    def finish_close():
        assert not window.isVisible()
        next_step()

    steps.append(close_while_busy)
    page.loadFinished.connect(lambda ok: wait_for("document.querySelectorAll('.case-record').length===2", next_step) if ok else app.exit(1))
    QTimer.singleShot(15000, lambda: app.exit(2))
    result = app.exec()
    research.shutdown()
    model_runner.shutdown()
    temporary.cleanup()
    return result


if __name__ == "__main__":
    sys.exit(main())
