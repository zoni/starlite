from pathlib import Path
from typing import Optional

import pytest
from _pytest.monkeypatch import MonkeyPatch
from click import ClickException

from starlite import Starlite
from starlite.cli._utils import StarliteEnv, _path_to_dotted_path
from tests.cli.conftest import CreateAppFileFixture


@pytest.mark.parametrize("env_name,attr_name", [("STARLITE_DEBUG", "debug"), ("STARLITE_RELOAD", "reload")])
@pytest.mark.parametrize(
    "env_value,expected_value",
    [("true", True), ("True", True), ("1", True), ("0", False), (None, False)],
)
def test_starlite_env_from_env_booleans(
    monkeypatch: MonkeyPatch,
    app_file: Path,
    attr_name: str,
    env_name: str,
    env_value: Optional[str],
    expected_value: bool,
) -> None:
    if env_value is not None:
        monkeypatch.setenv(env_name, env_value)

    env = StarliteEnv.from_env(f"{app_file.stem}:app")

    assert getattr(env, attr_name) is expected_value
    assert isinstance(env.app, Starlite)


def test_starlite_env_from_env_port(monkeypatch: MonkeyPatch, app_file: Path) -> None:
    env = StarliteEnv.from_env(f"{app_file.stem}:app")
    assert env.port is None

    monkeypatch.setenv("STARLITE_PORT", "7000")
    env = StarliteEnv.from_env(f"{app_file.stem}:app")
    assert env.port == 7000


def test_starlite_env_from_env_host(monkeypatch: MonkeyPatch, app_file: Path) -> None:
    env = StarliteEnv.from_env(f"{app_file.stem}:app")
    assert env.host is None

    monkeypatch.setenv("STARLITE_HOST", "0.0.0.0")
    env = StarliteEnv.from_env(f"{app_file.stem}:app")
    assert env.host == "0.0.0.0"


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("app.py", id="app_file"),
        pytest.param("application.py", id="application_file"),
        pytest.param("app/main.py", id="app_module"),
        pytest.param("app/any_name.py", id="app_module_random"),
        pytest.param("application/another_random_name.py", id="application_module_random"),
    ],
)
def test_env_from_env_autodiscover_from_files(
    path: str, app_file_content: str, app_file_app_name: str, create_app_file: CreateAppFileFixture
) -> None:
    directory = None
    if "/" in path:
        directory, path = path.split("/", 1)

    tmp_file_path = create_app_file(file=path, directory=directory, content=app_file_content)
    env = StarliteEnv.from_env(None)

    dotted_path = _path_to_dotted_path(tmp_file_path.relative_to(Path.cwd()))

    assert isinstance(env.app, Starlite)
    assert env.app_path == f"{dotted_path}:{app_file_app_name}"


@pytest.mark.parametrize(
    "module_name,app_file",
    [
        ("app", "main.py"),
        ("application", "main.py"),
        ("app", "anything.py"),
        ("application", "anything.py"),
    ],
)
def test_env_from_env_autodiscover_from_module(
    module_name: str,
    app_file: str,
    app_file_content: str,
    app_file_app_name: str,
    create_app_file: CreateAppFileFixture,
) -> None:
    create_app_file(
        file=app_file,
        directory=module_name,
        content=app_file_content,
        init_content=f"from .{app_file.split('.')[0]} import {app_file_app_name}",
    )
    env = StarliteEnv.from_env(None)

    assert isinstance(env.app, Starlite)
    assert env.app_path == f"{module_name}:{app_file_app_name}"


@pytest.mark.parametrize("path", [".app.py", "_app.py", ".application.py", "_application.py"])
def test_env_from_env_autodiscover_from_files_ignore_paths(
    path: str, app_file_content: str, create_app_file: CreateAppFileFixture
) -> None:
    create_app_file(file=path, directory=None, content=app_file_content)

    with pytest.raises(ClickException):
        StarliteEnv.from_env(None)
