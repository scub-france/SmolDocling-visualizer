# Docling Studio

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![Node](https://img.shields.io/badge/node-20+-green)
![Docling](https://img.shields.io/badge/powered%20by-Docling-orange)
![CI](https://github.com/scub-france/Docling-Studio/actions/workflows/ci.yml/badge.svg)
[![GitHub Stars](https://img.shields.io/github/stars/scub-france/Docling-Studio?style=flat-square&logo=github&label=Stars)](https://github.com/scub-france/Docling-Studio)

See what [Docling](https://github.com/docling-project/docling) extracts from your PDFs: every title, paragraph, table and picture, with its box drawn on the page.

![Docling Studio](docs/screenshots/presentation.gif)

## Run it

```bash
docker run -p 3000:3000 ghcr.io/scub-france/docling-studio:latest-local
```

Open <http://localhost:3000> and import a PDF. No GPU needed.

To build from source with Docker Compose, or to turn on Ask with a local model, see [Get started](docs/getting-started.md).

## What it does

- Runs Docling on your PDFs, in the container or on your own Docling Serve server.
- Draws the box of every element on the page, next to the document tree.
- Shows the text or the table of the element you click. Element types can be hidden.
- Answers questions about a document with a local model (Ollama), and shows the steps it took.
- Exports the result as Markdown or Docling JSON.

## Documentation

| Page | What is in it |
|------|---------------|
| [Get started](docs/getting-started.md) | Docker image, Docker Compose, turning on Ask |
| [User guide](docs/user-guide.md) | The screens, step by step |
| [Configuration](docs/configuration.md) | Settings and optional services |
| [Troubleshooting](docs/troubleshooting.md) | Common problems |
| [Architecture](docs/architecture.md) | How the code is organized |
| [Contributing](CONTRIBUTING.md) | Dev setup, tests, branches, pull requests |

The same pages are online at <https://scub-france.github.io/Docling-Studio/>.

## License

[MIT](LICENSE)

## Star history

<a href="https://www.star-history.com/?repos=scub-france%2FDocling-Studio&type=timeline&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=scub-france/Docling-Studio&type=timeline&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=scub-france/Docling-Studio&type=timeline&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=scub-france/Docling-Studio&type=timeline&legend=top-left" />
 </picture>
</a>
