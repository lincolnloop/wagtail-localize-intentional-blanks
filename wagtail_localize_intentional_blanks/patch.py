"""
Monkey-patch for wagtail-localize to support intentional blanks.

This patches TranslationSource._get_segments_for_translation() to check for
the __DO_NOT_TRANSLATE__ marker and use source values instead of translations
when the marker is present.
"""

import json
import logging

from wagtail_localize.models import TranslationSource
from wagtail_localize.segments import (
    OverridableSegmentValue,
    RelatedObjectSegmentValue,
    StringSegmentValue,
    TemplateSegmentValue,
)
from wagtail_localize.strings import StringValue

from .constants import get_setting

logger = logging.getLogger(__name__)

# Store the original method so we can call it if needed
_original_get_segments_for_translation = TranslationSource._get_segments_for_translation


def _get_segments_for_translation_with_intentional_blanks(self, locale, fallback=False):
    """
    Enhanced version of _get_segments_for_translation that handles intentional blanks.

    When a StringTranslation contains the __DO_NOT_TRANSLATE__ marker, this method
    uses the source value instead, allowing translators to mark segments as
    "do not translate" while still completing the translation.

    This works correctly for all field types including multi-segment RichTextField.
    """
    if not get_setting("ENABLED"):
        # Feature disabled, use original implementation
        return _original_get_segments_for_translation(self, locale, fallback)

    marker = get_setting("MARKER")
    backup_separator = get_setting("BACKUP_SEPARATOR")

    # Import here to avoid circular imports
    from wagtail_localize.models import MissingTranslationError, StringSegment

    string_segments = (
        StringSegment.objects.filter(source=self)
        .annotate_translation(locale)
        .select_related("context", "string")
    )

    segments = []

    for string_segment in string_segments:
        if string_segment.translation:
            # Check if this translation is marked as "do not translate"
            translation_data = string_segment.translation

            # Check for marker (exact match or with encoded backup)
            if translation_data == marker or translation_data.startswith(
                marker + backup_separator
            ):
                # Use source value instead of translation
                logger.debug(
                    f"Intentional blank detected for segment {string_segment.string_id} in locale {locale}, using source value"
                )
                string = StringValue(string_segment.string.data)
            else:
                # Use the translated value
                string = StringValue(translation_data)
        elif fallback:
            string = StringValue(string_segment.string.data)
        else:
            raise MissingTranslationError(string_segment, locale)

        segment_value = StringSegmentValue(
            string_segment.context.path,
            string,
            attrs=json.loads(string_segment.attrs),
        ).with_order(string_segment.order)

        segments.append(segment_value)

    # Handle template segments (templates are locale-independent)
    template_segments = self.templatesegment_set.all().select_related("template")
    for template_segment in template_segments:
        segment_value = TemplateSegmentValue(
            template_segment.context.path,
            template_segment.template.template_format,
            template_segment.template.template,
            template_segment.template.string_count,
        ).with_order(template_segment.order)

        segments.append(segment_value)

    # Handle related object segments
    related_object_segments = self.relatedobjectsegment_set.all().select_related(
        "object"
    )
    for related_object_segment in related_object_segments:
        try:
            instance = related_object_segment.object.get_instance(locale)
        except related_object_segment.object.content_type.model_class().DoesNotExist:
            if fallback:
                instance = related_object_segment.object.get_instance(self.locale)
            else:
                raise

        segment_value = RelatedObjectSegmentValue(
            related_object_segment.context.path,
            related_object_segment.object.content_type,
            instance.pk,
        ).with_order(related_object_segment.order)

        segments.append(segment_value)

    # Handle overridable segments (no locale filter needed - they're source-specific)
    overridable_segments = self.overridablesegment_set.all().select_related("context")
    for overridable_segment in overridable_segments:
        segment_value = OverridableSegmentValue(
            overridable_segment.context.path,
            overridable_segment.data_json,  # Use data_json field
        ).with_order(overridable_segment.order)

        segments.append(segment_value)

    return segments


def apply_patch():
    """
    Apply the monkey-patch to TranslationSource.

    This should be called from the app's ready() method.
    """
    TranslationSource._get_segments_for_translation = (
        _get_segments_for_translation_with_intentional_blanks
    )

    # Also patch update_from_db to migrate markers after syncing translated pages.
    # If a user 1. marks a field as 'Do Not Translate', then 2. updates the
    # source field value, then 3. clicks 'Sync translated pages', we want to
    # make sure that the field remains marked as 'Do Not Translate'.
    _patch_update_from_db()


# Store the original update_from_db method
_original_update_from_db = TranslationSource.update_from_db


def _update_from_db_with_marker_migration(self):
    """
    Enhanced version of update_from_db that migrates markers after updating.

    This ensures that when source content changes and is synced, any 'Do Not Translate'
    markers are automatically migrated to the new Strings.
    """
    # Call the original method to perform the update
    result = _original_update_from_db(self)

    if not get_setting("ENABLED"):
        return result

    # After updating, migrate any orphaned markers for all target locales
    from wagtail_localize.models import Translation

    from .utils import migrate_do_not_translate_markers

    translations = Translation.objects.filter(source=self)

    for translation in translations:
        migrate_do_not_translate_markers(self, translation.target_locale)

    return result


def _patch_update_from_db():
    """Patch the update_from_db method to migrate markers after sync."""
    TranslationSource.update_from_db = _update_from_db_with_marker_migration
