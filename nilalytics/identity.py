"""Pseudonymous identity: turn a raw user key into a stable person id.

A "user key" is any **stable, unique** string that identifies a person -- an
internal account id, an email, a phone number, etc. nilalytics is *key-agnostic*:
it hashes whatever you give it (salted with ``NILA_ID_SALT``) into a 32-char person
id. The raw value never reaches the lake, but re-hashing the same key always finds
the same person -- so you get privacy *and* lookup.

Two rules for the key:

* **Normalize before hashing** (lowercase emails, E.164 phones) -- ``A@x.com`` and
  ``a@x.com`` hash to different people otherwise.
* Use the **same** key at identify-time and lookup-time.
"""

from __future__ import annotations

import hashlib

from . import config


def hash_key(raw_key: str) -> str:
    """Salted hash of a raw user key -> stable pseudonymous person id (32 hex chars)."""
    return hashlib.sha256((config.ID_SALT + raw_key).encode()).hexdigest()[:32]


_USAGE = (
    "usage: nilalytics identify <user-key>\n\n"
    "Prints the person_id for a raw user key (email / account id / phone),\n"
    "so you never hash by hand. Look someone up with:\n"
    "  nilalytics query user $(nilalytics identify alireza@example.com) 3"
)


def main(argv=None) -> None:
    argv = list(argv or [])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_USAGE)
        return
    print(hash_key(argv[0]))
