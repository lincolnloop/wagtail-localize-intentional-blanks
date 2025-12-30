#!/bin/bash
set -e

echo "Setting up the wagtail-localize-intentional-blanks example project..."

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run migrations
echo "Running migrations..."
python manage.py migrate

# Create superuser
echo ""
echo "Creating superuser account..."
echo "Username: admin"
echo "Password: admin"
echo ""
python manage.py createsuperuser --noinput --username admin --email admin@example.com || true
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
try:
    user = User.objects.get(username='admin')
    user.set_password('admin')
    user.save()
    print('Superuser password set to: admin')
except User.DoesNotExist:
    pass
EOF

# Create locales
echo "Creating locales..."
python manage.py shell << EOF
from wagtail.models import Locale
Locale.objects.get_or_create(language_code='en')
Locale.objects.get_or_create(language_code='fr')
Locale.objects.get_or_create(language_code='es')
Locale.objects.get_or_create(language_code='de')
print('Locales created: en, fr, es, de')
EOF

# Create example content
echo ""
python manage.py setup_demo

echo ""
echo "============================================"
echo "Setup complete!"
echo "============================================"
echo ""
echo "Run the development server with:"
echo "  python manage.py runserver"
echo ""
echo "Then visit:"
echo "  http://localhost:8000/admin/"
echo ""
echo "Login credentials:"
echo "  Username: admin"
echo "  Password: admin"
echo ""
echo "To test the functionality:"
echo "1. Go to Pages in the admin"
echo "2. Select a page and choose 'Translate this page'"
echo "3. Choose a target language (e.g., French)"
echo "4. In the translation editor, use the 'Mark Do Not Translate' checkboxes"
echo "   to preserve source language values for specific segments"
echo ""
