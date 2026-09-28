# Rollback playbook

## Roll back or fix forward?

| Situation | Do this |
|-----------|---------|
| The new version is broken, the previous one worked | Roll back |
| The previous version has the same bug | Hotfix |
| The new version changed the database | Hotfix, or roll back with the database backup |
| Security hole in the new version | Roll back, and hotfix in parallel |

There are no database migrations. The schema is created at first start and never altered afterwards, so an older version can fail on a database written by a newer one.

## Docker image

1. Find the last good version:

    ```bash
    gh release list --repo scub-france/Docling-Studio
    ```

2. Remove the current container and start the previous version with the same volumes:

    ```bash
    docker rm -f docling-studio
    docker run -d --name docling-studio --restart unless-stopped -p 3000:3000 -v docling-data:/app/data -v docling-uploads:/app/uploads ghcr.io/scub-france/docling-studio:<previous>-local
    ```

3. If it fails on the database, restore the backup taken before the upgrade. The file is `docling_studio.db` in the `/app/data` volume.
4. Check `curl -s http://localhost:3000/api/health` shows the previous version.

## Docker Compose

Check out the previous tag and rebuild:

```bash
git checkout v<previous>
docker compose up -d --build
```

The database lives in the `db_data` volume.

## HuggingFace Space

Upload the previous tag from a clean clone, as in the [deployment checklist](deployment-checklist.md#huggingface-space), and add `--delete "*"` to the `hf upload` command. Without it, files that only the newer version had stay in the Space. It also deletes any file that exists only on the Space side.

## Afterwards

1. Open an issue describing the failure, with the version and the logs.
2. Fix it on a `hotfix/*` branch from `main`.
3. Deploy the fix with the [deployment checklist](deployment-checklist.md).
