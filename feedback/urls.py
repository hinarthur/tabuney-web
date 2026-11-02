from django.urls import path

from feedback.views import SurveyResponseCreateView, SurveyView

app_name = "feedback"

urlpatterns = [
    path("surveys/<int:survey_id>/responses/", SurveyResponseCreateView.as_view(), name="survey-respond"),
    path("surveys/<str:kind>/", SurveyView.as_view(), name="survey"),
]
