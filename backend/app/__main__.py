"""Run the backend with ``python -m app`` using APP_HOST / APP_PORT settings."""

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_config=None,  # keep our structured logging configuration
    )


if __name__ == "__main__":
    main()
