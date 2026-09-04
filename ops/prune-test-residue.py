#!/usr/bin/env python3
"""Remove the test residue that `tests_observability.py` left in the LIVE store.

    .venv/bin/python ../ops/prune-test-residue.py            # dry run (default)
    .venv/bin/python ../ops/prune-test-residue.py --apply    # actually delete

Run it from `backend/`. TAKE A BACKUP FIRST: `bash ops/backup.sh`.

WHY THIS EXISTS
---------------
Until 2026-09-04 `tests_observability.py` wrote into the real `ops.db` and
`data/jobs/` instead of a temp directory. One of its checks deliberately
tampers an artifact — `Path(row["path"]).write_bytes(b"tampered")` — to prove
that a file which no longer matches its digest is refused rather than served.
That is a good check. But because it ran against the live store, every run left
a permanently CORRUPT artifact and a fake job row behind, in a store the
platform declares PERMANENT and never purges.

Two things that actually matter followed from it:

  * the job history an engineer reads in Package Center filled with fake rows;
  * an integrity sweep of the artifact store reported dozens of corrupt
    documents, all of them residue. A corruption monitor that always fires is
    one nobody believes on the day it fires for real — which is the whole
    reason the digest is recorded.

The test is fixed (it now isolates itself, and asserts that it did). This
removes what the old behaviour already deposited. It is a ONE-OFF; if it ever
finds anything again, the isolation in that suite has regressed.

THE SIGNATURE IS DELIBERATELY NARROW. A job is removed only when ALL of:
  * it owns an artifact named exactly `Test.pdf`, AND
  * that file's bytes are exactly b"tampered" — the string the suite writes, AND
  * the job's actor is `alice` and its kind is `specification` — the fixture.
Nothing else is touched. A real customer document cannot match all four.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../backend")
sys.path.insert(0, os.getcwd())

# Never let an inherited test override point this at the wrong database: the
# whole job is to clean the LIVE store.
for _v in ("OPS_DB", "ARTIFACT_DIR"):
    os.environ.pop(_v, None)

from app.observability import artifacts, store        # noqa: E402

FIXTURE_BYTES = b"tampered"
APPLY = "--apply" in sys.argv


def main() -> int:
    conn = store.connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM vitech_artifact WHERE name='Test.pdf'").fetchall()]

    targets = []
    for a in rows:
        path = a.get("path") or ""
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            if f.read() != FIXTURE_BYTES:
                continue
        job = store.get_job(a["job_id"]) or {}
        if job.get("actor") == "alice" and job.get("kind") == "specification":
            targets.append(a["job_id"])

    total_jobs = conn.execute("SELECT count(*) FROM vitech_job").fetchone()[0]
    total_arts = conn.execute("SELECT count(*) FROM vitech_artifact").fetchone()[0]
    print(f"store holds {total_jobs} jobs / {total_arts} artifact rows")
    print(f"{len(targets)} match the test-fixture signature")

    if not targets:
        print("nothing to do — the store is clean")
        return 0

    keep = conn.execute(
        "SELECT DISTINCT name FROM vitech_artifact WHERE job_id NOT IN (%s)"
        % ",".join("?" * len(targets)), targets).fetchall()
    print(f"artifacts that will be KEPT: {sorted(r[0] for r in keep)}")

    if not APPLY:
        print("\nDRY RUN — nothing changed. Re-run with --apply to delete.")
        return 0

    removed = 0
    for job_id in targets:
        directory = artifacts.job_dir(job_id)
        if directory.exists():
            shutil.rmtree(directory)
            removed += 1
    placeholders = ",".join("?" * len(targets))
    conn.execute(f"DELETE FROM vitech_artifact WHERE job_id IN ({placeholders})", targets)
    conn.execute(f"DELETE FROM vitech_job WHERE job_id IN ({placeholders})", targets)
    conn.commit()

    print(f"removed {removed} job folders and {len(targets)} job rows")
    print("jobs remaining:",
          conn.execute("SELECT count(*) FROM vitech_job").fetchone()[0])
    print("artifact rows remaining:",
          conn.execute("SELECT count(*) FROM vitech_artifact").fetchone()[0])
    print("\nNow re-run `bash ops/backup.sh` — it should report every artifact "
          "digest-verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
