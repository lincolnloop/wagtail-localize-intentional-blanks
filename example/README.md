# Intentional Blanks Example Project

This is a demonstration Wagtail project showing how to use **wagtail-localize-intentional-blanks**.

## What This Demonstrates

This example shows how translators can mark specific translation segments as "do not translate", which tells wagtail-localize to use the source language value instead of requiring a translation.

Common use cases:
- **Brand names**: "Mozilla Firefox", "GitHub", product names
- **Technical terms**: API endpoints, configuration keys, code snippets
- **Proper nouns**: Company names, person names, place names
- **Product codes**: SKUs, model numbers, version numbers
- **Trademarks**: Registered brand names that shouldn't be translated

## Quick Start

### 1. Install Dependencies

```bash
cd example
pip install -r requirements.txt
```

### 2. Run Setup Script

```bash
./setup.sh
```

This will:
- Run database migrations
- Create a superuser (username: `admin`, password: `admin`)
- Create language locales (English, French, Spanish, German)
- Create example pages with translatable content

### 3. Start the Development Server

```bash
python manage.py runserver
```

### 4. Access the Admin

Visit http://localhost:8000/admin/ and log in with:
- **Username**: `admin`
- **Password**: `admin`

## Testing the Functionality

### Creating a Translation

1. Navigate to **Pages** in the Wagtail admin
2. Select the "Welcome to Intentional Blanks Demo" page
3. Click **"Translate this page"** in the page actions
4. Choose a target language (e.g., **French**)
5. Click **"Create"**

### Using "Mark 'Do Not Translate'"

In the translation editor, you'll see checkboxes labeled **"Mark 'Do Not Translate'"** next to each translatable segment:

1. **Check the box** next to a segment you want to preserve in the source language
2. The segment will:
   - Turn light green
   - Show a green left border
   - Display "USING SOURCE VALUE" badge
   - Hide the "Translate" button
   - Automatically use the source language text

3. **Uncheck the box** to revert back to manual translation mode

### Example Scenarios

**Scenario 1: Brand Names**
- Original (English): "Mozilla Firefox is a great browser"
- In the translation editor, mark "Mozilla Firefox" as "do not translate"
- French translation: "Mozilla Firefox est un excellent navigateur"
- The brand name stays in English while the rest is translated

**Scenario 2: Technical Specifications**
- Original: CPU model "Intel Core i7-12700K"
- Mark the technical spec as "do not translate"
- It remains unchanged in all language translations

## Project Structure

```
example/
├── manage.py              # Django management script
├── requirements.txt       # Project dependencies
├── setup.sh              # Automated setup script
├── README.md             # This file
├── db.sqlite3            # SQLite database (created after setup)
└── demo/                 # Django project
    ├── __init__.py
    ├── settings.py       # Django settings
    ├── urls.py           # URL configuration
    ├── wsgi.py           # WSGI configuration
    └── home/             # Home app with example models
        ├── __init__.py
        ├── models.py     # Page models (HomePage, ArticlePage)
        └── templates/    # Page templates
            └── home/
                ├── home_page.html
                └── article_page.html
```

## Example Models

### HomePage
Demonstrates basic translatable content with:
- Title and tagline
- Rich text body
- StreamField features (headings, paragraphs, image captions)

### ArticlePage
Demonstrates technical content that often needs source values preserved:
- Article metadata (date, title)
- Rich text content
- Technical specifications (as StreamField blocks)

## Manual Setup (Alternative to setup.sh)

If you prefer to set up manually:

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Create locales
python manage.py shell
>>> from wagtail.models import Locale
>>> Locale.objects.get_or_create(language_code='en')
>>> Locale.objects.get_or_create(language_code='fr')
>>> Locale.objects.get_or_create(language_code='es')
>>> Locale.objects.get_or_create(language_code='de')
>>> exit()

# Create example content (or create pages manually in admin)
python manage.py shell < create_content.py  # If you create this script
```

## Troubleshooting

### "No such table" errors
Run migrations: `python manage.py migrate`

### Can't log in
Reset the admin password:
```bash
python manage.py changepassword admin
```

### Translation editor not loading
Make sure wagtail-localize and wagtail-localize-intentional-blanks are installed:
```bash
pip install wagtail-localize wagtail-localize-intentional-blanks
```

### Checkboxes not appearing
1. Check that `wagtail_localize_intentional_blanks` is in `INSTALLED_APPS`
2. Check that the URL pattern is included in `urls.py`
3. Clear your browser cache and reload

## Learn More

- [wagtail-localize documentation](https://wagtail-localize.org/)
- [Wagtail documentation](https://docs.wagtail.org/)
- [wagtail-localize-intentional-blanks GitHub](https://github.com/lincolnloop/wagtail-localize-intentional-blanks)

## License

This example project is provided as-is for demonstration purposes.
