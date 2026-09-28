# API end-to-end tests

These tests call the Docling Studio REST API over HTTP with [Karate](https://karatelabs.github.io/karate/). No browser is involved. They cover the health endpoint, documents, analyses, and journeys that combine them. To write a test, follow [CONVENTIONS.md](../CONVENTIONS.md).

## Prerequisites

- Java 17 or newer, and Maven.
- Python 3, to generate the test PDFs.
- Docker, to run the app.

## Run the tests

Run the commands from the repository root.

```bash
# 1. Generate the test PDFs (again after a clean)
pip install fpdf2 pypdfium2
python e2e/generate-test-data.py

# 2. Start the app as CI does, then wait until Docling Serve converts a PDF
RATE_LIMIT_RPM=0 CONVERSION_MODE=remote docker compose --profile remote up -d --build --wait
bash .github/scripts/warmup-docling-serve.sh

# 3. Run the smoke tests, or the full scope
mvn test -f e2e/api/pom.xml -DbaseUrl=http://localhost:3000 -Dkarate.options="--tags @smoke"
mvn test -f e2e/api/pom.xml -DbaseUrl=http://localhost:3000 -Dkarate.options="--tags @smoke,@regression,@e2e"

# 4. Stop the app
docker compose --profile remote down
```

- `baseUrl` defaults to `http://localhost:8000`, where the backend listens when you run it without Docker. Compose publishes only port 3000, where the frontend forwards `/api` to the backend.
- `RATE_LIMIT_RPM=0` turns off the rate limit. A full run sends about 100 requests a minute, which is the default limit.
- `CONVERSION_MODE=remote` converts PDFs in the Docling Serve container, which ships with its models.

## Where the tests are

Features are in `src/test/resources/`, one folder per area:

- `health/`: the health endpoint. Tagged `@smoke`.
- `documents/`: upload, size limit, read, delete, page preview. Tagged `@regression`.
- `analyses/`: analysis jobs, pipeline options, batching, rechunking, deletion. Tagged `@regression`.
- `workflows/`: journeys across documents and analyses. Tagged `@e2e`.
- `ingestion/`: chunks sent to OpenSearch. Tagged `@e2e @ingestion`. Deprecated, removed in 0.8.0 with ingestion.
- `common/helpers/`: callable helpers to upload, analyze and clean up. Tagged `@ignore`.
- `common/data/`: JSON schemas, data-driven cases, and the generated PDFs (not in git).

`E2ERunner.java` has two methods. `testAll` runs `health/`, `documents/`, `analyses/` and `workflows/`. `testSmoke` runs the `@smoke` scenarios of `health/`. Maven runs both, and `--tags` replaces the tags of each, so the health scenarios run twice.

No runner scans `ingestion/`, so nothing runs it. To run it, start the ingestion services (see [Configuration](../../docs/configuration.md#ingestion-deprecated)) and pass the folder: `-Dkarate.options="--tags @ingestion classpath:ingestion"`.

## Tags in CI

- `ci.yml` runs `@smoke` on every pull request to `main` or a `release/*` branch, and on every push to `main`. Pull requests to a `release/*` branch run `@smoke,@regression,@e2e` instead.
- `release-gate.yml` runs `@smoke,@regression,@e2e` on every pull request to `main`.

## Reports

After a run, open `e2e/api/target/karate-reports/karate-summary.html`. CI uploads this folder as the `karate-api-reports` artifact.
