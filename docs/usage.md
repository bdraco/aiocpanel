(usage)=

# Usage

Assuming that you've followed the {ref}`installations steps <installation>`, you're now ready to use this package.

Start by importing it:

```python
import aiocpanel
```

Create an API token in cPanel under Security, Manage API Tokens, then build a client with an `aiohttp.ClientSession`:

<!-- skip: next -->

```python
import aiohttp
from aiocpanel import CpanelClient

async with aiohttp.ClientSession() as session:
    client = CpanelClient(session, "server.example.com", "user", "API_TOKEN")

    # The best installed certificate for a name, with its key and CA bundle
    cert = await client.fetch_certificate("home.example.com")
    print(cert.fullchain)

    # Ask AutoSSL to run, for example when a certificate is missing or expiring
    await client.start_autossl_check()

    # Find the Dynamic DNS record for a name, creating it if needed,
    # then point it at the caller's public IP
    url = await client.get_webcall_url("home.example.com", "Home Assistant")
    await client.call_webcall(url)
```

Errors raise subclasses of `CpanelError`: `CpanelAuthError` when the token is rejected, `CpanelConnectionError` when cPanel cannot be reached, `CpanelApiError` when a call fails, and `CpanelNoCertificateError` when there is no certificate for the name.
