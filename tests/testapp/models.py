"""
Test models for integration testing.
"""

from django.db import models

from wagtail.admin.panels import FieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page

from .blocks import TestBlock


class TestPage(Page):
    """
    A simple test page model for testing translation functionality.
    """

    title_field = models.CharField(max_length=255, blank=True)
    content = StreamField(
        [
            ("test_block", TestBlock()),
        ],
        blank=True,
        use_json_field=True,
    )

    content_panels = Page.content_panels + [
        FieldPanel("title_field"),
        FieldPanel("content"),
    ]

    class Meta:
        verbose_name = "Test Page"
