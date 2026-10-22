from dataclasses import dataclass
from datetime import date, datetime
from typing import final

from benin_business_id._enums import CheckStatus, RccmRegister, UnavailableReason
from benin_business_id._ifu import Ifu
from benin_business_id._rccm import Rccm


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class IfuCheckResult:
    """The outcome of IfuChecker.check(). Created by the checkers only."""

    status: CheckStatus
    checked_at: datetime
    """When the check ran, timezone-aware, in UTC."""
    input: str
    """The string received, or the value of the Ifu received."""
    ifu: Ifu | None
    """The parsed identifier; None for INVALID_FORMAT."""
    unavailable_reason: UnavailableReason | None = None
    """Set exactly when the status is UNAVAILABLE."""


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class RccmCheckResult:
    """The outcome of RccmChecker.check(). Created by the checkers only.

    Business fields are set for FOUND only. Results from the establishments register never
    carry the owner's name, phone or email; results from the companies register are returned
    as APIEx publishes them.
    """

    status: CheckStatus
    checked_at: datetime
    """When the check ran, timezone-aware, in UTC."""
    input: str
    """The string received, or the value of the Rccm received."""
    rccm: Rccm | None
    """The parsed identifier; None for INVALID_FORMAT."""
    name: str | None = None
    trade_name: str | None = None
    creation_date: date | None = None
    municipality: str | None = None
    district: str | None = None
    phone: str | None = None
    email: str | None = None
    main_activity: str | None = None
    former_number: str | None = None
    register: RccmRegister | None = None
    unavailable_reason: UnavailableReason | None = None
    """Set exactly when the status is UNAVAILABLE."""
    failure: Exception | None = None
    """The exception behind a technical failure; None otherwise, including DISABLED."""
