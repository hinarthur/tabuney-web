"""Cache-busting static URLs: ``{% static_v 'css/theme.css' %}`` -> ``/static/css/theme.css?v=<mtime>``.

The version is the file's modification time, so editing a static file is enough
to make browsers fetch it again — no hand-bumped ``?v=N`` in templates.
"""
import os

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


def versioned_static(path: str) -> str:
    """static(path) plus ``?v=<mtime>``; plain static(path) if the file can't be found."""
    url = static(path)
    try:
        found = finders.find(path)
        if not found and getattr(settings, "STATIC_ROOT", None):
            found = os.path.join(settings.STATIC_ROOT, path)
        if found and os.path.isfile(found):
            return f"{url}?v={int(os.path.getmtime(found))}"
    except OSError:
        pass
    return url


@register.simple_tag
def static_v(path):
    return versioned_static(path)
