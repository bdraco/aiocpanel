from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest
from aiointercept import aiointercept
from yarl import URL

from aiocpanel import (
    Certificate,
    CpanelApiError,
    CpanelAuthError,
    CpanelClient,
    CpanelConnectionError,
    CpanelNoCertificateError,
    DynamicDnsRecord,
)

BASE = "https://server.example.com:2083"
FETCH_URL = f"{BASE}/execute/SSL/fetch_best_for_domain?domain=home.example.com"
AUTOSSL_URL = f"{BASE}/execute/SSL/start_autossl_check"
LIST_URL = f"{BASE}/execute/DynamicDNS/list"
CREATE_URL = (
    f"{BASE}/execute/DynamicDNS/create"
    "?description=Home+Assistant&domain=home.example.com"
)
RECORD_ID = "abcdefghijklmnopqrstuvwxyzabcdef"
WEBCALL_URL = f"{BASE}/cpanelwebcall/{RECORD_ID}"


def ok(data: object) -> dict[str, object]:
    return {"status": 1, "data": data, "errors": None, "messages": None}


@pytest.fixture
async def mock() -> AsyncIterator[aiointercept]:
    async with aiointercept(mock_external_urls=True) as m:
        yield m


@pytest.fixture
async def client(mock: aiointercept) -> AsyncIterator[CpanelClient]:
    async with aiohttp.ClientSession() as session:
        yield CpanelClient(session, "server.example.com", "user", "token")


async def test_fetch_certificate(client: CpanelClient, mock: aiointercept) -> None:
    mock.get(FETCH_URL, payload=ok({"crt": "CRT\n", "key": "KEY", "cab": "CA\n"}))
    cert = await client.fetch_certificate("home.example.com")
    assert cert == Certificate(crt="CRT\n", key="KEY", cab="CA\n")
    assert cert.fullchain == "CRT\nCA\n"
    request = mock.requests[("GET", URL(FETCH_URL))][0]
    assert request.kwargs["headers"]["Authorization"] == "cpanel user:token"


def test_fullchain_without_bundle() -> None:
    assert Certificate(crt="CRT", key="KEY", cab=None).fullchain == "CRT\n"


@pytest.mark.parametrize("data", [None, {"crt": "", "key": ""}], ids=["none", "empty"])
async def test_fetch_certificate_missing(
    client: CpanelClient, mock: aiointercept, data: object
) -> None:
    mock.get(FETCH_URL, payload=ok(data))
    with pytest.raises(CpanelNoCertificateError):
        await client.fetch_certificate("home.example.com")


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        pytest.param({"status": 401}, CpanelAuthError, id="unauthorized"),
        pytest.param({"status": 403}, CpanelAuthError, id="forbidden"),
        pytest.param({"status": 500}, CpanelConnectionError, id="server_error"),
        pytest.param({"exception": True}, CpanelConnectionError, id="unreachable"),
        pytest.param({"body": "<html>"}, CpanelApiError, id="not_json"),
        pytest.param({"payload": []}, CpanelApiError, id="not_object"),
        pytest.param(
            {"payload": {"status": 0, "errors": ["Feature disabled"]}},
            CpanelApiError,
            id="api_error",
        ),
        pytest.param(
            {"payload": {"status": 0, "errors": None}}, CpanelApiError, id="no_errors"
        ),
    ],
)
async def test_errors(
    client: CpanelClient,
    mock: aiointercept,
    kwargs: dict[str, Any],
    error: type[Exception],
) -> None:
    mock.get(FETCH_URL, **kwargs)
    with pytest.raises(error):
        await client.fetch_certificate("home.example.com")


async def test_start_autossl_check(client: CpanelClient, mock: aiointercept) -> None:
    mock.get(AUTOSSL_URL, payload=ok(None))
    await client.start_autossl_check()
    assert ("GET", URL(AUTOSSL_URL)) in mock.requests


async def test_get_webcall_url_existing(
    client: CpanelClient, mock: aiointercept
) -> None:
    mock.get(
        LIST_URL,
        payload=ok(
            [
                {"id": "x" * 32, "domain": "other.example.com"},
                {"id": RECORD_ID, "domain": "Home.Example.com", "description": "HA"},
            ]
        ),
    )
    assert await client.get_webcall_url("home.example.com", "Home Assistant") == (
        WEBCALL_URL
    )
    assert ("GET", URL(CREATE_URL)) not in mock.requests


async def test_get_webcall_url_creates(
    client: CpanelClient, mock: aiointercept
) -> None:
    mock.get(LIST_URL, payload=ok([]))
    mock.get(CREATE_URL, payload=ok({"id": RECORD_ID, "created_time": 1}))
    assert await client.get_webcall_url("home.example.com", "Home Assistant") == (
        WEBCALL_URL
    )
    assert ("GET", URL(CREATE_URL)) in mock.requests


async def test_create_dynamic_dns_without_description(
    client: CpanelClient, mock: aiointercept
) -> None:
    mock.get(
        f"{BASE}/execute/DynamicDNS/create?domain=home.example.com",
        payload=ok({"id": RECORD_ID}),
    )
    assert await client.create_dynamic_dns("home.example.com") == DynamicDnsRecord(
        id=RECORD_ID, domain="home.example.com", description=None
    )


async def test_list_dynamic_dns_empty(client: CpanelClient, mock: aiointercept) -> None:
    mock.get(LIST_URL, payload=ok(None))
    assert await client.list_dynamic_dns() == []


async def test_call_webcall(client: CpanelClient, mock: aiointercept) -> None:
    mock.get(WEBCALL_URL, body=" updated \n")
    assert await client.call_webcall(WEBCALL_URL) == "updated"
