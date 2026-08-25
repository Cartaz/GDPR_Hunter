from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

from core.application.app_controller import AppController

_LOG = logging.getLogger(__name__)


class Bridge(QObject):
    stateChanged = Signal(object)
    operationFailed = Signal(str, str)

    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self._controller = controller

    @Slot(result="QVariant")
    def getBootstrapState(self) -> dict[str, object]:
        return self._controller.get_bootstrap_state()

    @Slot(str, result="QVariant")
    def setDisplayName(self, display_name: str) -> dict[str, object]:
        try:
            result = self._controller.set_display_name(display_name)
        except (ValueError, LookupError) as exc:
            return self._fail("INVALID_INPUT", str(exc))
        self.stateChanged.emit(self._controller.get_bootstrap_state())
        return {"ok": True, "result": result}

    @Slot(str, str, str, result="QVariant")
    def addIdentifier(self, kind: str, value: str, label: str) -> dict[str, object]:
        try:
            result = self._controller.add_identifier(kind, value, label or None)
        except (ValueError, LookupError) as exc:
            return self._fail("INVALID_INPUT", str(exc))
        self.stateChanged.emit(self._controller.get_bootstrap_state())
        return {"ok": True, "result": result}

    def _fail(self, code: str, message: str) -> dict[str, object]:
        _LOG.warning("Bridge operation failed: code=%s", code)
        self.operationFailed.emit(code, message)
        return {"ok": False, "error": {"code": code, "message": message}}
