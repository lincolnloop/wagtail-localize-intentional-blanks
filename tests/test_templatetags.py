"""
Unit tests for templatetags module.
"""

from django.template import Context, Template
from django.test import TestCase

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
from wagtail_localize_intentional_blanks.constants import DO_NOT_TRANSLATE_MARKER
from wagtail_localize_intentional_blanks.templatetags.intentional_blanks import (
    is_marked_do_not_translate,
    translation_stats,
)


@pytest.mark.django_db
class TestTemplatetagsFilters(TestCase):
    """Test template filters and tags."""

    def setUp(self):
        """Set up test data."""
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

    def test_is_marked_do_not_translate_filter_true(self):
        """Test is_marked_do_not_translate filter returns True for marked segments."""
        string_translation = StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data=DO_NOT_TRANSLATE_MARKER,
        )

        result = is_marked_do_not_translate(string_translation)

        assert result is True

    def test_is_marked_do_not_translate_filter_false(self):
        """Test is_marked_do_not_translate filter returns False for normal translations."""
        string_translation = StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data="Normal translation",
        )

        result = is_marked_do_not_translate(string_translation)

        assert result is False

    def test_is_marked_do_not_translate_in_template(self):
        """Test is_marked_do_not_translate filter in template context."""
        string_translation = StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data=DO_NOT_TRANSLATE_MARKER,
        )

        template = Template(
            "{% load intentional_blanks %}{% if translation|is_marked_do_not_translate %}marked{% else %}not marked{% endif %}"
        )
        context = Context({"translation": string_translation})
        result = template.render(context)

        assert "marked" in result
        assert "not marked" not in result

    def test_translation_stats_tag(self):
        """Test translation_stats template tag."""
        # Create some segments with different statuses
        for i in range(3):
            string = String.objects.create(
                data=f"Marked string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.marked_field_{i}", defaults={"object": self.source.object}
            )
            StringSegment.objects.create(
                source=self.source,
                string=string,
                context=context_obj,
                order=i + 1,
            )
            StringTranslation.objects.create(
                translation_of=string,
                locale=self.target_locale,
                context=context_obj,
                data=DO_NOT_TRANSLATE_MARKER,
            )

        for i in range(2):
            string = String.objects.create(
                data=f"Translated string {i}",
                locale=self.source_locale,
            )
            context_obj, _ = TranslationContext.objects.get_or_create(
                path=f"test.translated_field_{i}",
                defaults={"object": self.source.object},
            )
            StringSegment.objects.create(
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

        stats = translation_stats(self.translation)

        assert stats["total"] == 5
        assert stats["do_not_translate"] == 3
        assert stats["manually_translated"] == 2

    def test_translation_stats_empty(self):
        """Test translation_stats with no translations."""
        stats = translation_stats(self.translation)

        assert stats["total"] == 0
        assert stats["do_not_translate"] == 0
        assert stats["manually_translated"] == 0

    def test_template_tags_with_multiple_locales(self):
        """Test template tags work correctly with multiple target locales."""
        # Create another locale
        de_locale = Locale.objects.get_or_create(
            language_code="de", defaults={"language_code": "de"}
        )[0]

        # Create translation for German
        de_translation = Translation.objects.create(
            source=self.source,
            target_locale=de_locale,
        )

        # Mark segment for French but not German
        fr_string_translation = StringTranslation.objects.create(
            translation_of=self.string,
            locale=self.target_locale,
            context=self.segment.context,
            data=DO_NOT_TRANSLATE_MARKER,
        )

        de_string_translation = StringTranslation.objects.create(
            translation_of=self.string,
            locale=de_locale,
            context=self.segment.context,
            data="German translation",
        )

        # Check filter results
        assert is_marked_do_not_translate(fr_string_translation) is True
        assert is_marked_do_not_translate(de_string_translation) is False

        # Check stats for each locale
        fr_stats = translation_stats(self.translation)
        de_stats = translation_stats(de_translation)

        assert fr_stats["do_not_translate"] == 1
        assert fr_stats["manually_translated"] == 0

        assert de_stats["do_not_translate"] == 0
        assert de_stats["manually_translated"] == 1
