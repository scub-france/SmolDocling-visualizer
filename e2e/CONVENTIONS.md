# E2E test conventions

Rules for writing Karate API and UI tests in this repository.

## Architecture

`e2e/` holds two Maven projects side by side:

- `api/`: HTTP tests, no browser.
- `ui/`: browser tests in headless Chrome.

They are peers: each has its own `pom.xml`, runners and `karate-config.js`. Never nest one inside the other. `generate-test-data.py` writes the test PDFs into both.

Each project has its own classpath, so each has its own `common/helpers/`. The `upload`, `analyze` and `cleanup` helpers exist in both. Keep the copies identical.

## Golden rules

### 1. Never use `Thread.sleep()`: wait for a condition

```gherkin
# BAD: blocks the thread and skips Karate's retry
* def wait = function(){ java.lang.Thread.sleep(2000) }
* wait()

# GOOD: waits for the element, with retry and logging
* waitFor('[data-e2e=chunk-card]')

# GOOD: a longer budget for one slow step (300 tries, 1 second apart)
* retry(300, 1000).waitFor('[data-e2e=chunk-card]')

# GOOD: waits for one of several elements
* waitForAny('[data-e2e=result-tabs]', '[data-e2e=result-error]')

# GOOD: waits for any other condition. The expression must return true.
* waitUntil("document.querySelector('[data-e2e=parse-show-all]').disabled")
```

By default a wait tries 60 times, 2 seconds apart (`configure retry` in `karate-config.js`). In API tests, poll with `retry until`, placed before `method`:

```gherkin
Given path '/api/analyses', jobId
And retry until response.status == 'COMPLETED' || response.status == 'FAILED'
When method GET
```

### 2. Never use `delay()`: wait for the expected result

```gherkin
# BAD: arbitrary wait, flaky on a slow CI runner
* driver.inputFile('input[type=file]', filePath)
* delay(2000)
* waitFor('[data-e2e=doc-item]')

# GOOD: wait for the actual result
* driver.inputFile('input[type=file]', filePath)
* waitFor('[data-e2e=doc-item]')
```

The only acceptable `delay()` is for a CSS animation with no DOM change to wait for, such as a 250 ms sidebar transition. Even then, prefer `waitUntil()` on the final state.

`demo/ask-demo.feature` is not a test. It uses `delay()` on purpose, to hold each shot of a video.

### 3. Count elements with `karate.sizeOf()`, never `.length`

```gherkin
# BAD: .length may return #notpresent
* def tabs = locateAll('[data-e2e=tab-btn]')
* match tabs.length == 3

# BAD: runs once, without Karate's waits and retries
* def count = script("document.querySelectorAll('[data-e2e=tab-btn]').length")

# GOOD
* match karate.sizeOf(locateAll('[data-e2e=tab-btn]')) == 3

# GOOD: use assert for > and <
* assert karate.sizeOf(locateAll('[data-e2e=element-card]')) > 0
```

### 4. Select with `data-e2e` attributes, never CSS classes

```gherkin
# BAD: breaks when someone renames a class
* waitFor('.doc-item')
* click('.chunk-card')

# BAD: breaks in French, where the link reads "Paramètres"
* click('{a}Settings')

# GOOD: independent of CSS and language
* waitFor('[data-e2e=doc-item]')
* click('[data-e2e=chunk-card]')
* click('[data-e2e=nav-settings]')
```

CSS classes are for styling. `data-e2e` attributes are for tests. A frontend developer must be able to rename `.doc-item` without breaking a test. Add `data-e2e="..."` to every element a test uses.

Choose `data-e2e` values this way:

- kebab-case and descriptive: `doc-item`, `upload-zone`, `run-btn`, `result-tabs`.
- One value per role, not per instance: every document row is `doc-item`, every tab is `tab-btn`. Get them all with `locateAll()`.
- Not a CSS class name. Some existing values still equal a class on the same element; rename the `data-e2e` value when you touch one, so nobody mistakes it for styling.

To assert on text, as the language test does, set the language first:

```gherkin
* driver uiBaseUrl + '/settings'
* click('[data-e2e=lang-en]')
* waitFor('[data-e2e=sidebar]')
# The sidebar is now in English
* match text('[data-e2e=sidebar]') contains 'Home'
```

### 5. Set up through the API, check in the UI, clean up through the API

```gherkin
# Setup: fast and deterministic
* def upload = call read('classpath:common/helpers/upload.feature') { file: 'small.pdf' }
* def docId = upload.docId
* def analysis = call read('classpath:common/helpers/analyze.feature') { docId: '#(docId)' }

# Check: the actual UI test
* driver uiBaseUrl + '/analyses/' + analysis.jobId
* waitFor('[data-e2e=parse-tab]')
...

# Cleanup: fast, and independent of the UI state
* call read('classpath:common/helpers/cleanup-by-name.feature') { filename: 'small.pdf' }
```

Exception: a test about the UI action itself. `documents/upload.feature` uploads through the page because the upload UI is what it tests.

### 6. Put repeated steps in callable helpers

```gherkin
# BAD: the same cleanup lines in every scenario
Given path '/api/documents'
When method GET
Then status 200
* def uploaded = karate.filter(response, function(d){ return d.filename == 'small.pdf' })
* def cleanupId = uploaded[0].id
* call read('classpath:common/helpers/cleanup.feature') { docId: '#(cleanupId)' }

# GOOD: one line through a helper
* call read('classpath:common/helpers/cleanup-by-name.feature') { filename: 'small.pdf' }
```

Helpers go in `common/helpers/`, tagged `@ignore`, with a comment that shows how to call them.

A helper scenario that only one feature needs can stay in that feature. Tag it `@ignore` plus a name, such as `@editInline`, and call it with `karate.call('@editInline', { docId: docId })`.

### 7. Use `optional()` for elements that may or may not appear

```gherkin
# GOOD: does not fail if the section is already open
* def chevronOpen = optional('[data-e2e=config-chevron].open')
* if (!chevronOpen.present) click('[data-e2e=config-toggle]')
```

Never `waitFor()` an element that might not appear, such as a spinner that shows for a split second.

## Tag strategy

| Tag | Used on | Run by |
| --- | --- | --- |
| `@smoke` | API `health/` | `ci.yml` on every run, and `release-gate.yml` |
| `@regression` | API `documents/` and `analyses/`, and some UI features | API: `ci.yml` on pull requests to `release/*`, and `release-gate.yml`. UI: no CI job. |
| `@e2e` | API `workflows/` and `ingestion/` | Same as API `@regression`, except `ingestion/`, which no runner scans |
| `@ingestion` | API `ingestion/`, which needs OpenSearch and the embedding service. Deprecated, removed in 0.8.0 | No CI job |
| `@critical` | A few core UI journeys | `ci.yml` on pushes to `main`, and `release-gate.yml` on pull requests to `main` |
| `@ui` | Every UI feature | No CI job. Run them by hand with `UIRunner#testLocal`. |
| `@reasoning-off` | UI scenarios that expect Ask to be off (the default) | Nothing selects it. It records the assumption. |
| `@demo` | `demo/ask-demo.feature`, a video script | `DemoRunner` only |
| `@ignore` | Helpers | Never on their own: Karate skips them, and features call them. |

Tag every UI feature `@ui`. Add `@critical` only to a core journey, since it runs on every pull request to `main`.

## Driver config (karate-config.js)

```javascript
karate.configure('driver', {
  type: 'chrome',
  headless: true,
  showDriverLog: false,
  addOptions: ['--no-sandbox', '--disable-gpu'],
  screenshotOnFailure: true
});
```

- `--no-sandbox`: required in GitHub Actions and in Docker containers.
- `--disable-gpu`: avoids GPU problems in headless mode.
- `screenshotOnFailure`: saves the page to the report when a step fails.

`-Ddemo=true` swaps this for a visible Chrome at a fixed size. Only `demo/` uses it.

## File naming

| File | Convention |
| --- | --- |
| Feature files | `kebab-case.feature`, for example `batch-progress.feature` |
| Helpers | `kebab-case.feature` in `common/helpers/`, prefixed `ui-` when they drive the browser |
| Runners | `PascalCase.java` ending in `Runner`, for example `UIRunner.java` |
| Config | `karate-config.js` (Karate convention) |

## Running tests

Commands are in [api/README.md](api/README.md) and [ui/README.md](ui/README.md). Keep these runner rules in mind when you add tests:

- Maven runs every class whose name ends in `Runner`, and every method in it. Pick one with `-Dtest`, for example `-Dtest='UIRunner#testCritical'`.
- `--tags` in `-Dkarate.options` replaces the tags of every runner method. The folders each method scans stay the same.
- Runners scan fixed folders. `E2ERunner` scans `health/`, `documents/`, `analyses/` and `workflows/`. `UIRunner` scans `documents/`, `analyses/`, `navigation/` and `workflows/`. A feature in any other folder runs only if you pass its folder in `-Dkarate.options`.
- Keep anything that is not a test out of those folders, as `demo/` does.

## Common pitfalls

| Pitfall | Fix |
| --- | --- |
| `retry().until(...)` fails with a TypeError | `until` is not a driver method. Use `waitUntil("<js expression>")`. |
| `retry(n, ms).script(...)` does not wait | `script()` runs once. Use `retry(n, ms).waitUntil(...)` or `waitForAny(...)`. |
| `waitUntil(...)` times out although the page looks right | The expression must return `true`, not an element. Compare with `!= null`. |
| `locateAll().length` returns `#notpresent` | Use `karate.sizeOf(locateAll(...))`. |
| `match x > 0` fails with "no step-definition" | Use `assert x > 0` for numeric comparisons. |
| `if (...) call read(...)` fails with a JS error | Use `karate.call()` inside `if`. |
| `input()` on `input[type=file]` crashes | Use `driver.inputFile()`. |
| `waitFor()` on a spinner times out on fast operations | Wait for the result instead, or use `optional()`. |
| Nav links break when the language changes | Select with `data-e2e`, not text. |
| Tests break when a CSS class is renamed | Select with `[data-e2e=...]`, never `.class-name`. |
| `mvn test` in `e2e/ui` fails in `DemoRunner` | Pick a runner method with `-Dtest`. |
| Tests pass locally but fail in CI | Keep `--no-sandbox` in the Chrome options. |
