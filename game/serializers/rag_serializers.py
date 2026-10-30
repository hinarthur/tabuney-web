# game/serializers/rag_serializers.py
"""
RAG API Serializers
"""
from rest_framework import serializers


class QARequestSerializer(serializers.Serializer):
    """問答請求"""
    question = serializers.CharField(
        max_length=1000,
        help_text="用戶問題"
    )
    top_k = serializers.IntegerField(
        default=8,
        min_value=1,
        max_value=20,
        help_text="檢索數量"
    )
    category = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="可選：只搜特定分類（setup/gameplay/scoring 等）"
    )


class SourceSerializer(serializers.Serializer):
    """來源資訊"""
    index = serializers.IntegerField()
    chunk_id = serializers.CharField()
    start_page = serializers.IntegerField(allow_null=True)
    end_page = serializers.IntegerField(allow_null=True)
    heading = serializers.CharField()
    category = serializers.CharField()
    preview = serializers.CharField()
    score = serializers.FloatField()
    language = serializers.CharField()


class QAResponseSerializer(serializers.Serializer):
    """問答回應"""
    answer = serializers.CharField()
    sources = SourceSerializer(many=True)
    metadata = serializers.DictField(required=False)


class QADebugResponseSerializer(QAResponseSerializer):
    """問答回應（含 debug 資訊）"""
    retrieved_chunks = serializers.ListField(required=False)


# ===== Flowchart =====

class FlowchartQueryParamsSerializer(serializers.Serializer):
    """Flowchart 查詢參數"""
    DETAIL_CHOICES = (("concise", "Concise"), ("detailed", "Detailed"))
    FORMAT_CHOICES = (("json", "JSON"), ("reactflow", "React Flow"))

    detail = serializers.ChoiceField(choices=DETAIL_CHOICES, default="detailed")
    ruleset = serializers.CharField(default="basic", max_length=100)
    edition_id = serializers.UUIDField(required=False, allow_null=True)
    regenerate = serializers.BooleanField(default=False)
    # 注意：不能叫 `format`，會被 DRF 內容協商攔截
    render = serializers.ChoiceField(choices=FORMAT_CHOICES, default="json")


class FlowchartResponseSerializer(serializers.Serializer):
    """Flowchart 回應"""
    json = serializers.DictField()
    react_flow = serializers.DictField(required=False, allow_null=True)
    is_adjusted = serializers.BooleanField(required=False)
    source_chunks = serializers.ListField(child=serializers.CharField())
    cached = serializers.BooleanField()
    generated_at = serializers.DateTimeField()
    llm_model = serializers.CharField()
    prompt_version = serializers.CharField()


# ===== Script (game master 講稿) =====

class ScriptResponseSerializer(serializers.Serializer):
    """講稿回應（只出已審核講稿；不暴露 persona/atmosphere 原始欄位）"""
    title = serializers.CharField()
    script_text = serializers.CharField()
    language = serializers.CharField()
    is_adjusted = serializers.BooleanField()
    generated_at = serializers.DateTimeField(allow_null=True)
    prompt_version = serializers.CharField()