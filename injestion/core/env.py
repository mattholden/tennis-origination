"""
Load .env from project root. Call once at application startup (e.g. in runner).

Finds project root by walking up from this file until pyproject.toml or .env exists.
"""

from pathlib import Path


def _find_project_root() -> Path:
    """Walk up from this file until we find pyproject.toml or .env."""
    path = Path(__file__).resolve().parent
    for _ in range(10):  # avoid infinite loop
        if (path / "pyproject.toml").exists() or (path / ".env").exists():
            return path
        parent = path.parent
        if parent == path:
            break
        path = parent
    # Fallback: project root is parent of injestion/ (this file is injestion/core/env.py)
    return Path(__file__).resolve().parent.parent.parent


def load_env() -> None:
    """
    Load .env from project root. Safe to call multiple times.
    Call this at the start of the runner (or any entry point) so ingestion and
    other code can use os.environ without each module finding the root.
    """
    try:
        import dotenv
    except ImportError:
        return
    root = _find_project_root()
    dotenv.load_dotenv(root / ".env")
