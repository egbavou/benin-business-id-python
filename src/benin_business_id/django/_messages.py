"""Messages of the PHP package's Laravel rules. Django gives validators no field name, so
"The :attribute field" becomes "This field"."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.utils.functional import _StrPromise

# Keys are FailureReason values plus the existence keys, like the Laravel translation keys.
# Messages are translated lazily, in the language active when the error is rendered.
IFU_MESSAGES: Final[Mapping[str, "_StrPromise"]] = {
    "invalid_characters": _("This field must contain only digits."),
    "invalid_length": _("This field must contain 13 digits."),
    "invalid_checksum": _("This field is not a valid IFU."),
    "unknown_taxpayer_type": _("This field must start with a digit from 0 to 6."),
    "invalid_year": _("This field contains an invalid registration year."),
    "not_found": _("The IFU specified could not be found."),
    "unavailable": _("The IFU specified cannot be verified at the moment."),
}

RCCM_MESSAGES: Final[Mapping[str, "_StrPromise"]] = {
    "invalid_characters": _("This field contains unauthorised characters."),
    "invalid_length": _("This field does not have the length of an RCCM number."),
    "invalid_checksum": _("This field is not a valid RCCM number."),
    "invalid_structure": _("This field must have the form RB/COT/18 B 22272."),
    "invalid_country": _("This field must start with RB."),
    "unknown_registry": _("This field indicates an unknown registry."),
    "unknown_category": _("This field must have a category letter from A to E."),
    "invalid_year": _("This field contains an invalid year."),
    "not_found": _("The RCCM number specified is absent from the APIEx directory."),
    "unavailable": _("The RCCM number specified cannot be verified at the moment."),
    "verification_disabled": _("Online verification of RCCM numbers is disabled."),
}
