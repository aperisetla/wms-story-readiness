"""One-off helper: push GitHub repository secrets via the REST API.

Reads GH_PAT, GH_OWNER, GH_REPO and the secret name/value pairs from env,
fetches the repo's public key, encrypts each value with libsodium sealed
box, and PUTs it to /repos/{owner}/{repo}/actions/secrets/{name}.

Not committed intentionally (kept local; safe to delete after use).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from nacl import encoding, public


def _req(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "wms-story-readiness-bootstrap")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")}


def encrypt(public_key_b64: str, secret_value: str) -> str:
    pub = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(pub)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def main() -> int:
    token = os.environ["GH_PAT"]
    owner = os.environ["GH_OWNER"]
    repo = os.environ["GH_REPO"]
    secrets = json.loads(os.environ["GH_SECRETS_JSON"])  # {name: value}

    status, key = _req(
        "GET",
        f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key",
        token,
    )
    if status != 200:
        print(f"Failed to fetch public key: {status} {key}")
        return 1
    key_id = key["key_id"]
    pub_b64 = key["key"]

    for name, value in secrets.items():
        encrypted = encrypt(pub_b64, value)
        status, body = _req(
            "PUT",
            f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{name}",
            token,
            {"encrypted_value": encrypted, "key_id": key_id},
        )
        if status in (201, 204):
            print(f"OK  {name}")
        else:
            print(f"FAIL {name}: {status} {body}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
