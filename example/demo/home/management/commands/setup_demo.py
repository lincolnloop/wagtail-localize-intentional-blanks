from datetime import date

from django.core.management.base import BaseCommand

from wagtail.models import Locale, Page, Site

from demo.home.models import ArticlePage, HomePage


class Command(BaseCommand):
    help = "Set up demo content for the intentional blanks example"

    def handle(self, *args, **options):
        self.stdout.write("Creating example content...")

        # Get root page and default locale
        root = Page.objects.get(depth=1)
        en_locale, _ = Locale.objects.get_or_create(language_code="en")

        # Delete the default Wagtail page if it exists and isn't our HomePage
        home_pages = Page.objects.filter(slug="home", depth=2)
        for page in home_pages:
            if not isinstance(page.specific, HomePage):
                page.delete()
                self.stdout.write("Removed default Wagtail home page")
                # IMPORTANT: Refresh root from database after deletion
                root = Page.objects.get(depth=1)
                break

        # Check if HomePage already exists
        if HomePage.objects.exists():
            self.stdout.write(
                self.style.WARNING("Home page already exists, using existing")
            )
            home = HomePage.objects.first()
        else:
            # Create HomePage
            home = HomePage(
                title="Welcome to Intentional Blanks Demo",
                tagline="Demonstrating wagtail-localize-intentional-blanks",
                body=(
                    '<p>This demo shows how translators can mark segments as "do not translate" to preserve source language values.</p>'
                    "<p>Common use cases:</p>"
                    "<ul>"
                    "<li>Brand names and trademarks</li>"
                    "<li>Technical specifications</li>"
                    "<li>Product codes and SKUs</li>"
                    "<li>Proper nouns</li>"
                    "</ul>"
                ),
                slug="home",
                locale=en_locale,
            )
            root.add_child(instance=home)
            revision = home.save_revision()
            revision.publish()
            self.stdout.write(self.style.SUCCESS("✓ Home page created"))

        # Set as site root
        try:
            site = Site.objects.get(is_default_site=True)
            if site.root_page_id != home.id:
                site.root_page = home
                site.save()
                self.stdout.write(self.style.SUCCESS("✓ Site root page updated"))
        except Site.DoesNotExist:
            Site.objects.create(
                hostname="localhost",
                port=8000,
                root_page=home,
                is_default_site=True,
                site_name="Intentional Blanks Demo",
            )
            self.stdout.write(
                self.style.SUCCESS("✓ Site created with home as root page")
            )

        # Create an Article if it doesn't exist
        existing_article = ArticlePage.objects.filter(slug="firefox-specs").first()
        if not existing_article:
            article = ArticlePage(
                title="Mozilla Firefox Technical Specs",
                date=date.today(),
                intro="Technical specifications for Mozilla Firefox browser.",
                body=(
                    "<p>Mozilla Firefox is a free and open-source web browser developed by the Mozilla Foundation.</p>"
                    "<p>Key features include enhanced privacy protection, customizable interface, and cross-platform support.</p>"
                ),
                slug="firefox-specs",
                locale=en_locale,
                draft_title="Mozilla Firefox Technical Specs",
            )
            home.add_child(instance=article)
            revision = article.save_revision()
            revision.publish()
            self.stdout.write(self.style.SUCCESS("✓ Article page created"))
        else:
            self.stdout.write(
                self.style.WARNING("Article page already exists, skipping")
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Example content setup complete!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("")
        self.stdout.write("Pages created:")
        self.stdout.write(f"  • Home: {home.title}")
        if not existing_article:
            self.stdout.write("  • Article: Mozilla Firefox Technical Specs")
