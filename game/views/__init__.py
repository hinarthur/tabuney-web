# 把原本 views.py 的內容 re-export，保持舊 import 相容
from .original_views import *

# 或者明確列出
# from .original_views import YourView1, YourView2

from .chat_views import ChatView, MessageFeedbackView, ClearChatView, InteractionAPIView, CollectionAPIView
from .rag_views import RulebookQAView, RulebookFlowchartView, RulebookFlowchartAdjustView, RulebookScriptView