"""
wagtail-localize-intentional-blanks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A Wagtail library that extends wagtail-localize to allow translators to mark
translation segments as "do not translate". These segments count as not needing
to be translated, and fall back to the source page's value when rendered.

:copyright: (c) 2025 by Lincoln Loop, LLC
:license: MIT, see LICENSE for more details.
"""

__version__ = "0.1.0"
__author__ = "Lincoln Loop, LLC"
__license__ = "MIT"

# Public API
from .constants import DO_NOT_TRANSLATE_MARKER

# Utility functions can be imported from their modules if needed:
#   from wagtail_localize_intentional_blanks.utils import mark_segment_do_not_translate

__all__ = [
    "DO_NOT_TRANSLATE_MARKER",
]


# Default Django app config
default_app_config = "wagtail_localize_intentional_blanks.apps.IntentionalBlanksConfig"
