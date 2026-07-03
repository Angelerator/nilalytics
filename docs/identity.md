# Identity & cross‑device

nilalytics tracks users across devices **without knowing who they are**, using a
deterministic, pseudonymous model. There is no fingerprinting.

## Three IDs

| Attribute | Meaning | Set when |
|-----------|---------|----------|
| `anonymous.id` | a device / browser (random UUID, cookieless) | always |
| `session.id` | one visit / app session | always |
| `user.id` | a **person**, as a salted hash | after the user connects a shared key (login) |

Before login, two devices are genuinely **unlinkable** — the privacy‑correct
default. They merge only once the user connects them.

## Pseudonymous by design

`user.id` is a **salted hash** of a shared key (email, account id), computed
**client‑side**. The lake stores a stable person‑key it cannot reverse into a
real identity.

```python
# how nilalytics hashes (client-side)
import hashlib
def hash_key(raw, salt):
    return hashlib.sha256((salt + raw).encode()).hexdigest()[:32]
```

The salt is `NILA_ID_SALT` (auto‑generated and stored in the secrets file).

## The `identify` event

When a device learns the user, it emits an `identify` event linking that
device's `anonymous.id` to the hashed `user.id`. That single event is what makes
cross‑device stitching possible.

```
phone   anonymous.id=A1 ──identify──▶ user.id = hash(email)
laptop  anonymous.id=B7 ──identify──▶ user.id = hash(email)   ← same hash → same person
```

## Stitching

The `stitch` query builds the identity graph and unifies a person's activity
across all their devices:

```bash
nilalytics query stitch
```

```
person -> devices:
  88a52ac6...  2 device(s)  <-- multi-device
  ...
persons seen on >1 device: 5

unified events per person (across their devices):
  88a52ac6...  16 events across devices
```

## In your apps

- **Web (Faro):** `faro.api.setSession({id})`, `faro.api.setUser({id: hash})`, and a persisted `anonymous.id`. See [Web](web.md).
- **Mobile (OTel):** the same three attributes, with `anonymous.id` in Keychain / SharedPreferences. See [Mobile](mobile.md).

## Privacy notes

- Deterministic + hashed + consented is the defensible model; fingerprinting is not.
- Add a consent flag to events so you can honor opt‑outs.
- This is guidance, not legal advice.
