from enum import StrEnum, unique


@unique
class FailureReason(StrEnum):
    """Why an identifier failed format validation. Values are stable snake_case error codes."""

    INVALID_CHARACTERS = "invalid_characters"
    INVALID_LENGTH = "invalid_length"
    # Kept for the shared convention of the business-id packages; never produced for Benin.
    INVALID_CHECKSUM = "invalid_checksum"
    UNKNOWN_TAXPAYER_TYPE = "unknown_taxpayer_type"
    INVALID_YEAR = "invalid_year"
    INVALID_COUNTRY = "invalid_country"
    UNKNOWN_REGISTRY = "unknown_registry"
    UNKNOWN_CATEGORY = "unknown_category"
    INVALID_STRUCTURE = "invalid_structure"


@unique
class TaxpayerType(StrEnum):
    """The taxpayer category encoded by the first digit of an IFU."""

    INDIVIDUAL = "individual"
    COMPANY = "company"
    PUBLIC_ENTITY = "public_entity"
    INTERNATIONAL_ORGANIZATION = "international_organization"
    NGO = "ngo"

    @classmethod
    def from_digit(cls, digit: int) -> "TaxpayerType":
        """Return the type for an IFU's first digit (0 to 6)."""
        from benin_business_id._errors import InvalidIdentifierError

        if isinstance(digit, bool) or not isinstance(digit, int):
            raise TypeError(f"digit must be an int, not {type(digit).__name__}")

        if digit in (0, 1, 2):
            return cls.INDIVIDUAL

        try:
            return _TYPES_BY_DIGIT[digit]
        except KeyError:
            raise InvalidIdentifierError(FailureReason.UNKNOWN_TAXPAYER_TYPE, "IFU") from None


_TYPES_BY_DIGIT = {
    3: TaxpayerType.COMPANY,
    4: TaxpayerType.PUBLIC_ENTITY,
    5: TaxpayerType.INTERNATIONAL_ORGANIZATION,
    6: TaxpayerType.NGO,
}


@unique
class CheckStatus(StrEnum):
    """The outcome of an existence check."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    INVALID_FORMAT = "invalid_format"
    UNAVAILABLE = "unavailable"


@unique
class UnavailableReason(StrEnum):
    """Why an existence check returned UNAVAILABLE."""

    NO_SOURCE = "no_source"
    DISABLED = "disabled"
    TRANSPORT = "transport"
    HTTP_STATUS = "http_status"
    INVALID_JSON = "invalid_json"
    SCHEMA = "schema"


@unique
class RccmRegister(StrEnum):
    """The APIEx register in which an RCCM number was found."""

    COMPANIES = "companies"
    ESTABLISHMENTS = "establishments"
