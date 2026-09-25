# HuggingFace Hub dependency map

This page lists every place where Docling Studio downloads from `huggingface.co`, and the rule that keeps builds away from it.

## Why it matters

HuggingFace Hub limits anonymous downloads per IP address. GitHub-hosted runners share their IP addresses with many other projects, so a CI job that downloads a model can fail with HTTP 429 at any time. In 0.6.2 this broke the backend tests and the release gate.

The rule since then: a build downloads nothing from HuggingFace Hub unless it opts in.

## The one allowed build-time download

On every `v*` tag, `release.yml` builds the `local` image with `BAKE_MODELS=true`. The Docling models are downloaded at that moment and stored in the published image, `ghcr.io/scub-france/docling-studio:latest-local`.

Two settings keep this contained:

- Both Dockerfiles declare `ARG BAKE_MODELS=false`, so every other build leaves it off.
- `release.yml` turns it on for the `local` target only.

The embedding service has its own switch, `BAKE_MODEL`, also `false` by default. No pipeline turns it on.

## Where downloads happen

### When an image is built

| File | Command | Runs when |
|------|---------|-----------|
| `Dockerfile`, `local` stage | `docling-tools models download` | `BAKE_MODELS=true` |
| `document-parser/Dockerfile`, `local` stage | `docling-tools models download` | `BAKE_MODELS=true` |
| `embedding-service/Dockerfile` | `SentenceTransformer('${EMBEDDING_MODEL}')` | `BAKE_MODEL=true` |

### When the app runs

| Code | Downloads | When |
|------|-----------|------|
| `document-parser/infra/local_chunker.py`, `HybridChunker` | The tokenizer `sentence-transformers/all-MiniLM-L6-v2` | First hybrid chunking, with either conversion engine |
| `document-parser/infra/local_converter.py`, the Docling pipeline | Layout, table and OCR models | First analysis (`POST /api/analyses`) with `CONVERSION_ENGINE=local`. The copy baked into the image is not read: see [Use the published image](#use-the-published-image) |
| `embedding-service/main.py`, `_load_model()` | The `EMBEDDING_MODEL` (default `all-MiniLM-L6-v2`) | Service start, if the model was not baked |

The chunker always runs in the backend, whatever the engine (`build_chunker()` in `document-parser/bootstrap/factories.py`). Hybrid is the default chunker. So the `remote` engine still downloads the tokenizer as soon as someone uses hybrid chunking. The hierarchical chunker needs no tokenizer.

Downloads are cached under `~/.cache` inside the container. Mount a volume there to keep them when the container is recreated.

Ask (`POST /api/documents/{id}/reasoning`) uses no HuggingFace model. The LLM runs in Ollama, `gpt-oss:20b` by default. Ask needs the reasoning packages, which the published `-local` image has included since 0.7.1 (`WITH_REASONING=true` in `release.yml`). It is off by default. Turn it on with `REASONING_ENABLED=true` or in **Settings**. A value saved in **Settings** wins.

### In tests

Unit tests download nothing. Tests that chunk mock the `DocumentChunker` port, and the embedding service tests mock the model.

## Run without downloading Docling models

Use the remote engine. Docling then runs in the official Docling Serve image, which ships with its models:

```bash
CONVERSION_MODE=remote docker compose --profile remote up -d --build
```

- `--profile remote` starts the `docling-serve` service from `docker-compose.yml`.
- `CONVERSION_MODE=remote` builds the light `remote` backend image. Without it, Compose builds the `local` image.
- The embedding service starts only with the `ingestion` profile. Leave that profile off, or mount a volume on the service's cache.

Hybrid chunking still downloads its tokenizer on first use. Keep `~/.cache/huggingface` on a volume so this happens only once, or use the hierarchical chunker, which downloads nothing.

The end-to-end jobs in `ci.yml` and `release-gate.yml` start the stack this way. Their `@regression` and `@e2e` API tests use the hybrid chunker, so these jobs still download the tokenizer.

## Use the published image

```bash
docker pull ghcr.io/scub-france/docling-studio:latest-local
```

This image was built with `BAKE_MODELS=true`, so a copy of the Docling models is inside it, in `/home/appuser/.cache/docling/models`. The backend does not point Docling at that copy yet (`DOCLING_ARTIFACTS_PATH` is not set, and the converter passes no `artifacts_path`), so the first analysis still downloads the layout and table models. Hybrid chunking also downloads its tokenizer on first use.

## Adding a component that needs a HuggingFace model

1. Give its bake build argument a `false` default.
2. If a published image must ship the model, turn the argument on in `release.yml`. Do not change the Dockerfile default.
3. Add the new download to the tables on this page.

Reviewers: a new Dockerfile `RUN`, CI step or Compose service that downloads from HuggingFace Hub without an opt-in build argument is a red flag.
