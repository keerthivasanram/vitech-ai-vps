"""Create the first administrator and the agents' service key.

    .venv/bin/python -m app.auth.bootstrap admin  <username> [password]
    .venv/bin/python -m app.auth.bootstrap user   <username> [password] [role]
    .venv/bin/python -m app.auth.bootstrap service <name>
    .venv/bin/python -m app.auth.bootstrap list

Deny-by-default means an empty user table locks everyone out, which is the
correct failure but needs a way in. This is that way, and it is deliberately a
COMMAND rather than an environment variable read at startup: a seeded password
sitting in `.env` is a credential in a file that gets copied around, and it
tends to survive into production unchanged.

A generated password is printed ONCE and stored only as a hash.
"""
import secrets
import string
import sys

from . import store


def _generated() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    return "".join(secrets.choice(alphabet) for _ in range(20))


def _create_user(username: str, password: str | None, role: str) -> int:
    generated = password is None
    password = password or _generated()
    if store.get_user(username):
        print(f"User '{username}' already exists. Use `password` to reset it.")
        return 1
    store.create_user(username, password, name=username, role=role,
                      must_change=generated)
    print(f"Created {role} '{username}'.")
    if generated:
        print(f"  password: {password}")
        print("  (shown once; stored only as a scrypt hash. Change it at first login.)")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, *rest = argv

    if cmd == "admin":
        if not rest:
            print("usage: bootstrap admin <username> [password]")
            return 1
        return _create_user(rest[0], rest[1] if len(rest) > 1 else None, store.ROLE_ADMIN)

    if cmd == "user":
        if not rest:
            print("usage: bootstrap user <username> [password] [role]")
            return 1
        role = rest[2] if len(rest) > 2 else store.ROLE_ENGINEER
        if role not in store.HUMAN_ROLES:
            print(f"role must be one of {store.HUMAN_ROLES}")
            return 1
        return _create_user(rest[0], rest[1] if len(rest) > 1 else None, role)

    if cmd == "password":
        if len(rest) < 2:
            print("usage: bootstrap password <username> <new-password>")
            return 1
        row = store.get_user(rest[0])
        if not row:
            print(f"No such user: {rest[0]}")
            return 1
        store.set_password(row["id"], rest[1])
        n = store.revoke_user_sessions(row["id"])
        print(f"Password reset for '{rest[0]}'; {n} session(s) revoked.")
        return 0

    if cmd == "service":
        name = rest[0] if rest else "flowise-agents"
        key = store.create_service(name)
        print(f"Service principal '{name}' created/rotated.")
        print(f"  key: {key}")
        print("  (shown ONCE. Put it in the Flowise tool rows as the X-API-Key header;")
        print("   see ops/rotate-service-key.md. Only /api/tools/* accepts it.)")
        return 0

    if cmd == "list":
        print("Users:")
        for u in store.list_users():
            flag = "" if u["active"] else "  [disabled]"
            print(f"  {u['username']:20s} {u['role']:10s}{flag}")
        print("Service principals:")
        for s in store.list_services():
            flag = "" if s["active"] else "  [disabled]"
            print(f"  {s['name']:20s} {s['key_prefix']}…{flag}")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
