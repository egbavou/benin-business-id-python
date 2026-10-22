import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from tests import cases

from benin_business_id import FailureReason, Ifu, Rccm
from benin_business_id.pydantic import PydanticIfu, PydanticRccm


class Company(BaseModel):
    ifu: PydanticIfu
    rccm: PydanticRccm


class StrictCompany(BaseModel):
    model_config = ConfigDict(strict=True)

    ifu: PydanticIfu
    rccm: PydanticRccm


class OptionalCompany(BaseModel):
    ifu: PydanticIfu | None = None
    rccm: PydanticRccm | None = None


VALID = {"ifu": "3.201.200.247.219", "rccm": "RB/COT/07-B-1432"}


@pytest.mark.parametrize("model", [Company, StrictCompany])
def test_validates_strings_into_core_objects(model: type[BaseModel]) -> None:
    company = model.model_validate(VALID)

    assert company.ifu == Ifu("3201200247219")  # type: ignore[attr-defined]
    assert isinstance(company.rccm, Rccm)  # type: ignore[attr-defined]
    assert company.model_dump() == {"ifu": "3201200247219", "rccm": "RB/COT/07 B 1432"}
    assert company.model_dump_json() == '{"ifu":"3201200247219","rccm":"RB/COT/07 B 1432"}'


def test_validates_json_input() -> None:
    company = Company.model_validate_json('{"ifu":"3202444139959","rccm":"RB KDI 22 B 137"}')

    assert company.ifu.value == "3202444139959"
    assert company.rccm.value == "RB/KDI/22 B 137"


def test_returns_objects_of_the_right_type_unchanged() -> None:
    ifu = Ifu("3202444139959")
    rccm = Rccm("RB/COT/18 B 22272")
    company = Company(ifu=ifu, rccm=rccm)

    assert company.ifu is ifu
    assert company.rccm is rccm


@pytest.mark.parametrize(("raw", "reason"), cases.invalid_ifu())
def test_reports_each_ifu_failure_reason(raw: str, reason: FailureReason) -> None:
    with pytest.raises(ValidationError) as caught:
        Company(ifu=raw, rccm="RB/COT/18 B 22272")  # type: ignore[arg-type]

    (error,) = caught.value.errors()
    assert error["type"] == f"ifu_{reason.value}"
    assert error["ctx"] == {"reason": reason.value}
    assert error["loc"] == ("ifu",)
    assert not error["msg"].endswith(".")


@pytest.mark.parametrize(("raw", "reason"), cases.invalid_rccm())
def test_reports_each_rccm_failure_reason(raw: str, reason: FailureReason) -> None:
    with pytest.raises(ValidationError) as caught:
        Company(ifu="3202444139959", rccm=raw)  # type: ignore[arg-type]

    (error,) = caught.value.errors()
    assert error["type"] == f"rccm_{reason.value}"
    assert error["ctx"] == {"reason": reason.value}


@pytest.mark.parametrize(
    "value", [3202444139959, True, b"3202444139959", None, ["3202444139959"], Rccm("RB/COT/18 B 1")]
)
def test_rejects_values_that_are_not_strings_with_invalid_characters(value: object) -> None:
    for model in (Company, StrictCompany):
        with pytest.raises(ValidationError) as caught:
            model.model_validate({"ifu": value, "rccm": "RB/COT/18 B 22272"})

        (error,) = caught.value.errors()
        assert error["type"] == "ifu_invalid_characters"
        assert error["msg"] == "IFU must contain only digits"


def test_messages_describe_the_failure() -> None:
    with pytest.raises(ValidationError) as caught:
        Company(ifu="7202400000000", rccm="RB/OUI/22 B 12")  # type: ignore[arg-type]

    messages = {error["loc"][0]: error["msg"] for error in caught.value.errors()}
    assert messages == {
        "ifu": "IFU must start with a digit from 0 to 6",
        "rccm": "RCCM number indicates an unknown registry",
    }


def test_optional_fields_accept_none_and_otherwise_behave_the_same() -> None:
    empty = OptionalCompany()

    assert empty.ifu is None
    assert empty.model_dump() == {"ifu": None, "rccm": None}

    filled = OptionalCompany.model_validate(VALID)

    assert filled.model_dump() == {"ifu": "3201200247219", "rccm": "RB/COT/07 B 1432"}

    with pytest.raises(ValidationError) as caught:
        OptionalCompany.model_validate({"rccm": "RB/COT/24 M 12"})

    assert caught.value.errors()[0]["type"] == "rccm_unknown_category"


def test_publishes_validation_and_serialization_json_schemas() -> None:
    validation = Company.model_json_schema(mode="validation")["properties"]
    serialization = Company.model_json_schema(mode="serialization")["properties"]

    assert validation["ifu"]["type"] == "string"
    assert "pattern" not in validation["ifu"]
    assert serialization["ifu"]["pattern"] == "^[0-9]{13}$"
    assert serialization["rccm"]["pattern"] == (
        "^RB/[A-Z]{2,3}/(?:[0-9]{2}|[0-9]{4}) [A-E] [0-9]{1,6}$"
    )

    optional = OptionalCompany.model_json_schema(mode="serialization")["properties"]["ifu"]
    assert {"type": "string", "pattern": "^[0-9]{13}$"} in optional["anyOf"]


@pytest.mark.parametrize(("raw", "value", "year"), cases.valid_rccm())
def test_the_serialization_pattern_matches_every_normalized_rccm(
    raw: str, value: str, year: int
) -> None:
    import re

    pattern = Company.model_json_schema(mode="serialization")["properties"]["rccm"]["pattern"]

    assert re.fullmatch(pattern.strip("^$"), Rccm(raw).value)
