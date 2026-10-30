"""Django system check：偵測 Tier.limits 裡未在 member/features.py 註冊的
key。不擋 save、不擋 migrate，只在 `manage.py check`（含 runserver 啟動、
CI）時提醒——低成本的 drift 偵測，避免 key 打錯字/漏加時完全無聲無息。"""
from django.core.checks import Warning, register


@register()
def check_tier_limits_keys(app_configs, **kwargs):
    from .features import FEATURES
    from .models import Tier

    warnings = []
    try:
        tiers = list(Tier.objects.all())
    except Exception:
        # DB 可能還沒 migrate（例如全新環境跑 migrate 前的 check），略過即可
        return warnings

    for tier in tiers:
        limits = tier.limits if isinstance(tier.limits, dict) else {}
        unknown = set(limits) - set(FEATURES)
        if unknown:
            warnings.append(Warning(
                f"Tier '{tier.code}' 的 limits 有未在 member.features.FEATURES "
                f"註冊的 key：{sorted(unknown)}",
                hint="請將這些 key 加入 registry，或確認可以安全移除。",
                id='member.W001',
            ))
    return warnings
