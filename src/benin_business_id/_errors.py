from typing import final

from benin_business_id._enums import FailureReason, UnavailableReason


@final
class InvalidIdentifierError(ValueError):
    """Raised when an IFU or RCCM fails format validation."""

    def __init__(self, reason: FailureReason, identifier: str) -> None:
        super().__init__(f"Invalid {identifier}: {reason.value}.")
        self._reason = reason
        self._identifier = identifier

    @property
    def reason(self) -> FailureReason:
        return self._reason

    def __reduce__(self) -> tuple[type["InvalidIdentifierError"], tuple[FailureReason, str]]:
        return (type(self), (self._reason, self._identifier))


_DEFAULT_DIRECTORY_MESSAGES = {
    UnavailableReason.TRANSPORT: "The APIEx request failed before a response was received.",
    UnavailableReason.HTTP_STATUS: "APIEx returned an unexpected HTTP status.",
    UnavailableReason.INVALID_JSON: "APIEx returned invalid JSON.",
}
_SCHEMA_MESSAGE = "APIEx returned an unexpected response schema."


@final
class DirectoryError(RuntimeError):
    """A technical failure of the APIEx directory, exposed through RccmCheckResult.failure."""

    def __init__(self, reason: UnavailableReason, message: str | None = None) -> None:
        if message is None:
            message = _DEFAULT_DIRECTORY_MESSAGES.get(reason, _SCHEMA_MESSAGE)

        super().__init__(message)
        self._reason = reason
        self._message = message

    @property
    def reason(self) -> UnavailableReason:
        return self._reason

    def __reduce__(self) -> tuple[type["DirectoryError"], tuple[UnavailableReason, str]]:
        return (type(self), (self._reason, self._message))
