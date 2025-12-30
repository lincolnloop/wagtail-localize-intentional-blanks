from django.db import models

from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page

from .blocks import FeatureBlock, TechnicalSpecBlock


class HomePage(Page):
    """
    Example home page demonstrating wagtail-localize-intentional-blanks.

    This page includes translatable content where translators can mark
    certain segments as "do not translate" to use the source language value.
    """

    tagline = models.CharField(max_length=255, blank=True, help_text="A short tagline for the homepage")

    body = RichTextField(blank=True, help_text="Main content area with rich text")

    features = StreamField(
        [
            ("feature", FeatureBlock()),
        ],
        blank=True,
        use_json_field=True,
        help_text="Feature blocks that can be individually marked as 'do not translate'",
    )

    content_panels = Page.content_panels + [
        FieldPanel("tagline"),
        FieldPanel("body"),
        FieldPanel("features"),
    ]

    class Meta:
        verbose_name = "Home Page"


class ArticlePage(Page):
    """
    Example article page with translatable content.

    Demonstrates how product names, technical terms, or brand names
    can be marked to use source values instead of being translated.
    """

    date = models.DateField("Post date")
    intro = models.CharField(max_length=250)
    body = RichTextField(blank=True)

    # Technical content that might not need translation
    technical_specs = StreamField(
        [
            ("spec", TechnicalSpecBlock()),
        ],
        blank=True,
        use_json_field=True,
        help_text="Technical specifications - translators can mark these to use original values",
    )

    content_panels = Page.content_panels + [
        FieldPanel("date"),
        FieldPanel("intro"),
        FieldPanel("body"),
        FieldPanel("technical_specs"),
    ]

    class Meta:
        verbose_name = "Article Page"
