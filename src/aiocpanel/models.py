"""Data models for aiocpanel."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Certificate:
    """A certificate, its key and the CA bundle."""

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


@dataclass(frozen=True, slots=True)
class DynamicDnsRecord:
    """A cPanel Dynamic DNS record."""

    id: str
    domain: str
    description: str | None
