from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import constants
from app.config.settings import Settings, get_settings
from app.exceptions import ServiceError
from app.services import auth_service

router = APIRouter()


class ProvisionUserRequest(BaseModel):
    git_username: str
    email: str


def _settings_dependency() -> Settings:
    return get_settings()


def _raise_http_from_service_error(error: ServiceError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.get(constants.ROUTE_HEALTH)
async def health() -> dict[str, str]:
    return {constants.RESPONSE_KEY_STATUS: constants.RESPONSE_STATUS_OK}


@router.get(constants.ROUTE_INDEX)
async def index() -> dict[str, str]:
    return {constants.RESPONSE_KEY_MESSAGE: constants.INDEX_MESSAGE}


@router.get(constants.ROUTE_LOGIN, response_model=None)
async def login(
    request: Request,
    redirect: bool = False,
    settings: Settings = Depends(_settings_dependency),
) -> Any:
    try:
        return await auth_service.build_login_response(request, redirect, settings)
    except ServiceError as error:
        _raise_http_from_service_error(error)


@router.post(constants.ROUTE_ADMIN_USERS)
async def register_user(
    payload: ProvisionUserRequest,
    request: Request,
    settings: Settings = Depends(_settings_dependency),
) -> dict[str, Any]:
    try:
        user = await auth_service.register_allowed_user(
            request=request,
            settings=settings,
            git_username=payload.git_username,
            email=payload.email,
        )
        return {
            constants.RESPONSE_KEY_MESSAGE: constants.USER_PROVISIONED_MESSAGE,
            constants.RESPONSE_KEY_USER: user,
        }
    except ServiceError as error:
        _raise_http_from_service_error(error)


@router.get(constants.ROUTE_AUTH_CALLBACK)
async def auth_callback(
    request: Request,
    code: str,
    state: str,
    settings: Settings = Depends(_settings_dependency),
) -> dict[str, Any]:
    try:
        return await auth_service.handle_auth_callback(
            request=request,
            settings=settings,
            code=code,
            state=state,
        )
    except ServiceError as error:
        _raise_http_from_service_error(error)


@router.get(constants.ROUTE_ME)
async def me(request: Request) -> dict[str, Any]:
    try:
        return auth_service.get_current_user_response(request)
    except ServiceError as error:
        _raise_http_from_service_error(error)


@router.post(constants.ROUTE_LOGOUT)
async def logout(request: Request) -> dict[str, str]:
    return auth_service.logout_session(request)

