"""Server-side authentication, roles and audit.

Three principal kinds, and the distinction is the point:

    ENGINEER ......... a human. Runs the engines, generates documents.
    ADMINISTRATOR .... a human. Everything an engineer can do, plus system state.
    INTERNAL SERVICE . not a human. The Flowise agents, holding a service key
                       that reaches ONLY the agent tool endpoints.

A service principal is deliberately NOT "an engineer with a longer-lived
credential". It sits on its own axis with an explicit route allow-list, so a
leaked agent key cannot ingest, upload, read logs or browse the database — it
can only do the seven things the agents actually do.

STORAGE. This uses SQLite (`sqlite3`, standard library) on the persistent
volume, not the Postgres that Flowise runs on. Two reasons, both practical:
the backend has no Postgres client at all today, so Postgres would mean adding
`psycopg` to a dependency list the production review already flagged as
under-pinned; and Flowise owns `user`, `role`, `credential` and `apikey` in that
database, where the three agents live — the one asset not reproducible from git.
Keeping auth in its own file removes the collision risk entirely rather than
managing it. All SQL lives in `store.py`, so moving to Postgres later is one
module, not a rewrite.
"""
