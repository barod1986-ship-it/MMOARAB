from __future__ import annotations

import hmac
import ipaddress

from fastapi import Request

from .config import PairingStore, is_valid_extension_origin
from .errors import EngineApiError


def peer_is_loopback(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def extract_bearer(value: str | None) -> str:
    if not value or not value.startswith("Bearer "):
        raise EngineApiError("unauthorized", "Missing bearer token.", status_code=401)
    token = value[7:]
    if not token or len(token) > 512:
        raise EngineApiError("unauthorized", "Invalid bearer token.", status_code=401)
    return token


def authenticate_request(request: Request, pairing: PairingStore, *, allow_pairing: bool = False) -> str:
    origin = request.headers.get("origin")
    if not origin or not is_valid_extension_origin(origin):
        raise EngineApiError("unauthorized", "Sensitive endpoints require an exact extension origin.", status_code=401)
    supplied = extract_bearer(request.headers.get("authorization"))
    if not hmac.compare_digest(supplied.encode("utf-8"), pairing.token.encode("utf-8")):
        raise EngineApiError("unauthorized", "Invalid bearer token.", status_code=401)
    paired = pairing.paired_origin
    if paired is None:
        if not allow_pairing:
            raise EngineApiError("unauthorized", "Engine pairing is required.", status_code=401)
        try:
            pairing.pair(origin)
        except (ValueError, PermissionError) as exc:
            raise EngineApiError("unauthorized", str(exc), status_code=401) from exc
        paired = origin
    if not hmac.compare_digest(origin.encode("utf-8"), paired.encode("utf-8")):
        raise EngineApiError("unauthorized", "Extension origin does not match the paired origin.", status_code=401)
    return origin
