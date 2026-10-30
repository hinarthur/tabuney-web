"""Overview 橫幅右側示意流程圖的節點文字（三條泳道的標題與九個節點）。"""

from django.db import migrations

STRINGS = {
    'home.overview.art.setup': {
        'en': 'Setup', 'zh': '設置', 'ja': '準備', 'de': 'Aufbau', 'fr': 'Mise en place', 'es': 'Preparación',
    },
    'home.overview.art.prepare': {
        'en': 'Prepare the game', 'zh': '準備遊戲', 'ja': 'ゲームを準備する',
        'de': 'Spiel vorbereiten', 'fr': 'Préparer le jeu', 'es': 'Preparar el juego',
    },
    'home.overview.art.deal': {
        'en': 'Deal cards', 'zh': '發牌', 'ja': 'カードを配る',
        'de': 'Karten austeilen', 'fr': 'Distribuer les cartes', 'es': 'Repartir las cartas',
    },
    'home.overview.art.starter': {
        'en': 'Starting player', 'zh': '起始玩家', 'ja': 'スタートプレイヤー',
        'de': 'Startspieler', 'fr': 'Premier joueur', 'es': 'Jugador inicial',
    },
    'home.overview.art.gameplay': {
        'en': 'Gameplay', 'zh': '遊戲流程', 'ja': 'ゲームの流れ',
        'de': 'Spielablauf', 'fr': 'Déroulement', 'es': 'Desarrollo',
    },
    'home.overview.art.turn': {
        'en': 'Take your turn', 'zh': '輪到你的回合', 'ja': '自分の手番を行う',
        'de': 'Am Zug sein', 'fr': 'Jouer son tour', 'es': 'Jugar tu turno',
    },
    'home.overview.art.choose': {
        'en': 'Choose an action', 'zh': '選擇行動', 'ja': 'アクションを選ぶ',
        'de': 'Aktion wählen', 'fr': 'Choisir une action', 'es': 'Elegir una acción',
    },
    'home.overview.art.resolve': {
        'en': 'Resolve effect', 'zh': '結算效果', 'ja': '効果を解決する',
        'de': 'Effekt abhandeln', 'fr': 'Résoudre l’effet', 'es': 'Resolver el efecto',
    },
    'home.overview.art.endgame': {
        'en': 'End Game', 'zh': '遊戲結束', 'ja': 'ゲーム終了',
        'de': 'Spielende', 'fr': 'Fin de partie', 'es': 'Fin del juego',
    },
    'home.overview.art.trigger': {
        'en': 'Trigger end condition', 'zh': '觸發結束條件', 'ja': '終了条件を満たす',
        'de': 'Endbedingung erreichen', 'fr': 'Déclencher la fin', 'es': 'Cumplir la condición final',
    },
    'home.overview.art.scoring': {
        'en': 'Final scoring', 'zh': '最終計分', 'ja': '最終得点計算',
        'de': 'Schlusswertung', 'fr': 'Décompte final', 'es': 'Puntuación final',
    },
    'home.overview.art.winner': {
        'en': 'Determine the winner', 'zh': '決定勝者', 'ja': '勝者を決める',
        'de': 'Sieger ermitteln', 'fr': 'Désigner le vainqueur', 'es': 'Determinar al ganador',
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
        ('translation', '0047_remove_home_hero_stepflow_strings'),
    ]

    operations = [
        migrations.RunPython(add_strings, remove_strings),
    ]
