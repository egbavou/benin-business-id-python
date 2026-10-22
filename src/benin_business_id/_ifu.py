import re
from dataclasses import dataclass, field
from typing import Final, Self, final

from benin_business_id import _clock
from benin_business_id._cleanup import as_text, remove_separators
from benin_business_id._enums import FailureReason, TaxpayerType
from benin_business_id._errors import InvalidIdentifierError

_NON_DIGIT: Final = re.compile(r"[^0-9]")
_FIRST_YEAR: Final = 2006


@final
@dataclass(frozen=True, slots=True)
class Ifu:
    """A Beninese tax identifier (Identifiant Fiscal Unique).

    The constructor validates and normalizes its input, and raises InvalidIdentifierError
    when it does not follow the rule declared by the State: 13 digits, a taxpayer type from
    0 to 6, then a registration year from 2006 through the current year. The unpublished
    check digit is not verified.
    """

    value: str
    taxpayer_type: TaxpayerType = field(init=False, repr=False, compare=False)
    registration_year: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        digits = remove_separators(as_text(self.value, "Ifu"))

        if _NON_DIGIT.search(digits):
            raise InvalidIdentifierError(FailureReason.INVALID_CHARACTERS, "IFU")

        if len(digits) != 13:
            raise InvalidIdentifierError(FailureReason.INVALID_LENGTH, "IFU")

        taxpayer_type = TaxpayerType.from_digit(int(digits[0]))
        year = int(digits[1:5])

        if year < _FIRST_YEAR or year > _clock.current_year():
            raise InvalidIdentifierError(FailureReason.INVALID_YEAR, "IFU")

        object.__setattr__(self, "value", digits)
        object.__setattr__(self, "taxpayer_type", taxpayer_type)
        object.__setattr__(self, "registration_year", year)

    @classmethod
    def try_parse(cls, value: str) -> Self | None:
        """Return an Ifu, or None when the value is not a valid IFU."""
        try:
            return cls(value)
        except InvalidIdentifierError:
            return None

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return cls.try_parse(value) is not None

    def format(self) -> str:
        """Return the 13 digits: no official grouping exists."""
        return self.value

    def __str__(self) -> str:
        return self.value
