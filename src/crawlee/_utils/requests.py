from __future__ import annotations

import re
from base64 import b64encode
from hashlib import sha256
from logging import getLogger
from typing import TYPE_CHECKING, Optional
from urllib.parse import parse_qsl, urlencode, urlparse

from crawlee._utils.crypto import compute_short_hash

if TYPE_CHECKING:
    from crawlee._types import HttpMethod, HttpPayload

logger = getLogger(__name__)


def unique_key_to_request_id(unique_key: str, *, request_id_length: int = 15) -> str:
    """Generate a deterministic request ID based on a unique key.

    Args:
        unique_key: The unique key to convert into a request ID.
        request_id_length: The length of the request ID.

    Returns:
        A URL-safe, truncated request ID based on the unique key.
    """
    # Encode the unique key and compute its SHA-256 hash
    hashed_key = sha256(unique_key.encode('utf-8')).digest()

    # Encode the hash in base64 and decode it to get a string
    base64_encoded = b64encode(hashed_key).decode('utf-8')

    # Remove characters that are not URL-safe ('+', '/', or '=')
    url_safe_key = re.sub(r'(\+|\/|=)', '', base64_encoded)

    # Truncate the key to the desired length
    return url_safe_key[:request_id_length]


def normalize_url(url: str, *, keep_url_fragment: bool = False) -> str:
    """Normalizes a URL.

    This function cleans and standardizes a URL by removing leading and trailing whitespaces,
    converting the scheme and netloc to lower case, stripping unwanted tracking parameters
    (specifically those beginning with 'utm_'), sorting the remaining query parameters alphabetically,
    and optionally retaining the URL fragment. The goal is to ensure that URLs that are functionally
    identical but differ in trivial ways (such as parameter order or casing) are treated as the same.

    Args:
        url: The URL to be normalized.
        keep_url_fragment: Flag to determine whether the fragment part of the URL should be retained.

    Returns:
        A string containing the normalized URL.
    """
    # Parse the URL
    parsed_url = urlparse(url.strip())
    search_params = dict(parse_qsl(parsed_url.query))  # Convert query to a dict

    # Remove any 'utm_' parameters
    search_params = {k: v for k, v in search_params.items() if not k.startswith('utm_')}

    # Construct the new query string
    sorted_keys = sorted(search_params.keys())
    sorted_query = urlencode([(k, search_params[k]) for k in sorted_keys])

    # Construct the final URL
    new_url = (
        parsed_url._replace(
            query=sorted_query,
            scheme=parsed_url.scheme,
            netloc=parsed_url.netloc,
            path=parsed_url.path.rstrip('/'),
        )
        .geturl()
        .lower()
    )

    # Retain the URL fragment if required
    if not keep_url_fragment:
        new_url = new_url.split('#')[0]

    return new_url


def compute_unique_key(
    url: str,
    method: HttpMethod = 'GET',
    payload: Optional[HttpPayload] = None,
    *,
    keep_url_fragment: bool = False,
    use_extended_unique_key: bool = False,
    headers: Optional[dict[str, str]] = None,
    whitelisted_headers: Optional[list[str]] = None,
) -> str:
    """Computes a unique key for caching & deduplication of requests.

    This function computes a unique key by normalizing the provided URL and method.
    If `use_extended_unique_key` is True and a payload is provided, the payload is hashed and
    included in the key. If headers are provided, the whitelisted headers are also included in the key.

    Args:
        url: The request URL.
        method: The HTTP method, defaults to 'GET'.
        payload: The data to be sent as the request body, defaults to None.
        keep_url_fragment: A flag indicating whether to keep the URL fragment, defaults to False.
        use_extended_unique_key: A flag indicating whether to include a hashed payload in the key, defaults to False.
        headers: The HTTP headers to include in the key.
        whitelisted_headers: The list of whitelisted headers to include in the key.

    Returns:
        A string representing the unique key for the request.
    """
    # Normalize the URL and method.
    try:
        normalized_url = normalize_url(url, keep_url_fragment=keep_url_fragment)
    except Exception as exc:
        logger.warning(f'Failed to normalize URL: {exc}')
        normalized_url = url

    normalized_method = method.upper()

    # Compute the payload hash if required.
    if use_extended_unique_key and payload:
        if isinstance(payload, str):
            payload_in_bytes = payload.encode('utf-8')
        else:
            payload_in_bytes = payload

        payload_hash = compute_short_hash(payload_in_bytes)
        extended_key = f'{normalized_method}({payload_hash}):{normalized_url}'
    else:
        extended_key = normalized_url

    # Include whitelisted headers in the key.
    if headers and whitelisted_headers:
        header_parts = [f'{header}:{headers[header]}' for header in whitelisted_headers if header in headers]
        header_part = '|'.join(header_parts)
        return f'{extended_key}|{header_part}'

    return extended_key
