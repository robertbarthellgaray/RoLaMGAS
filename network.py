"""Verified HTTPS downloads using the operating system trust store.

ROLAMGAS_CA_BUNDLE may point at a PEM CA bundle supplied by the user's
network administrator. Certificate and hostname verification stay enabled.
"""
import json
import os
from pathlib import Path
import ssl
import urllib.error
import urllib.parse
import urllib.request


def tls_context():
    """Use native certificate-chain building, with a verified stdlib fallback."""
    try:
        import truststore
    except ImportError:
        context = ssl.create_default_context()
    else:
        # Avoid inject_into_ssl(): unrelated consumers must retain their context.
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    bundle = os.environ.get('ROLAMGAS_CA_BUNDLE') or os.environ.get('SSL_CERT_FILE')
    if bundle:
        path = Path(bundle).expanduser()
        if not path.is_file():
            raise ValueError('The configured CA bundle does not exist. Set ROLAMGAS_CA_BUNDLE to a trusted PEM CA file or remove the setting.')
        try:
            context.load_verify_locations(cafile=str(path))
        except (OSError, ssl.SSLError) as exc:
            raise ValueError('The configured CA bundle could not be loaded as PEM certificates. Ask your network administrator for the correct CA bundle.') from exc
    # Both implementations start secure; make the contract explicit.
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def _certificate_error(exc):
    reason = getattr(exc, 'reason', exc)
    return isinstance(reason, ssl.SSLCertVerificationError) or (
        isinstance(reason, ssl.SSLError) and 'CERTIFICATE_VERIFY_FAILED' in str(reason))


def request_json(url, timeout=90):
    """Fetch JSON over HTTPS without weakening trust after a TLS failure."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('External JSON downloads require an HTTPS URL')
    request = urllib.request.Request(url, headers={'User-Agent': 'RoLaMGAS/0.2 (JPL Horizons mission design)'})
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=tls_context()) as response:
            return json.load(response)
    except (urllib.error.URLError, ssl.SSLError) as exc:
        if _certificate_error(exc):
            raise RuntimeError(
                f'Could not verify the HTTPS certificate from {parsed.hostname}. '
                'Certificate checking remains enabled. Check the computer clock and operating-system updates. '
                'If a school, company proxy, or antivirus inspects HTTPS, ask its administrator to install the trusted root certificate '
                'or set ROLAMGAS_CA_BUNDLE to their PEM CA bundle, then restart RoLaMGAS. '
                'The bundled planet cache can still be used offline; new objects and dates outside that cache require a verified connection.'
            ) from exc
        if isinstance(exc, urllib.error.HTTPError):
            raise RuntimeError(f'{parsed.hostname} returned HTTP {exc.code}. Try again later; existing cached ephemerides are retained.') from exc
        raise RuntimeError(f'Could not reach {parsed.hostname}: {getattr(exc, "reason", exc)}. Check the network or use cached ephemerides.') from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'{parsed.hostname} returned invalid JSON. No ephemeris or target identity was accepted; try again later.') from exc
