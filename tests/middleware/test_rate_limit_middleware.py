from time import time
from typing import TYPE_CHECKING, Any

import pytest
from freezegun import freeze_time

from starlite import Request, Starlite, get
from starlite.middleware.rate_limit import (
    DURATION_VALUES,
    CacheObject,
    DurationUnit,
    RateLimitConfig,
)
from starlite.serialization import decode_json, encode_json
from starlite.static_files.config import StaticFilesConfig
from starlite.status_codes import HTTP_200_OK, HTTP_429_TOO_MANY_REQUESTS
from starlite.stores.base import Store
from starlite.testing import TestClient, create_test_client

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("unit", ["minute", "second", "hour", "day"])
async def test_rate_limiting(unit: DurationUnit) -> None:
    @get("/")
    def handler() -> None:
        return None

    config = RateLimitConfig(rate_limit=(unit, 1))
    cache_key = "RateLimitMiddleware::testclient"
    app = Starlite(route_handlers=[handler], middleware=[config.middleware])
    store = app.stores.get("rate_limit")

    with freeze_time() as frozen_time, TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == HTTP_200_OK
        cached_value = await store.get(cache_key)
        assert cached_value
        cache_object = CacheObject(**decode_json(cached_value))
        assert len(cache_object.history) == 1

        assert response.headers.get(config.rate_limit_policy_header_key) == f"1; w={DURATION_VALUES[unit]}"
        assert response.headers.get(config.rate_limit_limit_header_key) == "1"
        assert response.headers.get(config.rate_limit_remaining_header_key) == "0"
        assert response.headers.get(config.rate_limit_reset_header_key) == str(int(time()) - cache_object.reset)

        frozen_time.tick(DURATION_VALUES[unit] - 1)  # type: ignore[arg-type]

        response = client.get("/")
        assert response.status_code == HTTP_429_TOO_MANY_REQUESTS
        assert response.headers.get(config.rate_limit_policy_header_key) == f"1; w={DURATION_VALUES[unit]}"
        assert response.headers.get(config.rate_limit_limit_header_key) == "1"
        assert response.headers.get(config.rate_limit_remaining_header_key) == "0"
        assert response.headers.get(config.rate_limit_reset_header_key) == str(int(time()) - cache_object.reset)

        frozen_time.tick(1)  # type: ignore[arg-type]

        response = client.get("/")
        assert response.status_code == HTTP_200_OK


async def test_non_default_store(memory_store: Store) -> None:
    @get("/")
    def handler() -> None:
        return None

    app = Starlite(
        [handler], middleware=[RateLimitConfig(("second", 10)).middleware], stores={"rate_limit": memory_store}
    )

    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200

    assert await memory_store.exists("RateLimitMiddleware::testclient")


async def test_set_store_name(memory_store: Store) -> None:
    @get("/")
    def handler() -> None:
        return None

    app = Starlite(
        [handler],
        middleware=[RateLimitConfig(("second", 10), store="some_store").middleware],
        stores={"some_store": memory_store},
    )

    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200

    assert await memory_store.exists("RateLimitMiddleware::testclient")


async def test_reset() -> None:
    @get("/")
    def handler() -> None:
        return None

    config = RateLimitConfig(rate_limit=("second", 1))
    cache_key = "RateLimitMiddleware::testclient"
    app = Starlite(route_handlers=[handler], middleware=[config.middleware])
    store = app.stores.get("rate_limit")

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == HTTP_200_OK
        cached_value = await store.get(cache_key)
        assert cached_value
        cache_object = CacheObject(**decode_json(cached_value))
        assert cache_object.reset == int(time() + 1)

        cache_object.reset -= 2
        await store.set(cache_key, encode_json(cache_object))

        response = client.get("/")
        assert response.status_code == HTTP_200_OK


def test_exclude_patterns() -> None:
    @get("/excluded")
    def handler() -> None:
        return None

    @get("/not-excluded")
    def handler2() -> None:
        return None

    config = RateLimitConfig(rate_limit=("second", 1), exclude=["/excluded"])

    with create_test_client(route_handlers=[handler, handler2], middleware=[config.middleware]) as client:
        response = client.get("/excluded")
        assert response.status_code == HTTP_200_OK

        response = client.get("/excluded")
        assert response.status_code == HTTP_200_OK

        response = client.get("/not-excluded")
        assert response.status_code == HTTP_200_OK

        response = client.get("/not-excluded")
        assert response.status_code == HTTP_429_TOO_MANY_REQUESTS


def test_exclude_opt_key() -> None:
    @get("/excluded", skip_rate_limiting=True)
    def handler() -> None:
        return None

    @get("/not-excluded")
    def handler2() -> None:
        return None

    config = RateLimitConfig(rate_limit=("second", 1), exclude_opt_key="skip_rate_limiting")

    with create_test_client(route_handlers=[handler, handler2], middleware=[config.middleware]) as client:
        response = client.get("/excluded")
        assert response.status_code == HTTP_200_OK

        response = client.get("/excluded")
        assert response.status_code == HTTP_200_OK

        response = client.get("/not-excluded")
        assert response.status_code == HTTP_200_OK

        response = client.get("/not-excluded")
        assert response.status_code == HTTP_429_TOO_MANY_REQUESTS


def test_check_throttle_handler() -> None:
    @get("/path1")
    def handler1() -> None:
        return None

    @get("/path2")
    def handler2() -> None:
        return None

    def check_throttle_handler(request: Request[Any, Any, Any]) -> bool:
        return request.url.path == "/path1"

    config = RateLimitConfig(rate_limit=("minute", 1), check_throttle_handler=check_throttle_handler)

    with create_test_client(route_handlers=[handler1, handler2], middleware=[config.middleware]) as client:
        response = client.get("/path1")
        assert response.status_code == HTTP_200_OK

        response = client.get("/path1")
        assert response.status_code == HTTP_429_TOO_MANY_REQUESTS

        response = client.get("/path2")
        assert response.status_code == HTTP_200_OK

        response = client.get("/path2")
        assert response.status_code == HTTP_200_OK


async def test_rate_limiting_works_with_mounted_apps(tmpdir: "Path") -> None:
    # https://github.com/starlite-api/starlite/issues/781
    @get("/not-excluded")
    def handler() -> None:
        return None

    path1 = tmpdir / "test.css"
    path1.write_text("styles content", "utf-8")

    static_files_config = StaticFilesConfig(directories=[tmpdir], path="/src/static")  # pyright: ignore
    rate_limit_config = RateLimitConfig(rate_limit=("minute", 1), exclude=[r"^/src.*$"])
    with create_test_client(
        [handler], static_files_config=[static_files_config], middleware=[rate_limit_config.middleware]
    ) as client:
        response = client.get("/not-excluded")
        assert response.status_code == HTTP_200_OK

        response = client.get("/not-excluded")
        assert response.status_code == HTTP_429_TOO_MANY_REQUESTS

        response = client.get("/src/static/test.css")
        assert response.status_code == HTTP_200_OK
        assert response.text == "styles content"
