"""Data models for aiocpanel."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Certificate:
    """A certificate, its key and the CA bundle, as PEM text."""

    crt: str
    key: str
    cab: str | None

    @property
    def fullchain(self) -> str:
        """Return the leaf certificate followed by the CA bundle."""
        parts = [self.crt.strip()]
        if self.cab:
            parts.append(self.cab.strip())
        return "\n".join(parts) + "\n"

    @property
    def key_pem(self) -> str:
        """Return the private key with a single trailing newline."""
        return self.key.strip() + "\n"


@dataclass(frozen=True, slots=True)
class DynamicDnsRecord:
    """A cPanel Dynamic DNS record."""

    id: str
    domain: str
    webcall_url: str
