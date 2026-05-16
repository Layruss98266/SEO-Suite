# Repository Cleanup Recommendations

This document summarizes the files that look obsolete, redundant, or better archived outside the root of the repository.

## Highest-confidence deletions
These files are safe to remove and are not part of the active application surface.

- `dashboard.py`
  - Legacy entrypoint replaced by `main.py`.
  - `PROJECT_ANALYSIS.md` explicitly calls this file out as legacy.
  - No active source references to it exist in the codebase.

- `README.html`
  - Redundant generated copy of `README.md`.
  - If the repo is intended to use Markdown-based documentation, the HTML file is not needed.

## Strong archive/pruning candidates
These are planning, research, and review artifacts that may still be useful internally, but they clutter the root and can be moved to an `archive/` or `docs/` folder if kept.

- `CODE_ERRORS.md`
- `CODE_REVIEW.md`
- `FREE_TOOLS_RESEARCH.md`
- `PROJECT_ANALYSIS.md`
- `GITHUB_REFERENCE.md`
- `INSTALL_PACKAGES.md`
- `RECOMMENDED_PACKAGES.md`
- `agents.md`

> Note: Some of these files are still referenced by `TOOL_ROADMAP.md` and possibly by internal planning workflows. If you choose to delete them, update those references first.

## Workspace cleanup notes
These are not likely commits, but are runtime or local metadata files that are already ignored by `.gitignore`:

- `data/` directory contents
- `.env`
- `.vscode/`
- `.agentmaster/`
- `.claude/settings.local.json`

If you want the working folder clean, these can be removed locally, but they should remain ignored in git.

## Recommended action
1. Delete `dashboard.py` and `README.html` immediately.
2. Move the planning/research docs into `archive/` or a dedicated docs folder, or keep only the most active ones in root.
3. Keep `README.md`, `pyproject.toml`, `requirements.txt`, `main.py`, `app/`, `core/`, `tools/`, `tests/`, and `TOOL_ROADMAP.md` as the active codebase.
4. Optionally delete local runtime artifacts under `data/` and ignored local config files if you want a clean working directory.

## Rationale
- `dashboard.py` is a true code-level legacy file that no longer matches the current app entrypoint.
- `README.html` is a generated artifact that duplicates the canonical `README.md`.
- The other root markdown files are useful for planning, but they are not required for the product and can be archived to reduce repository noise.
