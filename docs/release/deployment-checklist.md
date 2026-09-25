# Deployment checklist

For a new version, once the tag `vX.Y.Z` exists and the release workflow has pushed the images. See [Maintainers](../maintainers.md) for the release itself.

## Before

- [ ] The images are on `ghcr.io/scub-france/docling-studio`: `X.Y.Z-local` and `X.Y.Z-remote`.
- [ ] `CHANGELOG.md` has the `[X.Y.Z]` section with its date.
- [ ] Back up the database. There are no database migrations: a version that changes existing tables may not start on an older database.

## Self-hosted (Docker image)

- [ ] Pull the image:

    ```bash
    docker pull ghcr.io/scub-france/docling-studio:X.Y.Z-local
    ```

- [ ] Remove the old container (`docker rm -f docling-studio`) and start the new one with the same volumes and variables:

    ```bash
    docker run -d --name docling-studio --restart unless-stopped -p 3000:3000 -v docling-data:/app/data -v docling-uploads:/app/uploads ghcr.io/scub-france/docling-studio:X.Y.Z-local
    ```

- [ ] Check the health endpoint:

    ```bash
    curl -s http://localhost:3000/api/health
    ```

    Expect `"status": "ok"`, `"database": "ok"` and `"version": "X.Y.Z"`.

With Docker Compose, the app is built from source: check out the tag, then run `docker compose up -d --build`. `docker compose pull` does not fetch the Docling Studio images.

## HuggingFace Space

The Space is a Docker Space built from the repository root (the root `Dockerfile`, `local` target).

Upload from a clean clone of the tag, never from your working copy: `--exclude` patterns only match at the root, so a working copy would also send `.venv`, `node_modules`, your local database and uploaded PDFs, and `.env`.

- [ ] Clone the tag into a new folder:

    ```bash
    git clone --depth 1 --branch vX.Y.Z https://github.com/scub-france/Docling-Studio.git space-upload
    cd space-upload
    ```

- [ ] Add the Space front matter at the top of its `README.md`: `sdk: docker`, `app_port: 3000`.
- [ ] Upload with the `hf` CLI (`huggingface-cli` no longer works):

    ```bash
    hf upload <space-id> . . --repo-type space --exclude ".git/*"
    ```

- [ ] Check the Space variables: `DEPLOYMENT_MODE=huggingface`, `MAX_PAGE_COUNT=20`.
- [ ] Wait for the build to finish, then check `/api/health` on the Space.

## Smoke test

- [ ] The app loads.
- [ ] Import a PDF in **Docs**.
- [ ] Run **New analysis** and wait for `COMPLETED` in **Analyses**.
- [ ] Open the result: boxes, tree and Properties show up.
- [ ] Download the Markdown.
- [ ] If Ask is on: ask one question.

## Roll back if

- `/api/health` fails or shows the wrong version.
- Import or analysis fails on a PDF that worked before.
- The app shows a blank page.

See the [rollback playbook](rollback-playbook.md).
