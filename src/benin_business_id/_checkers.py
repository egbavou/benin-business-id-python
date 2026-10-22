import math
from types import ModuleType, TracebackType
from typing import TYPE_CHECKING, Final, final

from benin_business_id import _apiex, _clock
from benin_business_id._cleanup import as_text
from benin_business_id._enums import CheckStatus, RccmRegister, UnavailableReason
from benin_business_id._errors import DirectoryError
from benin_business_id._ifu import Ifu
from benin_business_id._rccm import Rccm
from benin_business_id._results import IfuCheckResult, RccmCheckResult
from benin_business_id._settings import (
    DEFAULT_COMPANIES_URL,
    DEFAULT_ESTABLISHMENTS_URL,
    DEFAULT_TIMEOUT,
    ApiexSettings,
)

if TYPE_CHECKING:
    import httpx

_MISSING_HTTPX: Final = (
    "RCCM verification requires httpx: install it with 'pip install \"benin-business-id[httpx]\"'."
)


@final
class IfuChecker:
    """IFU existence checks.

    No authorised IFU existence source is currently available: the DGI search is protected by
    a CAPTCHA and is never queried. A valid IFU is therefore UNAVAILABLE with NO_SOURCE.
    """

    def check(self, ifu: str | Ifu) -> IfuCheckResult:
        return _check_ifu(ifu)


@final
class AsyncIfuChecker:
    """The asynchronous counterpart of IfuChecker. It performs no I/O."""

    async def check(self, ifu: str | Ifu) -> IfuCheckResult:
        return _check_ifu(ifu)


def _check_ifu(ifu: str | Ifu) -> IfuCheckResult:
    identifier: Ifu | None

    if isinstance(ifu, Ifu):
        text, identifier = ifu.value, ifu
    else:
        text = as_text(ifu, "IfuChecker.check()")
        identifier = Ifu.try_parse(text)

    return IfuCheckResult(
        status=CheckStatus.INVALID_FORMAT if identifier is None else CheckStatus.UNAVAILABLE,
        checked_at=_clock.now(),
        input=text,
        ifu=identifier,
        unavailable_reason=None if identifier is None else UnavailableReason.NO_SOURCE,
    )


class _RccmCheckerBase:
    """Configuration and result building shared by the sync and async RCCM checkers."""

    def __init__(
        self,
        has_client: bool,
        enabled: bool,
        companies_url: str,
        establishments_url: str,
        timeout: float | None,
    ) -> None:
        if not isinstance(enabled, bool):
            raise TypeError(f"enabled must be a bool, not {type(enabled).__name__}")

        for name, url in (
            ("companies_url", companies_url),
            ("establishments_url", establishments_url),
        ):
            if not isinstance(url, str):
                raise TypeError(f"{name} must be a str, not {type(url).__name__}")

        if timeout is not None:
            if has_client:
                raise ValueError("timeout only applies to the client the checker creates")

            if isinstance(timeout, bool) or not isinstance(timeout, int | float):
                raise TypeError(f"timeout must be a number, not {type(timeout).__name__}")

            if not timeout > 0:
                raise ValueError("timeout must be greater than 0")

        self._enabled = enabled
        self._companies_url = companies_url
        self._establishments_url = establishments_url
        self._timeout = DEFAULT_TIMEOUT if timeout is None else float(timeout)

    @property
    def enabled(self) -> bool:
        """Whether online verification is enabled. It is disabled by default."""
        return self._enabled

    def _client_timeout(self) -> float | None:
        # An infinite timeout, which the PHP configuration accepts, means no timeout in httpx.
        return None if math.isinf(self._timeout) else self._timeout

    def _url(self, register: RccmRegister) -> str:
        if register is RccmRegister.COMPANIES:
            return self._companies_url

        return self._establishments_url

    def _start(self, rccm: str | Rccm) -> RccmCheckResult | tuple[str, Rccm]:
        """Return the final result when no request is needed, else the input and identifier."""
        identifier: Rccm | None

        if isinstance(rccm, Rccm):
            text, identifier = rccm.value, rccm
        else:
            text = as_text(rccm, "RccmChecker.check()")
            identifier = Rccm.try_parse(text)

        if identifier is None:
            return _result(CheckStatus.INVALID_FORMAT, text, None)

        if not self._enabled:
            return _result(
                CheckStatus.UNAVAILABLE, text, identifier, reason=UnavailableReason.DISABLED
            )

        return text, identifier


@final
class RccmChecker(_RccmCheckerBase):
    """RCCM existence checks against the public APIEx directory.

    Verification is disabled by default: pass enabled=True to query the directory. A check
    makes up to four sequential GET requests and never raises: technical failures return
    UNAVAILABLE with a reason and the original exception in `failure`.

    An injected client keeps its own timeout, authentication, proxy, TLS and transport; the
    checker never closes it. Without a client, an enabled checker creates its own, with a
    10-second timeout by default, and close() releases it.
    """

    def __init__(
        self,
        client: "httpx.Client | None" = None,
        *,
        enabled: bool = False,
        companies_url: str = DEFAULT_COMPANIES_URL,
        establishments_url: str = DEFAULT_ESTABLISHMENTS_URL,
        timeout: float | None = None,
    ) -> None:
        super().__init__(client is not None, enabled, companies_url, establishments_url, timeout)
        self._client = client
        self._owns_client = False

        if client is None and enabled:
            self._client = _httpx().Client(
                timeout=self._client_timeout(),
                event_hooks={"response": [_drop_redirect_location]},
            )
            self._owns_client = True

    @classmethod
    def from_settings(
        cls, settings: ApiexSettings, client: "httpx.Client | None" = None
    ) -> "RccmChecker":
        """Build a checker from settings; settings.timeout only applies without a client."""
        return cls(
            client,
            enabled=settings.enabled,
            companies_url=settings.companies_url,
            establishments_url=settings.establishments_url,
            timeout=None if client is not None else settings.timeout,
        )

    def check(self, rccm: str | Rccm) -> RccmCheckResult:
        started = self._start(rccm)

        if isinstance(started, RccmCheckResult):
            return started

        text, identifier = started

        try:
            for register in _apiex.register_order(identifier):
                for exact in (True, False):
                    record = self._find(register, identifier, exact)

                    if record is not None:
                        return _found(text, identifier, record, register)
        except DirectoryError as error:
            return _unavailable(text, identifier, error)
        except Exception as error:
            return _result(
                CheckStatus.UNAVAILABLE,
                text,
                identifier,
                reason=UnavailableReason.SCHEMA,
                failure=error,
            )

        return _result(CheckStatus.NOT_FOUND, text, identifier)

    def close(self) -> None:
        """Close the client the checker created, if any. An injected client is left open."""
        if self._owns_client and self._client is not None:
            self._client.close()

    def __enter__(self) -> "RccmChecker":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _find(self, register: RccmRegister, rccm: Rccm, exact: bool) -> _apiex.Record | None:
        client = self._client
        assert client is not None, "an enabled checker always has a client"

        try:
            request = _apiex.build_request(
                self._url(register), register, rccm, exact, client.timeout
            )
            response = client.send(request, follow_redirects=False)
        except Exception as error:
            raise DirectoryError(UnavailableReason.TRANSPORT) from error

        return _apiex.read_page(response.status_code, response.content, rccm)


@final
class AsyncRccmChecker(_RccmCheckerBase):
    """The asynchronous counterpart of RccmChecker, on an httpx.AsyncClient.

    Same behaviour, configuration and guarantees; aclose() releases a client it created.
    """

    def __init__(
        self,
        client: "httpx.AsyncClient | None" = None,
        *,
        enabled: bool = False,
        companies_url: str = DEFAULT_COMPANIES_URL,
        establishments_url: str = DEFAULT_ESTABLISHMENTS_URL,
        timeout: float | None = None,
    ) -> None:
        super().__init__(client is not None, enabled, companies_url, establishments_url, timeout)
        self._client = client
        self._owns_client = False

        if client is None and enabled:
            self._client = _httpx().AsyncClient(
                timeout=self._client_timeout(),
                event_hooks={"response": [_drop_redirect_location_async]},
            )
            self._owns_client = True

    @classmethod
    def from_settings(
        cls, settings: ApiexSettings, client: "httpx.AsyncClient | None" = None
    ) -> "AsyncRccmChecker":
        """Build a checker from settings; settings.timeout only applies without a client."""
        return cls(
            client,
            enabled=settings.enabled,
            companies_url=settings.companies_url,
            establishments_url=settings.establishments_url,
            timeout=None if client is not None else settings.timeout,
        )

    async def check(self, rccm: str | Rccm) -> RccmCheckResult:
        started = self._start(rccm)

        if isinstance(started, RccmCheckResult):
            return started

        text, identifier = started

        try:
            for register in _apiex.register_order(identifier):
                for exact in (True, False):
                    record = await self._find(register, identifier, exact)

                    if record is not None:
                        return _found(text, identifier, record, register)
        except DirectoryError as error:
            return _unavailable(text, identifier, error)
        except Exception as error:
            return _result(
                CheckStatus.UNAVAILABLE,
                text,
                identifier,
                reason=UnavailableReason.SCHEMA,
                failure=error,
            )

        return _result(CheckStatus.NOT_FOUND, text, identifier)

    async def aclose(self) -> None:
        """Close the client the checker created, if any. An injected client is left open."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def __aenter__(self) -> "AsyncRccmChecker":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def _find(self, register: RccmRegister, rccm: Rccm, exact: bool) -> _apiex.Record | None:
        client = self._client
        assert client is not None, "an enabled checker always has a client"

        try:
            request = _apiex.build_request(
                self._url(register), register, rccm, exact, client.timeout
            )
            response = await client.send(request, follow_redirects=False)
        except Exception as error:
            raise DirectoryError(UnavailableReason.TRANSPORT) from error

        return _apiex.read_page(response.status_code, response.content, rccm)


def _drop_redirect_location(response: "httpx.Response") -> None:
    # The checker never follows redirects, yet httpx parses the Location header of a redirect
    # and raises on a malformed one. Dropping it on the client the checker owns keeps every
    # redirect an HTTP_STATUS failure, as with Guzzle's sendRequest().
    response.headers.pop("Location", None)


async def _drop_redirect_location_async(response: "httpx.Response") -> None:
    _drop_redirect_location(response)


def _httpx() -> ModuleType:
    try:
        import httpx
    except ImportError as error:
        raise ImportError(_MISSING_HTTPX) from error

    return httpx


def _result(
    status: CheckStatus,
    text: str,
    rccm: Rccm | None,
    *,
    reason: UnavailableReason | None = None,
    failure: Exception | None = None,
) -> RccmCheckResult:
    return RccmCheckResult(
        status=status,
        checked_at=_clock.now(),
        input=text,
        rccm=rccm,
        unavailable_reason=reason,
        failure=failure,
    )


def _unavailable(text: str, rccm: Rccm, error: DirectoryError) -> RccmCheckResult:
    cause = error.__cause__
    failure = cause if isinstance(cause, Exception) else error

    return _result(CheckStatus.UNAVAILABLE, text, rccm, reason=error.reason, failure=failure)


def _found(text: str, rccm: Rccm, record: _apiex.Record, register: RccmRegister) -> RccmCheckResult:
    return RccmCheckResult(
        status=CheckStatus.FOUND,
        checked_at=_clock.now(),
        input=text,
        rccm=rccm,
        **_apiex.details(record, register),
    )
