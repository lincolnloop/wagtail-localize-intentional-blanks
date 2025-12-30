"""
Test blocks for integration testing.
"""

from wagtail import blocks


class TestBlock(blocks.StructBlock):
    """
    A test block that supports source fallback.
    """

    title = blocks.CharBlock(max_length=255)
    description = blocks.TextBlock()
    url = blocks.URLBlock(required=False)

    class Meta:
        icon = "doc-full"
        label = "Test Block"


class TestBlockWithoutMixin(blocks.StructBlock):
    """
    A test block without the mixin for comparison.
    """

    title = blocks.CharBlock(max_length=255)
    description = blocks.TextBlock()

    class Meta:
        icon = "doc-full"
        label = "Test Block Without Mixin"
