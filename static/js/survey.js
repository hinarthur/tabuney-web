/*
 * 問卷浮動按鈕（templates/feedback/partials/survey_fab.html）。
 *
 * 流程：GET 問卷 → 沒有開放中的問卷（204）或這個分頁按過「先不要」就什麼都不畫；
 * 否則畫右下角的浮動按鈕，按下開 modal，正式送出後按鈕在這次瀏覽中消失。
 *
 * 不記「填過」，也不會因為填到一半關掉 modal 而丟掉進度：關閉只是把 modal 藏起來，
 * 再按浮動按鈕會回到原本那一題、答案都還在（匿名訪客只存在這一頁的記憶體裡）。
 * 真的離開這一頁（換頁、關分頁）時，才把已答的題目補送出去。
 * 會員補送的那份就是草稿：GET 會把它帶回來（data.draft），換頁、重新整理後接著填，
 * 正式送出時伺服器原地更新同一份，不會變成兩筆。
 * 「先不要」只存 sessionStorage：關掉分頁後下次還會再出現。
 * sessionStorage 可能被瀏覽器擋掉（無痕、封鎖網站資料），讀寫一律包 try/catch。
 *
 * GET 會回一顆簽章 token，送出時帶回去（後端用來擋機器人，見 feedback/security.py）。
 *
 * 使用者輸入只用 textContent 放進 DOM，不碰 innerHTML。
 */
(function () {
    'use strict';

    var root = document.getElementById('tj-survey');
    if (!root || !window.fetch) return;

    var cfg = root.dataset;
    var kind = cfg.kind;
    var editionId = cfg.edition || '';
    var scopeKey = kind === 'edition' ? editionId : 'site';
    var DISMISS_KEY = 'tj_survey_later:' + kind + ':' + scopeKey;
    var TEXT_MAX = 2000;  // 與 feedback/views.py 的 TEXT_MAX_LENGTH 一致

    function storageGet(store, key) { try { return store.getItem(key); } catch (e) { return null; } }
    function storageSet(store, key) { try { store.setItem(key, '1'); } catch (e) { /* 被擋就算了 */ } }

    if (storageGet(window.sessionStorage, DISMISS_KEY)) return;
    if (kind === 'edition' && !editionId) return;

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text) node.textContent = text;
        return node;
    }

    var url = cfg.api + encodeURIComponent(kind) + '/?l=' + encodeURIComponent(cfg.lang || 'en') +
        (editionId ? '&edition=' + encodeURIComponent(editionId) : '');

    fetch(url, { credentials: 'same-origin' })
        .then(function (res) { return res.status === 200 ? res.json() : null; })
        .then(function (data) {
            if (!data || !data.survey) return;
            if (!data.survey.questions || !data.survey.questions.length) return;
            token = data.token || '';
            draft = data.draft || null;
            renderFab(data.survey);
        })
        .catch(function () { /* 問卷是附加功能，失敗就不顯示 */ });

    // ── 浮動按鈕 ───────────────────────────────────────────────────────────────
    var fab = null;
    var token = '';
    var draft = null;   // 會員先前沒填完的答案（匿名一律是 null）

    // 開場動畫：載入約 1 秒後展開完整 CTA，停 3.5 秒再收成圓形圖示。
    // 每個瀏覽工作階段只播一次（sessionStorage），切換遊戲時直接是收合狀態；
    // hover / 鍵盤聚焦時由 CSS 重新展開。prefers-reduced-motion 直接顯示靜態圖示。
    var INTRO_KEY = 'tj_survey_intro_seen';
    var INTRO_DELAY = 1000;
    var INTRO_HOLD = 3500;

    function reducedMotion() {
        return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    function playIntro(node) {
        if (reducedMotion() || storageGet(window.sessionStorage, INTRO_KEY)) {
            node.classList.add('is-ready');   // 直接顯示收合的圓形圖示
            return;
        }
        storageSet(window.sessionStorage, INTRO_KEY);
        node.classList.add('is-intro');       // 先以展開狀態、透明度 0 放好位置
        setTimeout(function () {
            node.classList.add('is-ready');   // 淡入完整 CTA
            setTimeout(function () { node.classList.remove('is-intro'); }, INTRO_HOLD);
        }, INTRO_DELAY);
    }

    function renderFab(survey) {
        fab = el('div', 'tj-survey-fab tj-survey-fab--' + (kind === 'site' ? 'site' : 'edition'));
        var open = el('button', 'tj-survey-fab-open');
        open.type = 'button';
        open.setAttribute('aria-haspopup', 'dialog');
        open.setAttribute('aria-label', cfg.lFab);
        var icon = el('span', 'tj-survey-fab-icon');
        icon.setAttribute('aria-hidden', 'true');
        var tpl = document.getElementById('tj-survey-icon-' + (kind === 'site' ? 'site' : 'edition'));
        if (tpl && tpl.content) icon.appendChild(tpl.content.cloneNode(true));
        open.appendChild(icon);
        var label = el('span', 'tj-survey-fab-label', cfg.lFab);
        // 全站問卷只在 beta 期間出現，展開時在文字尾端標示 BETA（品牌用語不翻譯）
        if (kind === 'site') label.appendChild(el('span', 'tj-survey-fab-beta', 'BETA'));
        open.appendChild(label);
        open.addEventListener('click', function () { openModal(survey); });

        var later = el('button', 'tj-survey-fab-later', '×');
        later.type = 'button';
        later.title = cfg.lDismiss;
        later.setAttribute('aria-label', cfg.lDismiss);
        later.addEventListener('click', function () {
            storageSet(window.sessionStorage, DISMISS_KEY);
            removeFab();
        });

        fab.appendChild(open);
        fab.appendChild(later);
        document.body.appendChild(fab);
        playIntro(fab);
    }

    function removeFab() {
        if (fab && fab.parentNode) fab.parentNode.removeChild(fab);
        fab = null;
    }

    // ── 問卷 modal ─────────────────────────────────────────────────────────────
    var modal = null;
    var lastFocus = null;

    // 填到一半離開這一頁（換頁、關分頁）就把已答的題目先送出，必填題可缺漏。
    // 關閉 modal（×、Esc、點背景）不送：只是藏起來，之後還能接著填。
    // finished＝已經正式送出過；sending＝正式送出還在途中，兩者都不再補送。
    var session = null;   // { survey, form, finished, sending, partialSent }

    function sendPartial() {
        if (!session || session.finished || session.sending || session.partialSent) return;
        var answers = collectAnswers(session.form, session.survey);
        if (!Object.keys(answers).length) return;
        session.partialSent = true;
        var survey = session.survey;
        var headers = { 'Content-Type': 'application/json' };
        if (cfg.csrf) headers['X-CSRFToken'] = cfg.csrf;
        // keepalive：頁面正在關閉 / 跳轉時請求仍會送出
        fetch(cfg.api + survey.id + '/responses/', {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: true,
            headers: headers,
            body: JSON.stringify({
                edition_id: editionId,
                page: cfg.page || window.location.pathname,
                lang: cfg.lang,
                answers: answers,
                others: collectOthers(session.form),
                partial: true,
                token: token,
                website: session.form.elements.website ? session.form.elements.website.value : ''
            })
        }).catch(function () { /* 補送失敗就算了 */ });
    }

    window.addEventListener('pagehide', function () { if (session) sendPartial(); });

    function destroyModal() {
        if (!modal) return;
        modal.parentNode.removeChild(modal);
        modal = null;
        session = null;
        document.removeEventListener('keydown', onKey);
        if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    // 還沒送出的問卷只藏起來（保留作答進度）；已送出或已關閉的才真正移除
    function closeModal() {
        if (!modal) return;
        if (!session || session.finished) { destroyModal(); return; }
        modal.style.display = 'none';
        document.removeEventListener('keydown', onKey);
        if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    function onKey(e) { if (e.key === 'Escape') closeModal(); }

    function renderQuestion(q, index) {
        var box = el('fieldset', 'tj-survey-q');
        box.dataset.qid = q.id;
        var legend = el('legend', 'tj-survey-q-text', (index + 1) + '. ' + q.text);
        if (q.required) {
            var star = el('span', 'tj-survey-required', ' *');
            star.setAttribute('aria-label', cfg.lRequired);
            legend.appendChild(star);
        }
        box.appendChild(legend);

        if (q.type === 'text') {
            var ta = el('textarea', 'tj-survey-text');
            ta.name = 'q' + q.id;
            ta.rows = 3;
            ta.maxLength = TEXT_MAX;
            ta.setAttribute('aria-label', q.text);
            box.appendChild(ta);
        } else {
            if (q.type === 'multi') box.appendChild(el('div', 'tj-survey-hint', cfg.lMulti));
            var list = el('div', 'tj-survey-choices');
            q.choices.forEach(function (c) {
                var label = el('label', 'tj-survey-choice');
                var input = document.createElement('input');
                input.type = q.type === 'multi' ? 'checkbox' : 'radio';
                input.name = 'q' + q.id;
                input.value = c.id;
                label.appendChild(input);
                label.appendChild(el('span', null, c.text));
                list.appendChild(label);
                if (c.other) {
                    // 「其他」：選了才出現輸入欄
                    var otherBox = el('input', 'tj-survey-other');
                    otherBox.type = 'text';
                    otherBox.name = 'other' + c.id;
                    otherBox.maxLength = TEXT_MAX;
                    otherBox.hidden = true;
                    otherBox.setAttribute('aria-label', c.text);
                    list.appendChild(otherBox);
                    input.dataset.otherFor = c.id;
                }
            });
            box.appendChild(list);
        }
        // 單選時換了別的選項也要收起「其他」欄
        box.addEventListener('change', function () {
            box.querySelectorAll('input[data-other-for]').forEach(function (inp) {
                var field = box.querySelector('input[name="other' + inp.dataset.otherFor + '"]');
                field.hidden = !inp.checked;
                if (inp.checked && inp === document.activeElement) field.focus();
            });
        });
        box.appendChild(el('div', 'tj-survey-q-error'));
        return box;
    }

    function applyDraft(form, survey, draft) {
        var answers = draft.answers || {};
        var others = draft.others || {};
        survey.questions.forEach(function (q) {
            var v = answers[q.id];
            if (v === undefined || v === null) return;   // 題目被改過、或沒答的就略過
            if (q.type === 'text') {
                var field = form.elements['q' + q.id];
                if (field) field.value = v;
                return;
            }
            var ids = (Array.isArray(v) ? v : [v]).map(String);
            form.querySelectorAll('input[name="q' + q.id + '"]').forEach(function (inp) {
                if (ids.indexOf(String(inp.value)) < 0) return;
                inp.checked = true;
                inp.dispatchEvent(new Event('change', { bubbles: true }));   // 展開「其他」欄
            });
        });
        Object.keys(others).forEach(function (cid) {
            var f = form.querySelector('input[name="other' + cid + '"]');
            if (f) f.value = others[cid];
        });
    }

    // 被選中的「其他」選項填的字：{選項 id: 文字}
    function collectOthers(form) {
        var others = {};
        form.querySelectorAll('input[data-other-for]').forEach(function (inp) {
            if (!inp.checked) return;
            var field = form.querySelector('input[name="other' + inp.dataset.otherFor + '"]');
            var v = field ? field.value.trim() : '';
            if (v) others[inp.dataset.otherFor] = v;
        });
        return others;
    }

    function collectAnswers(form, survey) {
        var answers = {};
        survey.questions.forEach(function (q) {
            var name = 'q' + q.id;
            if (q.type === 'text') {
                var v = (form.elements[name].value || '').trim();
                if (v) answers[q.id] = v;
            } else {
                var picked = Array.prototype.filter.call(
                    form.querySelectorAll('input[name="' + name + '"]'),
                    function (i) { return i.checked; }
                ).map(function (i) { return parseInt(i.value, 10); });
                if (picked.length) answers[q.id] = q.type === 'multi' ? picked : picked[0];
            }
        });
        return answers;
    }

    function showErrors(form, errors) {
        var first = null;
        form.querySelectorAll('.tj-survey-q').forEach(function (box) {
            var code = errors[box.dataset.qid];
            var slot = box.querySelector('.tj-survey-q-error');
            box.classList.toggle('has-error', !!code);
            slot.textContent = !code ? '' : code === 'required' ? cfg.lErrRequired
                : code === 'too_long' ? cfg.lErrTooLong : cfg.lErrGeneric;
            if (code && !first) first = box;
        });
        if (first) first.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }

    function showThanks(content) {
        while (content.firstChild) content.removeChild(content.firstChild);
        content.appendChild(el('p', 'tj-survey-thanks', cfg.lThanks));
        var ok = el('button', 'btn-primary', cfg.lClose);
        ok.type = 'button';
        ok.addEventListener('click', closeModal);
        var actions = el('div', 'tj-survey-actions');
        actions.appendChild(ok);
        content.appendChild(actions);
        ok.focus();
    }

    function openModal(survey) {
        lastFocus = document.activeElement;
        if (modal) {
            // 先前藏起來的 modal：回到原本那一題，答案都還在
            if (modal.style.display === 'none') {
                modal.style.display = '';
                document.addEventListener('keydown', onKey);
                if (session && session.resume) session.resume();
            }
            return;
        }

        modal = el('div', 'tj-survey-modal');
        var backdrop = el('div', 'tj-survey-backdrop');
        backdrop.addEventListener('click', closeModal);
        var dialog = el('div', 'tj-survey-dialog');
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');
        dialog.setAttribute('aria-labelledby', 'tj-survey-title');

        var x = el('button', 'tj-survey-x', '×');
        x.type = 'button';
        x.setAttribute('aria-label', cfg.lClose);
        x.addEventListener('click', closeModal);
        dialog.appendChild(x);

        var content = el('div', 'tj-survey-content');
        var title = el('h3', null, survey.title || cfg.lFab);
        title.id = 'tj-survey-title';
        content.appendChild(title);
        // 讓使用者知道這份問卷是針對哪個遊戲（edition 問卷才有）
        if (cfg.editionName) {
            var target = el('p', 'tj-survey-target');
            var icon = el('i', 'fas fa-dice');
            icon.setAttribute('aria-hidden', 'true');
            target.appendChild(icon);
            target.appendChild(document.createTextNode(' ' + cfg.editionName));
            content.appendChild(target);
        }
        if (survey.intro) content.appendChild(el('p', 'tj-survey-intro', survey.intro));

        var form = el('form', 'tj-survey-form');
        form.noValidate = true;
        // honeypot：真人看不到也不會填（後端見 feedback/security.py）
        var hp = document.createElement('input');
        hp.type = 'text';
        hp.name = 'website';
        hp.className = 'tj-survey-hp';
        hp.tabIndex = -1;
        hp.autocomplete = 'off';
        hp.setAttribute('aria-hidden', 'true');
        form.appendChild(hp);

        var total = survey.questions.length;
        var step = 0;
        var progress = el('div', 'tj-survey-progress');
        var progressText = el('div', 'tj-survey-progress-text');
        progressText.setAttribute('aria-live', 'polite');
        var track = el('div', 'tj-survey-progress-track');
        track.setAttribute('role', 'progressbar');
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', String(total));
        var fill = el('div', 'tj-survey-progress-fill');
        track.appendChild(fill);
        progress.appendChild(progressText);
        progress.appendChild(track);
        form.appendChild(progress);

        // 一個版面一題：只顯示目前這一題，其餘題目留在 DOM 裡（hidden），
        // 所以中途離開時 collectAnswers 仍然拿得到全部已答的題目。
        var boxes = survey.questions.map(function (q, i) {
            var box = renderQuestion(q, i);
            form.appendChild(box);
            return box;
        });
        session = { survey: survey, form: form, finished: false, sending: false, partialSent: false };

        var formError = el('div', 'tj-survey-form-error');
        formError.setAttribute('role', 'status');
        form.appendChild(formError);

        var actions = el('div', 'tj-survey-actions');
        var back = el('button', 'btn-secondary tj-survey-back', cfg.lBack);
        back.type = 'button';
        var next = el('button', 'btn-primary', cfg.lNext);
        next.type = 'button';
        var submit = el('button', 'btn-primary', cfg.lSubmit);
        submit.type = 'submit';
        actions.appendChild(back);
        actions.appendChild(next);
        actions.appendChild(submit);
        form.appendChild(actions);

        function showStep(i, focus) {
            step = Math.max(0, Math.min(total - 1, i));
            boxes.forEach(function (box, idx) { box.hidden = idx !== step; });
            formError.textContent = '';
            progressText.textContent = (cfg.lStep || '{n} / {total}')
                .replace('{n}', step + 1).replace('{total}', total);
            track.setAttribute('aria-valuenow', String(step + 1));
            fill.style.width = Math.round((step + 1) * 100 / total) + '%';
            back.hidden = step === 0;
            next.hidden = step === total - 1;
            submit.hidden = step !== total - 1;
            if (focus) {
                var field = boxes[step].querySelector('input, textarea');
                if (field) field.focus();
            }
        }

        // 這一題必填卻還沒答 → 擋住並標紅；回傳是否可以往下走
        function indexOfFirstError(errors) {
            for (var k = 0; k < survey.questions.length; k++) {
                if (errors[survey.questions[k].id]) return k;
            }
            return step;
        }

        function stepIsComplete() {
            var q = survey.questions[step];
            if (!q.required) return true;
            var answers = collectAnswers(form, survey);
            if (q.id in answers) return true;
            var errs = {};
            errs[q.id] = 'required';
            showErrors(form, errs);
            return false;
        }

        function goNext() {
            if (step < total - 1 && stepIsComplete()) showStep(step + 1, true);
        }

        next.addEventListener('click', goNext);
        back.addEventListener('click', function () { showStep(step - 1, true); });

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            // Enter 在文字欄位裡會觸發 submit：還沒到最後一題就當作「下一題」
            if (step < total - 1) { goNext(); return; }
            formError.textContent = '';
            var answers = collectAnswers(form, survey);

            // 必填題先在前端擋一次，省一趟來回；後端會再驗一次
            var missing = {};
            survey.questions.forEach(function (q) {
                if (q.required && !(q.id in answers)) missing[q.id] = 'required';
            });
            showErrors(form, missing);
            if (Object.keys(missing).length) { showStep(indexOfFirstError(missing)); return; }
            if (!Object.keys(answers).length) { formError.textContent = cfg.lErrRequired; return; }

            var headers = { 'Content-Type': 'application/json' };
            if (cfg.csrf) headers['X-CSRFToken'] = cfg.csrf;
            submit.disabled = true;
            session.sending = true;

            fetch(cfg.api + survey.id + '/responses/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: headers,
                body: JSON.stringify({
                    edition_id: editionId,
                    page: cfg.page || window.location.pathname,
                    lang: cfg.lang,
                    answers: answers,
                    others: collectOthers(form),
                    token: token,
                    website: hp.value
                })
            }).then(function (res) {
                return res.json().catch(function () { return {}; }).then(function (data) {
                    return { status: res.status, data: data };
                });
            }).then(function (r) {
                if (r.data.success) {
                    session.finished = true;
                    removeFab();
                    showThanks(content);
                } else if (r.status === 410) {
                    removeFab();
                    destroyModal();
                } else if (r.data.errors) {
                    showErrors(form, r.data.errors);
                    showStep(indexOfFirstError(r.data.errors));
                } else {
                    formError.textContent = cfg.lErrGeneric;
                }
            }).catch(function () {
                formError.textContent = cfg.lErrGeneric;
            }).then(function () {
                if (session) session.sending = false;
                submit.disabled = false;
            });
        });

        content.appendChild(form);
        dialog.appendChild(content);
        modal.appendChild(backdrop);
        modal.appendChild(dialog);
        document.body.appendChild(modal);
        document.addEventListener('keydown', onKey);

        session.resume = function () { showStep(step, true); };

        // 把草稿填回表單，並從第一題還沒答的開始（都答完了就停在最後一題）
        var startStep = 0;
        if (draft) {
            applyDraft(form, survey, draft);
            var done = collectAnswers(form, survey);
            startStep = total - 1;
            for (var k = 0; k < total; k++) {
                if (!(survey.questions[k].id in done)) { startStep = k; break; }
            }
        }
        showStep(startStep, true);
    }
})();
