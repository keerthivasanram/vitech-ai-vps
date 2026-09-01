"""HTTP layer, split by concern.

`main.py` was a single 1,415-line module carrying 34 endpoints alongside the
response-assembly helpers. Splitting it changes no behaviour — every function
was moved verbatim, and `tests_api_contract.py` fingerprints all 28 endpoints
plus the OpenAPI schema to prove it.

The split also makes access control tractable: Phase B can apply an auth
dependency to a whole router in one line instead of decorating 34 functions,
and the security matrix maps naturally onto these modules.

ROUTER ORDER MATTERS where paths overlap — see `data.py`.
"""
