from typing import TYPE_CHECKING, Any, Dict, Optional

import pytest

from starlite import get
from starlite.di import Provide
from starlite.middleware.session.server_side import (
    ServerSideSessionBackend,
    ServerSideSessionConfig,
)
from starlite.openapi.config import OpenAPIConfig
from starlite.openapi.spec import Components, SecurityScheme
from starlite.security.session_auth import SessionAuth
from starlite.status_codes import HTTP_200_OK
from starlite.testing import create_test_client

if TYPE_CHECKING:
    from starlite.connection import ASGIConnection
    from starlite.handlers.base import BaseRouteHandler


def retrieve_user_handler(_: Dict[str, Any], __: "ASGIConnection") -> Any:
    pass


def test_abstract_security_config_sets_guards(session_backend_config_memory: ServerSideSessionConfig) -> None:
    async def guard(_: "ASGIConnection", __: "BaseRouteHandler") -> None:
        pass

    security_config = SessionAuth[Any, ServerSideSessionBackend](
        retrieve_user_handler=retrieve_user_handler,
        session_backend_config=session_backend_config_memory,
        guards=[guard],
    )

    with create_test_client([], on_app_init=[security_config.on_app_init]) as client:
        assert client.app.guards


def test_abstract_security_config_sets_dependencies(session_backend_config_memory: ServerSideSessionConfig) -> None:
    security_config = SessionAuth[Any, ServerSideSessionBackend](
        retrieve_user_handler=retrieve_user_handler,
        session_backend_config=session_backend_config_memory,
        dependencies={"value": Provide(lambda: 13)},
    )

    with create_test_client([], on_app_init=[security_config.on_app_init]) as client:
        assert client.app.dependencies.get("value")


def test_abstract_security_config_registers_route_handlers(
    session_backend_config_memory: ServerSideSessionConfig,
) -> None:
    @get("/")
    def handler() -> dict:
        return {"hello": "world"}

    security_config = SessionAuth[Any, ServerSideSessionBackend](
        retrieve_user_handler=retrieve_user_handler,
        exclude=["/"],
        session_backend_config=session_backend_config_memory,
        route_handlers=[handler],
    )

    with create_test_client([], on_app_init=[security_config.on_app_init]) as client:
        response = client.get("/")
        assert response.status_code == HTTP_200_OK
        assert response.json() == {"hello": "world"}


@pytest.mark.parametrize(
    "openapi_config, expected",
    (
        (None, None),
        (
            OpenAPIConfig(title="Starlite API", version="1.0.0", components=None),
            {
                "schemas": {},
                "securitySchemes": {
                    "sessionCookie": {
                        "type": "apiKey",
                        "description": "Session cookie authentication.",
                        "name": "session",
                        "in": "cookie",
                    }
                },
            },
        ),
        (
            OpenAPIConfig(
                title="Starlite API",
                version="1.0.0",
                components=[
                    Components(
                        security_schemes={
                            "app": SecurityScheme(
                                type="http",
                                name="test",
                                security_scheme_in="cookie",  # pyright: ignore
                                description="test.",
                            )
                        }
                    )
                ],
            ),
            {
                "schemas": {},
                "securitySchemes": {
                    "app": {"type": "http", "description": "test.", "name": "test", "in": "cookie"},
                    "sessionCookie": {
                        "type": "apiKey",
                        "description": "Session cookie authentication.",
                        "name": "session",
                        "in": "cookie",
                    },
                },
            },
        ),
        (
            OpenAPIConfig(
                title="Starlite API",
                version="1.0.0",
                components=Components(
                    security_schemes={
                        "app": SecurityScheme(
                            type="http",
                            name="test",
                            security_scheme_in="cookie",
                            description="test.",
                        )
                    }
                ),
            ),
            {
                "schemas": {},
                "securitySchemes": {
                    "sessionCookie": {
                        "type": "apiKey",
                        "description": "Session cookie authentication.",
                        "name": "session",
                        "in": "cookie",
                    },
                    "app": {"type": "http", "description": "test.", "name": "test", "in": "cookie"},
                },
            },
        ),
    ),
)
def test_abstract_security_config_setting_openapi_components(
    openapi_config: Optional["OpenAPIConfig"], expected: dict, session_backend_config_memory: ServerSideSessionConfig
) -> None:
    security_config = SessionAuth[Any, ServerSideSessionBackend](
        retrieve_user_handler=retrieve_user_handler, exclude=["/"], session_backend_config=session_backend_config_memory
    )
    with create_test_client([], on_app_init=[security_config.on_app_init], openapi_config=openapi_config) as client:
        if openapi_config is not None:
            assert client.app.openapi_schema
            assert client.app.openapi_config
            assert client.app.openapi_config.components
            assert client.app.openapi_config.components.to_schema() == expected
        else:
            assert not client.app.openapi_config


@pytest.mark.parametrize(
    "openapi_config, expected",
    (
        (None, None),
        (OpenAPIConfig(title="Starlite API", version="1.0.0", security=None), [{"sessionCookie": []}]),
        (
            OpenAPIConfig(title="Starlite API", version="1.0.0", security=[{"app": ["a", "b", "c"]}]),
            [{"app": ["a", "b", "c"]}, {"sessionCookie": []}],
        ),
    ),
)
def test_abstract_security_config_setting_openapi_security_requirements(
    openapi_config: Optional[OpenAPIConfig], expected: list, session_backend_config_memory: ServerSideSessionConfig
) -> None:
    security_config = SessionAuth[Any, ServerSideSessionBackend](
        retrieve_user_handler=retrieve_user_handler, exclude=["/"], session_backend_config=session_backend_config_memory
    )

    with create_test_client([], on_app_init=[security_config.on_app_init], openapi_config=openapi_config) as client:
        if openapi_config is not None:
            assert client.app.openapi_config
            assert client.app.openapi_config.security
            assert client.app.openapi_config.security == expected
        else:
            assert not client.app.openapi_config
