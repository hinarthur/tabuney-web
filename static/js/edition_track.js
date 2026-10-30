// 版本詳細頁的功能使用追蹤（Flowchart / Guide 兩個分頁專用）。
//
// flowchart 與講稿現在各自是一個獨立頁面，內容直接嵌在該頁 HTML 裡，沒有
// 獨立請求可以計數，所以由頁面載入時呼叫一次 window.trackFlowchart('open') /
// window.trackScript() 回報。只在已登入時送：匿名要送的話 ActivityTrackView
// 會要求前端自產 session_id，那等於發一個追蹤 ID 給不知情的訪客，違反站方的
// 匿名零識別碼原則。
//
// 這支檔案只在 flowchart / script 兩頁載入，edition_detail.js 只在 rulesbot
// 頁載入，兩者永不同頁，所以 getCookie 重複定義不會撞到。

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

var _sentOnce = {};

function _trackFeature(eventType, meta, once) {
    var ctx = window.editionInteraction || {};
    if (!ctx.isAuthenticated || !ctx.editionId) { return; }

    // 一次頁面載入只回報一次（重新整理才會再算一次）
    if (once) {
        if (_sentOnce[eventType]) { return; }
        _sentOnce[eventType] = true;
    }

    var payloadMeta = { edition_id: ctx.editionId };
    for (var k in (meta || {})) { payloadMeta[k] = meta[k]; }

    // fire-and-forget：追蹤失敗不該影響使用者，所以不檢查回應也不擋 UI
    fetch('/api/members/activity_track/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        credentials: 'same-origin',
        // flowchart 的 translate 會立刻導航離開，沒有 keepalive 請求會被瀏覽器取消
        keepalive: true,
        body: JSON.stringify({
            event_type: eventType,
            page: 'editionDetail',
            meta: payloadMeta
        })
    }).catch(function () { /* 追蹤失敗就算了 */ });
}

window.trackFlowchart = function (action) {
    var pill = document.querySelector('.flowchart-ruleset-pill.active[data-ruleset-key]');
    _trackFeature(
        'flowchart_' + action,
        { ruleset: pill ? pill.getAttribute('data-ruleset-key') : null },
        action === 'open'
    );
};

window.trackScript = function () {
    // 講稿有付費牆（can_view_script）。撞到付費牆和真的讀到講稿是兩件事：
    // 前者是升級漏斗的訊號，後者才是功能使用量，兩個都要能分辨。
    var pane = document.querySelector('.script-pane');
    var locked = pane ? !!pane.querySelector('.script-locked-notice') : false;
    _trackFeature(locked ? 'script_locked' : 'script_open', {}, true);
};
