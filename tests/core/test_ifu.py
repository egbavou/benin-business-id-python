import copy
import dataclasses
import pickle

import pytest
from tests import cases

from benin_business_id import FailureReason, Ifu, InvalidIdentifierError, TaxpayerType
from benin_business_id._clock import current_year


@pytest.mark.parametrize(("raw", "value", "taxpayer_type", "year"), cases.valid_ifu())
def test_normalizes_valid_ifus_and_exposes_their_components(
    raw: str, value: str, taxpayer_type: TaxpayerType, year: int
) -> None:
    ifu = Ifu(raw)

    assert Ifu.is_valid(raw)
    assert Ifu.try_parse(raw) == ifu
    assert ifu.value == value
    assert ifu.format() == value
    assert str(ifu) == value
    assert ifu.taxpayer_type is taxpayer_type
    assert ifu.registration_year == year


@pytest.mark.parametrize(("raw", "reason"), cases.invalid_ifu())
def test_rejects_invalid_ifus_in_the_specified_check_order(raw: str, reason: FailureReason) -> None:
    assert not Ifu.is_valid(raw)
    assert Ifu.try_parse(raw) is None

    with pytest.raises(InvalidIdentifierError) as caught:
        Ifu(raw)

    assert caught.value.reason is reason
    assert str(caught.value) == f"Invalid IFU: {reason.value}."


def test_accepts_the_year_boundaries_without_a_checksum_or_sequence_restriction() -> None:
    for year in (2006, current_year()):
        for tail in ("00000000", "99999999"):
            assert Ifu.is_valid(f"3{year}{tail}")


def test_uses_the_current_utc_year(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("benin_business_id._clock.current_year", lambda: 2030)

    assert Ifu("3203000000000").registration_year == 2030
    assert Ifu.try_parse("3203100000000") is None


@pytest.mark.parametrize("value", [3202444139959, b"3202444139959", None, ["3202444139959"]])
def test_rejects_values_that_are_not_strings(value: object) -> None:
    for parse in (Ifu, Ifu.try_parse, Ifu.is_valid):
        with pytest.raises(TypeError):
            parse(value)  # type: ignore[arg-type]


def test_ignores_methods_overridden_by_a_str_subclass() -> None:
    class Tricky(str):
        def __str__(self) -> str:
            return "0000000000000"

        def translate(self, *args: object) -> str:
            return "0000000000000"

    ifu = Ifu(Tricky("3.201.200.247.219"))

    assert ifu.value == "3201200247219"
    assert type(ifu.value) is str


def test_behaves_like_an_immutable_value_object() -> None:
    ifu = Ifu("3.201.200.247.219")

    assert ifu == Ifu("3201200247219")
    assert hash(ifu) == hash(Ifu("3201200247219"))
    assert ifu != Ifu("3202444139959")
    assert repr(ifu) == "Ifu(value='3201200247219')"

    with pytest.raises(dataclasses.FrozenInstanceError):
        ifu.value = "3202444139959"  # type: ignore[misc]

    for clone in (copy.copy(ifu), copy.deepcopy(ifu), pickle.loads(pickle.dumps(ifu))):
        assert clone == ifu
        assert clone.taxpayer_type is TaxpayerType.COMPANY
        assert clone.registration_year == 2012


def test_revalidates_on_dataclass_replace() -> None:
    ifu = Ifu("3201200247219")

    replaced = dataclasses.replace(ifu, value="4.201.710.116.446")

    assert replaced.value == "4201710116446"
    assert replaced.taxpayer_type is TaxpayerType.PUBLIC_ENTITY

    with pytest.raises(InvalidIdentifierError):
        dataclasses.replace(ifu, value="7202400000000")
