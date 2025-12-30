"""
Constants used throughout the library.
"""

# The marker value stored in StringTranslation.data to indicate "do not translate"
DO_NOT_TRANSLATE_MARKER = "__DO_NOT_TRANSLATE__"

# The separator used when encoding backup values in the marker
# Format: MARKER + BACKUP_SEPARATOR + original_value
# Example: "__DO_NOT_TRANSLATE__|backup|original_value"
BACKUP_SEPARATOR = "|backup|"

# Settings keys (can be overridden in Django settings)
SETTINGS_PREFIX = "WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS"

# Default configuration
DEFAULTS = {
    # Whether to enable the feature globally
    "ENABLED": True,
    # Custom marker (if you want to use a different value)
    "MARKER": DO_NOT_TRANSLATE_MARKER,
    # Custom backup separator (if you want to use a different value)
    "BACKUP_SEPARATOR": BACKUP_SEPARATOR,
    # Permission required to mark segments as "do not translate"
    # None = any translator, or specify a permission string
    "REQUIRED_PERMISSION": None,
}


def get_setting(key, default=None):
    """
    Get a setting value from Django settings.

    Args:
        key: Setting key (without prefix)
        default: Default value if not found

    Returns:
        The setting value
    """
    from django.conf import settings

    full_key = f"{SETTINGS_PREFIX}_{key}"
    return getattr(settings, full_key, DEFAULTS.get(key, default))
