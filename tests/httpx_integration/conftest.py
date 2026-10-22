import pytest
from tests.httpx_integration.support import MODES, Check, make_check


@pytest.fixture(params=MODES)
def check(request: pytest.FixtureRequest) -> Check:
    """A check on a fake directory, run once with RccmChecker and once with AsyncRccmChecker."""
    mode: str = request.param

    return make_check(mode)
