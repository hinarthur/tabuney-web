# initialize_site.py
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TJsite.settings")
django.setup()

from django.contrib.sites.models import Site

def create_site():
    # 確保 Site 表中沒有重複的條目
    if not Site.objects.filter(domain='localhost').exists():
        site = Site.objects.create(domain='localhost', name='Localhost')
        print("Created local site:", site)
    # if not Site.objects.filter(domain='example.com').exists():
    #     site = Site.objects.create(domain='example.com', name='My Server')
    #     print("Created server site:", site)

if __name__ == "__main__":
    create_site()
