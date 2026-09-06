"""Map errors at the UI boundary without leaking stored content or losing terminal signals."""
import logging

from core.application.research_service import ResearchCancelled
from core.storage.sensitive_store import StorageIntegrityError

_LOG = logging.getLogger(__name__)


def operation_error(error: Exception) -> tuple[str, str]:
    if isinstance(error, StorageIntegrityError):
        return "STORAGE_INTEGRITY", str(error)
    if isinstance(error, ResearchCancelled):
        return "CANCELLED", "Operation cancelled."
    if isinstance(error, PermissionError):
        return "APPROVAL_REQUIRED", str(error)
    if isinstance(error, (TypeError, ValueError, LookupError)):
        return "INVALID_INPUT", str(error)
    # Record the failure type and call stack, not arbitrary exception messages
    # which can contain model output, URLs or private response content.
    _LOG.error("Operation failed: %s", type(error).__name__, stack_info=True)
    return "OPERATION_FAILED", "Operation failed. Check the logs; retry only after resolving the cause."
