import re
from dataclasses import dataclass, field
from typing import Final, Self, final

from benin_business_id import _clock
from benin_business_id._cleanup import as_text, ascii_upper, remove_separators
from benin_business_id._enums import FailureReason
from benin_business_id._errors import InvalidIdentifierError

ACTIVE_REGISTRIES: Final = frozenset(
    {"COT", "ABC", "PNO", "PKO", "ABY", "LKS", "NAT", "DGO", "KDI", "APL", "SVL"}
)
# Former registry codes, only valid for numbers registered through 2020.
FORMER_REGISTRIES: Final = frozenset({"PN", "PK", "ODH", "POB", "ALD"})
CATEGORIES: Final = frozenset({"A", "B", "C", "D", "E"})

_INVALID_CHARACTER: Final = re.compile(r"[^A-Z0-9/]")
_STRUCTURE: Final = re.compile(r"([A-Z]{2})/?([A-Z]{2,3})/?([0-9]{2}|[0-9]{4})/?([A-Z])/?([0-9]+)")
_FIRST_YEAR: Final = 1990
_LAST_FORMER_YEAR: Final = 2020


@final
@dataclass(frozen=True, slots=True)
class Rccm:
    """A Beninese trade register number (Registre du Commerce et du Crédit Mobilier).

    The constructor validates its input against the strict rule drawn from the official
    register and normalizes it to the register's own form, for example 'RB/COT/18 B 22272'.
    It raises InvalidIdentifierError otherwise.
    """

    value: str
    registry_code: str = field(init=False, repr=False, compare=False)
    year: int = field(init=False, repr=False, compare=False)
    category: str = field(init=False, repr=False, compare=False)
    sequence_number: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        value = ascii_upper(remove_separators(as_text(self.value, "Rccm")))

        if _INVALID_CHARACTER.search(value):
            raise InvalidIdentifierError(FailureReason.INVALID_CHARACTERS, "RCCM")

        if value == "":
            raise InvalidIdentifierError(FailureReason.INVALID_LENGTH, "RCCM")

        match = _STRUCTURE.fullmatch(value)

        if match is None:
            raise InvalidIdentifierError(FailureReason.INVALID_STRUCTURE, "RCCM")

        country, registry, year_input, category, sequence = match.groups()

        if len(sequence) > 6:
            raise InvalidIdentifierError(FailureReason.INVALID_LENGTH, "RCCM")

        if country != "RB":
            raise InvalidIdentifierError(FailureReason.INVALID_COUNTRY, "RCCM")

        former_registry = registry in FORMER_REGISTRIES

        if not former_registry and registry not in ACTIVE_REGISTRIES:
            raise InvalidIdentifierError(FailureReason.UNKNOWN_REGISTRY, "RCCM")

        if category not in CATEGORIES:
            raise InvalidIdentifierError(FailureReason.UNKNOWN_CATEGORY, "RCCM")

        current_year = _clock.current_year()
        year = int(year_input)

        if len(year_input) == 2:
            year += 1900 if year > current_year % 100 else 2000
        elif year > _LAST_FORMER_YEAR:
            raise InvalidIdentifierError(FailureReason.INVALID_YEAR, "RCCM")

        if year < _FIRST_YEAR or year > current_year:
            raise InvalidIdentifierError(FailureReason.INVALID_YEAR, "RCCM")

        if former_registry and year > _LAST_FORMER_YEAR:
            raise InvalidIdentifierError(FailureReason.UNKNOWN_REGISTRY, "RCCM")

        object.__setattr__(self, "value", f"RB/{registry}/{year_input} {category} {sequence}")
        object.__setattr__(self, "registry_code", registry)
        object.__setattr__(self, "year", year)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "sequence_number", sequence)

    @classmethod
    def try_parse(cls, value: str) -> Self | None:
        """Return an Rccm, or None when the value is not a valid RCCM number."""
        try:
            return cls(value)
        except InvalidIdentifierError:
            return None

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return cls.try_parse(value) is not None

    def format(self) -> str:
        """Return the register's form, for example 'RB/COT/18 B 22272'."""
        return self.value

    def __str__(self) -> str:
        return self.value
