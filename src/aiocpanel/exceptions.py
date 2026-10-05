"""Exceptions raised by aiocpanel."""


class CpanelError(Exception):
    """Base error for cPanel requests."""


class CpanelConnectionError(CpanelError):
    """cPanel could not be reached."""


class CpanelAuthError(CpanelError):
    """cPanel rejected the credentials."""


class CpanelApiError(CpanelError):
    """cPanel returned an error for the call."""


class CpanelNoCertificateError(CpanelError):
    """cPanel has no certificate for the domain."""
