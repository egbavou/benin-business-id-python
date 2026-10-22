"""Port of the PHP Laravel tests (RulesTest, ServiceProviderTest) to the Django integration."""

import gettext
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from babel.messages.pofile import read_po
from django import forms
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import override_settings
from django.utils import translation
from tests import cases
from tests.httpx_integration.support import FakeApiex, page

from benin_business_id import FailureReason, Ifu, Rccm, RccmChecker
from benin_business_id.django._messages import IFU_MESSAGES, RCCM_MESSAGES
from benin_business_id.django.checkers import get_ifu_checker, get_rccm_checker
from benin_business_id.django.forms import IfuField, RccmField
from benin_business_id.django.validators import (
    IfuExistsValidator,
    IfuValidator,
    RccmExistsValidator,
    RccmValidator,
)

LOCALE = Path(__file__).resolve().parents[2] / "src/benin_business_id/django/locale"
FRENCH = {
    "ifu": {
        "invalid_characters": "Ce champ ne doit contenir que des chiffres.",
        "invalid_length": "Ce champ doit contenir 13 chiffres.",
        "invalid_checksum": "Ce champ n'est pas un IFU valide.",
        "unknown_taxpayer_type": "Ce champ doit commencer par un chiffre de 0 à 6.",
        "invalid_year": "Ce champ contient une année d'immatriculation invalide.",
        "not_found": "L'IFU indiqué est introuvable.",
        "unavailable": "L'IFU indiqué ne peut pas être vérifié pour le moment.",
    },
    "rccm": {
        "invalid_characters": "Ce champ contient des caractères non autorisés.",
        "invalid_length": "Ce champ n'a pas la longueur d'un numéro RCCM.",
        "invalid_checksum": "Ce champ n'est pas un numéro RCCM valide.",
        "invalid_structure": "Ce champ doit avoir la forme RB/COT/18 B 22272.",
        "invalid_country": "Ce champ doit commencer par RB.",
        "unknown_registry": "Ce champ indique un greffe inconnu.",
        "unknown_category": "Ce champ doit porter une lettre de catégorie de A à E.",
        "invalid_year": "Ce champ contient une année invalide.",
        "not_found": "Le numéro RCCM indiqué est absent de l'annuaire de l'APIEx.",
        "unavailable": "Le numéro RCCM indiqué ne peut pas être vérifié pour le moment.",
        "verification_disabled": "La vérification en ligne des numéros RCCM est désactivée.",
    },
}


def failure(
    validator: Callable[[object], None], value: object, language: str = "en"
) -> tuple[str | None, str]:
    """The code and message of the error, rendered in the given language."""
    with translation.override(language):
        with pytest.raises(ValidationError) as caught:
            validator(value)

        return caught.value.code, caught.value.messages[0]


@contextmanager
def rccm_directory(
    responses: list[httpx.Response | BaseException], enabled: bool = True
) -> Iterator[FakeApiex]:
    fake = FakeApiex(responses)

    with fake.client() as client:
        checker = RccmChecker(client, enabled=enabled)

        with override_settings(BENIN_BUSINESS_ID={"RCCM_CHECKER": checker}):
            yield fake


# Format validators


@pytest.mark.parametrize(("raw", "value", "taxpayer_type", "year"), cases.valid_ifu())
def test_ifu_validator_accepts_valid_values(
    raw: str, value: str, taxpayer_type: object, year: int
) -> None:
    IfuValidator()(raw)
    IfuValidator()(Ifu(raw))


@pytest.mark.parametrize(("raw", "reason"), cases.invalid_ifu())
@pytest.mark.parametrize("language", ["en", "fr"])
def test_ifu_validator_reports_one_message_per_reason(
    raw: str, reason: FailureReason, language: str
) -> None:
    code, message = failure(IfuValidator(), raw, language)

    assert code == reason.value
    assert message == (
        FRENCH["ifu"][reason.value] if language == "fr" else str(IFU_MESSAGES[reason.value])
    )


@pytest.mark.parametrize(("raw", "value", "year"), cases.valid_rccm())
def test_rccm_validator_accepts_valid_values(raw: str, value: str, year: int) -> None:
    RccmValidator()(raw)
    RccmValidator()(Rccm(raw))


@pytest.mark.parametrize(("raw", "reason"), cases.invalid_rccm())
@pytest.mark.parametrize("language", ["en", "fr"])
def test_rccm_validator_reports_one_message_per_reason(
    raw: str, reason: FailureReason, language: str
) -> None:
    code, message = failure(RccmValidator(), raw, language)

    assert code == reason.value
    assert message == (
        FRENCH["rccm"][reason.value] if language == "fr" else str(RCCM_MESSAGES[reason.value])
    )


@pytest.mark.parametrize(
    "value", [3202444139959, None, b"3202444139959", ["x"], Rccm("RB/COT/18 B 1")]
)
@pytest.mark.parametrize("language", ["en", "fr"])
def test_validators_reject_values_that_are_not_strings_with_invalid_characters(
    value: object, language: str
) -> None:
    code, message = failure(IfuValidator(), value, language)

    assert code == "invalid_characters"
    assert message == (
        FRENCH["ifu"]["invalid_characters"]
        if language == "fr"
        else "This field must contain only digits."
    )
    assert failure(RccmValidator(), Ifu("3202444139959"))[0] == "invalid_characters"


def test_validators_deconstruct_and_compare() -> None:
    for validator in (IfuValidator(), RccmValidator()):
        path, args, kwargs = validator.deconstruct()

        assert path == f"benin_business_id.django.validators.{type(validator).__name__}"
        assert (args, kwargs) == ((), {})
        assert validator == type(validator)()
        assert hash(validator) == hash(type(validator)())

    assert IfuValidator() != RccmValidator()

    strict = RccmExistsValidator(fail_when_unavailable=True)
    path, args, kwargs = strict.deconstruct()

    assert path == "benin_business_id.django.validators.RccmExistsValidator"
    assert kwargs == {"fail_when_unavailable": True}
    assert RccmExistsValidator(*args, **kwargs) == strict
    assert strict != RccmExistsValidator()
    assert strict != IfuExistsValidator(fail_when_unavailable=True)
    assert hash(strict) == hash(RccmExistsValidator(fail_when_unavailable=True))


# Existence validators


def test_ifu_existence_passes_by_default_and_fails_when_strict() -> None:
    IfuExistsValidator()("3202444139959")

    code, message = failure(IfuExistsValidator(fail_when_unavailable=True), "3202444139959", "fr")

    assert code == "unavailable"
    assert message == FRENCH["ifu"]["unavailable"]
    assert failure(IfuExistsValidator(), "7202400000000")[0] == "unknown_taxpayer_type"


def test_rccm_existence_rejects_invalid_formats_without_requests() -> None:
    with rccm_directory([]) as fake:
        assert failure(RccmExistsValidator(), "RB/COT/24 M 12")[0] == "unknown_category"
        assert failure(RccmExistsValidator(), 12)[0] == "invalid_characters"

    assert fake.requests == []


def test_rccm_existence_passes_when_found() -> None:
    with rccm_directory([page([{"Numéro RC": "RB/COT/18 B 22272"}])]) as fake:
        RccmExistsValidator(fail_when_unavailable=True)("RB/COT/18 B 22272")

    assert len(fake.requests) == 1


@pytest.mark.parametrize("language", ["en", "fr"])
def test_rccm_existence_fails_when_not_found(language: str) -> None:
    with rccm_directory([page() for _ in range(4)]):
        code, message = failure(RccmExistsValidator(), "RB/COT/18 B 22272", language)

    assert code == "not_found"
    assert message == (
        FRENCH["rccm"]["not_found"]
        if language == "fr"
        else "The RCCM number specified is absent from the APIEx directory."
    )


def test_rccm_existence_passes_when_unavailable_unless_strict() -> None:
    with rccm_directory([httpx.ConnectError("down"), httpx.ConnectError("down")]):
        RccmExistsValidator()("RB/COT/18 B 22272")
        code, message = failure(
            RccmExistsValidator(fail_when_unavailable=True), "RB/COT/18 B 22272", "fr"
        )

    assert code == "unavailable"
    assert message == FRENCH["rccm"]["unavailable"]


def test_rccm_existence_has_a_dedicated_message_when_verification_is_disabled() -> None:
    with rccm_directory([], enabled=False) as fake:
        RccmExistsValidator()("RB/COT/18 B 22272")
        code, message = failure(
            RccmExistsValidator(fail_when_unavailable=True), "RB/COT/18 B 22272", "fr"
        )

    assert code == "verification_disabled"
    assert message == FRENCH["rccm"]["verification_disabled"]
    assert fake.requests == []

    # Without any configuration, verification is disabled as well.
    assert get_rccm_checker().enabled is False
    assert failure(RccmExistsValidator(fail_when_unavailable=True), "RB/COT/18 B 22272")[0] == (
        "verification_disabled"
    )


# Shared checkers


def test_reads_the_setting_and_falls_back_to_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BENIN_RCCM_APIEX_ENABLED", "true")
    monkeypatch.setenv("BENIN_RCCM_APIEX_TIMEOUT", "4")
    monkeypatch.setenv("BENIN_RCCM_APIEX_COMPANIES_URL", "https://example.test/env-companies")

    with override_settings(
        BENIN_BUSINESS_ID={
            "RCCM_APIEX": {
                "TIMEOUT": None,
                "COMPANIES_URL": "https://example.test/setting-companies",
                "ESTABLISHMENTS_URL": "",
            }
        }
    ):
        checker = get_rccm_checker()

        assert checker.enabled is True
        assert isinstance(checker._client, httpx.Client)
        assert checker._client.timeout == httpx.Timeout(4.0)
        assert checker._companies_url == "https://example.test/setting-companies"
        assert checker._establishments_url == (
            "https://gdb.monentreprise.bj/data-view/registre%20pp/latest/310"
        )
        assert get_rccm_checker() is checker


@pytest.mark.parametrize(
    ("enabled", "timeout", "expected_enabled", "expected_timeout"),
    [
        (True, 3, True, 3.0),
        ("yes", "2.5", True, 2.5),
        (1, 0, True, 10.0),
        (2, -1, False, 10.0),
        ("maybe", "abc", False, 10.0),
        (False, True, False, 10.0),
    ],
)
def test_normalizes_setting_values_like_the_php_service_provider(
    enabled: object, timeout: object, expected_enabled: bool, expected_timeout: float
) -> None:
    with override_settings(
        BENIN_BUSINESS_ID={"RCCM_APIEX": {"ENABLED": enabled, "TIMEOUT": timeout}}
    ):
        checker = get_rccm_checker()

        assert checker.enabled is expected_enabled
        assert checker._timeout == expected_timeout


def test_rebuilds_the_shared_checker_and_closes_the_one_it_created() -> None:
    with override_settings(BENIN_BUSINESS_ID={"RCCM_APIEX": {"ENABLED": True}}):
        created = get_rccm_checker()
        client = created._client
        assert isinstance(client, httpx.Client)

    assert client.is_closed
    assert get_rccm_checker() is not created


def test_never_closes_an_injected_checker() -> None:
    fake = FakeApiex()

    with fake.client() as client:
        injected = RccmChecker(client, enabled=True)

        with override_settings(BENIN_BUSINESS_ID={"RCCM_CHECKER": injected}):
            assert get_rccm_checker() is injected

        assert not client.is_closed


@pytest.mark.parametrize(
    "setting",
    [["not", "a", "dict"], {"RCCM_APIEX": "enabled"}, {"RCCM_CHECKER": object()}],
)
def test_rejects_invalid_settings(setting: object) -> None:
    with override_settings(BENIN_BUSINESS_ID=setting), pytest.raises(ImproperlyConfigured):
        get_rccm_checker()


def test_shares_one_ifu_checker() -> None:
    assert get_ifu_checker() is get_ifu_checker()


# Form fields


class CompanyForm(forms.Form):
    ifu = IfuField()
    rccm = RccmField(required=False)


def test_form_fields_clean_values_into_core_objects() -> None:
    form = CompanyForm(data={"ifu": "3.201.200.247.219", "rccm": "RB/COT/07-B-1432"})

    assert form.is_valid(), form.errors
    assert form.cleaned_data == {"ifu": Ifu("3201200247219"), "rccm": Rccm("RB/COT/07 B 1432")}


@pytest.mark.parametrize("blank", ["", " \t", "\0", None])
def test_form_fields_leave_blank_values_to_required(blank: str | None) -> None:
    form = CompanyForm(data={"ifu": blank, "rccm": blank})

    assert not form.is_valid()
    assert form.errors.as_data()["ifu"][0].code == "required"
    assert form.cleaned_data["rccm"] is None


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (chr(0x00A0) * 3, "invalid_length"),
        ("\x1c3202444139959", "invalid_characters"),
        ("7202400000000", "unknown_taxpayer_type"),
    ],
)
def test_form_fields_report_the_failure_reason(value: str, code: str) -> None:
    with translation.override("fr"):
        form = CompanyForm(data={"ifu": value})

        assert not form.is_valid()
        error = form.errors.as_data()["ifu"][0]

        assert error.code == code
        assert error.messages == [FRENCH["ifu"][code]]


def test_form_fields_reject_values_that_are_not_strings() -> None:
    field = IfuField()

    with pytest.raises(ValidationError) as caught:
        field.clean(3202444139959)

    assert caught.value.code == "invalid_characters"

    with pytest.raises(ValidationError):
        RccmField().clean(Ifu("3202444139959"))


def test_form_fields_track_changes_on_normalized_values() -> None:
    field = RccmField()

    assert not field.has_changed("RB/COT/07-B-1432", "RB/COT/07 B 1432")
    assert not field.has_changed(Rccm("RB/COT/07 B 1432"), "rb cot 07 b 1432")
    assert field.has_changed("RB/COT/07 B 1432", "RB/COT/07 B 1433")
    assert field.has_changed("RB/COT/07 B 1432", "invalid")
    assert not RccmField(disabled=True).has_changed("RB/COT/07 B 1432", "anything")


def test_form_fields_display_objects_in_normalized_form() -> None:
    assert RccmField().prepare_value(Rccm("RB/COT/07-B-1432")) == "RB/COT/07 B 1432"
    assert RccmField().prepare_value("as typed") == "as typed"

    form = CompanyForm(initial={"ifu": Ifu("3201200247219")})

    assert 'value="3201200247219"' in str(form["ifu"])


def test_form_fields_accept_disabled_object_initial_values() -> None:
    class DisabledForm(forms.Form):
        rccm = RccmField(disabled=True)

    form = DisabledForm(data={}, initial={"rccm": Rccm("RB/COT/07 B 1432")})

    assert form.is_valid()
    assert form.cleaned_data["rccm"] == Rccm("RB/COT/07 B 1432")


def test_form_field_messages_can_be_overridden() -> None:
    field = RccmField(error_messages={"unknown_registry": "Custom message."})

    with pytest.raises(ValidationError) as caught:
        field.clean("RB/OUI/22 B 12")

    assert caught.value.messages == ["Custom message."]


# Translations


def test_translations_follow_the_active_language_after_import() -> None:
    validator = IfuValidator()

    assert failure(validator, "A", "fr")[1] == FRENCH["ifu"]["invalid_characters"]
    assert failure(validator, "A", "en")[1] == "This field must contain only digits."


def test_the_compiled_catalog_matches_the_po_file_and_covers_every_message() -> None:
    directory = LOCALE / "fr/LC_MESSAGES"

    with (directory / "django.po").open("rb") as po_file:
        catalog = read_po(po_file)

    with (directory / "django.mo").open("rb") as mo_file:
        compiled = gettext.GNUTranslations(mo_file)

    entries = {
        message.id: message.string
        for message in catalog
        if isinstance(message.id, str) and message.id
    }

    assert entries
    for msgid, msgstr in entries.items():
        assert compiled.gettext(msgid) == msgstr

    for identifier, messages in (("ifu", IFU_MESSAGES), ("rccm", RCCM_MESSAGES)):
        assert set(messages) == set(FRENCH[identifier])

        for key, message in messages.items():
            assert entries[str(message)] == FRENCH[identifier][key]
