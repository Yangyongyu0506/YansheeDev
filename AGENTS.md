# AGENTS.md
# Guidance for agentic coding in this repository.
# Keep this file up to date as tools and standards evolve.

## Repository overview
- Purpose: Yanshee robot development utilities and scripts.
- Primary language: Python (standalone scripts in `scripts/`).
- Notable files: `scripts/YanAPI.py` (robot REST API wrapper),
  `scripts/hello_yanapi.py` (example usage).

## Build, lint, test commands
This repo does not currently define a formal build, lint, or test system.
Use the commands below as working defaults, and update this file if a tool
chain is added (pyproject, requirements, CI workflow, etc.).

### Run example scripts
- Run the hello script (local):
  `python3 scripts/hello_yanapi.py`
- Run the free-style script (local):
  `python3 scripts/free-style.py 50`

### Build
- No build system detected.
- If packaging is added later, document `pip install -r requirements.txt`
  or `pip install -e .` here.

### Lint
- No linter configuration detected.
- If a linter is added, document its command here (e.g., `ruff check .`).

### Tests
- No test framework or test directory detected.
- If tests are added, document the full test and single-test commands here.

### Single test (placeholder)
- None available now. When tests exist, prefer an explicit command like:
  `pytest path/to/test_file.py -k test_name`

## Code style guidelines
These guidelines reflect patterns seen in the current codebase. When
contributing new code, match existing conventions unless a repo-wide
standard is introduced.

### Imports
- Standard library first, then third-party, then local imports.
- Keep imports at module top-level unless lazy import is required.
- Use explicit imports (avoid wildcard imports).
- Group and sort imports manually unless a formatter is added.

### Formatting
- Indent with 4 spaces; avoid tabs.
- Keep line length readable; wrap long argument lists across lines.
- Use blank lines to separate logical sections of functions.
- Preserve existing docstring style (triple quotes with parameter docs).

### Types
- Use Python type hints where existing code uses them.
- Prefer built-in typing hints (e.g., `list`, `dict`) only if the project
  moves to Python 3.9+ typing conventions; otherwise use `typing.List`.
- Return explicit sentinel values on failure if the existing API does so
  (e.g., return -1, empty list, or empty string as appropriate).

### Naming conventions
- Functions: snake_case (e.g., `get_robot_volume_value`).
- Constants: UPPER_SNAKE_CASE when appropriate.
- Modules and files: snake_case.
- Private helpers: prefix with a single underscore; current code uses
  double-underscore for internal helpers - follow existing usage.

### Error handling
- Prefer returning a structured response or sentinel with logging.
- Use `logging.error` for API error responses where appropriate.
- Catch broad exceptions in scripts to keep the robot safe and inform the
  user; log or print a short diagnostic message.

### API usage patterns
- REST calls use `requests` and JSON serialization with `json.dumps`.
- Responses are decoded with `response.content.decode("utf-8")` and parsed
  via `json.loads`.
- When an API call can fail, check the `code` field if present.

### Async and blocking behavior
- Some API functions use asyncio event loops for wait operations.
- Avoid nested event loops; follow the existing coroutine usage pattern.

### File and path handling
- Keep file paths explicit and consistent (e.g., `scripts/`).
- Avoid hardcoding OS-specific paths unless required by robot runtime.

### Comments and docstrings
- Use docstrings for public API functions and include Args/Returns format.
- Keep comments concise; only add when behavior is non-obvious.

## Robot safety and runtime notes
- Scripts may control physical hardware. Use safe defaults and warn users
  if a script can move or play audio.
- When adding new motion scripts, include safety notes (floor clearance,
  emergency stop availability).

## Project structure expectations
- New robot API helpers should live in `scripts/YanAPI.py` or a new module
  under `scripts/` with clear naming.
- Example or demo scripts should go in `scripts/` and be runnable with
  `python3`.

## Cursor / Copilot rules
- No Cursor rules detected in `.cursor/rules/` or `.cursorrules`.
- No Copilot instructions detected in `.github/copilot-instructions.md`.
- If any of these files are added later, mirror their guidance here.

## Update checklist
- If you add a build or test tool, update the command section.
- If you add lint/format tooling, document expected usage and config.
- Keep style guidance aligned with the most common pattern in the code.
