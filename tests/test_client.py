from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import pytest
from aiointercept import aiointercept

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
RECORD = DynamicDnsRecord(
    id=RECORD_ID,
    domain="home.example.com",
    webcall_url=f"{BASE}/cpanelwebcall/{RECORD_ID}",
)


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
    mock.get(FETCH_URL, payload=ok({"crt": "CRT", "key": "KEY", "cab": "CA"}))
    cert = await client.fetch_certificate("home.example.com")
    assert cert == Certificate(crt="CRT", key="KEY", cab="CA")
    mock.assert_called_with(FETCH_URL, headers={"Authorization": "cpanel user:token"})


@pytest.mark.parametrize(
    ("cab", "fullchain"),
    [("CA\n", "CRT\nCA\n"), (None, "CRT\n")],
    ids=["with_bundle", "without_bundle"],
)
def test_certificate_pem(cab: str | None, fullchain: str) -> None:
    cert = Certificate(crt="CRT\n", key=" KEY\n\n", cab=cab)
    assert cert.fullchain == fullchain
    assert cert.key_pem == "KEY\n"


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
        pytest.param({"status": 404}, CpanelApiError, id="not_found"),
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
    mock.assert_any_call(AUTOSSL_URL)


@pytest.mark.parametrize(
    ("records", "creates"),
    [
        pytest.param(
            [
                {"id": "x" * 32, "domain": "other.example.com"},
                {"id": RECORD_ID, "domain": "Home.Example.com", "description": "HA"},
            ],
            False,
            id="existing",
        ),
        pytest.param([], True, id="missing"),
    ],
)
async def test_ensure_dynamic_dns(
    client: CpanelClient,
    mock: aiointercept,
    records: list[dict[str, str]],
    creates: bool,
) -> None:
    mock.get(LIST_URL, payload=ok(records))
    mock.get(CREATE_URL, payload=ok({"id": RECORD_ID, "created_time": 1}))
    record = await client.ensure_dynamic_dns("home.example.com", "Home Assistant")
    assert record.id == RECORD_ID
    assert record.webcall_url == RECORD.webcall_url
    assert any(str(key[1]) == CREATE_URL for key in mock.requests) is creates


async def test_list_dynamic_dns_empty(client: CpanelClient, mock: aiointercept) -> None:
    mock.get(LIST_URL, payload=ok(None))
    assert await client.list_dynamic_dns() == []


async def test_call_webcall(client: CpanelClient, mock: aiointercept) -> None:
    mock.get(RECORD.webcall_url, body="ipv4: 203.0.113.7\n")
    assert await client.call_webcall(RECORD) == "ipv4: 203.0.113.7"


@pytest.mark.parametrize(
    ("status", "error"),
    [(404, CpanelApiError), (503, CpanelConnectionError)],
    ids=["unknown_record", "unavailable"],
)
async def test_call_webcall_errors(
    client: CpanelClient, mock: aiointercept, status: int, error: type[Exception]
) -> None:
    mock.get(RECORD.webcall_url, status=status)
    with pytest.raises(error):
        await client.call_webcall(RECORD)
