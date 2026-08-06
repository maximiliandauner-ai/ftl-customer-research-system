# Core application ownership

`apps.core` owns abstract UUID/time model primitives, safe structured logging, runtime system checks, and public liveness/readiness probes. It must not own commercial domain records or provider-specific behavior.
