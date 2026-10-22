import copy
import dataclasses
import pickle

import pytest
from tests import cases

from benin_business_id import FailureReason, InvalidIdentifierError, Rccm
from benin_business_id._clock import current_year

ACTIVE = ["COT", "ABC", "PNO", "PKO", "ABY", "LKS", "NAT", "DGO", "KDI", "APL", "SVL"]
FORMER = ["PN", "PK", "ODH", "POB", "ALD"]


@pytest.mark.parametrize(("raw", "value", "year"), cases.valid_rccm())
def test_normalizes_valid_rccms_and_preserves_year_spelling_and_leading_zeros(
    raw: str, value: str, year: int
) -> None:
    rccm = Rccm(raw)

    assert Rccm.is_valid(raw)
    assert Rccm.try_parse(raw) == rccm
    assert rccm.value == value
    assert rccm.format() == value
    assert str(rccm) == value
    assert rccm.year == year
    assert rccm.registry_code == value.split("/")[1]
    assert rccm.category == value.split(" ")[1]
    assert rccm.sequence_number == value.split(" ")[2]


@pytest.mark.parametrize(("raw", "reason"), cases.invalid_rccm())
def test_rejects_invalid_rccms_in_the_specified_check_order(
    raw: str, reason: FailureReason
) -> None:
    assert not Rccm.is_valid(raw)
    assert Rccm.try_parse(raw) is None

    with pytest.raises(InvalidIdentifierError) as caught:
        Rccm(raw)

    assert caught.value.reason is reason
    assert str(caught.value) == f"Invalid RCCM: {reason.value}."


def test_accepts_all_active_registries_and_all_former_registries_through_2020() -> None:
    short_year = f"{current_year() % 100:02d}"

    for registry in ACTIVE:
        assert Rccm.is_valid(f"RB/{registry}/{short_year} B 0")

    for registry in FORMER:
        assert Rccm.is_valid(f"RB/{registry}/2020 B 000000")
        assert not Rccm.is_valid(f"RB/{registry}/21 B 1")


def test_applies_the_dynamic_century_pivot_and_the_four_digit_year_boundaries() -> None:
    current = current_year()
    following = (current + 1) % 100
    previous_century = 1900 + following
    raw = f"RB/COT/{following:02d} B 1"

    assert Rccm(f"RB/COT/{current % 100:02d} B 1").year == current

    if previous_century < 1990:
        assert Rccm.try_parse(raw) is None
    else:
        assert Rccm(raw).year == previous_century

    assert Rccm("RB/COT/1990 B 1").year == 1990
    assert Rccm("RB/COT/2020 B 1").year == 2020
    assert Rccm.try_parse("RB/COT/1989 B 1") is None
    assert Rccm.try_parse(f"RB/COT/{current} B 1") is None


@pytest.mark.parametrize(
    ("year", "two_digits", "expected"),
    [(2089, "89", 2089), (2089, "90", 1990), (2089, "95", 1995), (2100, "00", 2000)],
)
def test_pivots_two_digit_years_on_the_current_year(
    monkeypatch: pytest.MonkeyPatch, year: int, two_digits: str, expected: int
) -> None:
    monkeypatch.setattr("benin_business_id._clock.current_year", lambda: year)

    assert Rccm(f"RB/COT/{two_digits} B 1").year == expected


def test_reads_a_two_digit_year_above_the_pivot_in_the_previous_century(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("benin_business_id._clock.current_year", lambda: 2026)

    assert Rccm("RB/COT/26 B 1").year == 2026
    # '27' is above the pivot, so it reads as 1927, which is before 1990.
    with pytest.raises(InvalidIdentifierError) as caught:
        Rccm("RB/COT/27 B 1")

    assert caught.value.reason is FailureReason.INVALID_YEAR


@pytest.mark.parametrize("letter", [chr(0x0131), chr(0x017F), chr(0x00DF)])
def test_uppercases_ascii_letters_only(letter: str) -> None:
    # str.upper() would turn these into I, S and SS; PHP's strtoupper() leaves them alone.
    with pytest.raises(InvalidIdentifierError) as caught:
        Rccm(f"RB/KD{letter}/22 B 137")

    assert caught.value.reason is FailureReason.INVALID_CHARACTERS


@pytest.mark.parametrize("value", [123, b"RB/COT/18 B 22272", None])
def test_rejects_values_that_are_not_strings(value: object) -> None:
    for parse in (Rccm, Rccm.try_parse, Rccm.is_valid):
        with pytest.raises(TypeError):
            parse(value)  # type: ignore[arg-type]


def test_behaves_like_an_immutable_value_object() -> None:
    rccm = Rccm("RB/COT/07-B-1432")

    assert rccm == Rccm("RB/COT/07 B 1432")
    assert hash(rccm) == hash(Rccm("rb cot 07 b 1432"))
    assert repr(rccm) == "Rccm(value='RB/COT/07 B 1432')"

    with pytest.raises(dataclasses.FrozenInstanceError):
        rccm.year = 2008  # type: ignore[misc]

    for clone in (copy.copy(rccm), copy.deepcopy(rccm), pickle.loads(pickle.dumps(rccm))):
        assert clone == rccm
        assert (clone.registry_code, clone.year, clone.category, clone.sequence_number) == (
            "COT",
            2007,
            "B",
            "1432",
        )

    assert dataclasses.replace(rccm, value="RB/LKS/2008-B-180").value == "RB/LKS/2008 B 180"

    with pytest.raises(InvalidIdentifierError):
        dataclasses.replace(rccm, value="RB/COT/24 M 12")
