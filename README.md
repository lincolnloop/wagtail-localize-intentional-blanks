# wagtail-localize-intentional-blanks

A Wagtail library that extends [wagtail-localize](https://github.com/wagtail/wagtail-localize) to allow translators to mark translation segments as "do not translate". These segments count as translated (contributing to progress) but fall back to the source page's value when rendered.

![url_intentionally_blank](https://raw.githubusercontent.com/lincolnloop/wagtail-localize-intentional-blanks/main/docs/images/url_intentionally_blank.png)
![number_intentionally_blank](https://raw.githubusercontent.com/lincolnloop/wagtail-localize-intentional-blanks/main/docs/images/number_intentionally_blank.png)


## Features

- ✅ **Translator Control**: Translators decide which fields to not translate
- ✅ **Per-Locale Flexibility**: One language can translate a value while another language can use the source value
- ✅ **Progress Tracking**: "Do not translate" segments count as translated by `wagtail-localize`
- ✅ **No Template Changes**: Works transparently with existing templates
- ✅ **Drop-in Integration**: Minimal code changes required
- ✅ **UI Included**: Adds "Do Not Translate" buttons to translation editor

## Installation

```bash
pip install wagtail-localize-intentional-blanks
```

## Quick Start

### 1. Add to INSTALLED_APPS

**Important:** `wagtail_localize_intentional_blanks` must come **before** `wagtail_localize` in `INSTALLED_APPS` for template overrides to work.

```python
# settings.py

INSTALLED_APPS = [
    # ... other apps
    'wagtail_localize_intentional_blanks',  # Must be BEFORE wagtail_localize
    'wagtail_localize',
    'wagtail_localize.locales',
    # ... other apps
]
```

### 2. Include URLs

```python
# urls.py

from django.urls import path, include

urlpatterns = [
    # ... other patterns
    path(
        'intentional-blanks/', include('wagtail_localize_intentional_blanks.urls')
    ),
]
```

That's it! The "Do Not Translate" button will now appear in the translation editor for all translatable fields. No code changes to your blocks or models required.

## How It Works

This library works by:

1. **Adding UI controls** - JavaScript adds "Do Not Translate" checkboxes to the translation editor
2. **Storing markers** - When checked, a marker string (`__DO_NOT_TRANSLATE__`) is stored in the translation
3. **Automatic replacement** - When rendering pages, signal handlers intercept segment retrieval and replace markers with source values
4. **Progress tracking** - Marked segments count as "translated" for progress calculation

**Key benefit:** No code changes to your blocks or models. The library handles everything automatically through wagtail-localize's signal-based extension mechanism.

## Usage

### In the Translation Editor

1. Open a page translation in wagtail-localize's editor
2. For each segment, you'll see a "Mark 'Do Not Translate'" checkbox
3. Check it to mark that segment as do not translate
4. The segment counts as translated (shows green)
5. When the page renders, it automatically shows the source value for that field
6. If the value in the original page changes, and the translated pages are synced, the segment still counts as translated (shows green) and when the page renders, it shows the updated source value for that field

### Common Use Cases

- **Brand names and trademarks** - Keep consistent across locales
- **Product codes and SKUs** - No translation needed
- **URLs** - Pages may contain the translations for different languages, but a URL is the same for all languages
- **IDs** - Not language-specific identifiers

### Configuration

You can customize behavior in your Django settings:

```python
# settings.py

# Enable/disable the feature globally
WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_ENABLED = True

# Custom marker (advanced)
WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_MARKER = "__DO_NOT_TRANSLATE__"

# Require specific permission (default: None = any translator)
WAGTAIL_LOCALIZE_INTENTIONAL_BLANKS_REQUIRED_PERMISSION = 'cms.can_mark_do_not_translate'
```

## Advanced Usage

### Programmatic API

You can programmatically mark segments as "do not translate" using the provided utilities:

```python
from wagtail_localize_intentional_blanks.utils import (
    mark_segment_do_not_translate,
    unmark_segment_do_not_translate,
    get_source_fallback_stats,
)
from wagtail_localize.models import Translation, StringSegment

# Mark a segment
translation = Translation.objects.get(id=123)
segment = StringSegment.objects.get(id=456)
mark_segment_do_not_translate(translation, segment, user=request.user)

# Unmark a segment
unmark_segment_do_not_translate(translation, segment)

# Get statistics
stats = get_source_fallback_stats(translation)
print(f"{stats['do_not_translate']} segments marked as do not translate")
print(f"{stats['manually_translated']} segments manually translated")
```

## Requirements

- Python 3.10+
- Django 5.2+
- Wagtail 7.0+
- wagtail-localize 1.14+

The Python, Django, and Wagtail versions follow `wagtail-localize`. Its 1.14
requires Wagtail 7.0+ & Django 5.2+, so older combinations are not installable.

These are the combinations CI tests. They mirror the hatch matrix in
`pyproject.toml`

| Python | Django | Wagtail |
|---|---|---|
| 3.10, 3.11 | 5.2 | 7.0 LTS |
| 3.12 | 6.0 | 7.4 LTS |
| 3.13, 3.14 | 6.1 | 8.0 |

## Internationalization (i18n)

The plugin UI is translatable. Django will automatically select the right language based on the user's browser settings (requires `django.middleware.locale.LocaleMiddleware` in your `MIDDLEWARE`).

### Adding a new language

1. From the `wagtail_localize_intentional_blanks` directory, generate a `.po` file for the new locale:

```bash
cd wagtail_localize_intentional_blanks
django-admin makemessages -l <language_code> --no-wrap
```

2. Edit `locale/<language_code>/LC_MESSAGES/django.po` and fill in the `msgstr` values.

3. Compile the translations:

```bash
django-admin compilemessages -l <language_code>
```

4. Submit a pull request with both the `.po` and `.mo` files.

For more details, see Django's [translation documentation](https://docs.djangoproject.com/en/stable/topics/i18n/translation/).

## Release

In order to make a release, we add a git tag and push it to GitHub. We have a GitHub Action that releases the code to PyPI when we add a new tag.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome!

## Development

### Setting Up for Development

1. Clone the repository:
```bash
git clone https://github.com/lincolnloop/wagtail-localize-intentional-blanks.git
cd wagtail-localize-intentional-blanks
```

2. Install the package with development dependencies:
```bash
pip install -e ".[dev]"
```

This installs the package in editable mode along with testing tools (pytest, black, flake8, etc.).

### Running Tests

Against the versions in your own virtualenv, run the suite with pytest:
```bash
pytest
```

Run tests with coverage:
```bash
pytest --cov=wagtail_localize_intentional_blanks
```

Run specific test files:
```bash
pytest tests/test_utils.py
pytest tests/test_views.py
```

### Running Tests Against Every Supported Version

The full support matrix is defined once, as a [hatch](https://hatch.pypa.io)
environment matrix in `pyproject.toml`, and CI runs tests against the matrix.
`uvx` fetches hatch on demand, so there is nothing to install beyond
[uv](https://docs.astral.sh/uv/):

```bash
uvx hatch run test:cov
```

That builds one isolated environment per combination and runs the suite in each.
The environments are cached outside the repository, so only the first creates
them.

To run a single interpreter's combinations:

```bash
uvx hatch run +py=3.12 test:cov
```

To run one exact combination, and to pass arguments through to pytest:

```bash
uvx hatch env show      # list the environment names
uvx hatch run test.py3.10-django5.2-wagtail7.0:run -q -k views
```

There is also an unpinned environment that resolves whatever Wagtail, Django and
wagtail-localize are current. CI runs it as advisory, so an upstream release that
breaks this package shows up before it is released upstream:

```bash
uvx hatch run latest:cov
```

Hatch needs the interpreters to already exist on your machine; it will not fetch
them for you. Install them once with:

```bash
uv python install 3.10 3.11 3.12 3.13 3.14
```

To delete the cached environments (after changing the matrix, say):

```bash
uvx hatch env prune
```

### Code Quality

Check code with ruff:
```bash
ruff check .
```

Format with ruff:
```bash
ruff format .
```

## Credits

Created by [Lincoln Loop, LLC](https://lincolnloop.com) for the Wagtail community.
