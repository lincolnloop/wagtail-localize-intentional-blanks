from django.apps import AppConfig


class IntentionalBlanksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wagtail_localize_intentional_blanks"
    verbose_name = "Wagtail Localize Intentional Blanks"

    def ready(self):
        """
        Run when Django starts.

        Register signal handlers, check dependencies, etc.
        """
        # Check that wagtail-localize is installed
        try:
            import wagtail_localize  # noqa: F401
        except ImportError:
            raise ImportError(
                "wagtail-localize must be installed to use wagtail-localize-intentional-blanks. Install it with: pip install wagtail-localize"
            )

        # Apply monkey-patch to wagtail-localize
        from .patch import apply_patch

        apply_patch()

        # Import wagtail hooks
        from . import wagtail_hooks  # noqa
