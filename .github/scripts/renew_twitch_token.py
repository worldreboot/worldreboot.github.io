"""Renew the app access token in code without logging credentials."""

import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib import error, parse, request


RENEW_BEFORE_SECONDS = 7 * 24 * 60 * 60


def request_json(req, allow_expired=False):
    try:
        with request.urlopen(req, timeout=30) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        if allow_expired and exc.code == 401:
            return None
        raise RuntimeError(f"Twitch returned HTTP {exc.code}; code was not changed.") from None
    except (error.URLError, TimeoutError, ValueError):
        raise RuntimeError("Twitch request failed; code was not changed.") from None
    if not isinstance(result, dict):
        raise RuntimeError("Twitch returned an invalid response; code was not changed.")
    return result


def validate(token):
    return request_json(
        request.Request(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f"Bearer {token}"},
        ),
        allow_expired=True,
    )


def check_app(metadata, client_id):
    if metadata.get("user_id"):
        raise RuntimeError("This job supports app tokens only; code was not changed.")
    if metadata.get("client_id") != client_id:
        raise RuntimeError("Token belongs to a different Twitch app; code was not changed.")
    expires_in = metadata.get("expires_in")
    if type(expires_in) is not int or expires_in <= 0:
        raise RuntimeError("Twitch returned an invalid token lifetime; code was not changed.")
    return expires_in


def renew(token_path=Path("code"), force=False):
    client_id = os.environ.get("TWITCH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("TWITCH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Set the TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET repository secrets.")

    existing = token_path.read_text(encoding="utf-8").strip() if token_path.exists() else ""
    if existing:
        if not re.fullmatch(r"Bearer [A-Za-z0-9._~-]+", existing):
            raise RuntimeError("code has an unexpected format; it was not changed.")
        metadata = validate(existing.removeprefix("Bearer "))
        if metadata is not None:
            remaining = check_app(metadata, client_id)
            if remaining > RENEW_BEFORE_SECONDS and not force:
                print(f"Token remains valid for {remaining // 86400} days; no renewal needed.")
                return False

    body = parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }).encode("utf-8")
    result = request_json(request.Request(
        "https://id.twitch.tv/oauth2/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ))
    token = result.get("access_token")
    if (not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9._~-]+", token)
            or result.get("token_type", "").lower() != "bearer"):
        raise RuntimeError("Twitch returned an invalid access token; code was not changed.")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{token}", flush=True)
    metadata = validate(token)
    if metadata is None:
        raise RuntimeError("New Twitch token failed validation; code was not changed.")
    check_app(metadata, client_id)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=token_path.parent,
                                         delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(f"Bearer {token}")
        temporary_path.replace(token_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print("Renewed and validated the Twitch app token.")
    return True


if __name__ == "__main__":
    try:
        renew(force=os.environ.get("FORCE_RENEW", "false").lower() == "true")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
