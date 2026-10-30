"""移除已下架 RN app（tjapp）專用的 67 個翻譯 key。

這批 key 用「英文句子當 key」的形式（app 端 en 直接 fallback 用 key，
所以從來沒有 en 列），跟網站用的點分 key（如 seo.game.search.title）
格式壁壘分明。

刪除前已核實網站端零引用：
  - 模板 {% t "..." %} 的字面 key、selectors.get_translation()、
    get_translations() 三條路徑與這份清單交集為 0
  - 全站只有兩處動態組 key（membership.tier.* 與 chat.opening.*），
    都是點分格式，組不出這些英文句子
  - 網站沒有任何地方呼叫 /api/translation/<lang>/

大小寫不撞：這裡的 'Cancel' / 'Privacy Policy' / 'Terms of Use' 與網站
在用的 'cancel' / 'privacy_policy' / 'terms_of_use' 是不同字串。

用 migration 而非在 admin 手動刪，是因為 translation.views.SyncTranslationView
只有 update_or_create、沒有刪除路徑，本機刪不會連帶清掉 VPS 上的資料；
走 migration 則部署時 VPS 跑 migrate 會一併清乾淨。

影響列數：67 key × de/fr/es/ja/zh = 335 列。
"""

from django.db import migrations

APP_ONLY_KEYS = [
    '1 year',
    '3 years',
    'Ad',
    'Adding Blog',
    'Bookmark',
    'Bookmark failed',
    'Bookmark the article',
    'Bookmarked',
    'Cancel',
    'Cannot connect to the server. Please try again later.',
    'Contact',
    'Contact us',
    'Content',
    'Customize',
    'Delete',
    'Delete this?',
    'Enter your feedback',
    'Enter your name or email',
    'Error',
    'Failed to log out',
    'Failed to submit feedback. Please try again.',
    'Free',
    'Go to Settings',
    'Guest',
    'Irrelevant',
    'Loading...',
    'Logout',
    'Member',
    'Members Feature',
    'Members Only',
    'Membership',
    'My labels',
    'New label name',
    'News',
    'No results found',
    'Please check your connection.',
    'Please enter a valid blog URL or RSS URL, such as example.com.',
    'Please enter the blog URL, or directly enter the RSS URL.',
    'Price',
    'Privacy Policy',
    'Recommend',
    'Recommend RSS or website',
    'Regarding Table Journey, I think ...\\n\\n',
    'Report irrelevant',
    'Save settings',
    'Save settings to the cloud.',
    'Share',
    'Sign in',
    'Style',
    'Subscriber',
    'Subscription Plans',
    'Success',
    'System Language',
    'Table Journey Feedback',
    'Tabletop Game',
    'Tabletop game keywords',
    'Terms of Use',
    'Thanks for your suggestions. It has been successfully added to the system.',
    'Thanks!',
    'US$1 / yr',
    'Unable to find valid RSS, please confirm the URL or enter the RSS URL directly.',
    'Upgrade',
    'View',
    'Wrong Format',
    'Your feedback has been submitted!',
    'Your subscription has',
    'days remaining.',
]


def remove_strings(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key__in=APP_ONLY_KEYS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0020_seo_page_titles'),
    ]

    operations = [
        # 不可逆：翻譯文字刪掉就沒了，硬要救請從備份還原。
        migrations.RunPython(remove_strings, migrations.RunPython.noop),
    ]
