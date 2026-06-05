import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.config import settings


class AuthError(Exception):
    pass


_HMAC_ALGORITHMS = {
    "HS256": hashlib.sha256,
    "HS384": hashlib.sha384,
    "HS512": hashlib.sha512,
}

_RSA_ALGORITHMS = {
    "RS256": hashes.SHA256,
    "RS384": hashes.SHA384,
    "RS512": hashes.SHA512,
}


def _b64url_decode(raw: str) -> bytes:
    padded = raw + ("=" * (-len(raw) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("utf-8"))
    except Exception as exc:
        raise AuthError("Malformed JWT encoding.") from exc


def _load_json_segment(segment: str) -> Dict[str, Any]:
    decoded = _b64url_decode(segment)
    try:
        value = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise AuthError("Malformed JWT payload.") from exc
    if not isinstance(value, dict):
        raise AuthError("Malformed JWT structure.")
    return value


def _to_int(value: Any, claim_name: str) -> int:
    try:
        return int(value)
    except Exception as exc:
        raise AuthError(f"Invalid '{claim_name}' claim type.") from exc


def _validate_time_claims(payload: Dict[str, Any]) -> None:
    now = int(time.time())
    leeway = max(0, int(settings.JWT_LEEWAY_SECONDS))

    if "exp" in payload:
        exp = _to_int(payload["exp"], "exp")
        if now > exp + leeway:
            raise AuthError("Token has expired.")

    if "nbf" in payload:
        nbf = _to_int(payload["nbf"], "nbf")
        if now + leeway < nbf:
            raise AuthError("Token is not active yet.")

    if "iat" in payload:
        iat = _to_int(payload["iat"], "iat")
        if now + leeway < iat:
            raise AuthError("Token issued-at time is in the future.")


def _validate_issuer_and_audience(payload: Dict[str, Any]) -> None:
    expected_issuer = settings.JWT_ISSUER.strip()
    if expected_issuer:
        actual_issuer = payload.get("iss")
        if actual_issuer != expected_issuer:
            raise AuthError("Invalid token issuer.")

    expected_audience = settings.JWT_AUDIENCE.strip()
    if expected_audience:
        actual_audience = payload.get("aud")
        if isinstance(actual_audience, str):
            is_valid = actual_audience == expected_audience
        elif isinstance(actual_audience, list):
            is_valid = expected_audience in {str(v) for v in actual_audience}
        else:
            is_valid = False
        if not is_valid:
            raise AuthError("Invalid token audience.")


def decode_and_validate_jwt(token: str) -> Dict[str, Any]:
    if not token:
        raise AuthError("Missing bearer token.")

    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("Malformed JWT.")

    header = _load_json_segment(parts[0])
    payload = _load_json_segment(parts[1])
    signature = _b64url_decode(parts[2])

    expected_alg = settings.JWT_ALGORITHM.strip().upper() or "HS256"
    header_alg = str(header.get("alg", "")).upper()
    if header_alg != expected_alg:
        raise AuthError("Unexpected token algorithm.")

    signing_input = f"{parts[0]}.{parts[1]}".encode("utf-8")

    digest_fn = _HMAC_ALGORITHMS.get(expected_alg)
    if digest_fn:
        secret = settings.JWT_SECRET_KEY.strip()
        if not secret:
            raise AuthError("JWT secret is not configured on the server.")
        expected_signature = hmac.new(secret.encode("utf-8"), signing_input, digest_fn).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise AuthError("Invalid token signature.")
    else:
        rsa_hash_fn = _RSA_ALGORITHMS.get(expected_alg)
        if not rsa_hash_fn:
            raise AuthError(
                f"Unsupported JWT algorithm '{expected_alg}'. Use one of: "
                f"{', '.join([*sorted(_HMAC_ALGORITHMS), *sorted(_RSA_ALGORITHMS)])}."
            )

        key_path = settings.JWT_PUBLIC_KEY_PATH.strip()
        if not key_path:
            raise AuthError("JWT public key path is not configured for RSA verification.")
        try:
            with open(key_path, "rb") as f:
                public_key_bytes = f.read()
        except OSError as exc:
            raise AuthError("JWT public key file could not be read.") from exc

        try:
            public_key = serialization.load_pem_public_key(public_key_bytes)
            public_key.verify(
                signature,
                signing_input,
                padding.PKCS1v15(),
                rsa_hash_fn(),
            )
        except InvalidSignature as exc:
            raise AuthError("Invalid token signature.") from exc
        except Exception as exc:
            raise AuthError("JWT public key is invalid.") from exc

    _validate_time_claims(payload)
    _validate_issuer_and_audience(payload)
    return payload
