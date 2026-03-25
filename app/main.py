from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import constants
from app.config.settings import get_settings
from app.controllers.auth_controller import router as auth_router
from app.services import auth_service

settings = get_settings()

app = FastAPI(title=constants.APP_TITLE, version=constants.APP_VERSION)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key or constants.SESSION_SECRET_FALLBACK,
    https_only=settings.session_https_only,
    same_site=constants.SESSION_SAME_SITE,
)
app.include_router(auth_router)


@app.on_event('startup')
async def verify_dependencies() -> None:
    auth_service.initialize_dependencies(settings)

