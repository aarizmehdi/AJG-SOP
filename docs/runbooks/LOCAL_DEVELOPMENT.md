# Local development

1. Copy `.env.example` to `.env.local` and keep `APP_MODE=fixture`.
2. Run `npm install` and `uv sync --python 3.12`.
3. Start the API with `uv run uvicorn apps.api.app.main:app --reload`.
4. Start the web app with `npm run dev`.
5. Open `http://localhost:5173/login` and choose an employee or administrator fixture.

Fixture documents are written beneath `.data/`, which is ignored by Git. Fixture content is synthetic and clearly labeled. Run `npm run typecheck`, `npm run lint`, `npm run test`, `npm run build`, `uv run ruff check .`, `uv run mypy apps services packages`, and `uv run pytest` before review.

Run the fixture evaluation harness from the repository root with `uv run python -m scripts.evaluation.run_fixture`.
