# Code review checklist

Use it when you review a pull request. Not every item applies to every change: skip items on purpose, not by accident.

## Correctness

- [ ] The code does what the pull request description says.
- [ ] Edge cases are handled: empty input, missing data, concurrent requests.
- [ ] Errors reach the user as clear messages, not stack traces.
- [ ] Existing behavior still works.

## Architecture

- [ ] Backend layers import only what they may. `document-parser/tests/test_architecture.py` checks it (see [coding standards](../architecture/coding-standards.md#layers)).
- [ ] Routes hold no business logic. They call a service.
- [ ] A new route does one domain operation, or is an atomic operation whose service explains why (see [API rules](../architecture.md#api-rules)).
- [ ] A frontend feature uses another feature only through `@/features/<name>`. ESLint checks it.
- [ ] Each new abstraction is needed now, not "in case".

## Security

- [ ] Input is validated at the API boundary with Pydantic schemas.
- [ ] No secrets, API keys or passwords in the code.
- [ ] Every SQL value goes through a `?` parameter, never into the query text. The persistence layer writes SQL by hand on aiosqlite, with no ORM.
- [ ] No `eval()`, `exec()` or `os.system()` on user input.
- [ ] HTML shown with `v-html` goes through DOMPurify.
- [ ] File paths built from user input cannot leave their folder.
- [ ] CORS settings are unchanged, or the change is explained.

## Tests

- [ ] New behavior has tests.
- [ ] Unit tests are deterministic: no sleep, no randomness, no network.
- [ ] Test names describe the scenario, not the implementation.
- [ ] End-to-end tests select elements with `data-e2e`, not CSS classes (see [e2e/CONVENTIONS.md](https://github.com/scub-france/Docling-Studio/blob/main/e2e/CONVENTIONS.md)).

## Code quality

- [ ] No dead code and no commented-out code.
- [ ] No `TODO` or `FIXME` without a linked issue.
- [ ] Functions stay within 30 lines, or have a good reason not to.
- [ ] Names are clear and match the code around them.
- [ ] No duplicated logic that should be shared.

## Documentation

- [ ] A user-visible change has a line under `[Unreleased]` in `CHANGELOG.md`.
- [ ] API changes show in the Pydantic schemas, which feed the generated API docs.
- [ ] A breaking change is marked in the commit message (see [commit conventions](commit-conventions.md)).

## Size and scope

- [ ] The pull request does one thing: a feature, a fix or a refactor.
- [ ] No unrelated formatting changes.
- [ ] It can be reviewed in about 15 minutes. If not, ask for a split.
- [ ] CI is green: lint, type check, tests and build.
