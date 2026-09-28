# Incident response

## Severity

| Level | What it means | Examples | React |
|-------|---------------|----------|-------|
| **SEV-1** | Service down, data lost, security breach | App unreachable, database corrupted, secret leaked | Now |
| **SEV-2** | A main feature is broken for everyone | Import fails, analyses crash, blank pages | Within 2 hours |
| **SEV-3** | A minor feature is broken, there is a workaround | Boxes misaligned, a missing translation | Next working day |

## Steps

1. **Detect.** `/api/health` shows `"status": "degraded"` or does not answer, a user opens an issue, CI fails on `main`, or a container keeps restarting. `/api/health` always answers HTTP 200: read the `status` and `database` fields.
2. **Assess.** Pick the severity. Find the broken part (backend, frontend, Docker, CI) and what changed last: `git log --oneline -10 main`.
3. **Tell people.** SEV-1: warn every maintainer right away. SEV-2 and SEV-3: open an issue labeled `bug`, with `P0` or `P1`.
4. **Mitigate first.** If it started with a deploy, [roll back](../release/rollback-playbook.md). If Docling itself fails in the backend, switch to the remote engine: the `-remote` image with `DOCLING_SERVE_URL`, or `CONVERSION_MODE=remote docker compose --profile remote up -d --build`.
5. **Fix.** Branch `hotfix/*` from `main`, fix the cause, add a test that reproduces it, then follow the [deployment checklist](../release/deployment-checklist.md).
6. **Write it up** for SEV-1 and SEV-2, in the incident issue.

## Post-mortem template

```markdown
## Post-mortem: <title>

- Date, severity, duration:
- Timeline: detected / mitigated / root cause found / fixed
- Root cause:
- Impact (who, how long, which data):
- What went well:
- What went wrong:
- Actions (owner, due date):
```
