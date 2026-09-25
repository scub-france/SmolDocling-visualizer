# Troubleshooting

## The Ask tab does not show up

The Ask tab is only on result pages (**Analyses**, then a row), in the right panel.

If it is missing there, open **Settings** › **Reasoning**:

- **Status** is **Disabled**: set it to **Enabled** and click **Save**.
- **Diagnostics** says **Reasoning unavailable** while Status is enabled: the reasoning packages are not in the image. Use `latest-local`, or build with `WITH_REASONING=true`. The `-remote` images never have them.
- `LLM_PROVIDER_TYPE` set to anything but `ollama` also turns Ask off.

The environment variables only give the starting values. After a **Save** in Settings, all four reasoning values come from the database, and changing `REASONING_ENABLED` has no effect until you click **Reset to environment**.

## Ask fails, or Test connection says "Host unreachable"

- Check that Ollama is running and that the model is pulled: `ollama list`.
- In a container, `localhost` is the container itself. Use `http://host.docker.internal:11434` as the Ollama URL. On Linux, Ollama must listen on all interfaces and the container needs the `host-gateway` mapping: see [Enable Ask](getting-started.md#enable-ask).

## A long PDF has an empty tree, and Ask cannot read it

This happens with Docker Compose on PDFs of more than 10 pages. The compose file sets `BATCH_PAGE_SIZE=10`, and batched analyses lose the document structure.

Put `BATCH_PAGE_SIZE=0` in `.env`, restart, and run a new analysis. Existing analyses stay as they are.

## The first analysis takes minutes

Docling downloads its models from HuggingFace during the first analysis, with the published image too. Wait for it: the next analyses reuse them until the container is recreated. The server needs access to `huggingface.co` for this.

## "File too large"

The file is over `MAX_FILE_SIZE_MB` (50 MB by default). Raise it, and keep `NGINX_MAX_BODY_SIZE` above it. See [Limits](configuration.md#limits).

## "429 Too Many Requests"

More than `RATE_LIMIT_RPM` requests in a minute (100 by default). Behind the bundled nginx, all users share this one limit. Raise it, or set `0` to turn it off.

## My documents are gone

`docker run` keeps the data inside the container: a restart keeps it, but removing the container or starting a new one from the image loses it. Mount volumes for `/app/data` and `/app/uploads`: see [Keep your data](getting-started.md#keep-your-data).

## The server does not start

Read the first error in the logs (`docker logs <container>` or `docker compose logs document-parser`):

- **`ValueError`**: a setting has an invalid value. The message usually names it. `invalid literal for int()` means a number setting got text. See [Configuration](configuration.md).
- **`STORE_SECRET_KEY is required`**: a store in the database has an encrypted password, and `STORE_SECRET_KEY` is not set. Set it back to the key used before. A new key cannot read the old passwords.

## `docker pull` from ghcr.io says "denied"

The images are public. This error usually comes from an old ghcr.io login saved on your machine. Run `docker logout ghcr.io` and pull again.

## The interface is in French

That is the default. Open **Paramètres** and set **Langue** to **EN**.

## Where is the API documentation (Swagger)?

It is served by the backend at `/docs`, which is not reachable through port 3000. Run the backend from source (see [Contributing](https://github.com/scub-france/Docling-Studio/blob/main/CONTRIBUTING.md)) and open <http://localhost:8000/docs>.
