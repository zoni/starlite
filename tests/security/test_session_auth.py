from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import uuid4

from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_401_UNAUTHORIZED,
)

from starlite import Request, Starlite, delete, get, post
from starlite.middleware.session.server_side import (
    ServerSideSessionBackend,
    ServerSideSessionConfig,
)
from starlite.security.session_auth import SessionAuth
from starlite.testing import create_test_client
from tests import User, UserFactory

if TYPE_CHECKING:
    from starlite.connection import ASGIConnection

user_instance = UserFactory.build()


def retrieve_user_handler(session_data: Dict[str, Any], _: "ASGIConnection") -> Optional[User]:
    if session_data["id"] == str(user_instance.id):
        return User(**session_data)
    return None


def test_authentication(session_backend_config_memory: ServerSideSessionConfig) -> None:
    session_auth = SessionAuth[Any, ServerSideSessionBackend](
        retrieve_user_handler=retrieve_user_handler,
        exclude=["login"],
        session_backend_config=session_backend_config_memory,
    )

    @post("/login")
    def login_handler(request: "Request[Any, Any, Any]", data: User) -> None:
        request.set_session(data.dict())

    @delete("/user/{user_id:str}")
    def delete_user_handler(request: "Request[User, Any, Any]") -> None:
        request.clear_session()

    @get("/user/{user_id:str}")
    def get_user_handler(request: "Request[User, Any, Any]") -> User:
        return request.user

    with create_test_client(
        route_handlers=[login_handler, delete_user_handler, get_user_handler],
        on_app_init=[session_auth.on_app_init],
    ) as client:
        response = client.get(f"user/{user_instance.id}")
        assert response.status_code == HTTP_401_UNAUTHORIZED, response.json()

        response = client.post("/login", json={"id": str(user_instance.id), "name": user_instance.name})
        assert response.status_code == HTTP_201_CREATED, response.json()

        response = client.get(f"user/{user_instance.id}")
        assert response.status_code == HTTP_200_OK, response.json()

        response = client.delete(f"user/{user_instance.id}")
        assert response.status_code == HTTP_204_NO_CONTENT, response.json()

        response = client.get(f"user/{user_instance.id}")
        assert response.status_code == HTTP_401_UNAUTHORIZED, response.json()

        response = client.post("/login", json={"id": str(uuid4()), "name": user_instance.name})
        assert response.status_code == HTTP_201_CREATED, response.json()

        response = client.get(f"user/{user_instance.id}")
        assert response.status_code == HTTP_401_UNAUTHORIZED, response.json()


def test_session_auth_openapi(session_backend_config_memory: "ServerSideSessionConfig") -> None:
    session_auth = SessionAuth[Any, ServerSideSessionBackend](
        retrieve_user_handler=retrieve_user_handler,
        session_backend_config=session_backend_config_memory,
    )
    app = Starlite(on_app_init=[session_auth.on_app_init])
    assert app.openapi_schema.to_schema() == {  # type: ignore
        "openapi": "3.1.0",
        "info": {"title": "Starlite API", "version": "1.0.0"},
        "servers": [{"url": "/"}],
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {
                "sessionCookie": {
                    "type": "apiKey",
                    "description": "Session cookie authentication.",
                    "name": session_backend_config_memory.key,
                    "in": "cookie",
                }
            },
        },
        "security": [{"sessionCookie": []}],
    }
