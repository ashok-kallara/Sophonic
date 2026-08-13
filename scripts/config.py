#!/usr/bin/env python3
"""Read/write Sophonic config (~/.sophonic/config.toml + .env) → JSON.

    uv run python scripts/config.py show
    uv run python scripts/config.py get vault.path
    uv run python scripts/config.py set vault.path /Users/me/vault
    uv run python scripts/config.py set features.gitlab true
    uv run python scripts/config.py unset gitlab.url
    uv run python scripts/config.py set-secret ZOOM_COOKIES --stdin   # paste, then Enter

Secrets go to ~/.sophonic/.env (0600); prefer --stdin so the value never lands in
shell history or a tool-call transcript. Non-secret settings are validated against the
config schema before they are written.
"""

from __future__ import annotations

import argparse
import sys

from _common import emit


def main() -> None:
    p = argparse.ArgumentParser(description="View and edit Sophonic configuration.")
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("show", help="Print effective config (secrets redacted)")
    g = sub.add_parser("get", help="Print one config value")
    g.add_argument("key", help="Dotted key, e.g. llm.model")
    s = sub.add_parser("set", help="Set a config key (validated)")
    s.add_argument("key")
    s.add_argument("value")
    u = sub.add_parser("unset", help="Remove a config key (revert to default)")
    u.add_argument("key")
    ss = sub.add_parser("set-secret", help="Store a secret in .env (0600)")
    ss.add_argument("name", help="Env var name, e.g. ZOOM_COOKIES or GITLAB_TOKEN")
    ss.add_argument("--stdin", action="store_true", help="Read the secret from stdin (recommended)")
    ss.add_argument("--value", help="Secret value (avoid — lands in shell history)")

    args = p.parse_args()

    from sophonic import config_io

    if args.action == "show":
        data = config_io.redacted()
        data["_secrets_in_env"] = config_io.env_secret_names()
        emit(data)
        return

    if args.action == "get":
        from sophonic.config import load_config

        node = load_config().model_dump(mode="json")
        for part in args.key.split("."):
            if not isinstance(node, dict) or part not in node:
                emit({"error": f"Unknown config key: {args.key}"})
                raise SystemExit(1)
            node = node[part]
        emit({args.key: node})
        return

    if args.action == "set":
        try:
            coerced = config_io.set_key(args.key, args.value)
        except Exception as exc:  # noqa: BLE001
            emit({"error": str(exc)})
            raise SystemExit(1)
        emit({"set": args.key, "value": coerced})
        return

    if args.action == "unset":
        try:
            removed = config_io.unset_key(args.key)
        except Exception as exc:  # noqa: BLE001
            emit({"error": str(exc)})
            raise SystemExit(1)
        emit({"unset": args.key, "removed": removed})
        return

    # set-secret
    if args.stdin:
        secret = sys.stdin.readline().rstrip("\n")
    elif args.value is not None:
        secret = args.value
    else:
        emit({"error": "Provide --stdin or --value"})
        raise SystemExit(1)
    if not secret:
        emit({"error": "Empty secret"})
        raise SystemExit(1)
    config_io.set_secret(args.name, secret)
    emit({"set_secret": args.name, "file": str(config_io.env_file())})


if __name__ == "__main__":
    main()
