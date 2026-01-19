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
from unittest.mock import Mock

from django.db.models.signals import post_save

from wagtail_localize_intentional_blanks.utils import (
    bulk_mark_segments,
    bulk_unmark_segments,
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

    def test_bulk_unmark_segments_without_backups(self):
        """Test bulk_unmark_segments deletes segments without backups."""
        # Create segments and mark them (no existing translations, so no backups)
        segments = []
        for i in range(5):
            string = String.objects.create(
                data=f"Test string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_field_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)
            mark_segment_do_not_translate(self.translation, segment)

        # Verify all are marked
        for segment in segments:
            assert StringTranslation.objects.filter(
                translation_of=segment.string,
                locale=self.target_locale,
                data=DO_NOT_TRANSLATE_MARKER,
            ).exists()

        # Bulk unmark
        count, segment_data = bulk_unmark_segments(self.translation, segments)

        assert count == 5, "Should have unmarked 5 segments"
        assert len(segment_data) == 5, "Should have data for 5 segments"

        # Verify all are unmarked (deleted)
        for segment in segments:
            assert not StringTranslation.objects.filter(
                translation_of=segment.string, locale=self.target_locale
            ).exists()
            # Check segment_data structure
            assert segment.id in segment_data
            assert segment_data[segment.id]["translated_value"] is None
            assert segment_data[segment.id]["source_value"] == segment.string.data

    def test_bulk_unmark_segments_with_backups(self):
        """Test bulk_unmark_segments restores segments with backups."""
        # Create segments with existing translations, then mark them
        segments = []
        original_translations = {}
        for i in range(5):
            string = String.objects.create(
                data=f"Test string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_backup_field_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)

            # Create existing translation first
            original_translation = f"Original translation {i}"
            original_translations[segment.id] = original_translation
            StringTranslation.objects.create(
                translation_of=string,
                locale=self.target_locale,
                context=context_obj,
                data=original_translation,
            )

            # Mark as do not translate (should encode backup)
            mark_segment_do_not_translate(self.translation, segment)

        # Verify all have encoded backups
        for segment in segments:
            st = StringTranslation.objects.get(
                translation_of=segment.string, locale=self.target_locale
            )
            expected = f"{DO_NOT_TRANSLATE_MARKER}{BACKUP_SEPARATOR}{original_translations[segment.id]}"
            assert st.data == expected

        # Bulk unmark
        count, segment_data = bulk_unmark_segments(self.translation, segments)

        assert count == 5, "Should have unmarked 5 segments"
        assert len(segment_data) == 5, "Should have data for 5 segments"

        # Verify all backups are restored
        for segment in segments:
            st = StringTranslation.objects.get(
                translation_of=segment.string, locale=self.target_locale
            )
            assert st.data == original_translations[segment.id]
            # Check segment_data structure
            assert segment.id in segment_data
            assert (
                segment_data[segment.id]["translated_value"]
                == original_translations[segment.id]
            )
            assert segment_data[segment.id]["source_value"] == segment.string.data

    def test_bulk_unmark_segments_mixed(self):
        """Test bulk_unmark_segments with a mix of segments with and without backups."""
        segments = []
        segments_with_backup = []
        segments_without_backup = []
        backup_data = {}

        # Create 3 segments with backups
        for i in range(3):
            string = String.objects.create(
                data=f"String with backup {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_mixed_backup_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)
            segments_with_backup.append(segment)

            # Create existing translation
            original = f"Backup translation {i}"
            backup_data[segment.id] = original
            StringTranslation.objects.create(
                translation_of=string,
                locale=self.target_locale,
                context=context_obj,
                data=original,
            )
            mark_segment_do_not_translate(self.translation, segment)

        # Create 2 segments without backups
        for i in range(2):
            string = String.objects.create(
                data=f"String without backup {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_mixed_no_backup_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 10,
            )
            segments.append(segment)
            segments_without_backup.append(segment)
            mark_segment_do_not_translate(self.translation, segment)

        # Bulk unmark all
        count, segment_data = bulk_unmark_segments(self.translation, segments)

        assert count == 5, "Should have unmarked 5 segments"
        assert len(segment_data) == 5, "Should have data for 5 segments"

        # Verify segments with backups are restored
        for segment in segments_with_backup:
            st = StringTranslation.objects.get(
                translation_of=segment.string, locale=self.target_locale
            )
            assert st.data == backup_data[segment.id]
            assert (
                segment_data[segment.id]["translated_value"] == backup_data[segment.id]
            )

        # Verify segments without backups are deleted
        for segment in segments_without_backup:
            assert not StringTranslation.objects.filter(
                translation_of=segment.string, locale=self.target_locale
            ).exists()
            assert segment_data[segment.id]["translated_value"] is None

    def test_bulk_unmark_segments_empty_list(self):
        """Test bulk_unmark_segments with empty list."""
        count, segment_data = bulk_unmark_segments(self.translation, [])
        assert count == 0
        assert segment_data == {}

    def test_bulk_unmark_segments_not_marked(self):
        """Test bulk_unmark_segments with segments that aren't marked."""
        # Create segments without marking them
        segments = []
        for i in range(3):
            string = String.objects.create(
                data=f"Unmarked string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_not_marked_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)

            # Create regular translation (not marked)
            StringTranslation.objects.create(
                translation_of=string,
                locale=self.target_locale,
                context=context_obj,
                data=f"Regular translation {i}",
            )

        # Try to bulk unmark - should do nothing
        count, segment_data = bulk_unmark_segments(self.translation, segments)

        assert count == 0, "Should not unmark any segments"
        assert segment_data == {}, "Should have no segment data"

        # Verify translations are unchanged
        for i, segment in enumerate(segments):
            st = StringTranslation.objects.get(
                translation_of=segment.string, locale=self.target_locale
            )
            assert st.data == f"Regular translation {i}"

    def test_bulk_unmark_segments_partial_marked(self):
        """Test bulk_unmark_segments when only some segments are marked."""
        segments = []
        marked_segments = []

        # Create 3 marked segments
        for i in range(3):
            string = String.objects.create(
                data=f"Marked string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_partial_marked_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)
            marked_segments.append(segment)
            mark_segment_do_not_translate(self.translation, segment)

        # Create 2 unmarked segments
        for i in range(2):
            string = String.objects.create(
                data=f"Unmarked string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_partial_unmarked_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 10,
            )
            segments.append(segment)

        # Bulk unmark all (should only affect marked ones)
        count, segment_data = bulk_unmark_segments(self.translation, segments)

        assert count == 3, "Should have unmarked only 3 marked segments"
        assert len(segment_data) == 3, "Should have data for 3 segments"

        # Verify only marked segments were affected
        for segment in marked_segments:
            assert segment.id in segment_data

    def test_bulk_unmark_segments_query_efficiency(self):
        """Test that bulk_unmark_segments uses efficient bulk operations."""
        # Create 7 segments with backups (will be updated)
        num_updates = 7
        num_deletes = 7
        segments = []
        for i in range(num_updates):
            string = String.objects.create(
                data=f"String with backup {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_query_backup_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)
            # Create existing translation
            StringTranslation.objects.create(
                translation_of=string,
                locale=self.target_locale,
                context=context_obj,
                data=f"Translation {i}",
            )
            mark_segment_do_not_translate(self.translation, segment)

        # Create 7 segments without backups (will be deleted)
        for i in range(num_deletes):
            string = String.objects.create(
                data=f"String without backup {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.bulk_unmark_query_no_backup_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + num_updates,
            )
            segments.append(segment)
            mark_segment_do_not_translate(self.translation, segment)

        # Test query count - verifies bulk operations are used
        # Expected query formula: 6 + N_deletes
        # Query breakdown:
        # 1. SAVEPOINT
        # 2. SELECT marked translations (with select_related for translation_of and context)
        # 3. SELECT for delete preparation (Django ORM requirement - refetches for CASCADE)
        # 4. DELETE bulk operation (single query regardless of count)
        # 5-N. Context lookups during CASCADE checks (N queries for N deletions)
        #      This is a Django ORM limitation when handling FK CASCADE relationships
        # N+1. UPDATE bulk operation (single query regardless of count)
        # N+2. RELEASE SAVEPOINT
        #
        # Note: Despite the N context lookups, this is still FAR more efficient than
        # calling unmark_segment_do_not_translate() in a loop, which would be ~3*N queries.
        # The core DELETE and UPDATE operations are true bulk operations (1 query each).
        expected_queries = 6 + num_deletes  # 6 base queries + N context lookups
        with self.assertNumQueries(expected_queries):
            count, segment_data = bulk_unmark_segments(self.translation, segments)

        total_segments = num_updates + num_deletes
        assert count == total_segments, (
            f"Should have unmarked {total_segments} segments"
        )
        assert len(segment_data) == total_segments, (
            f"Should have data for {total_segments} segments"
        )

        # Verify the bulk operations worked correctly
        for i in range(num_updates):
            # Segments with backups should be restored
            st = StringTranslation.objects.get(
                translation_of=segments[i].string, locale=self.target_locale
            )
            assert st.data == f"Translation {i}"

        # Segments without backups should be deleted
        for i in range(num_updates, num_updates + num_deletes):
            assert not StringTranslation.objects.filter(
                translation_of=segments[i].string, locale=self.target_locale
            ).exists()

    def test_bulk_mark_segments_triggers_signals(self):
        """Test that bulk_mark_segments triggers post_save signals."""
        # Create segments
        segments = []
        for i in range(3):
            string = String.objects.create(
                data=f"Test string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.signal_mark_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)

        # Create one existing translation to test update signal
        StringTranslation.objects.create(
            translation_of=segments[0].string,
            locale=self.target_locale,
            context=segments[0].context,
            data="Existing translation",
        )

        # Set up signal handler mock
        signal_handler = Mock()
        post_save.connect(signal_handler, sender=StringTranslation)

        try:
            # Call bulk_mark_segments
            count = bulk_mark_segments(self.translation, segments)

            # Verify signals were triggered
            # Should be called 3 times: 1 update (existing) + 2 creates (new)
            assert count == 3, "Should have marked 3 segments"
            assert signal_handler.call_count == 3, (
                f"Expected 3 post_save signals, got {signal_handler.call_count}"
            )

            # Verify signal calls have correct parameters
            calls = signal_handler.call_args_list
            created_count = sum(
                1 for call in calls if call.kwargs.get("created") is True
            )
            updated_count = sum(
                1 for call in calls if call.kwargs.get("created") is False
            )

            assert created_count == 2, (
                f"Expected 2 created signals, got {created_count}"
            )
            assert updated_count == 1, f"Expected 1 updated signal, got {updated_count}"

        finally:
            # Clean up signal handler
            post_save.disconnect(signal_handler, sender=StringTranslation)

    def test_bulk_unmark_segments_triggers_signals(self):
        """Test that bulk_unmark_segments triggers post_save signals for updates."""
        # Create segments with backups (will trigger update signals)
        segments = []
        for i in range(3):
            string = String.objects.create(
                data=f"Test string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.signal_unmark_{i}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            segments.append(segment)

            # Create existing translation
            StringTranslation.objects.create(
                translation_of=string,
                locale=self.target_locale,
                context=context_obj,
                data=f"Translation {i}",
            )
            # Mark it (creates backup)
            mark_segment_do_not_translate(self.translation, segment)

        # Set up signal handler mock
        signal_handler = Mock()
        post_save.connect(signal_handler, sender=StringTranslation)

        try:
            # Call bulk_unmark_segments
            count, segment_data = bulk_unmark_segments(self.translation, segments)

            # Verify signals were triggered
            # Should be called 3 times: all 3 segments have backups so they're updated
            assert count == 3, "Should have unmarked 3 segments"
            assert signal_handler.call_count == 3, (
                f"Expected 3 post_save signals, got {signal_handler.call_count}"
            )

            # Verify all signals are updates (created=False)
            for call in signal_handler.call_args_list:
                assert call.kwargs.get("created") is False, (
                    "All signals should be updates, not creates"
                )
                assert call.kwargs.get("update_fields") == ["data"], (
                    "Update fields should be ['data']"
                )

        finally:
            # Clean up signal handler
            post_save.disconnect(signal_handler, sender=StringTranslation)

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
