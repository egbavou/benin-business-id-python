"""Pydantic v2 integration: the PydanticIfu and PydanticRccm annotated types.

These are Annotated aliases, not classes: use the core Ifu and Rccm classes for isinstance()
checks. Existence is never checked here: a model must not make network calls while it
validates.
"""

from collections.abc import Callable, Mapping
from typing import Annotated, Final, LiteralString, TypeAlias, TypeVar

from pydantic import PlainSerializer, PlainValidator, WithJsonSchema
from pydantic_core import PydanticCustomError

from benin_business_id import FailureReason, Ifu, InvalidIdentifierError, Rccm

__all__ = ["PydanticIfu", "PydanticRccm"]

_Errors: TypeAlias = Mapping[FailureReason, tuple[LiteralString, LiteralString]]

# Error type and message for each failure reason the identifier can produce.
_IFU_ERRORS: Final[_Errors] = {
    FailureReason.INVALID_CHARACTERS: ("ifu_invalid_characters", "IFU must contain only digits"),
    FailureReason.INVALID_LENGTH: ("ifu_invalid_length", "IFU must contain 13 digits"),
    FailureReason.INVALID_CHECKSUM: ("ifu_invalid_checksum", "IFU is not valid"),
    FailureReason.UNKNOWN_TAXPAYER_TYPE: (
        "ifu_unknown_taxpayer_type",
        "IFU must start with a digit from 0 to 6",
    ),
    FailureReason.INVALID_YEAR: ("ifu_invalid_year", "IFU contains an invalid registration year"),
}

_RCCM_ERRORS: Final[_Errors] = {
    FailureReason.INVALID_CHARACTERS: (
        "rccm_invalid_characters",
        "RCCM number contains unauthorised characters",
    ),
    FailureReason.INVALID_LENGTH: (
        "rccm_invalid_length",
        "RCCM number does not have a valid length",
    ),
    FailureReason.INVALID_CHECKSUM: ("rccm_invalid_checksum", "RCCM number is not valid"),
    FailureReason.INVALID_STRUCTURE: (
        "rccm_invalid_structure",
        "RCCM number must have the form RB/COT/18 B 22272",
    ),
    FailureReason.INVALID_COUNTRY: ("rccm_invalid_country", "RCCM number must start with RB"),
    FailureReason.UNKNOWN_REGISTRY: (
        "rccm_unknown_registry",
        "RCCM number indicates an unknown registry",
    ),
    FailureReason.UNKNOWN_CATEGORY: (
        "rccm_unknown_category",
        "RCCM number must have a category letter from A to E",
    ),
    FailureReason.INVALID_YEAR: ("rccm_invalid_year", "RCCM number contains an invalid year"),
}

_Identifier = TypeVar("_Identifier", Ifu, Rccm)


def _validator(
    identifier_class: type[_Identifier], errors: _Errors
) -> Callable[[object], _Identifier]:
    def validate(value: object) -> _Identifier:
        if isinstance(value, identifier_class):
            return value

        # Non-strings are never converted, like the Laravel rules of the PHP package.
        if not isinstance(value, str):
            raise _error(errors, FailureReason.INVALID_CHARACTERS)

        try:
            return identifier_class(value)
        except InvalidIdentifierError as error:
            raise _error(errors, error.reason) from error

    return validate


def _error(errors: _Errors, reason: FailureReason) -> PydanticCustomError:
    error_type, message = errors[reason]
    return PydanticCustomError(error_type, message, {"reason": reason.value})


def _serialize(identifier: Ifu | Rccm) -> str:
    return identifier.value


PydanticIfu: TypeAlias = Annotated[
    Ifu,
    PlainValidator(_validator(Ifu, _IFU_ERRORS)),
    PlainSerializer(_serialize, return_type=str),
    # Input may contain separators, so the validation schema has no pattern.
    WithJsonSchema({"type": "string", "examples": ["3202444139959"]}, mode="validation"),
    WithJsonSchema({"type": "string", "pattern": "^[0-9]{13}$"}, mode="serialization"),
]

PydanticRccm: TypeAlias = Annotated[
    Rccm,
    PlainValidator(_validator(Rccm, _RCCM_ERRORS)),
    PlainSerializer(_serialize, return_type=str),
    WithJsonSchema({"type": "string", "examples": ["RB/COT/18 B 22272"]}, mode="validation"),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": "^RB/[A-Z]{2,3}/(?:[0-9]{2}|[0-9]{4}) [A-E] [0-9]{1,6}$",
        },
        mode="serialization",
    ),
]
