import logging
from typing import TYPE_CHECKING, Any, Dict
from unittest.mock import Mock, patch

import pytest

from starlite import Request, get
from starlite.logging.config import (
    LoggingConfig,
    _get_default_handlers,
    default_handlers,
    default_picologging_handlers,
)
from starlite.logging.picologging import (
    QueueListenerHandler as PicologgingQueueListenerHandler,
)
from starlite.logging.standard import (
    QueueListenerHandler as StandardQueueListenerHandler,
)
from starlite.status_codes import HTTP_200_OK
from starlite.testing import create_test_client

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture


@pytest.mark.parametrize(
    "dict_config_class, handlers, expected_called",
    [
        ["logging.config.dictConfig", default_handlers, True],
        ["logging.config.dictConfig", default_picologging_handlers, False],
        ["picologging.config.dictConfig", default_handlers, False],
        ["picologging.config.dictConfig", default_picologging_handlers, True],
    ],
)
def test_correct_dict_config_called(
    dict_config_class: str, handlers: Dict[str, Dict[str, Any]], expected_called: bool
) -> None:
    with patch(dict_config_class) as dict_config_mock:
        log_config = LoggingConfig(handlers=handlers)
        log_config.configure()
        if expected_called:
            assert dict_config_mock.called
        else:
            assert not dict_config_mock.called


@pytest.mark.parametrize("picologging_exists", [True, False])
def test_correct_default_handlers_set(picologging_exists: bool) -> None:
    with patch("starlite.logging.config.find_spec") as find_spec_mock:
        find_spec_mock.return_value = picologging_exists
        log_config = LoggingConfig()

        if picologging_exists:
            assert log_config.handlers == default_picologging_handlers
        else:
            assert log_config.handlers == default_handlers


@pytest.mark.parametrize(
    "dict_config_class, handlers",
    [
        ["logging.config.dictConfig", default_handlers],
        ["picologging.config.dictConfig", default_picologging_handlers],
    ],
)
def test_dictconfig_startup(dict_config_class: str, handlers: Any) -> None:
    with patch(dict_config_class) as dict_config_mock:
        test_logger = LoggingConfig(
            handlers=handlers,
        )
        with create_test_client([], on_startup=[test_logger.configure]):
            assert dict_config_mock.called


LoggingConfig(
    handlers=default_handlers,
    loggers={
        "test_logger": {"level": "INFO", "handlers": ["queue_listener"], "propagate": True},
    },
).configure()


def test_standard_queue_listener_logger(caplog: "LogCaptureFixture") -> None:
    with caplog.at_level("INFO", logger="test_logger"):
        logger = logging.getLogger("test_logger")
        logger.info("Testing now!")
        assert "Testing now!" in caplog.text
        var = "test_var"
        logger.info("%s", var)
        assert var in caplog.text


@patch("picologging.config.dictConfig")
def test_picologging_dictconfig_when_disabled(dict_config_mock: Mock) -> None:
    test_logger = LoggingConfig(loggers={"app": {"level": "INFO", "handlers": ["console"]}}, handlers=default_handlers)
    with create_test_client([], on_startup=[test_logger.configure]):
        assert not dict_config_mock.called


def test_get_default_logger() -> None:
    with create_test_client(logging_config=LoggingConfig(handlers=default_handlers)) as client:
        assert isinstance(client.app.logger.handlers[0], StandardQueueListenerHandler)
        new_logger = client.app.get_logger()
        assert isinstance(new_logger.handlers[0], StandardQueueListenerHandler)


def test_get_picologging_logger() -> None:
    with create_test_client(logging_config=LoggingConfig(handlers=default_picologging_handlers)) as client:
        assert isinstance(client.app.logger.handlers[0], PicologgingQueueListenerHandler)
        new_logger = client.app.get_logger()
        assert isinstance(new_logger.handlers[0], PicologgingQueueListenerHandler)


@pytest.mark.parametrize(
    "handlers, listener",
    [
        [default_handlers, StandardQueueListenerHandler],
        [default_picologging_handlers, PicologgingQueueListenerHandler],
    ],
)
def test_connection_logger(handlers: Any, listener: Any) -> None:
    @get("/")
    def handler(request: Request) -> Dict[str, bool]:
        return {"isinstance": isinstance(request.logger.handlers[0], listener)}  # type: ignore

    with create_test_client(route_handlers=[handler], logging_config=LoggingConfig(handlers=handlers)) as client:
        response = client.get("/")
        assert response.status_code == HTTP_200_OK
        assert response.json()["isinstance"]


def test_validation() -> None:
    logging_config = LoggingConfig(handlers={}, loggers={})
    assert logging_config.handlers["queue_listener"] == _get_default_handlers()["queue_listener"]
    assert logging_config.loggers["starlite"]


@pytest.mark.parametrize(
    "handlers, listener",
    [
        [default_handlers, StandardQueueListenerHandler],
        [default_picologging_handlers, PicologgingQueueListenerHandler],
    ],
)
def test_root_logger(handlers: Any, listener: Any) -> None:
    logging_config = LoggingConfig(handlers=handlers)
    get_logger = logging_config.configure()
    root_logger = get_logger()
    isinstance(root_logger.handlers[0], listener)  # type: ignore


@pytest.mark.parametrize(
    "handlers, listener",
    [
        [default_handlers, StandardQueueListenerHandler],
        [default_picologging_handlers, PicologgingQueueListenerHandler],
    ],
)
def test_customizing_handler(handlers: Any, listener: Any) -> None:
    handlers["queue_listener"]["handlers"] = ["cfg://handlers.console"]

    logging_config = LoggingConfig(handlers=handlers)
    get_logger = logging_config.configure()
    root_logger = get_logger()
    isinstance(root_logger.handlers[0], listener)  # type: ignore
