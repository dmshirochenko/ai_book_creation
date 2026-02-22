"""Rate limiter configuration."""

from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_rate_limit_key(request):
    """Key by X-User-Id header when present, otherwise by IP."""
    user_id = request.headers.get("X-User-Id")
    if user_id:
        return user_id
    return get_remote_address(request)


limiter = Limiter(key_func=_get_rate_limit_key)
