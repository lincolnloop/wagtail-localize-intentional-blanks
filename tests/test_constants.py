"""
Unit tests for constants module.
"""

from django.test import TestCase, override_settings

from wagtail_localize_intentional_blanks.constants import (
    DEFAULTS,
    DO_NOT_TRANSLATE_MARKER,
    get_setting,
)


class TestConstants(TestCase):
    """Test constants and settings."""

    def test_do_not_translate_marker_value(self):
        """Test that DO_NOT_TRANSLATE_MARKER has the correct value."""
        assert DO_NOT_TRANSLATE_MARKER == "__DO_NOT_TRANSLATE__"

    def test_defaults_structure(self):
        """Test that DEFAULTS contains expected keys."""
        assert "ENABLED" in DEFAULTS
        assert "MARKER" in DEFAULTS
        assert "REQUIRED_PERMISSION" in DEFAULTS

    def test_defaults_values(self):
        """Test default values."""
        assert DEFAULTS["ENABLED"] is True
        assert DEFAULTS["MARKER"] == DO_NOT_TRANSLATE_MARKER
        assert DEFAULTS["REQUIRED_PERMISSION"] is None

    def test_get_setting_returns_default(self):
        """Test get_setting returns default value when setting is not defined."""
        value = get_setting("ENABLED")
        assert value is True

    def test_get_setting_returns_custom_default(self):
        """Test get_setting returns provided default when key not in DEFAULTS."""
        value = get_setting("NONEXISTENT_KEY", default="custom_default")
        assert value == "custom_default"

    @override_settings(WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_ENABLED=False)
    def test_get_setting_returns_django_setting(self):
        """Test get_setting returns value from Django settings."""
        value = get_setting("ENABLED")
        assert value is False

    @override_settings(WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_MARKER="__CUSTOM_MARKER__")
    def test_get_setting_custom_marker(self):
        """Test get_setting with custom marker."""
        value = get_setting("MARKER")
        assert value == "__CUSTOM_MARKER__"

    @override_settings(
        WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_REQUIRED_PERMISSION="cms.can_translate"
    )
    def test_get_setting_custom_permission(self):
        """Test get_setting with custom permission."""
        value = get_setting("REQUIRED_PERMISSION")
        assert value == "cms.can_translate"

    def test_get_setting_with_none_default(self):
        """Test get_setting when default is None."""
        value = get_setting("NONEXISTENT_KEY")
        assert value is None
