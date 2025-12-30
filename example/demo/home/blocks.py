"""
Custom blocks for the example project.

These blocks demonstrate the "do not translate" functionality.
The monkey-patch in patch.py automatically handles marker replacement during rendering.
"""

from wagtail import blocks


class FeatureBlock(blocks.StructBlock):
    """
    A feature block demonstrating intentional blanks support.

    Translators can mark individual fields as "do not translate" using
    the checkboxes in the translation editor. The source language value
    will be used automatically.
    """

    heading = blocks.CharBlock(max_length=100, help_text="Feature heading")
    paragraph = blocks.TextBlock(help_text="Feature description")
    image_caption = blocks.CharBlock(max_length=200, required=False, help_text="Optional image caption")

    class Meta:
        icon = "doc-full"
        label = "Feature"


class TechnicalSpecBlock(blocks.StructBlock):
    """
    A technical specification block demonstrating intentional blanks.

    Useful for product specs, brand names, or technical terms that
    often don't need translation.
    """

    spec_name = blocks.CharBlock(max_length=100, help_text="Specification name (e.g., 'CPU', 'RAM', 'Display')")
    spec_value = blocks.CharBlock(max_length=200, help_text="Specification value (e.g., '8GB', '2.4GHz', '15.6 inches')")

    class Meta:
        icon = "cog"
        label = "Technical Specification"
