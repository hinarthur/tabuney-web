"""
新增 FAQ 頁面的問答內容與 SEO 描述翻譯字串（en/zh/ja/de/fr/es）。
"""

from django.db import migrations

STRINGS = {
    'faq.title': {
        'en': 'Frequently Asked Questions',
        'zh': '常見問答',
        'ja': 'よくある質問',
        'de': 'Häufig gestellte Fragen',
        'fr': 'Foire aux questions',
        'es': 'Preguntas frecuentes',
    },
    'seo.faq.description': {
        'en': 'Answers to common questions about Tabuney — the AI Rulesbot, rules flowcharts, '
              'GM scripts, membership plans, supported languages and your data.',
        'zh': 'Tabuney 常見問答：AI 規則問答機器人、規則流程圖、GM 講稿、會員方案、支援語言與資料處理相關問題。',
        'ja': 'Tabuneyに関するよくある質問。AIルールボット、ルールフローチャート、GMスクリプト、'
              'メンバーシッププラン、対応言語、データの取り扱いについて。',
        'de': 'Antworten auf häufige Fragen zu Tabuney — den KI-Regelbot, Regel-Flussdiagramme, '
              'GM-Skripte, Mitgliedschaftspläne, unterstützte Sprachen und deine Daten.',
        'fr': "Réponses aux questions fréquentes sur Tabuney : le Rulesbot IA, les organigrammes de règles, "
              "les scripts de MJ, les formules d'adhésion, les langues prises en charge et vos données.",
        'es': 'Respuestas a preguntas frecuentes sobre Tabuney: el Rulesbot de IA, los diagramas de flujo de reglas, '
              'los guiones de GM, los planes de membresía, los idiomas disponibles y tus datos.',
    },
    'faq.rulesbot.question': {
        'en': 'How does the AI Rulesbot work?',
        'zh': 'AI 規則問答機器人是怎麼運作的？',
        'ja': 'AIルールボットはどう使うのですか？',
        'de': 'Wie funktioniert der KI-Regelbot?',
        'fr': 'Comment fonctionne le Rulesbot IA ?',
        'es': '¿Cómo funciona el Rulesbot de IA?',
    },
    'faq.rulesbot.answer': {
        'en': 'Search for your game, then ask the Rulesbot any rules question in plain language — it answers '
              'based on that game\'s official rulebook. Free accounts can preview it, Members get 13 questions '
              'a week, and Subscribers get unlimited questions.',
        'zh': '先搜尋你的遊戲，再用一般的口語向 Rulesbot 提問任何規則問題，它會依照該遊戲的官方規則書回答。'
              '免費帳號可以試用；會員每週可問 13 次；訂閱會員則不限次數。',
        'ja': 'ゲームを検索してから、Rulesbotに普段の言葉でルールについて質問してください。そのゲームの'
              '公式ルールブックに基づいて回答します。無料アカウントはお試し利用、メンバーは週13回、'
              'サブスクライバーは無制限に質問できます。',
        'de': 'Suche zuerst dein Spiel und stelle dem Rulesbot dann jede Regelfrage in normaler Sprache — er '
              'antwortet anhand der offiziellen Spielregeln. Kostenlose Konten können ihn testen, Mitglieder '
              'erhalten 13 Fragen pro Woche, Abonnenten unbegrenzt viele.',
        'fr': "Recherchez d'abord votre jeu, puis posez n'importe quelle question de règles au Rulesbot en "
              "langage courant — il répond en s'appuyant sur les règles officielles de ce jeu. Les comptes "
              "gratuits peuvent l'essayer, les Membres ont 13 questions par semaine, les Abonnés en ont un "
              "nombre illimité.",
        'es': 'Busca primero tu juego y luego pregúntale al Rulesbot cualquier duda de reglas con tus propias '
              'palabras: responde basándose en el reglamento oficial de ese juego. Las cuentas gratuitas pueden '
              'probarlo, los Miembros tienen 13 preguntas por semana y los Suscriptores tienen preguntas '
              'ilimitadas.',
    },
    'faq.flowchart.question': {
        'en': 'What is the rules flowchart?',
        'zh': '規則流程圖是什麼？',
        'ja': 'ルールフローチャートとは何ですか？',
        'de': 'Was ist das Regel-Flussdiagramm?',
        'fr': "Qu'est-ce que l'organigramme des règles ?",
        'es': '¿Qué es el diagrama de flujo de reglas?',
    },
    'faq.flowchart.answer': {
        'en': "A visual, step-by-step flowchart of a game's setup and turn structure, so you can follow the "
              'rules without reading the whole rulebook. Members can browse the basic ruleset in English; '
              'Subscribers get every ruleset in all supported languages, plus printing.',
        'zh': '以視覺化的方式，一步步呈現遊戲的開場設置與回合流程，讓你不用讀完整本規則書也能跟著玩。'
              '會員可瀏覽英文版的基本規則流程圖；訂閱會員則可瀏覽所有語言的所有規則版本，並能列印。',
        'ja': 'ゲームのセットアップとターンの流れを、視覚的にステップごとに示したものです。ルールブック'
              '全体を読まなくてもプレイできます。メンバーは英語版の基本ルールセットを閲覧でき、'
              'サブスクライバーは全言語・全ルールセットの閲覧と印刷が可能です。',
        'de': 'Ein visuelles Schritt-für-Schritt-Flussdiagramm für Aufbau und Rundenablauf eines Spiels, mit '
              'dem du den Regeln folgen kannst, ohne das ganze Regelheft zu lesen. Mitglieder können das '
              'englische Basisregelwerk durchsuchen, Abonnenten erhalten jedes Regelwerk in allen Sprachen '
              'sowie Druckfunktion.',
        'fr': "Un organigramme visuel, étape par étape, de la mise en place et du déroulement des tours d'un "
              "jeu, pour suivre les règles sans lire tout le livret. Les Membres peuvent consulter le "
              "règlement de base en anglais ; les Abonnés ont accès à tous les règlements dans toutes les "
              "langues, avec impression.",
        'es': 'Un diagrama de flujo visual, paso a paso, de la preparación y el desarrollo de turnos de un '
              'juego, para seguir las reglas sin leer todo el manual. Los Miembros pueden consultar el '
              'reglamento básico en inglés; los Suscriptores tienen acceso a todos los reglamentos en todos '
              'los idiomas, con impresión incluida.',
    },
    'faq.script.question': {
        'en': 'What is a GM script?',
        'zh': 'GM 講稿是什麼？',
        'ja': 'GMスクリプトとは何ですか？',
        'de': 'Was ist ein GM-Skript?',
        'fr': "Qu'est-ce qu'un script de MJ ?",
        'es': '¿Qué es un guion de GM?',
    },
    'faq.script.answer': {
        'en': 'A ready-to-read, first-person script a game master can read aloud to explain setup and rules '
              'in under 5 minutes — great for teaching a game at the table. GM scripts are available to '
              'Subscribers.',
        'zh': '一份可直接唸出來的第一人稱講稿，讓主持人在 5 分鐘內就能講解完開場設置與規則，'
              '很適合在桌邊教學。GM 講稿是訂閱會員的專屬功能。',
        'ja': 'ゲームマスターがそのまま読み上げられる一人称のスクリプトで、5分以内にセットアップと'
              'ルールを説明できます。卓上での説明にぴったりです。GMスクリプトはサブスクライバー限定の'
              '機能です。',
        'de': 'Ein vorlesefertiges Skript in Ich-Form, mit dem ein Spielleiter Aufbau und Regeln in unter '
              '5 Minuten erklären kann — ideal, um ein Spiel direkt am Tisch zu vermitteln. GM-Skripte '
              'stehen Abonnenten zur Verfügung.',
        'fr': "Un script à la première personne, prêt à être lu, qui permet à un maître du jeu d'expliquer "
              "la mise en place et les règles en moins de 5 minutes — idéal pour enseigner un jeu à table. "
              "Les scripts de MJ sont réservés aux Abonnés.",
        'es': 'Un guion en primera persona, listo para leer, con el que un director de juego puede explicar '
              'la preparación y las reglas en menos de 5 minutos, ideal para enseñar un juego en la mesa. '
              'Los guiones de GM están disponibles para Suscriptores.',
    },
    'faq.plans.question': {
        'en': "What's the difference between Free, Member and Subscriber?",
        'zh': '免費、會員、訂閱會員有什麼差別？',
        'ja': '無料・メンバー・サブスクリプションの違いは何ですか？',
        'de': 'Was ist der Unterschied zwischen Free, Mitglied und Abonnent?',
        'fr': 'Quelle est la différence entre Gratuit, Membre et Abonné ?',
        'es': '¿Cuál es la diferencia entre Gratis, Miembro y Suscriptor?',
    },
    'faq.plans.answer': {
        'en': 'Free lets you browse games and view PLATVM competency tags. Members can save a collection and '
              'preferences, ask the Rulesbot up to 13 times a week, and browse the basic flowchart in English. '
              'Subscribers get unlimited Rulesbot questions, every flowchart ruleset in all languages with '
              'printing, and GM scripts. See the Membership page for full details.',
        'zh': '免費帳號可以瀏覽遊戲與查看 PLATVM 素養標籤。會員可以儲存收藏與偏好設定、每週向 Rulesbot '
              '提問最多 13 次，並瀏覽英文版的基本流程圖。訂閱會員則不限次數提問、可瀏覽所有語言的所有'
              '規則流程圖並列印，還能使用 GM 講稿。詳細內容請見會員方案頁面。',
        'ja': '無料アカウントはゲームの閲覧とPLATVMコンピテンシータグの確認ができます。メンバーは'
              'コレクションと設定の保存、週13回までのRulesbotへの質問、英語版の基本フローチャートの'
              '閲覧が可能です。サブスクライバーはRulesbotへの質問が無制限、全言語・全ルールセットの'
              'フローチャート閲覧と印刷、GMスクリプトが利用できます。詳しくはメンバーシップページを'
              'ご覧ください。',
        'de': 'Free ermöglicht das Durchsuchen von Spielen und die Ansicht der PLATVM-Kompetenz-Tags. '
              'Mitglieder können eine Sammlung und Einstellungen speichern, bis zu 13 Fragen pro Woche an '
              'den Rulesbot stellen und das englische Basis-Flussdiagramm durchsuchen. Abonnenten erhalten '
              'unbegrenzte Rulesbot-Fragen, jedes Flussdiagramm-Regelwerk in allen Sprachen inklusive Druck '
              'sowie GM-Skripte. Alle Details findest du auf der Mitgliedschaftsseite.',
        'fr': "L'offre Gratuite permet de parcourir les jeux et de consulter les tags de compétence PLATVM. "
              "Les Membres peuvent enregistrer une collection et des préférences, poser jusqu'à 13 questions "
              "par semaine au Rulesbot, et consulter l'organigramme de base en anglais. Les Abonnés "
              "bénéficient de questions illimitées au Rulesbot, de tous les règlements en organigramme dans "
              "toutes les langues avec impression, et des scripts de MJ. Voir la page Adhésion pour tous les "
              "détails.",
        'es': 'El plan Gratis permite explorar juegos y ver las etiquetas de competencia PLATVM. Los Miembros '
              'pueden guardar una colección y preferencias, hacer hasta 13 preguntas por semana al Rulesbot y '
              'consultar el diagrama de flujo básico en inglés. Los Suscriptores obtienen preguntas ilimitadas '
              'al Rulesbot, todos los reglamentos en diagrama de flujo en todos los idiomas con impresión, y '
              'guiones de GM. Consulta la página de Membresía para más detalles.',
    },
    'faq.languages.question': {
        'en': 'What languages are supported?',
        'zh': '支援哪些語言？',
        'ja': 'どの言語に対応していますか？',
        'de': 'Welche Sprachen werden unterstützt?',
        'fr': 'Quelles langues sont prises en charge ?',
        'es': '¿Qué idiomas están disponibles?',
    },
    'faq.languages.answer': {
        'en': 'The site and flowcharts are available in Deutsch, English, Español, Français, 日本語 and 中文. '
              'Use the language switcher in the header to change languages.',
        'zh': '網站與流程圖支援德文、英文、西班牙文、法文、日文與中文。可以在頁首使用語言切換選單來'
              '改變語言。',
        'ja': 'サイトとフローチャートはドイツ語、英語、スペイン語、フランス語、日本語、中国語に対応'
              'しています。ヘッダーの言語切り替えメニューから変更できます。',
        'de': 'Website und Flussdiagramme sind auf Deutsch, Englisch, Spanisch, Französisch, Japanisch und '
              'Chinesisch verfügbar. Nutze den Sprachumschalter im Header, um die Sprache zu ändern.',
        'fr': "Le site et les organigrammes sont disponibles en allemand, anglais, espagnol, français, "
              "japonais et chinois. Utilisez le sélecteur de langue dans l'en-tête pour changer de langue.",
        'es': 'El sitio y los diagramas de flujo están disponibles en alemán, inglés, español, francés, '
              'japonés y chino. Usa el selector de idioma en la cabecera para cambiarlo.',
    },
    'faq.collection.question': {
        'en': 'Do I need an account to save my collection?',
        'zh': '我需要註冊帳號才能儲存收藏嗎？',
        'ja': 'コレクションを保存するにはアカウントが必要ですか？',
        'de': 'Brauche ich ein Konto, um meine Sammlung zu speichern?',
        'fr': "Ai-je besoin d'un compte pour enregistrer ma collection ?",
        'es': '¿Necesito una cuenta para guardar mi colección?',
    },
    'faq.collection.answer': {
        'en': 'Yes. Signing in with Google lets you save owned, wishlisted and played games with your own '
              'ratings and notes. Without an account you can still browse and search games, but nothing is '
              'saved.',
        'zh': '是的。用 Google 登入後，你可以儲存已擁有、想要與玩過的遊戲，並加上自己的評分與備註。'
              '沒有帳號依然可以瀏覽與搜尋遊戲，但不會儲存任何紀錄。',
        'ja': 'はい。Googleでログインすると、所有・欲しい・プレイ済みのゲームを自分の評価やメモと'
              'ともに保存できます。アカウントがなくてもゲームの閲覧や検索は可能ですが、保存はされません。',
        'de': 'Ja. Mit der Anmeldung über Google kannst du besessene, gewünschte und gespielte Spiele mit '
              'eigenen Bewertungen und Notizen speichern. Ohne Konto kannst du weiterhin Spiele durchsuchen '
              'und suchen, aber nichts wird gespeichert.',
        'fr': 'Oui. En vous connectant avec Google, vous pouvez enregistrer les jeux possédés, souhaités et '
              'joués avec vos propres notes et évaluations. Sans compte, vous pouvez toujours parcourir et '
              'rechercher des jeux, mais rien ne sera enregistré.',
        'es': 'Sí. Al iniciar sesión con Google puedes guardar los juegos que posees, deseas y has jugado con '
              'tus propias valoraciones y notas. Sin una cuenta, puedes seguir explorando y buscando juegos, '
              'pero no se guardará nada.',
    },
    'faq.privacy.question': {
        'en': 'How is my data handled?',
        'zh': '我的資料會怎麼被處理？',
        'ja': '私のデータはどのように扱われますか？',
        'de': 'Wie werden meine Daten verarbeitet?',
        'fr': 'Comment mes données sont-elles traitées ?',
        'es': '¿Cómo se tratan mis datos?',
    },
    'faq.privacy.answer': {
        'en': "We only collect what's needed to run the service, and anonymous visitors aren't tracked with "
              'cookies or session identifiers. See our Privacy Policy for full details.',
        'zh': '我們只會收集提供服務所必需的資料，匿名訪客不會被 cookie 或 session 識別碼追蹤。'
              '詳細內容請見我們的隱私權政策。',
        'ja': 'サービスの提供に必要な情報のみを収集しており、匿名の訪問者をCookieやセッションIDで'
              '追跡することはありません。詳しくはプライバシーポリシーをご覧ください。',
        'de': 'Wir erfassen nur, was für den Betrieb des Dienstes nötig ist, und anonyme Besucher werden '
              'nicht per Cookie oder Sitzungs-ID verfolgt. Details findest du in unserer Datenschutzerklärung.',
        'fr': "Nous ne collectons que ce qui est nécessaire au fonctionnement du service, et les visiteurs "
              "anonymes ne sont pas suivis par cookies ni identifiants de session. Voir notre politique de "
              "confidentialité pour tous les détails.",
        'es': 'Solo recopilamos lo necesario para prestar el servicio, y los visitantes anónimos no son '
              'rastreados con cookies ni identificadores de sesión. Consulta nuestra política de privacidad '
              'para más detalles.',
    },
    'faq.deleteaccount.question': {
        'en': 'How do I delete my account and data?',
        'zh': '如何刪除我的帳號與資料？',
        'ja': 'アカウントとデータを削除するにはどうすればよいですか？',
        'de': 'Wie lösche ich mein Konto und meine Daten?',
        'fr': 'Comment supprimer mon compte et mes données ?',
        'es': '¿Cómo elimino mi cuenta y mis datos?',
    },
    'faq.deleteaccount.answer': {
        'en': "Email us at info@ttoper.com and we'll process your deletion request within 3 business days.",
        'zh': '請寄信到 info@ttoper.com，我們會在 3 個工作天內處理你的刪除請求。',
        'ja': 'info@ttoper.com までメールをお送りください。3営業日以内に削除リクエストを処理いたします。',
        'de': 'Schreib uns eine E-Mail an info@ttoper.com, wir bearbeiten deine Löschanfrage innerhalb von '
              '3 Werktagen.',
        'fr': 'Écrivez-nous à info@ttoper.com, nous traiterons votre demande de suppression sous 3 jours '
              'ouvrés.',
        'es': 'Escríbenos a info@ttoper.com y procesaremos tu solicitud de eliminación en un plazo de '
              '3 días hábiles.',
    },
    'footer.link.faq': {
        'en': 'FAQ',
        'zh': '常見問答',
        'ja': 'よくある質問',
        'de': 'FAQ',
        'fr': 'FAQ',
        'es': 'Preguntas frecuentes',
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
    Translation.objects.filter(key__in=list(STRINGS.keys())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('translation', '0014_membership_new_rows'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
