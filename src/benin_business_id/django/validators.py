from collections.abc import Mapping
from typing import TYPE_CHECKING, ClassVar, NoReturn

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

from benin_business_id import CheckStatus, FailureReason, Ifu, InvalidIdentifierError, Rccm
from benin_business_id.django._messages import IFU_MESSAGES, RCCM_MESSAGES
from benin_business_id.django.checkers import get_ifu_checker, get_rccm_checker

if TYPE_CHECKING:
    # Typing-only base that declares the deconstruct() method added by @deconstructible.
    from django.utils.deconstruct import _Deconstructible
    from django.utils.functional import _StrPromise
else:
    _Deconstructible = object


class _IdentifierValidator(_Deconstructible):
    _identifier_class: ClassVar[type[Ifu] | type[Rccm]]
    _messages: ClassVar[Mapping[str, "_StrPromise"]]

    def __call__(self, value: object) -> None:
        self._parse(value)

    def _parse(self, value: object) -> Ifu | Rccm:
        if isinstance(value, self._identifier_class):
            return value

        # Non-strings are never converted, like the Laravel rules of the PHP package.
        if not isinstance(value, str):
            self._fail(FailureReason.INVALID_CHARACTERS.value)

        try:
            return self._identifier_class(value)
        except InvalidIdentifierError as error:
            self._fail(error.reason.value, error)

    def _fail(self, key: str, cause: Exception | None = None) -> NoReturn:
        raise ValidationError(self._messages[key], code=key) from cause

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self)

    def __hash__(self) -> int:
        return hash(type(self))


@deconstructible
class IfuValidator(_IdentifierValidator):
    """Validate an IFU format. Raises ValidationError with the failure reason as its code."""

    _identifier_class = Ifu
    _messages = IFU_MESSAGES


@deconstructible
class RccmValidator(_IdentifierValidator):
    """Validate an RCCM format. Raises ValidationError with the failure reason as its code."""

    _identifier_class = Rccm
    _messages = RCCM_MESSAGES


class _ExistsValidator(_IdentifierValidator):
    def __init__(self, fail_when_unavailable: bool = False) -> None:
        self.fail_when_unavailable = fail_when_unavailable

    def __call__(self, value: object) -> None:
        status, enabled = self._check(self._parse(value))

        if status is CheckStatus.NOT_FOUND:
            self._fail("not_found")

        if status is CheckStatus.UNAVAILABLE and self.fail_when_unavailable:
            self._fail("unavailable" if enabled else "verification_disabled")

    def _check(self, identifier: Ifu | Rccm) -> tuple[CheckStatus, bool]:
        """Return the check status and whether online verification is enabled."""
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is type(self)
            and isinstance(other, _ExistsValidator)
            and other.fail_when_unavailable == self.fail_when_unavailable
        )

    def __hash__(self) -> int:
        return hash((type(self), self.fail_when_unavailable))


@deconstructible
class IfuExistsValidator(_ExistsValidator):
    """Check that an IFU exists, like the PHP package's IfuExistsRule.

    Invalid formats fail. As no authorised IFU source exists, a valid IFU is UNAVAILABLE: it
    passes by default and fails with fail_when_unavailable=True.
    """

    _identifier_class = Ifu
    _messages = IFU_MESSAGES

    def _check(self, identifier: Ifu | Rccm) -> tuple[CheckStatus, bool]:
        if not isinstance(identifier, Ifu):
            raise TypeError("IfuExistsValidator checks IFUs only")

        return get_ifu_checker().check(identifier).status, True


@deconstructible
class RccmExistsValidator(_ExistsValidator):
    """Check that an RCCM number is in the APIEx directory, like RccmExistsRule.

    Invalid formats and NOT_FOUND fail. UNAVAILABLE passes by default; with
    fail_when_unavailable=True it fails, with a dedicated message when online verification
    is disabled.
    """

    _identifier_class = Rccm
    _messages = RCCM_MESSAGES

    def _check(self, identifier: Ifu | Rccm) -> tuple[CheckStatus, bool]:
        if not isinstance(identifier, Rccm):
            raise TypeError("RccmExistsValidator checks RCCM numbers only")

        checker = get_rccm_checker()

        return checker.check(identifier).status, checker.enabled
