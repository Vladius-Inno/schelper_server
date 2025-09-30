from contextlib import asynccontextmanager
from fastapi import FastAPI
# from fastapi.staticfiles import StaticFiles

import logging

from .db import init_db
from .routers import auth as auth_router
from .routers import users as users_router
from .routers import tasks as tasks_router
from .routers import subjects as subjects_router
from .routers import health as health_router
from .admin_flet import create_admin_app
from .routers import import_homework as import_homework_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schemas at startup
    # Silence noisy passlib bcrypt backend probing warnings
    logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)
    await init_db()
    try:
        yield
    finally:
        # place for graceful shutdown hooks if needed
        pass


def create_app() -> FastAPI:
    app = FastAPI(title="Schelper Server - Auth", lifespan=lifespan)
    # app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(auth_router.router)
    app.include_router(users_router.router)
    app.include_router(subjects_router.router)
    app.include_router(tasks_router.router)
    app.include_router(health_router.router)
    app.include_router(import_homework_router.router)
    # Mount Flet-based admin interface
    app.mount("/admin", create_admin_app(app))

    return app


app = create_app()
