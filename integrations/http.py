"""Kleine HTTP-hulpjes: JSON ophalen met de certificaten van het besturingssysteem."""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request


def ssl_context() -> ssl.SSLContext:
    """Gebruik de certificaten van het besturingssysteem (truststore).

    Virusscanners en bedrijfsnetwerken die HTTPS inspecteren zetten hun eigen
    certificaat in Windows; met truststore vertrouwt Python dat net als je browser.
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def get_json(url: str, params: dict | None = None, timeout: float = 5.0):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "thuis-dashboard", "Accept": "application/json"})
    kwargs = {"context": ssl_context()} if url.startswith("https:") else {}
    with urllib.request.urlopen(req, timeout=timeout, **kwargs) as resp:
        return json.loads(resp.read().decode("utf-8"))
