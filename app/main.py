from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import configurator, health, inventory, orders, reservations
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="FastAPI backend for firearms inventory, order reservations, and AR rifle/pistol configurator workflows.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(inventory.router, prefix=settings.api_prefix)
    app.include_router(orders.router, prefix=settings.api_prefix)
    app.include_router(reservations.router, prefix=settings.api_prefix)
    app.include_router(configurator.router, prefix=settings.api_prefix)

    return app


app = create_app()
