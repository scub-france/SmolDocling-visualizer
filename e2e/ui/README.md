# UI end-to-end tests

These tests drive Docling Studio in a headless Chrome with [Karate UI](https://github.com/karatelabs/karate/tree/master/karate-core). Most of them create their data through the API, check the page, then delete the data through the API. To write a test, follow [CONVENTIONS.md](../CONVENTIONS.md).

## Prerequisites

- Java 17 or newer, Maven, and Google Chrome.
- Python 3, to generate the test PDFs.
- Docker, to run the app.

## Run the tests

Run the commands from the repository root.

```bash
# 1. Generate the test PDFs (again after a clean)
pip install fpdf2 pypdfium2
python e2e/generate-test-data.py

# 2. Start the app as CI does, then wait until Docling Serve converts a PDF
STUDIO_MODE_ENABLED=true RATE_LIMIT_RPM=0 CONVERSION_MODE=remote \
  docker compose --profile remote up -d --build --wait
bash .github/scripts/warmup-docling-serve.sh

# 3. Run the @critical tests (the CI scope), or every @ui test
mvn test -f e2e/ui/pom.xml -Dtest='UIRunner#testCritical' -DbaseUrl=http://localhost:3000
mvn test -f e2e/ui/pom.xml -Dtest='UIRunner#testLocal' -DbaseUrl=http://localhost:3000

# 4. Stop the app
docker compose --profile remote down
```

- `STUDIO_MODE_ENABLED=true`: most `@critical` tests open `/studio`, which redirects to `/docs` without it.
- `RATE_LIMIT_RPM=0` turns off the rate limit, 100 requests a minute by default.
- `baseUrl` (the API) defaults to `http://localhost:8000`, and `uiBaseUrl` (the pages) to `http://localhost:3000`. These are the ports when you run the app without Docker. Compose publishes only port 3000, hence `-DbaseUrl`.
- Always pick a runner method with `-Dtest`. Without it, Maven also runs `DemoRunner`, which fails without `-DdemoDocId`.

## Where the tests are

Features are in `src/test/resources/`, one folder per area:

- `documents/`: upload, delete, upload errors, and the document workspace.
- `analyses/`: running an analysis, batch progress, rechunking, pipeline options, the saved analysis page.
- `navigation/`: sidebar, language switch, reasoning flag.
- `workflows/`: one full journey in the browser.
- `common/helpers/`: API helpers (upload, analyze, cleanup) and browser helpers (prefix `ui-`).
- `common/data/generated/`: the test PDFs (not in git).
- `demo/`: a scripted walkthrough for a video, run only by `DemoRunner`. It is not a test.

`UIRunner.java` has three methods. `testAll` runs every feature in the first four folders, `testLocal` the `@ui` ones, and `testCritical` the `@critical` ones in `documents/` and `analyses/`. To list the critical features, run `grep -rlE '^@.*critical' e2e/ui/src/test/resources`.

## Tags in CI

CI runs `@critical` only: `ci.yml` on every push to `main`, and `release-gate.yml` on every pull request to `main`. Both call `mvn test` with `-Dkarate.options="--tags @critical"` and no `-Dtest`. The `--tags` option replaces the tags of each `UIRunner` method, so every critical scenario runs three times.

Every feature also has `@ui`. Some have `@regression`, or `@reasoning-off` on scenarios that expect Ask to be off (the default). No CI job selects these tags, so tests outside `@critical` may be out of date.

## Reports

After a run, open `e2e/ui/target/karate-reports/karate-summary.html`. A failed step adds a screenshot. CI uploads this folder as the `karate-ui-reports` artifact.
