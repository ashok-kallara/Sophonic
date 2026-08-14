"""Config read/write CLI — shared by the `sophonic-config` console script and the
plugin's `scripts/config.py` shim (which skills call over Bash).

Prints a single JSON object. Secrets go to ~/.sophonic/.env (0600); prefer --stdin so a
value never lands in shell history or a tool-call transcript. Non-secret settings are
validated against the config schema before they are written.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sophonic-config", description="View and edit Sophonic configuration.")
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("show", help="Print effective config (secrets redacted)")
    g = sub.add_parser("get", help="Print one config value")
    g.add_argument("key", help="Dotted key, e.g. vault.path")
    s = sub.add_parser("set", help="Set a config key (validated)")
    s.add_argument("key")
    s.add_argument("value")
    u = sub.add_parser("unset", help="Remove a config key (revert to default)")
    u.add_argument("key")
    ss = sub.add_parser("set-secret", help="Store a secret in .env (0600)")
    ss.add_argument("name", help="Env var name, e.g. ZOOM_COOKIES or GITLAB_TOKEN")
    ss.add_argument("--stdin", action="store_true", help="Read the secret from stdin (recommended)")
    ss.add_argument("--value", help="Secret value (avoid — lands in shell history)")

    args = p.parse_args(argv)

    from sophonic import config_io

    if args.action == "show":
        data = config_io.redacted()
        data["_secrets_in_env"] = config_io.env_secret_names()
        _emit(data)
        return 0

    if args.action == "get":
        from sophonic.config import load_config

        node = load_config().model_dump(mode="json")
        for part in args.key.split("."):
            if not isinstance(node, dict) or part not in node:
                _emit({"error": f"Unknown config key: {args.key}"})
                return 1
            node = node[part]
        _emit({args.key: node})
        return 0

    if args.action == "set":
        try:
            coerced = config_io.set_key(args.key, args.value)
        except Exception as exc:  # noqa: BLE001
            _emit({"error": str(exc)})
            return 1
        _emit({"set": args.key, "value": coerced})
        return 0

    if args.action == "unset":
        try:
            removed = config_io.unset_key(args.key)
        except Exception as exc:  # noqa: BLE001
            _emit({"error": str(exc)})
            return 1
        _emit({"unset": args.key, "removed": removed})
        return 0

    # set-secret
    if args.stdin:
        secret = sys.stdin.readline().rstrip("\n")
    elif args.value is not None:
        secret = args.value
    else:
        _emit({"error": "Provide --stdin or --value"})
        return 1
    if not secret:
        _emit({"error": "Empty secret"})
        return 1
    config_io.set_secret(args.name, secret)
    _emit({"set_secret": args.name, "file": str(config_io.env_file())})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
