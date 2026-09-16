from __future__ import annotations

import base64

import pytest

import main
from core.application.paths import AppPaths
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.secret_store import ExistingArchiveKeyMissing, SecretStore
from core.storage.sensitive_store import SensitiveStore

_TEST_KEY = b"a" * 32


def _configure_paths(monkeypatch: pytest.MonkeyPatch, tmp_path) -> AppPaths:
    paths = AppPaths(data_dir=tmp_path / "data", config_dir=tmp_path / "config")
    monkeypatch.setattr(main, "default_app_paths", lambda: paths)
    return paths


def _seed_encrypted_archive(paths: AppPaths) -> None:
    database = Database(paths.database_path)
    database.initialize()
    identity_repository = IdentityRepository(database, SensitiveStore(_TEST_KEY))
    identity = identity_repository.get_or_create_identity()
    assert identity.id is not None
    identity_repository.set_display_name(identity.id, "Private identity")


def test_first_launch_creates_key_before_database(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    paths = _configure_paths(monkeypatch, tmp_path)
    stored: dict[str, str] = {}
    monkeypatch.setattr(
        "core.storage.secret_store.keyring.get_password",
        lambda _service, _name: stored.get("key"),
    )
    monkeypatch.setattr(
        "core.storage.secret_store.keyring.set_password",
        lambda _service, _name, value: stored.__setitem__("key", value),
    )

    controller, *_ = main.build_controller()

    assert len(base64.urlsafe_b64decode(stored["key"])) == 32
    assert paths.database_path.is_file()
    assert controller.get_bootstrap_state()["identity"]["displayName"] is None


def test_existing_archive_without_key_is_preserved(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    paths = _configure_paths(monkeypatch, tmp_path)
    _seed_encrypted_archive(paths)
    original_archive = paths.database_path.read_bytes()
    attempted_writes: list[str] = []
    monkeypatch.setattr("core.storage.secret_store.keyring.get_password", lambda *_: None)
    monkeypatch.setattr(
        "core.storage.secret_store.keyring.set_password",
        lambda _service, _name, value: attempted_writes.append(value),
    )

    with pytest.raises(ExistingArchiveKeyMissing, match="encryption key is missing"):
        main.build_controller()

    assert attempted_writes == []
    assert paths.database_path.read_bytes() == original_archive


def test_existing_archive_reuses_its_original_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    paths = _configure_paths(monkeypatch, tmp_path)
    _seed_encrypted_archive(paths)
    encoded_key = base64.urlsafe_b64encode(_TEST_KEY).decode("ascii")
    monkeypatch.setattr("core.storage.secret_store.keyring.get_password", lambda *_: encoded_key)
    monkeypatch.setattr(
        "core.storage.secret_store.keyring.set_password",
        lambda *_: pytest.fail("Existing key must not be replaced"),
    )

    controller, *_ = main.build_controller()

    assert controller.get_bootstrap_state()["identity"]["displayName"] == "Private identity"


def test_orphaned_artifacts_prevent_new_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    paths = _configure_paths(monkeypatch, tmp_path)
    paths.artifacts_dir.mkdir(parents=True)
    (paths.artifacts_dir / "existing.dat").write_bytes(SensitiveStore(_TEST_KEY).encrypt_text("secret"))
    monkeypatch.setattr("core.storage.secret_store.keyring.get_password", lambda *_: None)
    monkeypatch.setattr(
        "core.storage.secret_store.keyring.set_password",
        lambda *_: pytest.fail("Orphaned artifacts must not be paired with a new key"),
    )

    with pytest.raises(ExistingArchiveKeyMissing):
        main.build_controller()

    assert not paths.database_path.exists()
    assert (paths.artifacts_dir / "existing.dat").is_file()


def test_creation_requires_an_explicit_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.storage.secret_store.keyring.get_password", lambda *_: None)
    monkeypatch.setattr(
        "core.storage.secret_store.keyring.set_password",
        lambda *_: pytest.fail("No implicit key creation is permitted"),
    )

    with pytest.raises(TypeError):
        SecretStore().get_or_create_master_key()
