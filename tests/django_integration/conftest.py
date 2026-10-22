from collections.abc import Iterator

import django
import pytest
from django.conf import settings

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=["benin_business_id.django"],
        USE_I18N=True,
        LANGUAGE_CODE="en",
        LANGUAGES=[("en", "English"), ("fr", "French")],
    )
    django.setup()


@pytest.fixture(autouse=True)
def fresh_checkers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Each test starts from an unconfigured environment and a fresh shared checker."""
    from benin_business_id.django.checkers import reset_checkers

    for variable in (
        "BENIN_RCCM_APIEX_ENABLED",
        "BENIN_RCCM_APIEX_TIMEOUT",
        "BENIN_RCCM_APIEX_COMPANIES_URL",
        "BENIN_RCCM_APIEX_ESTABLISHMENTS_URL",
    ):
        monkeypatch.delenv(variable, raising=False)

    reset_checkers()
    yield
    reset_checkers()
