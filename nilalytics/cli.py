"""Unified nilalytics command-line interface.

After installing the package (``pip install nilalytics`` / ``uv sync``), the
``nilalytics`` command is available anywhere:

    nilalytics server                 # ingest + Quack catalog server
    nilalytics gateway                # public ingest gateway (CORS, tokens, TLS)
    nilalytics emit --persons 5       # send sample events
    nilalytics query report           # analytics report over Quack
    nilalytics query user --key alireza@example.com 3   # one person's activity, last 3 days
    nilalytics identify alireza@example.com             # -> that person's person_id
    nilalytics maintenance --expire   # flush inlined data + compact

Each subcommand delegates to its module, which is also runnable directly via
``python -m nilalytics.<module>``.
"""

from __future__ import annotations

import sys

_USAGE = """usage: nilalytics <command> [args]

commands:
  server                      run the ingest + Quack catalog server
  gateway                     run the public ingest gateway (CORS, short-lived tokens, TLS)
  emit [options]              send sample logs/traces/metrics (--persons for cross-device)
  query [subcommand] [args]   report | user_events | user <id|--key value> [days] | subject <name> [days] | traces | metrics | stitch | asof | changes | snapshots | errors
  identify <user-key>         print the person_id for a raw key (email / account id / phone)
  maintenance [--expire]      flush inlined data to Parquet + compact
  maintenance --retention-dry-run [--days N]   preview what data retention would delete (read-only)
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_USAGE)
        return 0

    command, rest = argv[0], argv[1:]
    if command == "server":
        from . import server
        server.main(rest)
    elif command == "gateway":
        from . import gateway
        gateway.main(rest)
    elif command == "emit":
        from . import emitter
        emitter.main(rest)
    elif command == "query":
        from . import query
        query.main(rest)
    elif command == "identify":
        from . import identity
        identity.main(rest)
    elif command == "maintenance":
        from . import maintenance
        maintenance.main(rest)
    else:
        print(f"unknown command: {command}\n\n{_USAGE}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
