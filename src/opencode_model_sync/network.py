"""TLS trust roots included in standalone builds."""
import ssl

import certifi


def tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context
