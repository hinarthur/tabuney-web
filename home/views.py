from django.views import View
from django.http import HttpResponse
from django.views.generic import TemplateView

from stats.utils import log_page_visit

# class HomeView(View):
#     def get(self, request):
#         if getattr(request, 'subdomain', '') == '':
#             return HttpResponse("Hello from ttoper.com")
#         return HttpResponse(status=404)

class HomeView(TemplateView):
    template_name = "index.html"

    def get(self, request, *args, **kwargs):
        log_page_visit(request, 'home')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from game.selectors import random_flowchart_editions

        context = super().get_context_data(**kwargs)
        context['guide_editions'] = random_flowchart_editions(4)
        context['news_works'] = self._latest_works(getattr(self.request, 'lang', 'en'))
        context['hero_flow'] = self._hero_flow(getattr(self.request, 'lang', 'en'))
        return context


    @staticmethod
    def _hero_flow(lang):
        """hero Step Flow 示範資料，依語言快取 10 分鐘（localize 要查翻譯表）。"""
        from django.core.cache import cache
        from game.selectors import hero_step_flow

        key = f'home_hero_flow:{lang}'
        data = cache.get(key)
        if data is None:
            data = hero_step_flow(lang)
            if data is not None:
                cache.set(key, data, 600)
        return data

    @staticmethod
    def _latest_works(lang, limit=3):
        """首頁「From the tabletop world」：目前語言最新、且有配圖的文章；不足就用英文補。"""
        from feed.models import Work

        def pick(language):
            return list(
                Work.objects.filter(lang=language, irrelevant=0, image__isnull=False)
                .exclude(image='').order_by('-publishdate')[:limit]
            )

        works = pick(lang)
        if len(works) < limit and lang != 'en':
            works += pick('en')[:limit - len(works)]
        return works


class AboutView(TemplateView):
    template_name = "about.html"

    def get(self, request, *args, **kwargs):
        log_page_visit(request, 'about')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """把通用的 WebPage 換成 AboutPage，並指向組織本身。

        這讓 /about/ 成為 Organization 的官方說明頁 —— AI 引擎要驗證
        「Tabuney 是誰」時會走這條路徑。
        """
        context = super().get_context_data(**kwargs)

        from django.conf import settings
        from game.structured_data import org_id, webpage_jsonld

        # 網址要與 context processor 的 canonical 一致（含語言前綴），@id 才對得上。
        context['jsonld_nodes'] = [
            webpage_jsonld(
                settings.SITE_URL,
                settings.SITE_URL + self.request.path,
                page_type="AboutPage",
                about_id=org_id(settings.SITE_URL),
            ),
        ]
        return context


class FaqView(TemplateView):
    """FAQ 頁。模板本身不需要 view，這裡存在只為了補 FAQPage 結構化資料。

    問答內容在 DB，模板用 {% t %} 一題一題取；JSON-LD 得在 render 之前就備好，
    所以在這裡用 faq_content 的題目清單一次撈完再組節點。
    """

    template_name = "faq.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from django.conf import settings
        from game.structured_data import faq_jsonld
        from translation.selectors import get_translations

        from home.faq_content import build_questions, translation_keys

        lang = getattr(self.request, 'lang', settings.LANGUAGE_CODE)
        strings = get_translations(lang, translation_keys())

        # 網址要與 context processor 的 canonical 一致（含語言前綴），@id 才對得上。
        context['jsonld_nodes'] = [
            faq_jsonld(
                settings.SITE_URL,
                settings.SITE_URL + self.request.path,
                build_questions(strings),
            ),
        ]
        return context


class RobotsView(TemplateView):
    """robots.txt。放在 Django 而非 nginx，才進得了版控、也讀得到 SITE_URL。"""

    template_name = "robots.txt"
    content_type = "text/plain"


class LlmsTxtView(TemplateView):
    """llms.txt。跟 robots.txt 同樣走 Django：進得了版控、讀得到 SITE_URL，
    日後想加動態內容（例如近期更新的遊戲）也不用換網址。"""

    template_name = "llms.txt"
    content_type = "text/plain; charset=utf-8"