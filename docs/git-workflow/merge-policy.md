# Merge policy

## Where each branch goes

| Branch | Starts from | Pull request to | Merge with |
|--------|-------------|-----------------|------------|
| `feature/*`, `fix/*`, `docs/*`, `test/*`, `chore/*` | `release/x.y.z` | `release/x.y.z` | Merge commit or squash |
| `release/x.y.z` | `main` | `main` | Rebase and merge |
| `hotfix/*` | `main` | `main` | Squash |

`main` only receives releases and hotfixes.

## Before merging

1. CI is green.
2. The branch is up to date with its target.
3. Review comments are answered.
4. A user-visible change has its line under `[Unreleased]` in `CHANGELOG.md`.

On `main`, GitHub enforces one approval, an up-to-date branch and the required checks. Release branches are not protected: ask for a review anyway.

## Commit messages

- **Squash**: make the squash title follow [Conventional Commits](commit-conventions.md), with the pull request number: `fix(upload): reject empty PDFs (#142)`. For a single-commit pull request, GitHub proposes the commit title without the number: add it.
- **Merge commit**: keep GitHub's default title, `Merge pull request #142 from …`. The commits inside already follow the conventions.

## Conflicts

- Rebase your branch on its target, or merge the target into it when the rebase is painful.
- Warn reviewers before force-pushing a branch they are reviewing.

## After merging

- Delete the work branch. GitHub does not do it automatically on this repository.
- Keep release branches.
- Never delete tags.
