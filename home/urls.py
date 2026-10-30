from django.urls import path

from .views import HomeView

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
]

# 原本這裡有 /de /es /fr /jp /zh 五條，各自指向 index_de.html 之類的 template，
# 但那些檔案從來沒存在過，任何人點進去都是 500。語言前綴會在 Phase 3 由
# i18n_patterns 正式接手（/de/ /es/ /fr/ /ja/ /zh/，注意是 ja 不是 jp）。
