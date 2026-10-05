"""Async client for the cPanel UAPI and Dynamic DNS webcalls."""

import json
from typing import Any

import aiohttp
from yarl import URL

from .exceptions import (
    CpanelApiError,
    CpanelAuthError,
    CpanelConnectionError,
    CpanelNoCertificateError,
)
from .models import Certificate, DynamicDnsRecord

DEFAULT_PORT = 2083
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class CpanelClient:
    """Talk to a single cPanel account using an API token."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str,
        token: str,
        port: int = DEFAULT_PORT,
    ) -> None:
        self._session = session
        self._server_url = URL.build(scheme="https", host=host, port=port)
        self._headers = {"Authorization": f"cpanel {username}:{token}"}

    async def _get(
        self,
        url: URL | str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        """
        GET a URL and return the status and body.

        Server errors are raised as connection errors since they are usually
        temporary; client errors are left to the caller.
        """
        try:
            async with self._session.get(
                url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                status, body = resp.status, await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CpanelConnectionError(str(err) or type(err).__name__) from err
        if status >= 500:
            raise CpanelConnectionError(f"cPanel returned HTTP {status}")
        return status, body

    async def _uapi(self, module: str, function: str, **params: str) -> Any:
        """Call a UAPI function and return its data."""
        status, body = await self._get(
            self._server_url / "execute" / module / function,
            params=params,
            headers=self._headers,
        )
        if status in (401, 403):
            raise CpanelAuthError(f"cPanel returned HTTP {status}")
        if status >= 400:
            raise CpanelApiError(f"cPanel returned HTTP {status}")
        try:
            response = json.loads(body)
        except ValueError as err:
            raise CpanelApiError(f"Unexpected response from cPanel: {err}") from err
        if not isinstance(response, dict):
            raise CpanelApiError("Unexpected response from cPanel")
        if not response.get("status"):
            raise CpanelApiError("; ".join(response.get("errors") or ["unknown error"]))
        return response.get("data")

    def _record(self, record_id: str, domain: str) -> DynamicDnsRecord:
        return DynamicDnsRecord(
            id=record_id,
            domain=domain,
            webcall_url=str(self._server_url / "cpanelwebcall" / record_id),
        )

    async def fetch_certificate(self, domain: str) -> Certificate:
        """Return the best installed certificate for a domain."""
        data = await self._uapi("SSL", "fetch_best_for_domain", domain=domain)
        if not data or not data.get("crt") or not data.get("key"):
            raise CpanelNoCertificateError(f"No certificate found for {domain}")
        return Certificate(crt=data["crt"], key=data["key"], cab=data.get("cab"))

    async def start_autossl_check(self) -> None:
        """Ask cPanel to run AutoSSL for the account."""
        await self._uapi("SSL", "start_autossl_check")

    async def list_dynamic_dns(self) -> list[DynamicDnsRecord]:
        """Return the account's Dynamic DNS records."""
        return [
            self._record(record["id"], record["domain"])
            for record in await self._uapi("DynamicDNS", "list") or []
        ]

    async def create_dynamic_dns(
        self, domain: str, description: str
    ) -> DynamicDnsRecord:
        """Create a Dynamic DNS record."""
        data = await self._uapi(
            "DynamicDNS", "create", domain=domain, description=description
        )
        return self._record(data["id"], domain)

    async def ensure_dynamic_dns(
        self, domain: str, description: str
    ) -> DynamicDnsRecord:
        """Return the Dynamic DNS record for a domain, creating it if missing."""
        domain = domain.lower()
        for record in await self.list_dynamic_dns():
            if record.domain.lower() == domain:
                return record
        return await self.create_dynamic_dns(domain, description)

    async def call_webcall(self, record: DynamicDnsRecord) -> str:
        """
        Call a record's webcall so cPanel points it at the caller's public IP.

        Returns the response text from cPanel.
        """
        status, body = await self._get(record.webcall_url)
        if status >= 400:
            raise CpanelApiError(f"cPanel returned HTTP {status}")
        return body.strip()
