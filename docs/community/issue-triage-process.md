# Issue triage

## Labels

Only these labels exist on the repository.

| Kind | Labels |
|------|--------|
| Type | `bug`, `enhancement` (features too), `documentation`, `test`, `chore`, `question` |
| Priority | `P0` must have, `P1` should have, `P2` nice to have |
| Area | `backend`, `frontend`, `infra`, `architecture`, `search` |
| Outcome | `duplicate`, `invalid`, `wontfix` |
| Help | `good first issue`, `help wanted` |
| Automatic | `docling-compat`: opened by the daily Docling compatibility check when the tests fail against the latest Docling |

Issue titles start with a tag matching the type: `[BUG]`, `[FEATURE]`, `[ENHANCEMENT]`, `[DOC]`, `[TEST]`, `[CHORE]`.

## Triage a new issue

```mermaid
flowchart LR
    New(["New issue"]) --> Dup{"Already<br/>reported?"}
    Dup -->|yes| D("Label duplicate,<br/>link the original, close")
    Dup -->|no| Scope{"In scope?"}
    Scope -->|no| W("Label wontfix,<br/>explain, close")
    Scope -->|yes| Info{"Enough<br/>information?"}
    Info -->|no| Ask("Ask in a comment")
    Info -->|yes| Tag("Type + area + priority,<br/>then a milestone")

    classDef grey fill:#607D8B1F,stroke:#607D8B,stroke-width:1.5px
    classDef amber fill:#FFB3001F,stroke:#FFB300,stroke-width:1.5px
    classDef red fill:#E539351F,stroke:#E53935,stroke-width:1.5px
    classDef blue fill:#2196F31F,stroke:#2196F3,stroke-width:1.5px
    classDef green fill:#43A0471F,stroke:#43A047,stroke-width:1.5px
    class New grey
    class Dup,Scope,Info amber
    class D,W red
    class Ask blue
    class Tag green
```

- Easy and well described? Add `good first issue`.
- Information still missing after 30 days: close with a comment. It can be reopened.

## Answering

- Every issue gets an answer, even "thanks, we will look next week".
- If it will not be fixed soon, say so.
- Close with a comment that explains the outcome.

There is no stale bot: closing old issues is done by hand.
