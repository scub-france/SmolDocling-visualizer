# Security response

How maintainers handle a reported vulnerability. The public policy is [SECURITY.md](https://github.com/scub-france/Docling-Studio/blob/main/SECURITY.md).

## Timeline

| Step | Within | What to do |
|------|--------|------------|
| Acknowledge | 48 hours | Answer the reporter in the advisory |
| Assess | 7 days | Set the severity (table below) |
| Fix | 14 days if critical, 30 days otherwise | Fix and test in private |
| Release | The day the fix is ready | Publish the patched version |
| Disclose | After the release | Publish the GitHub Security Advisory |

## Severity

| Severity | Criteria | Example |
|----------|----------|---------|
| Critical | Remote exploit, data breach, no login needed | SQL injection on upload |
| High | Serious impact under some conditions | Path traversal on file download |
| Medium | Limited impact | XSS in the result display |
| Low | Minimal, mostly theoretical | Details leaked in an error message |

## Fix

The repository is public, so every branch is public. Work in private:

1. In the draft advisory, create a **temporary private fork** and fix there.
2. Add a test that reproduces the problem.
3. Check the fix against the [security audit checklist](../audit/audits/08-security.md).
4. Get a review from another maintainer.
5. Merge, release and deploy: see the [deployment checklist](../release/deployment-checklist.md).
6. Publish the advisory, with a CVE if one was assigned.

## Advisory template

```markdown
# <Title>

- Severity: Critical | High | Medium | Low
- Affected versions: < X.Y.Z
- Fixed in: X.Y.Z
- CVE: (if assigned)

## Description
What the problem is, without exploit details.

## Impact
What an attacker could do.

## Mitigation
Upgrade to X.Y.Z, or the workaround.

## Credit
The reporter, unless they prefer not.
```

## Dependencies

```bash
cd document-parser
uv pip install pip-audit
uv run pip-audit
```

```bash
cd frontend
npm audit
```

Critical or high: update now and ship a patch release. Medium or low: include it in the next release. The release gate also runs both audits on every release pull request.
