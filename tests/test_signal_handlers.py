"""
Unit tests for signal handlers.

Tests that the signal handlers correctly replace marker strings with source
values when rendering translated pages.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from wagtail.models import Locale, Page
from wagtail_localize.models import (
    MissingTranslationError,
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
from wagtail_localize_intentional_blanks.utils import mark_segment_do_not_translate


User = get_user_model()


@pytest.mark.django_db
class TestSignalHandlerFunctionality(TestCase):
    """
    Test that signal handlers handle intentional blanks for _get_segments_for_translation().

    When calling TranslationSource._get_segments_for_translation(), the signal
    handlers should correctly integrate with wagtail-localize, so that the
    expected values are set.
    """

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

        # Create translation source
        self.source, created = TranslationSource.get_or_create_from_instance(self.page)

        # Create translation
        self.translation = Translation.objects.create(
            source=self.source,
            target_locale=self.target_locale,
        )

    def test_replaces_plain_marker_with_source_value(self):
        """Test that _get_segments_for_translation replaces plain marker with source value."""
        # Create a string segment with source value
        source_value = "English Source Text"
        string = String.objects.create(
            data=source_value,
            locale=self.source_locale,
        )
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.field", defaults={"object": self.source.object}
        )
        segment = StringSegment.objects.create(
            source=self.source,
            string=string,
            context=context_obj,
            order=0,
            attrs="{}",
        )

        # Mark as do not translate (no existing translation, so no backup)
        mark_segment_do_not_translate(self.translation, segment, user=self.user)

        # Verify the marker is stored in the database
        st = StringTranslation.objects.get(
            translation_of=string, locale=self.target_locale
        )
        assert st.data == DO_NOT_TRANSLATE_MARKER

        # Get segments for translation
        # Use fallback=True to handle automatically created page segments (title, slug, etc)
        segments = self.source._get_segments_for_translation(
            self.target_locale, fallback=True
        )

        # Find our segment in the results
        string_segments = [s for s in segments if hasattr(s, "string")]
        assert len(string_segments) > 0

        # The segment should have the source value, not the marker
        found = False
        for seg in string_segments:
            if seg.string.data == source_value:
                found = True
                break

        assert found, (
            f"Expected to find source value '{source_value}' in segments, but it was not found"
        )

    def test_replaces_marker_with_backup_using_source_value(self):
        """Test that marker with encoded backup is replaced with source value."""
        # Create a string segment with source value
        source_value = "English Source Text"
        string = String.objects.create(
            data=source_value,
            locale=self.source_locale,
        )
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.field2", defaults={"object": self.source.object}
        )
        segment = StringSegment.objects.create(
            source=self.source,
            string=string,
            context=context_obj,
            order=0,
            attrs="{}",
        )

        # Create an existing translation first
        StringTranslation.objects.create(
            translation_of=string,
            locale=self.target_locale,
            context=context_obj,
            data="French Translation",
        )

        # Mark as do not translate (existing translation, so backup is encoded)
        mark_segment_do_not_translate(self.translation, segment, user=self.user)

        # Verify the marker with backup is stored
        st = StringTranslation.objects.get(
            translation_of=string, locale=self.target_locale
        )
        assert (
            st.data == f"{DO_NOT_TRANSLATE_MARKER}{BACKUP_SEPARATOR}French Translation"
        )

        # Get segments for translation
        # Use fallback=True to handle automatically created page segments (title, slug, etc)
        segments = self.source._get_segments_for_translation(
            self.target_locale, fallback=True
        )

        # The segment should have the source value, not the marker or backup
        string_segments = [s for s in segments if hasattr(s, "string")]
        found = False
        for seg in string_segments:
            if seg.string.data == source_value:
                found = True
                break

        assert found, f"Expected to find source value '{source_value}' in segments"

    def test_does_not_affect_normal_translations(self):
        """Test that normal translations are returned unchanged."""
        # Create a string segment
        source_value = "English Source"
        translated_value = "Texte français"
        string = String.objects.create(
            data=source_value,
            locale=self.source_locale,
        )
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.normal_field", defaults={"object": self.source.object}
        )
        StringSegment.objects.create(
            source=self.source,
            string=string,
            context=context_obj,
            order=0,
            attrs="{}",
        )

        # Create a normal translation (not marked)
        StringTranslation.objects.create(
            translation_of=string,
            locale=self.target_locale,
            context=context_obj,
            data=translated_value,
        )

        # Get segments for translation
        # Use fallback=True to handle automatically created page segments (title, slug, etc)
        segments = self.source._get_segments_for_translation(
            self.target_locale, fallback=True
        )

        # The segment should have the translated value
        string_segments = [s for s in segments if hasattr(s, "string")]
        found = False
        for seg in string_segments:
            if seg.string.data == translated_value:
                found = True
                break

        assert found, (
            f"Expected to find translated value '{translated_value}' in segments"
        )

    def test_handles_mixed_translations(self):
        """Test that signal handlers handle mix of marked and normal translations."""
        # Create multiple segments
        segments_data = [
            # (source_val, trans_val, mark_as_dnt),
            ("source1", "translation1", False),  # Normal translation
            ("source2", None, True),  # Marked do not translate
            ("source3", "translation3", False),  # Normal translation
            ("source4", "translation4", True),  # Marked with backup
        ]

        created_segments = []
        for i, (source_val, trans_val, mark_as_dnt) in enumerate(segments_data):
            string = String.objects.create(
                data=source_val,
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.mixed_field_{i}", defaults={"object": self.source.object}
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i,
                attrs="{}",
            )

            if trans_val and not mark_as_dnt:
                # Normal translation
                StringTranslation.objects.create(
                    translation_of=string,
                    locale=self.target_locale,
                    context=context_obj,
                    data=trans_val,
                )
            elif trans_val and mark_as_dnt:
                # Create translation first, then mark (creates backup)
                StringTranslation.objects.create(
                    translation_of=string,
                    locale=self.target_locale,
                    context=context_obj,
                    data=trans_val,
                )
                mark_segment_do_not_translate(self.translation, segment)
            elif mark_as_dnt:
                # Just mark (no backup)
                mark_segment_do_not_translate(self.translation, segment)

            created_segments.append((segment, source_val, trans_val, mark_as_dnt))

        # Get segments for translation
        # Use fallback=True to handle automatically created page segments (title, slug, etc)
        segments = self.source._get_segments_for_translation(
            self.target_locale, fallback=True
        )
        string_segments = [s for s in segments if hasattr(s, "string")]

        # Verify results
        # - segments[0]: should have "translation1"
        # - segments[1]: should have "source2" (marked, no backup)
        # - segments[2]: should have "translation3"
        # - segments[3]: should have "source4" (marked with backup)

        segment_values = {s.string.data for s in string_segments}

        # Check marked segments return source values
        assert "source2" in segment_values, "Marked segment should return source value"
        assert "source4" in segment_values, (
            "Marked segment with backup should return source value"
        )

        # Check normal translations are preserved
        assert "translation1" in segment_values, (
            "Normal translation should be preserved"
        )
        assert "translation3" in segment_values, (
            "Normal translation should be preserved"
        )

        # Check markers are NOT in the results
        assert DO_NOT_TRANSLATE_MARKER not in segment_values, (
            "Marker should not appear in segments"
        )

    @override_settings(WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_ENABLED=False)
    def test_disabled_when_feature_disabled(self):
        """Test that signal handler does not apply when feature is disabled."""
        # Create a string segment
        source_value = "English Source"
        string = String.objects.create(
            data=source_value,
            locale=self.source_locale,
        )
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.disabled_field", defaults={"object": self.source.object}
        )
        segment = StringSegment.objects.create(
            source=self.source,
            string=string,
            context=context_obj,
            order=0,
            attrs="{}",
        )

        # Mark as do not translate
        mark_segment_do_not_translate(self.translation, segment)

        # Verify the marker is stored
        st = StringTranslation.objects.get(
            translation_of=string, locale=self.target_locale
        )
        assert st.data == DO_NOT_TRANSLATE_MARKER

        # With feature disabled, the signal handler is bypassed and markers are NOT replaced.
        # Since a translation exists (the marker), wagtail-localize returns it as-is
        # Note: We use fallback=True to handle the page's auto-created segments
        segments = self.source._get_segments_for_translation(
            self.target_locale, fallback=True
        )
        string_segments = [s for s in segments if hasattr(s, "string")]

        # Verify that the marker is NOT replaced (feature is disabled)
        found_marker = False
        for seg in string_segments:
            if seg.string.data == DO_NOT_TRANSLATE_MARKER:
                found_marker = True
                break

        assert found_marker, "With feature disabled, marker should NOT be replaced"

    def test_handles_empty_translation_source(self):
        """Test that signal handlers handle pages with no string segments gracefully."""
        # Create a minimal page with no additional content
        empty_page = Page(title="Empty", slug="empty-page", locale=self.source_locale)
        self.root_page.add_child(instance=empty_page)

        # Create translation source
        empty_source, _ = TranslationSource.get_or_create_from_instance(empty_page)

        # Create translation
        Translation.objects.create(
            source=empty_source,
            target_locale=self.target_locale,
        )

        # Should not raise any errors
        segments = empty_source._get_segments_for_translation(
            self.target_locale, fallback=True
        )

        # Should return minimal segments (just the page's title and slug).
        assert isinstance(segments, list)
        assert [segment.path for segment in segments] == ["title", "slug"]

    def test_preserves_segment_order(self):
        """Test that signal handlers preserve the order of segments."""
        # Create multiple segments with specific order
        segment_data = [
            ("first", 0),
            ("second", 1),
            ("third", 2),
        ]

        for text, order in segment_data:
            string = String.objects.create(
                data=text,
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.order_field_{order}",
                defaults={"object": self.source.object},
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=order,
                attrs="{}",
            )
            # Mark all as do not translate
            mark_segment_do_not_translate(self.translation, segment)

        # Get segments
        # Use fallback=True to handle automatically created page segments (title, slug, etc)
        segments = self.source._get_segments_for_translation(
            self.target_locale, fallback=True
        )
        string_segments = [s for s in segments if hasattr(s, "string")]

        # Verify we got segments back
        assert len(string_segments) >= 3, "Should have at least 3 string segments"

        # Note: Order is preserved via the order attribute, not list position
        segment_values = [s.string.data for s in string_segments]
        assert "first" in segment_values
        assert "second" in segment_values
        assert "third" in segment_values
        for string_segment in string_segments:
            if string_segment.string.data == "first":
                assert string_segment.order == 0
            elif string_segment.string.data == "second":
                assert string_segment.order == 1
            elif string_segment.string.data == "third":
                assert string_segment.order == 2

    def test_raises_missing_translation_error_without_fallback(self):
        """Test that MissingTranslationError is raised when translation is missing and fallback=False."""
        # Create a string segment without translation
        source_value = "Untranslated Text"
        string = String.objects.create(
            data=source_value,
            locale=self.source_locale,
        )
        context_obj, _ = TranslationContext.objects.get_or_create(
            path="test.missing_field", defaults={"object": self.source.object}
        )
        StringSegment.objects.create(
            source=self.source,
            string=string,
            context=context_obj,
            order=0,
            attrs="{}",
        )

        # Do NOT create a StringTranslation for this segment

        # Should raise MissingTranslationError when fallback=False
        with pytest.raises(MissingTranslationError):
            self.source._get_segments_for_translation(
                self.target_locale, fallback=False
            )

    def test_sync_via_update_translations_view_preserves_markers(self):
        """
        Integration test: markers persist and migrate when syncing via UpdateTranslationsView.

        This tests the complete real-world workflow:
        1. User marks a field as "Do Not Translate"
        2. User modifies the source page content
        3. User clicks "Sync translated pages" (calls UpdateTranslationsView)
        4. The marker should be migrated to the new content and preserved
        """
        from tests.testapp.models import TestPage

        # Step 1: Create a TestPage with actual content in a custom field
        test_page = TestPage(
            title="Test Page for Migration",
            slug="test-migration-page",
            locale=self.source_locale,
            title_field="Original Title Field Content",
        )
        self.root_page.add_child(instance=test_page)

        # Create translation source for this page
        test_source, _ = TranslationSource.get_or_create_from_instance(test_page)

        # Create translation
        test_translation = Translation.objects.create(
            source=test_source,
            target_locale=self.target_locale,
        )

        # Step 2: Find the title_field segment and mark it as Do Not Translate
        title_field_segment = StringSegment.objects.get(
            source=test_source, context__path="title_field"
        )

        mark_segment_do_not_translate(
            test_translation, title_field_segment, user=self.user
        )

        # Verify marker was created
        original_string_id = title_field_segment.string.id
        marker_st = StringTranslation.objects.get(
            translation_of=title_field_segment.string,
            locale=self.target_locale,
            context=title_field_segment.context,
        )
        assert marker_st.data == DO_NOT_TRANSLATE_MARKER
        original_marker_id = marker_st.id

        # Step 3: Modify the page content (simulating user editing the source page)
        test_page.title_field = "Updated Title Field Content"
        test_page.save_revision().publish()

        # Step 4: Call UpdateTranslationsView via HTTP
        # This simulates the user clicking "Sync translated pages" in the admin
        client = Client()

        # Make sure the user has proper permissions
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

        client.force_login(self.user)

        # Get the proper URL using reverse
        url = reverse("wagtail_localize:update_translations", args=[test_source.id])

        # POST to sync translations
        response = client.post(url, {})

        # Should redirect on success (302) or return 200
        assert response.status_code in [200, 302], (
            f"Sync view failed with status {response.status_code}"
        )

        # Step 5: Verify the marker was migrated to the new String
        # Get the title_field segment after refresh
        title_field_segment_after = StringSegment.objects.get(
            source=test_source, context__path="title_field"
        )

        # The String should have changed (new content)
        assert title_field_segment_after.string.id != original_string_id, (
            "String should have been updated to new content"
        )
        assert title_field_segment_after.string.data == "Updated Title Field Content"

        # The marker should have been migrated to the new String
        marker_st_after = StringTranslation.objects.get(
            translation_of=title_field_segment_after.string,
            locale=self.target_locale,
            context=title_field_segment_after.context,
        )
        assert marker_st_after.data == DO_NOT_TRANSLATE_MARKER, (
            "Marker should have been migrated to new String"
        )
        assert marker_st_after.id == original_marker_id, (
            "Should be the same StringTranslation record, just updated"
        )

        # Step 6: Verify no orphaned marker remains on the old String
        orphaned_markers = StringTranslation.objects.filter(
            translation_of_id=original_string_id,
            locale=self.target_locale,
        )
        assert orphaned_markers.count() == 0, (
            "No markers should remain on the old String"
        )

        # Step 7: Verify the field renders with the NEW source value
        segments = test_source._get_segments_for_translation(
            self.target_locale, fallback=True
        )
        string_segments = [s for s in segments if hasattr(s, "string")]
        assert any(
            s.string.data == "Updated Title Field Content" for s in string_segments
        ), "Field should render with new source value when marked as Do Not Translate"
