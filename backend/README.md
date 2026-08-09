# HackMatrix Backend

FastAPI backend setup using [uv](https://github.com/astral-sh/uv).

## Prerequisites

- [uv](https://github.com/astral-sh/uv) (Python package and project manager)

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

### 2. Run Development Server

```bash
uv run uvicorn main:app --reload
```

Server will start at `http://127.0.0.1:8000`.

### 3. API Documentation

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## Adding Dependencies

To add a new package:

```bash
uv add <package_name>
```
