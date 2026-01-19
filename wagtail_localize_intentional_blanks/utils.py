"""
Utility functions for marking segments as "do not translate".
"""

import logging

from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
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
        raise ValueError(
            "WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_MARKER must be set to a non-empty string. Check your Django settings."
        )

    if backup_separator is None or backup_separator == "":
        raise ValueError(
            "WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_BACKUP_SEPARATOR must be set to a non-empty string. Check your Django settings."
        )


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

    logger.info(
        f"Marking segment: string_id={segment.string.id}, locale={translation.target_locale}, context='{segment.context}', marker='{marker}'"
    )

    # Check if there's an existing translation with real data (not the marker)
    backup_separator = get_backup_separator()
    try:
        existing = StringTranslation.objects.get(
            translation_of=segment.string,
            locale=translation.target_locale,
            context=segment.context,
        )
        # Encode backup in the marker itself
        if existing.data != marker and not existing.data.startswith(
            marker + backup_separator
        ):
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

    logger.info(
        f"StringTranslation {'created' if created else 'updated'}: id={string_translation.id}"
    )

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
    all_for_string = StringTranslation.objects.filter(
        translation_of=segment.string, locale=translation.target_locale
    )
    logger.info(
        f"Total StringTranslation records for this string in locale: {all_for_string.count()}"
    )
    for st in all_for_string:
        logger.info(f"  - id={st.id}, context='{st.context}', data='{st.data}'")

    # Find the marked translation (could be just marker or marker with encoded backup)
    try:
        # Try to find with exact marker first
        try:
            marked_translation = StringTranslation.objects.get(
                translation_of=segment.string,
                locale=translation.target_locale,
                context=segment.context,
                data=marker,
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
            backup_data = (
                marked_translation.data.split(backup_separator, 1)[1]
                if backup_separator in marked_translation.data
                else None
            )
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
    return string_translation.data == marker or string_translation.data.startswith(
        marker + backup_separator
    )


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
    string_ids = StringSegment.objects.filter(source=translation.source).values_list(
        "string_id", flat=True
    )

    # Query translations for these strings in the target locale
    all_translations = StringTranslation.objects.filter(
        locale=translation.target_locale, translation_of_id__in=string_ids
    )

    # Match both exact marker and encoded backup format
    do_not_translate = all_translations.filter(
        Q(data=marker) | Q(data__startswith=marker + backup_separator)
    )
    manually_translated = all_translations.exclude(
        Q(data=marker) | Q(data__startswith=marker + backup_separator)
    )

    return {
        "total": all_translations.count(),
        "do_not_translate": do_not_translate.count(),
        "manually_translated": manually_translated.count(),
    }


def bulk_mark_segments(translation, segments, user=None):
    """
    Mark multiple segments as "do not translate" using optimized batch operations.

    This function uses bulk_create and bulk_update to minimize database queries,
    making it highly performant even for large numbers of segments.

    Note: This function manually triggers post_save signals for created and updated
    StringTranslations to ensure other parts of the system (like wagtail-localize)
    are notified of changes.

    Args:
        translation: Translation instance
        segments: Iterable of StringSegment instances
        user: Optional user who made the change

    Returns:
        int: Number of segments marked

    Example:
        >>> segments = StringSegment.objects.filter(source=source)
        >>> count = bulk_mark_segments(translation, segments)
        >>> print(f"Marked {count} segments")
    """
    validate_configuration()
    marker = get_marker()
    backup_separator = get_backup_separator()

    with transaction.atomic():
        # Convert to list if needed and filter out segments without strings
        segments = [s for s in segments if s.string_id]

        if not segments:
            return 0

        # Fetch existing translations once - single query
        string_ids = [s.string_id for s in segments]
        existing_translations = StringTranslation.objects.filter(
            translation_of_id__in=string_ids,
            locale=translation.target_locale,
        ).select_related("translation_of")

        # Build lookup dict: (string_id, context) -> translation
        existing_map = {
            (st.translation_of_id, st.context): st for st in existing_translations
        }

        to_create = []
        to_update = []

        for segment in segments:
            key = (segment.string_id, segment.context)
            existing = existing_map.get(key)

            if existing:
                # Check if we need to backup
                if existing.data != marker and not existing.data.startswith(
                    marker + backup_separator
                ):
                    existing.data = f"{marker}{backup_separator}{existing.data}"
                else:
                    existing.data = marker
                existing.last_translated_by = user
                existing.translation_type = StringTranslation.TRANSLATION_TYPE_MANUAL
                to_update.append(existing)
            else:
                to_create.append(
                    StringTranslation(
                        translation_of=segment.string,
                        locale=translation.target_locale,
                        context=segment.context,
                        data=marker,
                        translation_type=StringTranslation.TRANSLATION_TYPE_MANUAL,
                        last_translated_by=user,
                    )
                )

        # Batch operations - 2 queries total instead of 2*N
        created_count = 0
        updated_count = 0

        if to_create:
            # Perform bulk create
            StringTranslation.objects.bulk_create(to_create, batch_size=500)
            created_count = len(to_create)
            logger.info(f"Bulk created {created_count} StringTranslations")

            # Manually trigger post_save signals since bulk_create doesn't trigger them
            for st in to_create:
                post_save.send(
                    sender=StringTranslation,
                    instance=st,
                    created=True,
                    update_fields=None,
                    raw=False,
                )

        if to_update:
            # Perform bulk update
            StringTranslation.objects.bulk_update(
                to_update,
                ["data", "last_translated_by", "translation_type"],
                batch_size=500,
            )
            updated_count = len(to_update)
            logger.info(f"Bulk updated {updated_count} StringTranslations")

            # Manually trigger post_save signals since bulk_update doesn't trigger them
            for st in to_update:
                post_save.send(
                    sender=StringTranslation,
                    instance=st,
                    created=False,
                    update_fields=["data", "last_translated_by", "translation_type"],
                    raw=False,
                )

        return created_count + updated_count


def bulk_unmark_segments(translation, segments):
    """
    Unmark multiple segments from "do not translate" using optimized batch operations.

    This function uses bulk operations to minimize database queries, making it
    much faster than unmarking segments one by one.

    Note: This function manually triggers post_save signals for updated StringTranslations
    to ensure other parts of the system (like wagtail-localize) are notified of changes.
    The delete() method automatically triggers pre_delete and post_delete signals.

    Args:
        translation: Translation instance
        segments: Iterable of StringSegment instances

    Returns:
        tuple: (affected_count: int, segment_data: dict)
            - affected_count: Number of segments unmarked
            - segment_data: Dict mapping segment IDs to their data (translated_value, source_value)

    Example:
        >>> segments = StringSegment.objects.filter(source=source)
        >>> count, data = bulk_unmark_segments(translation, segments)
        >>> print(f"Unmarked {count} segments")
    """
    validate_configuration()
    marker = get_marker()
    backup_separator = get_backup_separator()

    with transaction.atomic():
        # Convert to list if needed and filter out segments without strings
        segments = [s for s in segments if s.string_id]

        if not segments:
            return 0, {}

        # Build lookup: string_id -> segment for quick access
        string_to_segment = {s.string_id: s for s in segments}

        # Fetch all relevant translations once - single query
        string_ids = [s.string_id for s in segments]
        marked_translations = (
            StringTranslation.objects.filter(
                translation_of_id__in=string_ids, locale=translation.target_locale
            )
            .filter(Q(data=marker) | Q(data__startswith=marker + backup_separator))
            .select_related("translation_of", "context")
        )

        to_delete = []
        to_update = []
        segment_data = {}

        for st in marked_translations:
            segment = string_to_segment.get(st.translation_of_id)
            if not segment:
                continue

            # Check if has backup
            if st.data.startswith(marker + backup_separator):
                # Extract backup data
                parts = st.data.split(backup_separator, 1)
                if len(parts) > 1:
                    backup_data = parts[1]
                    st.data = backup_data
                    to_update.append(st)
                    segment_data[segment.id] = {
                        "translated_value": backup_data,
                        "source_value": segment.string.data if segment.string else "",
                    }
                else:
                    # Malformed backup, delete it
                    to_delete.append(st.id)
                    segment_data[segment.id] = {
                        "translated_value": None,
                        "source_value": segment.string.data if segment.string else "",
                    }
            else:
                # No backup, delete the marker
                to_delete.append(st.id)
                segment_data[segment.id] = {
                    "translated_value": None,
                    "source_value": segment.string.data if segment.string else "",
                }

        # Batch operations - 2 queries instead of 3*N
        deleted_count = 0
        updated_count = 0

        if to_delete:
            # delete() triggers pre_delete and post_delete signals automatically
            deleted_count, _ = marked_translations.filter(id__in=to_delete).delete()
            logger.info(f"Bulk deleted {deleted_count} StringTranslations")

        if to_update:
            # Perform bulk update
            StringTranslation.objects.bulk_update(to_update, ["data"], batch_size=500)
            updated_count = len(to_update)
            logger.info(f"Bulk updated {updated_count} StringTranslations")

            # Manually trigger post_save signals since bulk_update doesn't trigger them
            for st in to_update:
                post_save.send(
                    sender=StringTranslation,
                    instance=st,
                    created=False,
                    update_fields=["data"],
                    raw=False,
                )

        return deleted_count + updated_count, segment_data


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
    string_ids = StringSegment.objects.filter(source=translation.source).values_list(
        "string_id", flat=True
    )

    # Find translations marked as "do not translate" (match both exact marker and encoded backup format)
    marked_string_translations = StringTranslation.objects.filter(
        locale=translation.target_locale, translation_of_id__in=string_ids
    ).filter(Q(data=marker) | Q(data__startswith=marker + backup_separator))

    # Get the string IDs of marked translations
    marked_string_ids = marked_string_translations.values_list(
        "translation_of_id", flat=True
    )

    # Return the segments that have these marked strings
    return StringSegment.objects.filter(
        source=translation.source, string_id__in=marked_string_ids
    )


def migrate_do_not_translate_markers(translation_source, target_locale):
    """
    Migrate "Do Not Translate" markers when source Strings change.

    When the source page content changes, wagtail-localize creates new String
    objects. This function finds StringTranslation records with the marker that
    point to old Strings and updates them to point to the current Strings based
    on matching context paths.

    This ensures that "Do Not Translate" markings persist across sync operations.

    Args:
        translation_source: TranslationSource instance
        target_locale: Target Locale instance

    Returns:
        int: Number of StringTranslation records migrated

    Example:
        >>> from wagtail_localize.models import TranslationSource, Locale
        >>> source = TranslationSource.objects.get(id=123)
        >>> locale = Locale.objects.get(language_code='fr')
        >>> count = migrate_do_not_translate_markers(source, locale)
        >>> print(f"Migrated {count} markers")
    """
    validate_configuration()
    marker = get_marker()
    backup_separator = get_backup_separator()

    # Get all current StringSegments for this source
    current_segments = StringSegment.objects.filter(
        source=translation_source
    ).select_related("string", "context")

    migrated_count = 0

    # For each current segment, check if there's an old marker to migrate
    for segment in current_segments:
        # Find orphanzed markers - these are StringTranslations with the marker
        # for this context+locale that DON'T point to the current String.
        orphaned_markers = (
            StringTranslation.objects.filter(
                locale=target_locale,
                context=segment.context,
            )
            .filter(Q(data=marker) | Q(data__startswith=marker + backup_separator))
            .exclude(translation_of=segment.string)
        )

        # If we found orphaned markers, migrate them to the current String
        for orphaned_marker in orphaned_markers:
            old_string_id = orphaned_marker.translation_of_id
            logger.info(
                f"Migrating marker: context='{segment.context}', "
                f"old_string_id={old_string_id} -> new_string_id={segment.string.id}, "
                f"locale={target_locale}"
            )

            # Check if there's already a StringTranslation for the new String
            # (this can happen if wagtail-localize created one during sync)
            existing_for_new_string = StringTranslation.objects.filter(
                translation_of=segment.string,
                locale=target_locale,
                context=segment.context,
            ).exclude(id=orphaned_marker.id)

            if existing_for_new_string.exists():
                # Delete the existing one to avoid unique constraint violation
                logger.info(
                    f"Deleting existing StringTranslation for new String "
                    f"to avoid conflict: {existing_for_new_string.first().id}"
                )
                existing_for_new_string.delete()

            # Update the StringTranslation to point to the new String
            orphaned_marker.translation_of = segment.string
            orphaned_marker.save()

            migrated_count += 1

    if migrated_count > 0:
        logger.info(
            f"Migrated {migrated_count} 'Do Not Translate' markers for source {translation_source.id} to locale {target_locale}"
        )

    return migrated_count
