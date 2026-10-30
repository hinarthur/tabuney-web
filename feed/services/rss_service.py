# feed/services/rss_service.py
import feedparser
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from feed.models import Rss

def discover_rss(url: str):
    feed = feedparser.parse(url)
    if feed.bozo == 0 and feed.feed:
        return {
            'rss': url,
            'sitename': feed.feed.get('title'),
            'lang': feed.feed.get('language'),
            'logo': None,
        }

    resp = requests.get(url, timeout=10)
    soup = BeautifulSoup(resp.content, 'html.parser')

    links = soup.find_all('link', type=[
        'application/rss+xml',
        'application/atom+xml'
    ])

    for link in links:
        rss_url = urljoin(url, link.get('href'))
        feed = feedparser.parse(rss_url)
        if feed.bozo == 0:
            return {
                'rss': rss_url,
                'sitename': feed.feed.get('title'),
                'lang': feed.feed.get('language'),
                'logo': None,
            }

    return None