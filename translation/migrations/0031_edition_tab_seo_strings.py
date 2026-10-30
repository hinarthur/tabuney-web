"""版本詳細頁四個分頁各自的 meta description 字串。

四個分頁拆成獨立頁面後，如果 description 還是共用同一段（原本是 edition.summary），
四個網址在搜尋結果與 AI 回答引擎眼中仍然長得一樣。這裡給 rulesbot / flowchart /
script 三頁各自一段只有那一頁成立的描述；info 頁繼續用 summary —— 那段本來就是在
描述遊戲本身，最適合 info。

{% t %} 沒有插值能力，所以沿用專案既有的 prefix/suffix 拆句慣例（見
chat.opening.prefix / .suffix）。flowchart 那組中間還要插入階段數與步驟數，
所以拆成 prefix + 名稱 + mid + 階段數 + phases + 步驟數 + steps。
"""

from django.db import migrations

STRINGS = {
    # ── Rulesbot ──────────────────────────────────────────────────────
    'seo.game.chat.desc.prefix': {
        'en': 'Ask any rules question about ',
        'zh': '',
        'ja': '',
        'de': 'Stelle jede Regelfrage zu ',
        'fr': 'Posez toutes vos questions de règles sur ',
        'es': 'Haz cualquier pregunta sobre las reglas de ',
    },
    'seo.game.chat.desc.suffix': {
        'en': ' and get an answer that cites the rulebook passage it came from.',
        'zh': ' 的規則隨問隨答，每個答案都標明出自規則書的哪一段。',
        'ja': ' のルールについて何でも質問できます。回答にはルールブックの出典が付きます。',
        'de': ' — jede Antwort nennt die Stelle im Regelheft, aus der sie stammt.',
        'fr': ' : chaque réponse cite le passage du livret de règles dont elle provient.',
        'es': ': cada respuesta cita el pasaje del reglamento del que proviene.',
    },

    # ── Flowchart ─────────────────────────────────────────────────────
    'seo.game.flowchart.desc.prefix': {
        'en': 'Turn-by-turn flowchart for ',
        'zh': '',
        'ja': '',
        'de': 'Ablaufdiagramm Zug für Zug für ',
        'fr': 'Diagramme de déroulement tour par tour pour ',
        'es': 'Diagrama de flujo turno a turno de ',
    },
    'seo.game.flowchart.desc.mid': {
        'en': ' — ',
        'zh': ' 的完整遊戲流程圖，共 ',
        'ja': ' のゲーム進行フローチャート。',
        'de': ' — ',
        'fr': ' — ',
        'es': ' — ',
    },
    'seo.game.flowchart.desc.phases': {
        'en': ' phases and ',
        'zh': ' 個階段、',
        'ja': ' フェイズ・',
        'de': ' Phasen und ',
        'fr': ' phases et ',
        'es': ' fases y ',
    },
    'seo.game.flowchart.desc.steps': {
        'en': ' steps, with a full text outline you can read without JavaScript.',
        'zh': ' 個步驟，並附不需 JavaScript 就能閱讀的文字版大綱。',
        'ja': ' ステップを、JavaScript なしでも読めるテキスト版の概要付きで掲載。',
        'de': ' Schritte, mit vollständiger Textgliederung, die auch ohne JavaScript lesbar ist.',
        'fr': " étapes, avec un sommaire textuel complet lisible sans JavaScript.",
        'es': ' pasos, con un esquema de texto completo legible sin JavaScript.',
    },

    # ── GM 講稿 ───────────────────────────────────────────────────────
    'seo.game.script.desc.prefix': {
        'en': 'Host script for ',
        'zh': '',
        'ja': '',
        'de': 'Moderationsskript für ',
        'fr': "Script d'animation pour ",
        'es': 'Guion de anfitrión para ',
    },
    'seo.game.script.desc.suffix': {
        'en': ': a first-person opening you can read aloud to set the scene and teach new players.',
        'zh': ' 的主持人開場講稿：以第一人稱寫成，照著唸就能營造氣氛並帶新手開局。',
        'ja': ' のホスト用進行台本。一人称で書かれており、読み上げるだけで雰囲気づくりと初心者へのルール説明ができます。',
        'de': ': ein Text in der Ich-Form, den du vorlesen kannst, um Stimmung zu erzeugen und Neulingen die Regeln beizubringen.',
        'fr': " : un texte à la première personne à lire à voix haute pour installer l'ambiance et expliquer les règles aux débutants.",
        'es': ': un texto en primera persona para leer en voz alta, crear ambiente y enseñar las reglas a quienes empiezan.',
    },
}


def add_strings(apps, schema_editor):
    Tribe = apps.get_model('translation', 'Tribe')
    Translation = apps.get_model('translation', 'Translation')

    for key, translations in STRINGS.items():
        for lang, value in translations.items():
            tribe = Tribe.objects.filter(language=lang).first()
            if tribe is None:
                continue
            Translation.objects.update_or_create(
                tribe=tribe, key=key,
                defaults={'value': value, 'is_synced': False},
            )


def remove_strings(apps, schema_editor):
    Translation = apps.get_model('translation', 'Translation')
    Translation.objects.filter(key__in=STRINGS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0030_color_vision_not_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
