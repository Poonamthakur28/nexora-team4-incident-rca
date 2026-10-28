"""Run the API with `python -m app` (add `--reload` for development)."""

import sys

import uvicorn

from app.core.config import API_ROOT, get_settings


def main() -> None:
    settings = get_settings()
    reload = "--reload" in sys.argv[1:]
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=reload,
        reload_dirs=[str(API_ROOT / "app")] if reload else None,
        log_config=None,
    )


if __name__ == "__main__":
    main()
