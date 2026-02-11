"""
Signal handlers for wagtail-localize integration.

These handlers implement the intentional blanks functionality using
wagtail-localize's signal-based extension mechanism, replacing the
previous monkey-patching approach.
"""

import logging

from wagtail_localize.signals import post_source_update, process_string_segment
from wagtail_localize.strings import StringValue

from .constants import get_setting

logger = logging.getLogger(__name__)


def handle_process_string_segment(
    sender, string_segment, string_value, locale, fallback, source, **kwargs
):
    """
    Handle the process_string_segment signal to implement intentional blanks.

    When a StringTranslation contains the DO_NOT_TRANSLATE marker,
    return the source value instead of the translation.
    """
    if not get_setting("ENABLED"):
        return None

    marker = get_setting("MARKER")
    backup_separator = get_setting("BACKUP_SEPARATOR")

    translation_data = string_segment.translation
    if not translation_data:
        return None

    # Check for marker (exact match or with encoded backup)
    if translation_data == marker or translation_data.startswith(
        marker + backup_separator
    ):
        logger.debug(
            "Intentional blank detected for segment %s in locale %s, using source value",
            string_segment.string_id,
            locale,
        )
        # Return source value instead of translation
        return StringValue(string_segment.string.data)

    return None


def handle_post_source_update(sender, source, **kwargs):
    """
    Handle the post_source_update signal to migrate markers after sync.

    When source content changes and is synced, migrate any 'Do Not Translate'
    markers to the new Strings.
    """
    if not get_setting("ENABLED"):
        return

    from wagtail_localize.models import Translation

    from .utils import migrate_do_not_translate_markers

    translations = Translation.objects.filter(source=source)

    for translation in translations:
        migrate_do_not_translate_markers(source, translation.target_locale)


def register_signal_handlers():
    """Register all signal handlers."""
    process_string_segment.connect(
        handle_process_string_segment,
        dispatch_uid="intentional_blanks_process_string_segment",
    )
    post_source_update.connect(
        handle_post_source_update,
        dispatch_uid="intentional_blanks_post_source_update",
    )


def unregister_signal_handlers():
    """Unregister all signal handlers (useful for testing)."""
    process_string_segment.disconnect(
        handle_process_string_segment,
        dispatch_uid="intentional_blanks_process_string_segment",
    )
    post_source_update.disconnect(
        handle_post_source_update,
        dispatch_uid="intentional_blanks_post_source_update",
    )
