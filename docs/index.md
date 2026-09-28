# Docling Studio

Docling Studio is a web app to see what [Docling](https://github.com/docling-project/docling) extracts from a PDF. Import a document, run an analysis, and check each title, paragraph, table and picture against the page it came from.

```mermaid
flowchart LR
    PDF(["Your PDF"]) --> Docling("Docling analysis")
    Docling --> View("Boxes on the page<br/>+ document tree")
    View --> Ask("Ask a question")
    View --> Export("Markdown or<br/>Docling JSON")

    classDef grey fill:#607D8B1F,stroke:#607D8B,stroke-width:1.5px
    classDef blue fill:#2196F31F,stroke:#2196F3,stroke-width:1.5px
    classDef orange fill:#FF57221F,stroke:#FF5722,stroke-width:2px
    classDef teal fill:#0096881F,stroke:#009688,stroke-width:1.5px
    class PDF grey
    class Docling blue
    class View orange
    class Ask,Export teal
```

Try it with one command:

```bash
docker run -p 3000:3000 ghcr.io/scub-france/docling-studio:latest-local
```

Then open <http://localhost:3000>.

## Where to go next

| I want to… | Read |
|------------|------|
| Install and run it | [Get started](getting-started.md) |
| Learn the screens | [User guide](user-guide.md) |
| Change a setting | [Configuration](configuration.md) |
| Fix a problem | [Troubleshooting](troubleshooting.md) |
| Change the code | [Contributing](https://github.com/scub-france/Docling-Studio/blob/main/CONTRIBUTING.md), then [Architecture](architecture.md) |
| Publish a release | [Maintainers](maintainers.md) |

Docling Studio is open source under the [MIT license](https://github.com/scub-france/Docling-Studio/blob/main/LICENSE).
