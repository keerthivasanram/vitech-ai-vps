"""Developer-operations backend: tracing, logging, jobs, metrics.

STRICTLY ADDITIVE. Nothing in here may change an engineering calculation, a
document, a retrieval result or a response body. The proof is
`tests_api_contract.py`: all 28 endpoint fingerprints must stay byte-identical
*without re-recording* after Phase C. That is why the request id travels as an
`X-Request-ID` response header and a `contextvar` and never enters a payload.

Two rules this package holds itself to:

1. **Observability never blocks engineering.** Records go onto a bounded queue
   and are written by a background thread. If the queue is full the record is
   DROPPED and counted — a lost span is acceptable, a stalled quotation is not.

2. **Customer requirements never reach the logs.** The requirement text is
   engineering data: it belongs on the job record, behind a role, and nowhere
   else. Log lines carry the request id, so a trace can be reconstructed
   without copying customer content into a file that gets tailed and shipped.
"""
