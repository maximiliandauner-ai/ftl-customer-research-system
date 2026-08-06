# Sources application ownership

`apps.sources` owns source candidates/endpoints, every fetch attempt, immutable source snapshots and storage-backed artifacts, safe-fetch policy, ingestion orchestration, and source-facing views. Connector parsing and normalized job postings belong to the later `jobs` app; raw fetched content is never rendered by this app.
