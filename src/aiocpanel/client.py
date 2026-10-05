"""Async client for the cPanel UAPI and Dynamic DNS webcalls."""

import json
from typing import Any

import aiohttp

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
        """Initialize the client."""
        self._session = session
        self._server_url = f"https://{host}:{port}"
        self._headers = {"Authorization": f"cpanel {username}:{token}"}

    async def _get(self, url: str, **kwargs: Any) -> str:
        """GET a URL and return the body."""
        try:
            async with self._session.get(
                url, timeout=REQUEST_TIMEOUT, **kwargs
            ) as resp:
                if resp.status in (401, 403):
                    raise CpanelAuthError(f"cPanel returned HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CpanelConnectionError(str(err) or type(err).__name__) from err

    async def uapi(self, module: str, function: str, **params: str) -> Any:
        """Call a UAPI function and return its data."""
        body = await self._get(
            f"{self._server_url}/execute/{module}/{function}",
            params=params,
            headers=self._headers,
        )
        try:
            response = json.loads(body)
        except ValueError as err:
            raise CpanelApiError(f"Unexpected response from cPanel: {err}") from err
        if not isinstance(response, dict):
            raise CpanelApiError("Unexpected response from cPanel")
        if not response.get("status"):
            raise CpanelApiError("; ".join(response.get("errors") or ["unknown error"]))
        return response.get("data")

    async def fetch_certificate(self, domain: str) -> Certificate:
        """Return the best installed certificate for a domain."""
        data = await self.uapi("SSL", "fetch_best_for_domain", domain=domain)
        if not data or not data.get("crt") or not data.get("key"):
            raise CpanelNoCertificateError(f"No certificate found for {domain}")
        return Certificate(crt=data["crt"], key=data["key"], cab=data.get("cab"))

    async def start_autossl_check(self) -> None:
        """Ask cPanel to run AutoSSL for the account."""
        await self.uapi("SSL", "start_autossl_check")

    async def list_dynamic_dns(self) -> list[DynamicDnsRecord]:
        """Return the account's Dynamic DNS records."""
        return [
            DynamicDnsRecord(
                id=record["id"],
                domain=record["domain"],
                description=record.get("description"),
            )
            for record in await self.uapi("DynamicDNS", "list") or []
        ]

    async def create_dynamic_dns(
        self, domain: str, description: str | None = None
    ) -> DynamicDnsRecord:
        """Create a Dynamic DNS record."""
        params = {"domain": domain}
        if description is not None:
            params["description"] = description
        data = await self.uapi("DynamicDNS", "create", **params)
        return DynamicDnsRecord(id=data["id"], domain=domain, description=description)

    async def get_webcall_url(self, domain: str, description: str | None = None) -> str:
        """Return the webcall URL for a domain, creating its record if needed."""
        domain = domain.lower()
        record = next(
            (r for r in await self.list_dynamic_dns() if r.domain.lower() == domain),
            None,
        )
        if record is None:
            record = await self.create_dynamic_dns(domain, description)
        return self.webcall_url(record)

    def webcall_url(self, record: DynamicDnsRecord) -> str:
        """Return the webcall URL for a record."""
        return f"{self._server_url}/cpanelwebcall/{record.id}"

    async def call_webcall(self, url: str) -> str:
        """Call a Dynamic DNS webcall so cPanel records the caller's public IP."""
        return (await self._get(url)).strip()
