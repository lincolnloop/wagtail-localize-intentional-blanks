"""
Unit tests for utils module.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

import pytest
from wagtail.models import Locale, Page
from wagtail_localize.models import (
    String,
    StringSegment,
    StringTranslation,
    Translation,
    TranslationContext,
    TranslationSource,
)
from wagtail_localize_intentional_blanks.constants import (
    BACKUP_SEPARATOR,
    DO_NOT_TRANSLATE_MARKER,
)
from wagtail_localize_intentional_blanks.utils import (
    bulk_mark_segments,
    get_marker,
    get_segments_do_not_translate,
    get_source_fallback_stats,
    is_do_not_translate,
    mark_segment_do_not_translate,
    migrate_do_not_translate_markers,
    unmark_segment_do_not_translate,
    validate_configuration,
)

User = get_user_model()


@pytest.mark.django_db
class TestUtilsFunctions(TestCase):
    """Test utility functions."""

    def setUp(self):
        """Set up test data."""
        # Create locales
        self.source_locale = Locale.objects.get_or_create(
            language_code="en", defaults={"language_code": "en"}
        )[0]
        self.target_locale = Locale.objects.get_or_create(
            language_code="fr", defaults={"language_code": "fr"}
        )[0]

        # Create a test user
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create a root page
        self.root_page = Page.objects.filter(depth=1).first()
        if not self.root_page:
            self.root_page = Page.add_root(title="Root", slug="root")

        # Create a test page
        self.page = Page(title="Test Page", slug="test-page", locale=self.source_locale)
        self.root_page.add_child(instance=self.page)

        # Create translation source using the proper wagtail-localize API
        self.source, created = TranslationSource.get_or_create_from_instance(self.page)

        # Use the first segment that was automatically created
        self.segment = StringSegment.objects.filter(source=self.source).first()
        if not self.segment:
            # If no segments exist, create a minimal one with proper context
            context_obj, _ = TranslationContext.objects.get_or_create(
                path="test.field", defaults={"object": self.source.object}
            )
            self.string = String.objects.create(
                data="Test string",
                locale=self.source_locale,
            )
            self.segment = StringSegment.objects.create(
                source=self.source,
                string=self.string,
                context=context_obj,
                order=0,
            )
        else:
            self.string = self.segment.string

        # Create translation
        self.translation = Translation.objects.create(
            source=self.source,
            target_locale=self.target_locale,
        )

    def test_get_marker(self):
        """Test get_marker returns the correct marker."""
        marker = get_marker()
        assert marker == DO_NOT_TRANSLATE_MARKER

    def test_mark_segment_do_not_translate_creates_translation(self):
        """Test marking a segment creates a StringTranslation."""
        result = mark_segment_do_not_translate(
            self.translation, self.segment, user=self.user
        )

        assert result is not None
        assert isinstance(result, StringTranslation)
        assert result.data == DO_NOT_TRANSLATE_MARKER
        assert result.locale == self.target_locale
        assert result.translation_of == self.string
        assert result.last_translated_by == self.user

    def test_mark_segment_do_not_translate_without_user(self):
        """Test marking a segment without providing user."""
        result = mark_segment_do_not_translate(self.translation, self.segment)

        assert result is not None
        assert result.data == DO_NOT_TRANSLATE_MARKER
        assert result.last_translated_by is None

    def test_mark_segment_do_not_translate_updates_existing(self):
        """Test marking a segment updates existing translation and encodes backup."""
        # Create initial translation with different data
        StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data="Original translation",
        )

        result = mark_segment_do_not_translate(
            self.translation, self.segment, user=self.user
        )

        # Should encode the backup in the data field
        assert (
            result.data
            == f"{DO_NOT_TRANSLATE_MARKER}{BACKUP_SEPARATOR}Original translation"
        )
        # Should only have one translation
        count = StringTranslation.objects.filter(
            translation_of=self.string,
            locale=self.target_locale,
        ).count()
        assert count == 1

    def test_unmark_segment_do_not_translate_without_backup(self):
        """Test unmarking a segment without backup deletes it."""
        # First mark it (no existing translation, so no backup)
        mark_segment_do_not_translate(self.translation, self.segment)

        # Verify it exists
        assert StringTranslation.objects.filter(
            translation_of=self.string,
            locale=self.target_locale,
            data=DO_NOT_TRANSLATE_MARKER,
        ).exists()

        # Unmark it
        result = unmark_segment_do_not_translate(self.translation, self.segment)

        # Should return 1 (deleted)
        assert result == 1
        # Verify it's removed
        assert not StringTranslation.objects.filter(
            translation_of=self.string, locale=self.target_locale
        ).exists()

    def test_unmark_segment_do_not_translate_with_backup(self):
        """Test unmarking a segment with backup restores the original."""
        # Create initial translation
        StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data="Original translation",
        )

        # Mark it (should encode backup)
        mark_segment_do_not_translate(self.translation, self.segment)

        # Verify it has encoded backup
        st = StringTranslation.objects.get(
            translation_of=self.string, locale=self.target_locale
        )
        assert (
            st.data
            == f"{DO_NOT_TRANSLATE_MARKER}{BACKUP_SEPARATOR}Original translation"
        )

        # Unmark it
        result = unmark_segment_do_not_translate(self.translation, self.segment)

        # Should return 1 (updated)
        assert result == 1
        # Verify it restored the backup
        st = StringTranslation.objects.get(
            translation_of=self.string, locale=self.target_locale
        )
        assert st.data == "Original translation"

    def test_unmark_segment_does_nothing_if_not_marked(self):
        """Test unmarking a segment that isn't marked doesn't raise error."""
        # Should not raise any exception
        unmark_segment_do_not_translate(self.translation, self.segment)

    def test_is_do_not_translate_returns_true(self):
        """Test is_do_not_translate returns True for marked segments."""
        string_translation = mark_segment_do_not_translate(
            self.translation, self.segment
        )

        assert is_do_not_translate(string_translation) is True

    def test_is_do_not_translate_returns_true_with_backup(self):
        """Test is_do_not_translate returns True for marked segments with encoded backup."""
        # Create existing translation first
        StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data="Original translation",
        )

        string_translation = mark_segment_do_not_translate(
            self.translation, self.segment
        )

        # Should still be recognized as do not translate even with encoded backup
        assert is_do_not_translate(string_translation) is True
        assert string_translation.data.startswith(DO_NOT_TRANSLATE_MARKER)

    def test_is_do_not_translate_returns_false(self):
        """Test is_do_not_translate returns False for normal translations."""
        string_translation = StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data="Normal translation",
        )

        assert is_do_not_translate(string_translation) is False

    def test_get_source_fallback_stats_all_marked(self):
        """Test get_source_fallback_stats when all segments are marked."""
        # Create and mark segments
        for i in range(3):
            string = String.objects.create(
                data=f"Test string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.field_{i}", defaults={"object": self.source.object}
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            mark_segment_do_not_translate(self.translation, segment)

        stats = get_source_fallback_stats(self.translation)

        assert stats["total"] == 3
        assert stats["do_not_translate"] == 3
        assert stats["manually_translated"] == 0

    def test_get_source_fallback_stats_mixed(self):
        """Test get_source_fallback_stats with mixed translations."""
        # Create segments
        segments = []
        for i in range(5):
            string = String.objects.create(
                data=f"Test string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.mixed_field_{i}", defaults={"object": self.source.object}
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)

        # Mark 2 as do not translate
        mark_segment_do_not_translate(self.translation, segments[0])
        mark_segment_do_not_translate(self.translation, segments[1])

        # Translate 3 manually
        for i in range(2, 5):
            StringTranslation.objects.create(
                translation_of=segments[i].string,
                locale=self.target_locale,
                context=segments[i].context,
                data=f"Translation {i}",
            )

        stats = get_source_fallback_stats(self.translation)

        assert stats["total"] == 5
        assert stats["do_not_translate"] == 2
        assert stats["manually_translated"] == 3

    def test_get_source_fallback_stats_no_translations(self):
        """Test get_source_fallback_stats with no translations."""
        stats = get_source_fallback_stats(self.translation)

        assert stats["total"] == 0
        assert stats["do_not_translate"] == 0
        assert stats["manually_translated"] == 0

    def test_bulk_mark_segments(self):
        """Test bulk_mark_segments marks multiple segments."""
        # Create segments
        segments = []
        for i in range(5):
            string = String.objects.create(
                data=f"Test string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_field_{i}", defaults={"object": self.source.object}
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)

        # Bulk mark
        count = bulk_mark_segments(self.translation, segments, user=self.user)

        assert count == 5

        # Verify all are marked
        for segment in segments:
            st = StringTranslation.objects.get(
                translation_of=segment.string, locale=self.target_locale
            )
            assert st.data == DO_NOT_TRANSLATE_MARKER
            assert st.last_translated_by == self.user

    def test_bulk_mark_segments_empty_list(self):
        """Test bulk_mark_segments with empty list."""
        count = bulk_mark_segments(self.translation, [], user=self.user)
        assert count == 0

    def test_get_segments_do_not_translate(self):
        """Test get_segments_do_not_translate returns marked segments."""
        # Create segments
        marked_segments = []
        unmarked_segments = []

        for i in range(3):
            string = String.objects.create(
                data=f"Marked string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.marked_{i}", defaults={"object": self.source.object}
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            mark_segment_do_not_translate(self.translation, segment)
            marked_segments.append(segment)

        for i in range(2):
            string = String.objects.create(
                data=f"Unmarked string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.unmarked_{i}", defaults={"object": self.source.object}
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 10,
            )
            StringTranslation.objects.create(
                translation_of=string,
                locale=self.target_locale,
                context=context_obj,
                data=f"Translation {i}",
            )
            unmarked_segments.append(segment)

        # Get marked segments
        result = get_segments_do_not_translate(self.translation)

        assert result.count() == 3
        for segment in marked_segments:
            assert segment in result
        for segment in unmarked_segments:
            assert segment not in result

    def test_get_segments_do_not_translate_empty(self):
        """Test get_segments_do_not_translate with no marked segments."""
        result = get_segments_do_not_translate(self.translation)
        assert result.count() == 0

    def test_migrate_do_not_translate_markers_updates_orphaned_markers(self):
        """Test that migrate_do_not_translate_markers updates orphaned markers to new Strings."""
        # Create initial String and mark as Do Not Translate
        old_string = String.objects.create(data="Old Value", locale=self.source_locale)
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.migrate_field", defaults={"object": self.source.object}
        )
        segment = StringSegment.objects.create(
            source=self.source,
            string=old_string,
            context=context_obj,
            order=0,
            attrs="{}",
        )

        mark_segment_do_not_translate(self.translation, segment)

        # Verify marker is stored
        old_st = StringTranslation.objects.get(
            translation_of=old_string, locale=self.target_locale, context=context_obj
        )
        assert old_st.data == DO_NOT_TRANSLATE_MARKER

        # Simulate source change: create new String and update segment
        new_string = String.objects.create(data="New Value", locale=self.source_locale)
        segment.string = new_string
        segment.save()

        # Call migration
        count = migrate_do_not_translate_markers(self.source, self.target_locale)

        # Verify migration happened
        assert count == 1, "Should have migrated 1 marker"

        # Verify the StringTranslation now points to new String
        new_st = StringTranslation.objects.get(
            translation_of=new_string, locale=self.target_locale, context=context_obj
        )
        assert new_st.data == DO_NOT_TRANSLATE_MARKER
        assert new_st.id == old_st.id, "Should be same record, updated"

        # Verify no orphaned markers left
        orphaned = StringTranslation.objects.filter(
            translation_of=old_string, locale=self.target_locale
        )
        assert orphaned.count() == 0

    def test_migrate_do_not_translate_markers_preserves_backup(self):
        """Test that migration preserves encoded backup in marker."""
        # Create String with translation, then mark as Do Not Translate
        old_string = String.objects.create(data="Original", locale=self.source_locale)
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.migrate_backup_field", defaults={"object": self.source.object}
        )

        # Create existing translation
        StringTranslation.objects.create(
            translation_of=old_string,
            locale=self.target_locale,
            context=context_obj,
            data="French Translation",
        )

        segment = StringSegment.objects.create(
            source=self.source,
            string=old_string,
            context=context_obj,
            order=0,
            attrs="{}",
        )

        # Mark as Do Not Translate (should encode backup)
        mark_segment_do_not_translate(self.translation, segment)

        # Verify backup is encoded
        old_st = StringTranslation.objects.get(
            translation_of=old_string, locale=self.target_locale, context=context_obj
        )
        expected = f"{DO_NOT_TRANSLATE_MARKER}{BACKUP_SEPARATOR}French Translation"
        assert old_st.data == expected

        # Update to new String
        new_string = String.objects.create(data="Updated", locale=self.source_locale)
        segment.string = new_string
        segment.save()

        # Migrate
        count = migrate_do_not_translate_markers(self.source, self.target_locale)
        assert count == 1

        # Verify backup is preserved
        new_st = StringTranslation.objects.get(
            translation_of=new_string, locale=self.target_locale, context=context_obj
        )
        assert new_st.data == expected, "Backup should be preserved in migrated marker"

    def test_migrate_do_not_translate_markers_handles_multiple_contexts(self):
        """Test that migration correctly handles multiple segments with different contexts."""
        # Create two segments with different contexts
        string1 = String.objects.create(data="Value 1", locale=self.source_locale)
        string2 = String.objects.create(data="Value 2", locale=self.source_locale)

        context1, _ = TranslationContext.objects.get_or_create(
            path="test.field1", defaults={"object": self.source.object}
        )
        context2, _ = TranslationContext.objects.get_or_create(
            path="test.field2", defaults={"object": self.source.object}
        )

        segment1 = StringSegment.objects.create(
            source=self.source, string=string1, context=context1, order=0, attrs="{}"
        )
        segment2 = StringSegment.objects.create(
            source=self.source, string=string2, context=context2, order=1, attrs="{}"
        )

        # Mark both as Do Not Translate
        mark_segment_do_not_translate(self.translation, segment1)
        mark_segment_do_not_translate(self.translation, segment2)

        # Update both strings
        new_string1 = String.objects.create(
            data="New Value 1", locale=self.source_locale
        )
        new_string2 = String.objects.create(
            data="New Value 2", locale=self.source_locale
        )

        segment1.string = new_string1
        segment1.save()
        segment2.string = new_string2
        segment2.save()

        # Migrate
        count = migrate_do_not_translate_markers(self.source, self.target_locale)
        assert count == 2, "Should migrate both markers"

        # Verify both markers migrated correctly
        st1 = StringTranslation.objects.get(
            translation_of=new_string1, locale=self.target_locale, context=context1
        )
        st2 = StringTranslation.objects.get(
            translation_of=new_string2, locale=self.target_locale, context=context2
        )

        assert st1.data == DO_NOT_TRANSLATE_MARKER
        assert st2.data == DO_NOT_TRANSLATE_MARKER

    def test_migrate_do_not_translate_markers_ignores_current_markers(self):
        """Test that migration doesn't affect markers that already point to current Strings."""
        # Create String and mark as Do Not Translate
        string = String.objects.create(data="Current Value", locale=self.source_locale)
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.current_field", defaults={"object": self.source.object}
        )
        segment = StringSegment.objects.create(
            source=self.source, string=string, context=context_obj, order=0, attrs="{}"
        )

        mark_segment_do_not_translate(self.translation, segment)

        # Don't change the String - migration should find nothing to migrate
        count = migrate_do_not_translate_markers(self.source, self.target_locale)
        assert count == 0, "Should not migrate markers that are already current"

        # Verify marker is still there and unchanged
        st = StringTranslation.objects.get(
            translation_of=string, locale=self.target_locale, context=context_obj
        )
        assert st.data == DO_NOT_TRANSLATE_MARKER

    def test_migrate_do_not_translate_markers_handles_conflict(self):
        """
        Test that migration handles the case where a StringTranslation already exists for the new String.

        This simulates what happens during wagtail-localize sync, where new StringTranslation
        records are created for new Strings, which would conflict with our migration.
        """
        # Create initial String and mark as Do Not Translate
        old_string = String.objects.create(data="Old Value", locale=self.source_locale)
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.conflict_field", defaults={"object": self.source.object}
        )
        segment = StringSegment.objects.create(
            source=self.source,
            string=old_string,
            context=context_obj,
            order=0,
            attrs="{}",
        )

        mark_segment_do_not_translate(self.translation, segment)

        # Get the marker StringTranslation
        marker_st = StringTranslation.objects.get(
            translation_of=old_string, locale=self.target_locale, context=context_obj
        )
        assert marker_st.data == DO_NOT_TRANSLATE_MARKER

        # Simulate source change: create new String and update segment
        new_string = String.objects.create(data="New Value", locale=self.source_locale)
        segment.string = new_string
        segment.save()

        # Simulate wagtail-localize creating a new StringTranslation for the new String
        # (this is what causes the unique constraint conflict)
        conflicting_st = StringTranslation.objects.create(
            translation_of=new_string,
            locale=self.target_locale,
            context=context_obj,
            data="Some translation",  # Not a marker
            translation_type=StringTranslation.TRANSLATION_TYPE_MACHINE,
        )

        # Call migration - should handle the conflict by deleting the conflicting record
        count = migrate_do_not_translate_markers(self.source, self.target_locale)
        assert count == 1, "Should have migrated 1 marker"

        # Verify the marker was migrated successfully
        migrated_st = StringTranslation.objects.get(
            translation_of=new_string, locale=self.target_locale, context=context_obj
        )
        assert migrated_st.data == DO_NOT_TRANSLATE_MARKER
        assert migrated_st.id == marker_st.id, "Should be the same record, updated"

        # Verify the conflicting record was deleted
        assert not StringTranslation.objects.filter(id=conflicting_st.id).exists()

        # Verify no orphaned markers remain
        orphaned = StringTranslation.objects.filter(
            translation_of=old_string, locale=self.target_locale
        )
        assert orphaned.count() == 0


@pytest.mark.django_db
class TestValidateConfiguration(TestCase):
    """Test configuration validation."""

    def test_validate_configuration_with_valid_settings(self):
        """Test that validate_configuration passes with valid default settings."""
        # Should not raise any exception
        validate_configuration()

    @override_settings(WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_MARKER=None)
    def test_validate_configuration_raises_when_marker_is_none(self):
        """Test that validate_configuration raises ValueError when MARKER is None."""
        with pytest.raises(ValueError) as exc_info:
            validate_configuration()

        assert (
            "WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_MARKER must be set to a non-empty string"
            in str(exc_info.value)
        )

    @override_settings(WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_MARKER="")
    def test_validate_configuration_raises_when_marker_is_empty(self):
        """Test that validate_configuration raises ValueError when MARKER is empty string."""
        with pytest.raises(ValueError) as exc_info:
            validate_configuration()

        assert (
            "WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_MARKER must be set to a non-empty string"
            in str(exc_info.value)
        )

    @override_settings(WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_BACKUP_SEPARATOR=None)
    def test_validate_configuration_raises_when_backup_separator_is_none(self):
        """Test that validate_configuration raises ValueError when BACKUP_SEPARATOR is None."""
        with pytest.raises(ValueError) as exc_info:
            validate_configuration()

        assert (
            "WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_BACKUP_SEPARATOR must be set to a non-empty string"
            in str(exc_info.value)
        )

    @override_settings(WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_BACKUP_SEPARATOR="")
    def test_validate_configuration_raises_when_backup_separator_is_empty(self):
        """Test that validate_configuration raises ValueError when BACKUP_SEPARATOR is empty string."""
        with pytest.raises(ValueError) as exc_info:
            validate_configuration()

        assert (
            "WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_BACKUP_SEPARATOR must be set to a non-empty string"
            in str(exc_info.value)
        )
