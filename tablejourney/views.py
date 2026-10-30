from django.views import View
from django.http import HttpResponse

# class TableJourneyView(View):
    # def get(self, request):
    #     return HttpResponse("Welcome to TableJourney!")

from django.conf import settings
from django.views.generic import TemplateView

class TableJourneyView(TemplateView):
    template_name = 'tablejourney/home.html'

    def get_context_data(self, **kwargs):
        print('home')
        
        context = super().get_context_data(**kwargs)
        context['GOOGLE_CLIENT_ID'] = settings.SOCIAL_AUTH_GOOGLE_CLIENT_ID
        # print('context::',context)
        return context
        
class DashboardView(View):
    # print('dashboard')
    def get(self, request):
        print('getting dashboard')
        return HttpResponse("TableJourney Dashboard!")
