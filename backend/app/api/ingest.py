"""Offer-record ingestion into the vector store."""
from fastapi import APIRouter
from .. import config
from .. import jobs
from ..ingest import ingest_source

router = APIRouter()


@router.post("/api/ingest")
def run_ingest(reset: bool = True):
    """Kick off batched ingestion in the background and return a job id.
    Poll GET /api/ingest/{job_id} for progress. Scales to thousands of files."""
    job_id = jobs.create_job()

    def work(progress):
        return ingest_source(
            reset=reset,
            batch_size=config.BATCH_SIZE,
            progress=lambda done, _total: progress(done),
        )

    jobs.run(job_id, work)
    return {"job_id": job_id, "source": str(config.DATA_SOURCE),
            "batch_size": config.BATCH_SIZE}


@router.get("/api/ingest/{job_id}")
def ingest_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return {"error": "unknown job_id"}
    return job
