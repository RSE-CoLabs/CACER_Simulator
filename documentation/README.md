# Repository documentation

This folder contains the MkDocs configuration, the documentation sources, and
the generated static site for the CACER Simulator repository.

## Layout

- `mkdocs.yml`: MkDocs configuration file.
- `docs/`: Markdown sources, tutorials, API pages, and documentation assets.
- `site/`: generated static website produced by MkDocs.

## Local preview

From the repository root:

```powershell
.venv\Scripts\mkdocs.exe serve -f documentation\mkdocs.yml
```

## Build

From the repository root:

```powershell
.venv\Scripts\mkdocs.exe build -f documentation\mkdocs.yml
```
