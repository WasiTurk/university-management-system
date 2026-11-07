# Contributing

Thanks for your interest in improving this project!

## Setup
```bash
git clone https://github.com/WasiTurk/university-management-system.git
cd university-management-system
python main.py --init
python -m unittest discover -v
```

## Guidelines
- Create a feature branch: `git checkout -b feature/my-change`
- Keep business rules in `ums/services.py` and permission checks via `@require(...)`
- Schema changes go in `schema.sql` (use `IF NOT EXISTS`) and need a test
- Use parameterized SQL only, never string-format user input into queries
- Add or update tests in `tests/` and make sure they pass
- Use clear commit messages, e.g. `feat: add attendance table`, `fix: gpa rounding`

## Reporting bugs
Open an issue using the bug report template.
