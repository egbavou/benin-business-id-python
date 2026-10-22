"""Offline validation of Beninese business identifiers (IFU, RCCM), with optional RCCM
existence checks against the public APIEx directory."""

from benin_business_id._checkers import AsyncIfuChecker, AsyncRccmChecker, IfuChecker, RccmChecker
from benin_business_id._enums import (
    CheckStatus,
    FailureReason,
    RccmRegister,
    TaxpayerType,
    UnavailableReason,
)
from benin_business_id._errors import DirectoryError, InvalidIdentifierError
from benin_business_id._ifu import Ifu
from benin_business_id._rccm import Rccm
from benin_business_id._results import IfuCheckResult, RccmCheckResult
from benin_business_id._settings import (
    DEFAULT_COMPANIES_URL,
    DEFAULT_ESTABLISHMENTS_URL,
    DEFAULT_TIMEOUT,
    ApiexSettings,
)

__all__ = [
    "DEFAULT_COMPANIES_URL",
    "DEFAULT_ESTABLISHMENTS_URL",
    "DEFAULT_TIMEOUT",
    "ApiexSettings",
    "AsyncIfuChecker",
    "AsyncRccmChecker",
    "CheckStatus",
    "DirectoryError",
    "FailureReason",
    "Ifu",
    "IfuCheckResult",
    "IfuChecker",
    "InvalidIdentifierError",
    "Rccm",
    "RccmCheckResult",
    "RccmChecker",
    "RccmRegister",
    "TaxpayerType",
    "UnavailableReason",
]
