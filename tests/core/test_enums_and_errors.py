import pickle

import pytest

from benin_business_id import (
    CheckStatus,
    DirectoryError,
    FailureReason,
    Ifu,
    InvalidIdentifierError,
    RccmRegister,
    TaxpayerType,
    UnavailableReason,
)
from benin_business_id._cleanup import PCRE_SPACE_CODE_POINTS


def members(
    enum: type[FailureReason | CheckStatus | UnavailableReason | RccmRegister],
) -> dict[str, str]:
    return {member.name: member.value for member in enum}


def test_defines_the_php_values_in_the_php_order() -> None:
    assert members(FailureReason) == {
        "INVALID_CHARACTERS": "invalid_characters",
        "INVALID_LENGTH": "invalid_length",
        "INVALID_CHECKSUM": "invalid_checksum",
        "UNKNOWN_TAXPAYER_TYPE": "unknown_taxpayer_type",
        "INVALID_YEAR": "invalid_year",
        "INVALID_COUNTRY": "invalid_country",
        "UNKNOWN_REGISTRY": "unknown_registry",
        "UNKNOWN_CATEGORY": "unknown_category",
        "INVALID_STRUCTURE": "invalid_structure",
    }
    assert members(CheckStatus) == {
        "FOUND": "found",
        "NOT_FOUND": "not_found",
        "INVALID_FORMAT": "invalid_format",
        "UNAVAILABLE": "unavailable",
    }
    assert members(RccmRegister) == {"COMPANIES": "companies", "ESTABLISHMENTS": "establishments"}


def test_defines_exactly_the_six_unavailable_reasons_in_order() -> None:
    assert list(members(UnavailableReason).items()) == [
        ("NO_SOURCE", "no_source"),
        ("DISABLED", "disabled"),
        ("TRANSPORT", "transport"),
        ("HTTP_STATUS", "http_status"),
        ("INVALID_JSON", "invalid_json"),
        ("SCHEMA", "schema"),
    ]


@pytest.mark.parametrize(
    ("digit", "taxpayer_type"),
    [
        (0, TaxpayerType.INDIVIDUAL),
        (1, TaxpayerType.INDIVIDUAL),
        (2, TaxpayerType.INDIVIDUAL),
        (3, TaxpayerType.COMPANY),
        (4, TaxpayerType.PUBLIC_ENTITY),
        (5, TaxpayerType.INTERNATIONAL_ORGANIZATION),
        (6, TaxpayerType.NGO),
    ],
)
def test_maps_taxpayer_digits(digit: int, taxpayer_type: TaxpayerType) -> None:
    assert TaxpayerType.from_digit(digit) is taxpayer_type


@pytest.mark.parametrize("digit", [-1, 7, 8, 9, 10])
def test_rejects_unsupported_taxpayer_digits(digit: int) -> None:
    with pytest.raises(InvalidIdentifierError) as caught:
        TaxpayerType.from_digit(digit)

    assert caught.value.reason is FailureReason.UNKNOWN_TAXPAYER_TYPE


@pytest.mark.parametrize("digit", [True, 1.0, "1", None])
def test_rejects_taxpayer_digits_that_are_not_ints(digit: object) -> None:
    with pytest.raises(TypeError):
        TaxpayerType.from_digit(digit)  # type: ignore[arg-type]


def test_invalid_identifier_errors_survive_pickle() -> None:
    error = InvalidIdentifierError(FailureReason.UNKNOWN_REGISTRY, "RCCM")
    clone = pickle.loads(pickle.dumps(error))

    assert isinstance(error, ValueError)
    assert clone.reason is FailureReason.UNKNOWN_REGISTRY
    assert str(clone) == "Invalid RCCM: unknown_registry."


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        (UnavailableReason.TRANSPORT, "The APIEx request failed before a response was received."),
        (UnavailableReason.HTTP_STATUS, "APIEx returned an unexpected HTTP status."),
        (UnavailableReason.INVALID_JSON, "APIEx returned invalid JSON."),
        (UnavailableReason.SCHEMA, "APIEx returned an unexpected response schema."),
    ],
)
def test_directory_errors_use_the_php_default_messages(
    reason: UnavailableReason, message: str
) -> None:
    error = DirectoryError(reason)
    clone = pickle.loads(pickle.dumps(DirectoryError(reason, "APIEx returned HTTP 503.")))

    assert str(error) == message
    assert error.reason is reason
    assert clone.reason is reason
    assert str(clone) == "APIEx returned HTTP 503."


def test_removes_exactly_the_pcre_spaces_dots_and_hyphens() -> None:
    # PHP's preg_replace('/[\s.\-]+/u', '') removes exactly these 28 code points (PHP 8.5).
    expected = {*PCRE_SPACE_CODE_POINTS, ord("."), ord("-")}

    assert len(expected) == 28
    assert {0x1C, 0x1D, 0x1E, 0x1F, 0x200B, 0xFEFF}.isdisjoint(expected)

    for code_point in range(0x110000):
        accepted = Ifu.is_valid(f"32024{chr(code_point)}44139959")

        assert accepted == (code_point in expected), hex(code_point)
