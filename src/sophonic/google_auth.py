"""Shared Google OAuth 2.0 desktop-app flow for gcal + gmail."""

from __future__ import annotations

from pathlib import Path

from sophonic.config import config_dir, load_config


def _token_path() -> Path:
    tokens = config_dir() / "tokens"
    tokens.mkdir(mode=0o700, parents=True, exist_ok=True)
    return tokens / "google.json"


def _require_desktop_client(secret_file: Path) -> None:
    """Fail early with a clear message if the client secret is a Web-app client.

    Sophonic authenticates via a localhost loopback port (`run_local_server`), which
    only a 'Desktop app' OAuth client accepts. A 'Web application' client requires
    exact pre-registered redirect URIs and otherwise fails with a confusing
    `redirect_uri_mismatch` error from Google.
    """
    import json

    try:
        data = json.loads(secret_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read Google client secret at {secret_file}: {exc}") from exc

    if "installed" not in data and "web" in data:
        raise ValueError(
            f"{secret_file} is a 'Web application' OAuth client, but Sophonic needs a "
            "'Desktop app' client (it signs in via a localhost loopback port). In Google "
            "Cloud Console → APIs & Services → Credentials, create an OAuth client ID of "
            "type 'Desktop app', download the JSON, and replace this file. See the README "
            "'Google OAuth setup' section."
        )


def _granted_scopes(token_path: Path) -> set[str]:
    """Scopes actually granted in a stored token file (empty if missing/unreadable)."""
    import json
    try:
        return set(json.loads(token_path.read_text(encoding="utf-8")).get("scopes", []))
    except (OSError, json.JSONDecodeError):
        return set()


def _token_covers(token_path: Path, scopes: list[str]) -> bool:
    """True if the stored token was granted every requested scope."""
    return set(scopes).issubset(_granted_scopes(token_path))


def get_credentials():
    """Return valid Google credentials, running OAuth flow if needed."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError

    cfg = load_config().google
    scopes = cfg.scopes
    token_path = _token_path()
    secret_file = Path(str(cfg.client_secret_file).replace("~", str(Path.home())))

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        # A stored token only carries the scopes granted at consent time; adding a scope
        # to config does not expand it, and a refresh cannot add scopes. If the token is
        # missing any requested scope, discard it so the full consent flow re-runs.
        if creds and not _token_covers(token_path, scopes):
            creds = None

    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError:
                # Revoked/expired refresh token, or scopes changed — fall back to consent.
                creds = None
        if not refreshed:
            if not secret_file.exists():
                raise FileNotFoundError(
                    f"Google OAuth client secret not found at {secret_file}. "
                    "Download it from https://console.cloud.google.com/ and place it there."
                )
            _require_desktop_client(secret_file)
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_file), scopes)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        token_path.chmod(0o600)

    return creds
