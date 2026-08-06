# 29 — Backup, Restore, and Local-to-Server Migration

**Specification version:** 2.1  
**Primary owner:** DevOps and data

## Purpose

Make PostgreSQL and artifact data portable from the laptop to a future server, prove restore integrity, and avoid code or schema redesign during deployment.

## Transfer unit

```text
immutable application image/tag and Git commit
PostgreSQL logical backup
artifact/media/report archive or object-store copy
active knowledge release/Git commit
production environment and secrets (transferred separately)
backup manifest and checksums
```

Redis/broker contents are not canonical and are not part of disaster recovery.

## Backup layout

```text
backups/<timestamp>/
  database.dump
  artifacts.tar.zst or object_manifest.json
  backup_manifest.json
  SHA256SUMS
```

## Correct PostgreSQL backup command

Do not rely on host-shell expansion of container-only environment variables.

```bash
mkdir -p "backups/$STAMP"
docker compose exec -T postgres sh -lc \
  'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner --no-acl' \
  > "backups/$STAMP/database.dump"
```

Check the pipeline exit status, non-zero file size, `pg_restore --list`, and SHA-256. The script records PostgreSQL server/client version, schema migration leaf nodes, application image/tag, Git commit, row-count summary, artifact count/bytes, and timestamp.

## BackupRecordV2

```text
started_at/completed_at
status running|complete|verification_failed|failed
backup_type full|database_only|artifact_only
postgres_version
schema_migration_manifest
app_git_commit/app_image
file/storage locations
size_bytes
sha256
artifact_manifest_hash
verified_at
restore_drill_at nullable
safe_error
```

## Artifact backup

When using local Django storage:

- quiesce or snapshot consistently according to policy;
- archive configured media/report roots;
- include storage keys and hashes from `SourceArtifact`;
- verify artifact manifest against files.

With S3-compatible storage, copy/version according to provider policy and export a manifest; do not duplicate huge content unnecessarily in the database dump.

## Restore procedure

1. Check out/pull the compatible application tag.
2. Create server environment and secrets.
3. Start a **clean** PostgreSQL 18 container/volume and broker.
4. Create the target database/user if required.
5. Restore:

```bash
docker compose exec -T postgres sh -lc \
  'pg_restore --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --clean --if-exists --no-owner --no-acl' \
  < backups/<stamp>/database.dump
```

For a new empty database, `--clean` is optional; scripts should support a safe explicit mode.

6. Restore/copy artifacts to the configured storage backend.
7. Run the one-off release migration service.
8. Run `python manage.py verify_installation --manifest ...`.
9. Start web, workers, outbox dispatcher, and exactly one Beat.
10. Run smoke tests and compare counts/hashes.
11. Record a `RestoreRecord` and audit event.

## PostgreSQL major upgrades

PostgreSQL 18 official images use `/var/lib/postgresql` for the mounted persistent root. Do not mount/reuse a pre-18 volume at the wrong path. Do not major-upgrade by simply changing the image tag. Use tested dump/restore or a supported `pg_upgrade` plan.

## Server layout

```text
/opt/ftl-opportunity-radar/
  compose.yaml
  compose.prod.yaml
  .env.nonsecret
  secrets/
  backups/
  deployment/
```

Secrets have restrictive permissions and are not stored in Git or backup manifests.

## Migration from laptop

Recommended sequence:

1. update local system to a tagged release;
2. stop writes or record a cutoff;
3. create and verify full backup;
4. deploy same image/tag to server;
5. restore database/artifacts;
6. configure domain/TLS/webhook endpoint;
7. verify counts, source links, research artifacts, and login;
8. switch DNS/use;
9. keep local copy read-only until server backup/restore succeeds;
10. rotate any temporarily transferred secrets.

## Recovery objectives

Initial targets:

```text
RPO: 24 hours
RTO: 4 hours
```

Tighten after real usage. A backup that has never been restored is not considered verified.

## Acceptance criteria

- Backup restores into an empty clean environment.
- Schema, row counts, artifact hashes, and application verification pass.
- Host/container environment expansion is correct.
- PostgreSQL major/version and volume path are recorded.
- No laptop-specific path or code rewrite is required.
- Redis loss does not lose canonical state.
- A restore drill is documented before server migration.
