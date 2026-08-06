# Accounts application ownership

`apps.accounts` owns the canonical FTL team role, its assignment service, and group/permission policy. Django's built-in user remains the authentication identity under ADR-002. Users are deactivated rather than deleted so operational and audit authorship remains intact.

