"""
Unit tests for views module.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
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

User = get_user_model()


@pytest.mark.django_db
class TestMarkSegmentView(TestCase):
    """Test mark_segment_do_not_translate_view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create user
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create locales
        self.source_locale = Locale.objects.get_or_create(
            language_code="en", defaults={"language_code": "en"}
        )[0]
        self.target_locale = Locale.objects.get_or_create(
            language_code="fr", defaults={"language_code": "fr"}
        )[0]

        # Create a root page
        self.root_page = Page.objects.filter(depth=1).first()
        if not self.root_page:
            self.root_page = Page.add_root(title="Root", slug="root")

        # Create test page
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

    def test_mark_segment_requires_login(self):
        """Test that marking requires authentication."""
        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.post(url)

        # Should redirect to login
        assert response.status_code == 302

    def test_mark_segment_requires_post(self):
        """Test that marking requires POST method."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.get(url)

        # Should not allow GET
        assert response.status_code == 405

    def test_mark_segment_success(self):
        """Test successfully marking a segment."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert data["do_not_translate"] is True
        assert data["source_value"] == self.string.data
        assert "message" in data

        # Verify StringTranslation was created
        st = StringTranslation.objects.get(
            translation_of=self.string, locale=self.target_locale
        )
        assert st.data == DO_NOT_TRANSLATE_MARKER

    def test_unmark_segment_success(self):
        """Test successfully unmarking a segment."""
        self.client.login(username="testuser", password="testpass")

        # First mark it
        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )
        self.client.post(url, {"do_not_translate": "true"})

        # Then unmark it
        response = self.client.post(url, {"do_not_translate": "false"})

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert data["do_not_translate"] is False

        # Verify StringTranslation was removed (no marker or encoded marker)
        assert not StringTranslation.objects.filter(
            translation_of=self.string, locale=self.target_locale
        ).exists()

    def test_mark_segment_invalid_translation_id(self):
        """Test with invalid translation ID."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[99999, self.segment.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["success"] is False
        assert "error" in data

    def test_mark_segment_invalid_segment_id(self):
        """Test with invalid segment ID."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, 99999],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["success"] is False
        assert "Segment" in data["error"] and "not found" in data["error"]

    def test_mark_segment_updates_existing_translation(self):
        """Test marking updates existing translation and encodes backup."""
        self.client.login(username="testuser", password="testpass")

        # Create existing translation
        StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data="Existing translation",
        )

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 200

        # Should have updated, not created new
        count = StringTranslation.objects.filter(
            translation_of=self.string, locale=self.target_locale
        ).count()
        assert count == 1

        # Should have encoded the backup
        st = StringTranslation.objects.get(
            translation_of=self.string, locale=self.target_locale
        )
        assert (
            st.data
            == f"{DO_NOT_TRANSLATE_MARKER}{BACKUP_SEPARATOR}Existing translation"
        )

    def test_unmark_segment_restores_backup(self):
        """Test unmarking restores the backed up translation."""
        self.client.login(username="testuser", password="testpass")

        # Create existing translation
        StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data="Original translation",
        )

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )

        # Mark it
        self.client.post(url, {"do_not_translate": "true"})

        # Unmark it
        response = self.client.post(url, {"do_not_translate": "false"})

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert data["do_not_translate"] is False
        assert data["translated_value"] == "Original translation"

        # Verify backup was restored
        st = StringTranslation.objects.get(
            translation_of=self.string, locale=self.target_locale
        )
        assert st.data == "Original translation"

    @override_settings(
        WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_REQUIRED_PERMISSION="cms.can_translate"
    )
    def test_mark_segment_permission_denied(self):
        """Test marking fails without required permission."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 403
        data = json.loads(response.content)
        assert data["success"] is False

    def test_mark_segment_invalid_parameter(self):
        """Test marking with invalid do_not_translate parameter."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.post(url, {"do_not_translate": "invalid_value"})

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["success"] is False
        assert "Invalid do_not_translate parameter" in data["error"]

        # Verify no StringTranslation was created
        assert not StringTranslation.objects.filter(
            translation_of=self.string, locale=self.target_locale
        ).exists()

    def test_mark_segment_missing_parameter(self):
        """Test marking with missing do_not_translate parameter."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:mark_segment_do_not_translate",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.post(url)

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["success"] is False


@pytest.mark.django_db
class TestGetSegmentStatusView(TestCase):
    """Test get_segment_status view."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create user
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create locales
        self.source_locale = Locale.objects.get_or_create(
            language_code="en", defaults={"language_code": "en"}
        )[0]
        self.target_locale = Locale.objects.get_or_create(
            language_code="fr", defaults={"language_code": "fr"}
        )[0]

        # Create a root page
        self.root_page = Page.objects.filter(depth=1).first()
        if not self.root_page:
            self.root_page = Page.add_root(title="Root", slug="root")

        # Create test page
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

    def test_get_status_requires_login(self):
        """Test that getting status requires authentication."""
        url = reverse(
            "wagtail_localize_intentional_blanks:get_segment_status",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.get(url)

        # Should redirect to login
        assert response.status_code == 302

    def test_get_status_not_marked(self):
        """Test getting status for unmarked segment."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:get_segment_status",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.get(url)

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert data["do_not_translate"] is False
        assert data["source_text"] == self.string.data
        assert data["translated_text"] is None

    def test_get_status_marked(self):
        """Test getting status for marked segment."""
        self.client.login(username="testuser", password="testpass")

        # Mark the segment
        StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data=DO_NOT_TRANSLATE_MARKER,
        )

        url = reverse(
            "wagtail_localize_intentional_blanks:get_segment_status",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.get(url)

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert data["do_not_translate"] is True
        assert data["source_text"] == self.string.data
        assert data["translated_text"] is None

    def test_get_status_with_translation(self):
        """Test getting status for translated segment."""
        self.client.login(username="testuser", password="testpass")

        # Add translation
        StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data="French translation",
        )

        url = reverse(
            "wagtail_localize_intentional_blanks:get_segment_status",
            args=[self.translation.id, self.segment.id],
        )

        response = self.client.get(url)

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert data["do_not_translate"] is False
        assert data["translated_text"] == "French translation"

    def test_get_status_invalid_ids(self):
        """Test getting status with invalid IDs."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:get_segment_status",
            args=[99999, 99999],
        )

        response = self.client.get(url)

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["success"] is False


@pytest.mark.django_db
class TestGetTranslationStatusView(TestCase):
    """Test get_translation_status view (bulk endpoint)."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create user
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create locales
        self.source_locale = Locale.objects.get_or_create(
            language_code="en", defaults={"language_code": "en"}
        )[0]
        self.target_locale = Locale.objects.get_or_create(
            language_code="fr", defaults={"language_code": "fr"}
        )[0]

        # Create a root page
        self.root_page = Page.objects.filter(depth=1).first()
        if not self.root_page:
            self.root_page = Page.add_root(title="Root", slug="root")

        # Create test page
        self.page = Page(
            title="Test Page", slug="test-page-bulk", locale=self.source_locale
        )
        self.root_page.add_child(instance=self.page)

        # Create translation source using the proper wagtail-localize API
        self.source, created = TranslationSource.get_or_create_from_instance(self.page)

        # Create multiple strings and segments with proper TranslationContext
        self.strings = []
        self.segments = []
        for i in range(5):
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
                order=i,
            )
            self.strings.append(string)
            self.segments.append(segment)

        # Create translation
        self.translation = Translation.objects.create(
            source=self.source,
            target_locale=self.target_locale,
        )

    def test_get_translation_status_requires_login(self):
        """Test that getting translation status requires authentication."""
        url = reverse(
            "wagtail_localize_intentional_blanks:get_translation_status",
            args=[self.translation.id],
        )

        response = self.client.get(url)

        # Should redirect to login
        assert response.status_code == 302

    def test_get_translation_status_no_marked_segments(self):
        """Test getting status when no segments are marked."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:get_translation_status",
            args=[self.translation.id],
        )

        response = self.client.get(url)

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert data["segments"] == {}

    def test_get_translation_status_some_marked_segments(self):
        """Test getting status when some segments are marked."""
        self.client.login(username="testuser", password="testpass")

        # Mark segments 0, 2, and 4 as "do not translate"
        for i in [0, 2, 4]:
            StringTranslation.objects.create(
                translation_of=self.strings[i],
                locale=self.target_locale,
                context=self.segments[i].context,
                data=DO_NOT_TRANSLATE_MARKER,
            )

        url = reverse(
            "wagtail_localize_intentional_blanks:get_translation_status",
            args=[self.translation.id],
        )

        response = self.client.get(url)

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert len(data["segments"]) == 3

        # Check that the correct segments are marked (using StringSegment IDs)
        for i in [0, 2, 4]:
            segment_id = str(self.segments[i].id)
            assert segment_id in data["segments"]
            assert data["segments"][segment_id]["do_not_translate"] is True
            assert data["segments"][segment_id]["source_text"] == f"Test string {i}"

        # Check that unmarked segments are not in response
        for i in [1, 3]:
            segment_id = str(self.segments[i].id)
            assert segment_id not in data["segments"]

    def test_get_translation_status_all_marked_segments(self):
        """Test getting status when all segments are marked."""
        self.client.login(username="testuser", password="testpass")

        # Mark all segments
        for i in range(5):
            StringTranslation.objects.create(
                translation_of=self.strings[i],
                locale=self.target_locale,
                context=self.segments[i].context,
                data=DO_NOT_TRANSLATE_MARKER,
            )

        url = reverse(
            "wagtail_localize_intentional_blanks:get_translation_status",
            args=[self.translation.id],
        )

        response = self.client.get(url)

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert len(data["segments"]) == 5

        # Check all segments are marked (using StringSegment IDs)
        for i in range(5):
            segment_id = str(self.segments[i].id)
            assert segment_id in data["segments"]

    def test_get_translation_status_invalid_translation_id(self):
        """Test getting status with invalid translation ID."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:get_translation_status", args=[99999]
        )

        response = self.client.get(url)

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["success"] is False
        assert "error" in data


@pytest.mark.django_db
class TestToggleAllDoNotTranslateView(TestCase):
    """Test toggle_all_do_not_translate_view (bulk mark/unmark endpoint)."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create user
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create locales
        self.source_locale = Locale.objects.get_or_create(
            language_code="en", defaults={"language_code": "en"}
        )[0]
        self.target_locale = Locale.objects.get_or_create(
            language_code="fr", defaults={"language_code": "fr"}
        )[0]

        # Create a root page
        self.root_page = Page.objects.filter(depth=1).first()
        if not self.root_page:
            self.root_page = Page.add_root(title="Root", slug="root")

        # Create test page
        self.page = Page(
            title="Test Page Bulk Toggle",
            slug="test-page-bulk-toggle",
            locale=self.source_locale,
        )
        self.root_page.add_child(instance=self.page)

        # Create translation source using the proper wagtail-localize API
        self.source, created = TranslationSource.get_or_create_from_instance(self.page)

        # Create multiple strings and segments with proper TranslationContext
        self.strings = []
        self.segments = []
        for i in range(5):
            string = String.objects.create(
                data=f"Test string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.field_bulk_{i}", defaults={"object": self.source.object}
            )
            segment = StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i,
            )
            self.strings.append(string)
            self.segments.append(segment)

        # Create translation
        self.translation = Translation.objects.create(
            source=self.source,
            target_locale=self.target_locale,
        )

    def test_toggle_all_requires_login(self):
        """Test that toggling all requires authentication."""
        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        # Should redirect to login
        assert response.status_code == 302

    def test_toggle_all_requires_post(self):
        """Test that toggling all requires POST method."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )

        response = self.client.get(url)

        # Should not allow GET
        assert response.status_code == 405

    def test_mark_all_segments_success(self):
        """Test successfully marking all segments."""
        self.client.login(username="testuser", password="testpass")

        # Verify StringTranslations for our test strings don't exist yet
        for string in self.strings:
            assert not StringTranslation.objects.filter(
                translation_of=string, locale=self.target_locale
            ).exists()

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )
        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 200
        data = json.loads(response.content)

        assert data["success"] is True
        assert data["do_not_translate"] is True
        # Check that all segments from the source were marked (including auto-created ones)
        total_segments = StringSegment.objects.filter(source=self.source).count()
        assert data["affected_count"] == total_segments
        assert len(data["segment_ids"]) == total_segments
        assert f"Marked {total_segments} segments" in data["message"]

        # Verify our test StringTranslations were created with marker
        for string in self.strings:
            st = StringTranslation.objects.get(
                translation_of=string, locale=self.target_locale
            )
            assert st.data == DO_NOT_TRANSLATE_MARKER

    def test_unmark_all_segments_success(self):
        """Test successfully unmarking all segments."""
        self.client.login(username="testuser", password="testpass")

        # First mark ALL segments
        all_segments = StringSegment.objects.filter(source=self.source)
        for segment in all_segments:
            if segment.string:
                StringTranslation.objects.create(
                    translation_of=segment.string,
                    locale=self.target_locale,
                    context=segment.context,
                    data=DO_NOT_TRANSLATE_MARKER,
                )

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )
        response = self.client.post(url, {"do_not_translate": "false"})

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["do_not_translate"] is False
        # Check count matches all segments in source
        total_segments = StringSegment.objects.filter(source=self.source).count()
        assert data["affected_count"] == total_segments
        assert len(data["segment_ids"]) == total_segments
        assert f"Unmarked {total_segments} segments" in data["message"]

        # Verify all StringTranslations were removed
        count = StringTranslation.objects.filter(
            translation_of__in=self.strings, locale=self.target_locale
        ).count()
        assert count == 0

    def test_unmark_all_returns_translated_values(self):
        """Test unmarking all segments returns translated values in segment_data."""
        self.client.login(username="testuser", password="testpass")

        # Create some existing translations before marking
        for i in [0, 2, 4]:
            StringTranslation.objects.create(
                translation_of=self.strings[i],
                locale=self.target_locale,
                context=self.segments[i].context,
                data=f"French translation {i}",
            )

        # Mark all segments (will encode backups)
        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )
        self.client.post(url, {"do_not_translate": "true"})

        # Now unmark all
        response = self.client.post(url, {"do_not_translate": "false"})

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "segment_data" in data

        # Verify segments with translations have translated_value
        for i in [0, 2, 4]:
            segment_id = str(self.segments[i].id)
            assert segment_id in data["segment_data"]
            assert (
                data["segment_data"][segment_id]["translated_value"]
                == f"French translation {i}"
            )
            assert (
                data["segment_data"][segment_id]["source_value"] == f"Test string {i}"
            )

        # Verify segments without translations have null translated_value
        for i in [1, 3]:
            segment_id = str(self.segments[i].id)
            assert segment_id in data["segment_data"]
            assert data["segment_data"][segment_id]["translated_value"] is None
            assert (
                data["segment_data"][segment_id]["source_value"] == f"Test string {i}"
            )

    def test_mark_all_with_some_already_marked(self):
        """Test marking all when some segments are already marked."""
        self.client.login(username="testuser", password="testpass")

        # Pre-mark segments 0 and 2
        for i in [0, 2]:
            StringTranslation.objects.create(
                translation_of=self.strings[i],
                locale=self.target_locale,
                context=self.segments[i].context,
                data=DO_NOT_TRANSLATE_MARKER,
            )

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        total_segments = StringSegment.objects.filter(source=self.source).count()
        assert data["affected_count"] == total_segments
        assert len(data["segment_ids"]) == total_segments

        # Verify our test segments are now marked
        count = StringTranslation.objects.filter(
            translation_of__in=self.strings,
            locale=self.target_locale,
            data=DO_NOT_TRANSLATE_MARKER,
        ).count()
        assert count == 5

    def test_unmark_all_with_backups(self):
        """Test that unmarking all segments restores their translated values."""
        self.client.login(username="testuser", password="testpass")

        # Create existing translations for all segments
        for i, string in enumerate(self.strings):
            StringTranslation.objects.create(
                translation_of=string,
                locale=self.target_locale,
                context=self.segments[i].context,
                data=f"Original translation {i}",
            )

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )

        # Mark all (will store the previously translated values)
        self.client.post(url, {"do_not_translate": "true"})

        # Verify backups were encoded
        for i, string in enumerate(self.strings):
            st = StringTranslation.objects.get(
                translation_of=string, locale=self.target_locale
            )
            assert (
                st.data
                == f"{DO_NOT_TRANSLATE_MARKER}{BACKUP_SEPARATOR}Original translation {i}"
            )

        # Unmark all
        response = self.client.post(url, {"do_not_translate": "false"})

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        total_segments = StringSegment.objects.filter(source=self.source).count()
        assert data["affected_count"] == total_segments
        # Verify our test translated values were restored
        for i, string in enumerate(self.strings):
            st = StringTranslation.objects.get(
                translation_of=string, locale=self.target_locale
            )
            assert st.data == f"Original translation {i}"

    def test_toggle_all_invalid_translation_id(self):
        """Test with invalid translation ID."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[99999],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["success"] is False
        assert "Translation not found" in data["error"]

    def test_toggle_all_invalid_parameter(self):
        """Test with invalid do_not_translate parameter."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )

        response = self.client.post(url, {"do_not_translate": "invalid_value"})

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["success"] is False
        assert "Invalid do_not_translate parameter" in data["error"]

    def test_toggle_all_missing_parameter(self):
        """Test with missing do_not_translate parameter."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )

        response = self.client.post(url)

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["success"] is False

    @override_settings(
        WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_REQUIRED_PERMISSION="cms.can_translate"
    )
    def test_toggle_all_permission_denied(self):
        """Test toggling all fails without required permission."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 403
        data = json.loads(response.content)
        assert data["success"] is False

    def test_toggle_all_no_segments(self):
        """Test toggling all when translation has no segments."""
        self.client.login(username="testuser", password="testpass")

        # Create a new page without segments
        empty_page = Page(
            title="Empty Page",
            slug="empty-page-test",
            locale=self.source_locale,
        )
        self.root_page.add_child(instance=empty_page)

        # Create empty source and delete its auto-created segments
        empty_source, _ = TranslationSource.get_or_create_from_instance(empty_page)
        StringSegment.objects.filter(source=empty_source).delete()

        # Create translation
        empty_translation = Translation.objects.create(
            source=empty_source,
            target_locale=self.target_locale,
        )

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[empty_translation.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["success"] is False
        assert "No segments found" in data["error"]

    def test_mark_all_returns_all_segment_ids(self):
        """Test that marking all returns all segment IDs."""
        self.client.login(username="testuser", password="testpass")

        url = reverse(
            "wagtail_localize_intentional_blanks:toggle_all_do_not_translate",
            args=[self.translation.id],
        )

        response = self.client.post(url, {"do_not_translate": "true"})

        assert response.status_code == 200
        data = json.loads(response.content)

        # Check all segment IDs from the source are returned
        returned_ids = set(data["segment_ids"])
        all_segment_ids = set(
            StringSegment.objects.filter(source=self.source).values_list(
                "id", flat=True
            )
        )

        assert returned_ids == all_segment_ids

        # Also verify our test segments are included
        test_segment_ids = {seg.id for seg in self.segments}
        assert test_segment_ids.issubset(returned_ids)
