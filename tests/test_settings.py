from __future__ import annotations

from config.settings import AppSettings, SettingsStore
from main import _validated_inference_endpoint


def test_malformed_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not-json", encoding="utf-8")

    assert SettingsStore(path).load() == AppSettings()


def test_settings_are_bounded_and_choices_validated(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"window_width": 50, "window_height": 99999, "inference_location": "TRUST_ME"}',
        encoding="utf-8",
    )

    settings = SettingsStore(path).load()

    assert settings.window_width == 960
    assert settings.window_height == 2160
    assert settings.inference_location == "LOCAL_PROCESS"


def test_semantically_invalid_inference_settings_recover_to_local_defaults() -> None:
    settings = AppSettings(
        inference_endpoint="http://example.com",
        inference_location="REMOTE",
    )

    endpoint = _validated_inference_endpoint(settings)

    defaults = AppSettings()
    assert endpoint.url == defaults.inference_endpoint
    assert settings.inference_endpoint == defaults.inference_endpoint
    assert settings.inference_location == defaults.inference_location


def test_settings_save_is_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    expected = AppSettings(window_width=1440, window_height=900, inference_location="USER_APPROVED_LAN")

    store = SettingsStore(path)
    store.save(expected)

    assert store.load() == expected
