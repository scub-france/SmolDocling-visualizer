# Commit conventions

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), so the history is easy to scan. The changelog is written by hand, not generated from them (see [Changelog](#changelog)).

## Format

```text
<type>(<scope>): <description>

[body]

[footer]
```

## Types

| Type | Use it for | Example |
|------|------------|---------|
| `feat` | A new feature | `feat(bbox): clear the Parse view focus with a show-all button` |
| `fix` | A bug fix | `fix(frontend): make the dev route badge readable in both themes` |
| `docs` | Documentation only | `docs(design): accept the runtime reasoning config design` |
| `style` | Formatting only | `style: collapse the analysis guard in chunk_service to ruff's formatting` |
| `refactor` | A code change that keeps the behavior | `refactor(api): centralize app state dependencies` |
| `perf` | Faster, same behavior | `perf(analysis): load a saved analysis's tree once` |
| `test` | Tests only | `test(frontend): cover the dev route badge label` |
| `build` | Docker images, dependencies, build tooling | `build(deps): bound python-multipart upper version` |
| `ci` | GitHub Actions workflows | `ci(docling-compat): fix version-capture quoting in canary` |
| `chore` | Anything else, such as releases | `chore(release): freeze [0.7.2]` |

## Scopes

The scope is optional. Name the area you changed. Scopes already in use:

| Area | Scopes |
|------|--------|
| Frontend | `frontend` |
| Backend layers | `api`, `domain`, `infra` |
| Features | `analysis`, `parse`, `chunking`, `reasoning`, `export`, `settings`, `stores`, `neo4j`, `bbox` |
| Tests | `tests`, `e2e`, `e2e-ui` |
| Build and delivery | `ci`, `docker`, `nginx`, `deps`, `security`, `release` |
| Docs | `design`, `audit`, `changelog` |

## Rules

1. Write the description in the imperative, in lowercase, with no final period. Keep the whole first line to 72 characters at most.
2. Use the body to explain why. The diff already shows what.
3. Mark a breaking change with `!` after the type or scope (`feat(api)!: rename /analyses to /jobs`), or with a `BREAKING CHANGE:` footer.
4. Reference the issue with `(#142)` at the end of the first line, or with `Closes #142` in the footer. Only `Closes #142` (or `Fixes #142`) closes the issue, once the commit reaches a `release/*` branch (`auto-close-issues.yml`).

## Example

```text
fix(upload): reject empty PDFs

Empty files were accepted and failed later, during conversion,
with no clear message. Rejecting them at upload tells the user
right away.

Closes #142
```

## Changelog

`CHANGELOG.md` is written by hand and follows [Keep a Changelog](https://keepachangelog.com/). Add a line under `[Unreleased]` for each user-visible change. At release time, a `chore(release): freeze [X.Y.Z]` commit turns `[Unreleased]` into the new version's section.
