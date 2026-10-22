from typing import TYPE_CHECKING, Any, ClassVar

from django import forms
from django.core.exceptions import ValidationError

from benin_business_id import FailureReason, Ifu, InvalidIdentifierError, Rccm
from benin_business_id._php import trim
from benin_business_id.django._messages import IFU_MESSAGES, RCCM_MESSAGES

if TYPE_CHECKING:
    from django.utils.functional import _StrOrPromise

_REASONS = {reason.value for reason in FailureReason}


class _IdentifierField(forms.Field):
    _identifier_class: ClassVar[type[Ifu] | type[Rccm]]

    def to_python(self, value: Any) -> Ifu | Rccm | None:
        if value is None:
            return None

        if isinstance(value, self._identifier_class):
            return value

        # Non-strings are never converted, like the Laravel rules of the PHP package.
        if not isinstance(value, str):
            raise self._error(FailureReason.INVALID_CHARACTERS)

        # Like Laravel, a value that is blank after PHP's trim() is left to the required rule.
        if trim(value) == "":
            return None

        try:
            return self._identifier_class(value)
        except InvalidIdentifierError as error:
            raise self._error(error.reason) from error

    def prepare_value(self, value: Any) -> Any:
        if isinstance(value, self._identifier_class):
            return value.format()

        return value

    def has_changed(self, initial: Any, data: Any) -> bool:
        if self.disabled:
            return False

        try:
            return self.to_python(initial) != self.to_python(data)
        except ValidationError:
            return True

    def _error(self, reason: FailureReason) -> ValidationError:
        return ValidationError(self.error_messages[reason.value], code=reason.value)


class IfuField(_IdentifierField):
    """Form field whose cleaned value is an Ifu (or None when empty)."""

    _identifier_class = Ifu
    default_error_messages: ClassVar[dict[str, "_StrOrPromise"]] = {
        key: message for key, message in IFU_MESSAGES.items() if key in _REASONS
    }


class RccmField(_IdentifierField):
    """Form field whose cleaned value is an Rccm (or None when empty)."""

    _identifier_class = Rccm
    default_error_messages: ClassVar[dict[str, "_StrOrPromise"]] = {
        key: message for key, message in RCCM_MESSAGES.items() if key in _REASONS
    }
