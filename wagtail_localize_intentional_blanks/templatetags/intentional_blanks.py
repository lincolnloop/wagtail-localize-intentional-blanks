"""
Template tags and filters for intentional blanks.

These template tags can be used to display information about
translation status and "do not translate" markers in templates.
"""

from django import template
from django.utils.translation import gettext as _

from ..utils import get_source_fallback_stats, is_do_not_translate

register = template.Library()


@register.filter
def is_marked_do_not_translate(string_translation):
    """
    Template filter to check if a StringTranslation is marked as "do not translate".

    Usage:
        {% load intentional_blanks %}
        {% if translation|is_marked_do_not_translate %}
            <span class="badge">Do not translate</span>
        {% endif %}

    Args:
        string_translation: StringTranslation instance

    Returns:
        bool: True if marked as "do not translate"
    """
    return is_do_not_translate(string_translation)


@register.simple_tag
def translation_stats(translation):
    """
    Template tag to get translation statistics.

    Usage:
        {% load intentional_blanks %}
        {% translation_stats translation as stats %}
        <p>{{ stats.do_not_translate }} segments marked as do not translate</p>
        <p>{{ stats.manually_translated }} segments manually translated</p>

    Args:
        translation: Translation instance

    Returns:
        dict: Statistics about translation
    """
    return get_source_fallback_stats(translation)


@register.inclusion_tag("wagtail_localize_intentional_blanks/i18n_strings.html")
def intentional_blanks_i18n():
    """
    Output a JSON script block with translated UI strings for JavaScript.

    Usage:
        {% load intentional_blanks %}
        {% intentional_blanks_i18n %}
    """
    return {
        "i18n_strings": {
            "checkboxLabel": _("Mark 'Do Not Translate'"),
            "markAll": _("Mark All 'Do Not Translate'"),
            "unmarkAll": _("Unmark All 'Do Not Translate'"),
            "marking": _("Marking..."),
            "unmarking": _("Unmarking..."),
            "usingSourceValue": _("Using source value"),
            "markAllDescription": _("Mark All fields as 'Do Not Translate'"),
            "failedToUpdate": _("Failed to update segment"),
            "networkError": _("Network error occurred"),
            "failedToMarkAll": _("Failed to mark all segments"),
            "failedToUnmarkAll": _("Failed to unmark all segments"),
        }
    }
