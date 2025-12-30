"""
Utility functions for marking segments as "do not translate".
"""

import logging

from django.db.models import Q

from wagtail_localize.models import StringSegment, StringTranslation

from .constants import get_setting

logger = logging.getLogger(__name__)


def get_marker():
    """Get the configured marker value."""
    return get_setting("MARKER")


def get_backup_separator():
    """
    Get the configured backup separator value.

    The backup separator is used when encoding backup values in the marker.
    Format: MARKER + BACKUP_SEPARATOR + original_value
    Example: "__DO_NOT_TRANSLATE__|backup|original_value"
    """
    return get_setting("BACKUP_SEPARATOR")


def validate_configuration():
    """
    Validate that required configuration values are set.

    Raises:
        ValueError: If marker or backup_separator is None or empty
    """
    marker = get_marker()
    backup_separator = get_backup_separator()

    if marker is None or marker == "":
        raise ValueError("WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_MARKER must be set to a non-empty string. Check your Django settings.")

    if backup_separator is None or backup_separator == "":
        raise ValueError("WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_BACKUP_SEPARATOR must be set to a non-empty string. Check your Django settings.")


def mark_segment_do_not_translate(translation, segment, user=None):
    """
    Mark a translation segment as "do not translate".

    Args:
        translation: Translation instance
        segment: StringSegment instance
        user: Optional user who made the change (for audit log)

    Returns:
        The created/updated StringTranslation

    Example:
        >>> from wagtail_localize.models import Translation, StringSegment
        >>> translation = Translation.objects.get(id=123)
        >>> segment = StringSegment.objects.get(id=456)
        >>> mark_segment_do_not_translate(translation, segment)
    """
    validate_configuration()
    marker = get_marker()

    logger.info(f"Marking segment: string_id={segment.string.id}, locale={translation.target_locale}, context='{segment.context}', marker='{marker}'")

    # Check if there's an existing translation with real data (not the marker)
    backup_separator = get_backup_separator()
    try:
        existing = StringTranslation.objects.get(translation_of=segment.string, locale=translation.target_locale, context=segment.context)
        # Encode backup in the marker itself
        if existing.data != marker and not existing.data.startswith(marker + backup_separator):
            backup_data = existing.data
            logger.info(f"Backing up existing translation: '{backup_data}'")
            # Encode backup in the data field: __DO_NOT_TRANSLATE__|backup|original_value
            marker_with_backup = f"{marker}{backup_separator}{backup_data}"
        else:
            marker_with_backup = marker
    except StringTranslation.DoesNotExist:
        marker_with_backup = marker

    string_translation, created = StringTranslation.objects.update_or_create(
        translation_of=segment.string,
        locale=translation.target_locale,
        context=segment.context,
        defaults={
            "data": marker_with_backup,
            "translation_type": StringTranslation.TRANSLATION_TYPE_MANUAL,
            "last_translated_by": user,
        },
    )

    logger.info(f"StringTranslation {'created' if created else 'updated'}: id={string_translation.id}")

    return string_translation


def unmark_segment_do_not_translate(translation, segment):
    """
    Remove "do not translate" marking, allowing manual translation.

    Args:
        translation: Translation instance
        segment: StringSegment instance

    Returns:
        int: Number of records deleted

    Example:
        >>> unmark_segment_do_not_translate(translation, segment)
    """
    validate_configuration()
    marker = get_marker()
    backup_separator = get_backup_separator()

    # Log what we're trying to delete
    logger.info(
        f"Attempting to unmark segment: string_id={segment.string.id}, "
        f"locale={translation.target_locale}, context='{segment.context}', marker='{marker}'"
    )

    # First, let's see ALL StringTranslation records for this string in this locale
    all_for_string = StringTranslation.objects.filter(translation_of=segment.string, locale=translation.target_locale)
    logger.info(f"Total StringTranslation records for this string in locale: {all_for_string.count()}")
    for st in all_for_string:
        logger.info(f"  - id={st.id}, context='{st.context}', data='{st.data}'")

    # Find the marked translation (could be just marker or marker with encoded backup)
    try:
        # Try to find with exact marker first
        try:
            marked_translation = StringTranslation.objects.get(
                translation_of=segment.string, locale=translation.target_locale, context=segment.context, data=marker
            )
            backup_data = None
        except StringTranslation.DoesNotExist:
            # Try to find with encoded backup
            marked_translation = StringTranslation.objects.get(
                translation_of=segment.string,
                locale=translation.target_locale,
                context=segment.context,
                data__startswith=marker + backup_separator,
            )
            # Extract backup from encoded data: __DO_NOT_TRANSLATE__|backup|original_value
            backup_data = marked_translation.data.split(backup_separator, 1)[1] if backup_separator in marked_translation.data else None
            logger.info(f"Found backup in data field: '{backup_data}'")

        if backup_data:
            # Restore the backup
            logger.info(f"Restoring backup translation: '{backup_data}'")
            marked_translation.data = backup_data
            marked_translation.save()
            return 1  # Updated
        else:
            # No backup, just delete
            marked_translation.delete()
            logger.info("Deleted marked translation (no backup)")
            return 1  # Deleted

    except StringTranslation.DoesNotExist:
        logger.info("No matching StringTranslation found to delete")
        return 0


def is_do_not_translate(string_translation):
    """
    Check if a StringTranslation is marked as "do not translate".

    Args:
        string_translation: StringTranslation instance

    Returns:
        bool: True if marked as "do not translate"

    Example:
        >>> from wagtail_localize.models import StringTranslation
        >>> st = StringTranslation.objects.get(id=789)
        >>> if is_do_not_translate(st):
        ...     print("Marked as do not translate")
    """
    validate_configuration()
    marker = get_marker()
    backup_separator = get_backup_separator()
    return string_translation.data == marker or string_translation.data.startswith(marker + backup_separator)


def get_source_fallback_stats(translation):
    """
    Get statistics on how many segments are marked as "do not translate".

    Args:
        translation: Translation instance

    Returns:
        dict with counts:
            - total: Total translated segments
            - do_not_translate: Segments marked as "do not translate"
            - manually_translated: Segments with manual translations

    Example:
        >>> stats = get_source_fallback_stats(translation)
        >>> print(f"{stats['do_not_translate']} segments marked as do not translate")
    """
    validate_configuration()
    marker = get_marker()
    backup_separator = get_backup_separator()

    # Get all string IDs from segments belonging to this translation source
    string_ids = StringSegment.objects.filter(source=translation.source).values_list("string_id", flat=True)

    # Query translations for these strings in the target locale
    all_translations = StringTranslation.objects.filter(locale=translation.target_locale, translation_of_id__in=string_ids)

    # Match both exact marker and encoded backup format
    do_not_translate = all_translations.filter(Q(data=marker) | Q(data__startswith=marker + backup_separator))
    manually_translated = all_translations.exclude(Q(data=marker) | Q(data__startswith=marker + backup_separator))

    return {
        "total": all_translations.count(),
        "do_not_translate": do_not_translate.count(),
        "manually_translated": manually_translated.count(),
    }


def bulk_mark_segments(translation, segments, user=None):
    """
    Mark multiple segments as "do not translate" in a single operation.

    Args:
        translation: Translation instance
        segments: Iterable of StringSegment instances
        user: Optional user who made the change

    Returns:
        int: Number of segments marked

    Example:
        >>> segments = StringSegment.objects.filter(source=source)[:10]
        >>> count = bulk_mark_segments(translation, segments)
        >>> print(f"Marked {count} segments")
    """
    count = 0

    for segment in segments:
        mark_segment_do_not_translate(translation, segment, user=user)
        count += 1

    return count


def get_segments_do_not_translate(translation):
    """
    Get all segments that are marked as "do not translate" for a translation.

    Args:
        translation: Translation instance

    Returns:
        QuerySet of StringSegment instances

    Example:
        >>> segments = get_segments_do_not_translate(translation)
        >>> for segment in segments:
        ...     print(f"Segment {segment.id}: {segment.string.data}")
    """
    validate_configuration()
    marker = get_marker()
    backup_separator = get_backup_separator()

    # Get all string IDs from segments belonging to this translation source
    string_ids = StringSegment.objects.filter(source=translation.source).values_list("string_id", flat=True)

    # Find translations marked as "do not translate" (match both exact marker and encoded backup format)
    marked_string_translations = StringTranslation.objects.filter(locale=translation.target_locale, translation_of_id__in=string_ids).filter(
        Q(data=marker) | Q(data__startswith=marker + backup_separator)
    )

    # Get the string IDs of marked translations
    marked_string_ids = marked_string_translations.values_list("translation_of_id", flat=True)

    # Return the segments that have these marked strings
    return StringSegment.objects.filter(source=translation.source, string_id__in=marked_string_ids)
