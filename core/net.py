"""Shared outbound HTTP helpers. Every urlopen in the project goes through here so the
certifi fallback (macOS python.org builds ship without system roots) applies everywhere."""
from __future__ import annotations

import ssl
import urllib.request


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


SSL_CONTEXT = ssl_context()


def urlopen(req, timeout: int = 60):
    return urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT)
