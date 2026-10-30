/*
 * RulebookScript admin 表單的逐級收窄：
 *   edition → rulebook → (ruleset, source_flowchart)
 *
 * 上游一改動，下游就重新抓選項並清空舊值，避免存出「rulebook 不屬於 edition」或
 * 「ruleset 沒有對應 RulebookNode」這類必定生成失敗的組合。
 * 伺服器端 RulebookScriptAdminForm.clean() 有同樣的驗證，這裡只負責即時性。
 *
 * 注意：Django 的 Media 合併會把本檔排在 admin/js/jquery.init.js 之前，載入當下
 * django.jQuery 還不存在，所以一切都要等 DOMContentLoaded 之後再取。
 */
(function () {
    'use strict';

    function boot() {
        if (typeof django === 'undefined' || !django.jQuery) {
            return;
        }
        var $ = django.jQuery;

        var $edition = $('#id_edition');
        var $rulebook = $('#id_rulebook');
        var $ruleset = $('#id_ruleset');
        var $flowchart = $('#id_source_flowchart');

        if (!$rulebook.length) {
            return;
        }

        var url = $rulebook.data('options-url');
        if (!url) {
            return;
        }

        var EMPTY = '---------';

        // 重建 select 的 options；keep 為要保留的既有值（載入當下用）
        function fill($select, items, keep, placeholder) {
            if (!$select.length) {
                return;
            }
            var current = keep !== undefined ? keep : $select.val();
            $select.empty();
            $select.append($('<option>').val('').text(placeholder || EMPTY));
            $.each(items, function (i, item) {
                var value = typeof item === 'string' ? item : item.id;
                var text = typeof item === 'string' ? item : item.text;
                var $opt = $('<option>').val(value).text(text);
                if (current && String(current) === String(value)) {
                    $opt.prop('selected', true);
                }
                $select.append($opt);
            });
        }

        function load(params, done) {
            $.getJSON(url, params).done(done).fail(function () {
                // 抓不到就維持現狀，交給送出時的伺服器端驗證處理
            });
        }

        // edition 變更 → 重抓 rulebook，並清空更下游
        function reloadRulebooks(keep) {
            var edition = $edition.val();
            if (!edition) {
                fill($rulebook, [], null, '請先選擇 Edition');
                fill($ruleset, [], null, '請先選擇 Rulebook');
                fill($flowchart, [], null, '請先選擇 Rulebook');
                return;
            }
            load({ edition: edition }, function (data) {
                fill($rulebook, data.rulebooks, keep);
                lastRulebook = $rulebook.val();
                reloadRulebookChildren(undefined, undefined);
            });
        }

        // rulebook 變更 → 重抓 ruleset 與 flowchart
        function reloadRulebookChildren(keepRuleset, keepFlowchart) {
            var rulebook = $rulebook.val();
            if (!rulebook) {
                fill($ruleset, [], null, '請先選擇 Rulebook');
                fill($flowchart, [], null, '請先選擇 Rulebook');
                return;
            }
            load({ rulebook: rulebook }, function (data) {
                fill($ruleset, data.rulesets, keepRuleset);
                fill($flowchart, data.flowcharts, keepFlowchart, '（不指定，自動比對）');
            });
        }

        // select2 初始化時會對 #id_edition 觸發一次 change，值其實沒變。若不擋掉，
        // 編輯既有資料一進頁面就會被當成「使用者改了 edition」而清空下游的既有選取。
        var lastEdition = $edition.val();
        var lastRulebook = $rulebook.val();

        // edition 是 select2 欄位，change 由 jQuery 觸發，必須用 django.jQuery 監聽
        $edition.on('change', function () {
            var value = $edition.val();
            if (value === lastEdition) {
                return;
            }
            lastEdition = value;
            lastRulebook = null;
            reloadRulebooks(null);
        });
        $rulebook.on('change', function () {
            var value = $rulebook.val();
            if (value === lastRulebook) {
                return;
            }
            lastRulebook = value;
            reloadRulebookChildren(null, null);
        });

        // 初次載入：edition 已有值但 rulebook 還沒有選項時補齊，並保留目前選擇
        if ($edition.val() && !$rulebook.find('option').filter(function () {
            return this.value !== '';
        }).length) {
            reloadRulebooks($rulebook.val());
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
