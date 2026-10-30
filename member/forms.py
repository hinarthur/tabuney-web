from django import forms

from .features import FEATURES, FeatureKind, FeatureStatus
from .models import Tier


def _build_feature_field(spec):
    help_text = spec.description
    if spec.status is FeatureStatus.UNREFERENCED:
        help_text = f"[未使用] {help_text}"
    if spec.kind is FeatureKind.BOOL:
        return forms.BooleanField(required=False, label=spec.label, help_text=help_text)
    return forms.IntegerField(
        required=False, label=spec.label,
        help_text=help_text + "（-1=無限, 0=停用）",
    )


class TierLimitsForm(forms.ModelForm):
    """依 member/features.py 的 registry 動態產生一個欄位/一個 flag 的
    結構化編輯表單，取代原本裸 JSON textarea 手打 key 名稱的方式。

    feat__<key> 這批欄位是在 class body 之後、用迴圈補成 class attribute
    （見檔案最後），不是在 __init__ 動態塞進 self.fields——這是必要的：
    Django admin 的 ModelAdmin.get_form() 會依 fieldsets 用
    modelform_factory() 重新包一層 TierLimitsForm 的 subclass，那個機制
    只認得「class 建立當下就存在」的欄位（declared_fields），只存在於某
    個 instance 的 self.fields 不會被看見，會直接丟 FieldError。

    未在 registry 內的既有 key（理論上不該有，但保險起見）會原樣保留
    寫回 limits，不會因為表單只認得註冊過的 key 就被靜默洗掉。
    """

    class Meta:
        model = Tier
        fields = ['code', 'name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.limits if isinstance(self.instance.limits, dict) else {}
        self._unknown_keys = {k: v for k, v in current.items() if k not in FEATURES}

        # class 級欄位已經存在（見檔案最後的迴圈），這裡只補上依 instance
        # 現值算出的 initial，不重新建立欄位物件。
        for key, spec in FEATURES.items():
            field_name = f"feat__{key}"
            if field_name not in self.fields:
                continue
            raw = current.get(key, spec.default)
            if spec.kind is FeatureKind.BOOL:
                try:
                    self.initial[field_name] = int(raw) != 0
                except (TypeError, ValueError):
                    self.initial[field_name] = False
            else:
                try:
                    self.initial[field_name] = int(raw)
                except (TypeError, ValueError):
                    self.initial[field_name] = spec.default

    def clean(self):
        cleaned = super().clean()
        limits = dict(self._unknown_keys)
        for key, spec in FEATURES.items():
            field_name = f"feat__{key}"
            val = cleaned.get(field_name)
            if spec.kind is FeatureKind.BOOL:
                limits[key] = 1 if val else 0
            else:
                limits[key] = int(val) if val not in (None, '') else spec.default
        cleaned['limits'] = limits
        return cleaned

    def save(self, commit=True):
        self.instance.limits = self.cleaned_data['limits']
        return super().save(commit=commit)


# feat__<key> 必須是 class attribute 才會被 Django 的 declared_fields 機制
# 認得（見上面 docstring）。TierLimitsForm.declared_fields / base_fields 在
# class 建立當下已經是固定的 dict 物件，這裡用原地 update()（不是重新賦值）
# 補上，讓之後任何依 TierLimitsForm 建立的 subclass（包括 admin 的
# modelform_factory）都能讀到最新內容。
_feature_fields = {f"feat__{k}": _build_feature_field(s) for k, s in FEATURES.items()}
TierLimitsForm.declared_fields.update(_feature_fields)
TierLimitsForm.base_fields.update(_feature_fields)
