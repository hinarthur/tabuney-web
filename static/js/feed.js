/**
 * Feed 列表與詳情頁共用腳本
 */
(function () {
    'use strict';

    /**
 * 建立符合 Google 品牌指南的登入按鈕
 */
    function createGoogleSignInButton(text, onClick) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn-google-signin';
        btn.innerHTML = `
        <svg class="google-icon" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
            <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
            <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
            <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
            <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
        </svg>
        <span class="google-text">${text}</span>
    `;
        btn.addEventListener('click', onClick);
        return btn;
    }

    /**
     * 觸發登入（統一入口）
     */
    function triggerGoogleSignIn(closeModalFn) {
        if (closeModalFn) closeModalFn();

        if (window.authHandler) {
            window.authHandler.handleLogin();
        } else {
            document.getElementById('login-btn')?.click();
        }
    }
    /**
     * 距今多久：<=24h 顯示 1d，滿 7 天用週 (1w, 2w)，滿 52 週用年 (1y, 2y)
     * @param {string|Date} date - ISO 字串或 Date
     * @returns {string} 例如 "1d", "2d", "1w", "2y"
     */
    function timeAgo(date) {
        const d = date instanceof Date ? date : new Date(date);
        const now = Date.now();
        const diffMs = now - d.getTime();
        if (diffMs < 0) return '0d';

        const diffH = diffMs / (1000 * 60 * 60);
        if (diffH <= 24) return '1d';

        const diffD = diffH / 24;
        if (diffD < 30) return Math.ceil(diffD) + 'd';

        const diffW = diffD / 7;
        if (diffW < 52) return Math.floor(diffW) + 'w';

        const diffY = diffW / 52;
        return Math.floor(diffY) + 'y';
    }

    function runWhenReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    const FEEDLIST_LANG_STORAGE_KEY = 'feedlist_lang';

    /* =========================
       CSRF / Toast
       ========================= */
    function getCsrfToken() {
        return (
            document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
            document.cookie
                .split('; ')
                .find((row) => row.startsWith('csrftoken='))
                ?.split('=')[1] ||
            ''
        );
    }

    function showToast(message, duration = 3000) {
        const existing = document.querySelector('.toast');
        if (existing) existing.remove();

        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => toast.classList.add('show'), 10);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 500);
        }, duration);
    }

    /* =========================
       Modal Controller (ARIA/Focus/Scroll lock)
       - 不要求改 HTML：支援既有 close 按鈕 id
       ========================= */
    function createModalController(modalEl, opts = {}) {
        if (!modalEl) return null;

        const options = {
            closeSelectors: opts.closeSelectors || []
        };

        const backdropEl = modalEl.querySelector('.bookmark-modal-backdrop');
        const contentEl =
            modalEl.querySelector('[role="dialog"]') ||
            modalEl.querySelector('.bookmark-modal-content');

        let isOpen = false;
        let lastActiveEl = null;

        // scroll lock
        let scrollY = 0;
        let bodyWidth = null;

        const FOCUSABLE_SEL = [
            'a[href]',
            'button:not([disabled])',
            'input:not([disabled])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            '[tabindex]:not([tabindex="-1"])'
        ].join(',');

        function isInDocument(el) {
            return !!(el && el.ownerDocument && el.ownerDocument.contains(el));
        }

        function safeFocus(el) {
            if (!el) return false;
            if (!isInDocument(el)) return false;
            if (typeof el.focus !== 'function') return false;
            try {
                el.focus({ preventScroll: true });
            } catch (e) {
                // Safari/older browsers may not support preventScroll
                try { el.focus(); } catch (e2) { return false; }
            }
            return true;
        }

        function getFocusable() {
            if (!contentEl) return [];
            return Array.from(contentEl.querySelectorAll(FOCUSABLE_SEL))
                .filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length));
        }

        function lockScroll() {
            scrollY = window.scrollY || document.documentElement.scrollTop || 0;
            bodyWidth = document.body.getBoundingClientRect().width;

            document.body.classList.add('modal-open');
            document.body.style.position = 'fixed';
            document.body.style.top = `-${scrollY}px`;
            document.body.style.left = '0';
            document.body.style.right = '0';
            document.body.style.width = `${bodyWidth}px`;
        }

        function unlockScroll() {
            document.body.classList.remove('modal-open');
            document.body.style.position = '';
            document.body.style.top = '';
            document.body.style.left = '';
            document.body.style.right = '';
            document.body.style.width = '';
            window.scrollTo(0, scrollY);
        }

        function focusInitial() {
            const focusables = getFocusable();
            if (focusables.length) {
                safeFocus(focusables[0]);
                return;
            }
            // fallback: focus dialog container (need tabindex=-1 in HTML)
            safeFocus(contentEl);
        }

        function trapTab(e) {
            if (e.key !== 'Tab') return;
            const focusables = getFocusable();
            if (!focusables.length) {
                e.preventDefault();
                safeFocus(contentEl);
                return;
            }

            const first = focusables[0];
            const last = focusables[focusables.length - 1];
            const active = document.activeElement;

            if (e.shiftKey) {
                if (active === first || !contentEl || !contentEl.contains(active)) {
                    e.preventDefault();
                    safeFocus(last);
                }
            } else {
                if (active === last) {
                    e.preventDefault();
                    safeFocus(first);
                }
            }
        }

        function onKeyDown(e) {
            if (!isOpen) return;
            if (e.key === 'Escape' || e.key === 'Esc') {
                e.preventDefault();
                close();
                return;
            }
            trapTab(e);
        }

        function isCloseClickTarget(target) {
            if (!target) return false;
            if (target.closest?.('[data-modal-close]')) return true;
            if (target.closest?.('#bookmark-modal-close')) return true;
            if (target.closest?.('#bookmark-list-modal-close')) return true;
            if (target.closest?.('#filter-modal-close')) return true;
            for (const sel of options.closeSelectors) {
                if (target.closest?.(sel)) return true;
            }
            return false;
        }

        function open(triggerEl) {
            if (isOpen) return;
            isOpen = true;

            lastActiveEl = triggerEl || document.activeElement;

            modalEl.classList.add('show');
            modalEl.setAttribute('aria-hidden', 'false');

            lockScroll();

            // focus after it becomes visible
            setTimeout(focusInitial, 0);
            document.addEventListener('keydown', onKeyDown, true);
        }

        function close() {
            if (!isOpen) return;
            isOpen = false;

            document.removeEventListener('keydown', onKeyDown, true);

            // 关键：先把焦点移出 modal，再 aria-hidden=true
            const restoreTarget = lastActiveEl;
            lastActiveEl = null;

            const active = document.activeElement;
            const focusWasInside = !!(active && modalEl.contains(active));

            if (focusWasInside) {
                // 尽量把 focus 移回触发按钮；不行就 blur
                const ok = safeFocus(restoreTarget);
                if (!ok && active && typeof active.blur === 'function') active.blur();
            }

            modalEl.classList.remove('show');
            modalEl.setAttribute('aria-hidden', 'true');

            unlockScroll();

            // 若焦点当时不在 modal 里，也尝试恢复（可选）
            if (!focusWasInside) {
                safeFocus(restoreTarget);
            }
        }

        backdropEl?.addEventListener('click', close);

        modalEl.addEventListener('click', (e) => {
            // 1) 如果點的是 close 按鈕或其後代，關閉
            if (isCloseClickTarget(e.target)) {
                e.preventDefault();
                close();
                return;
            }

            // 2) 如果點擊的目標是 content 或其內部元素，不關閉
            if (contentEl && contentEl.contains(e.target)) {
                return;
            }

            // 3) 其他情況（點在 backdrop 或 modalEl 自己）-> 關閉
            close();
        });

        return { open, close, isOpen: () => isOpen, modalEl, contentEl };
    }

    /* =========================
       Feed List
       ========================= */
    function initFeedList() {
        const feedListEl = document.getElementById('feed-list');
        const loadingEl = document.getElementById('loading');
        const btnMagazine = document.getElementById('view-magazine');
        const btnCard = document.getElementById('view-card');
        const btnMasonry = document.getElementById('view-masonry');

        if (!feedListEl) return;

        let offset = 0;
        const limit = 30;
        let loading = false;
        let hasMore = true;
        let filterConfig = null;
        let enabledLangs = [];

        // page/bookmark mode state
        let currentFeedMode = 'feeds'; // 'feeds' or 'bookmarks'
        const feedListTitleEl = document.getElementById('feed-list-title');
        const initialFeedTitle = feedListTitleEl ? feedListTitleEl.textContent.trim() : '';

        // bookmark paging state (used for page-based bookmarks view)
        let bookmarkOffset = 0;
        let bookmarkHasMore = true;
        let bookmarkLoading = false;

        const MOBILE_BREAKPOINT = 768;

        function setViewMode(mode) {
            feedListEl.dataset.view = mode;
            localStorage.setItem('feedView', mode);
            btnMagazine?.classList.toggle('active', mode === 'magazine');
            btnCard?.classList.toggle('active', mode === 'card');
            btnMasonry?.classList.toggle('active', mode === 'masonry');
        }

        function getEffectiveView() {
            if (window.innerWidth <= MOBILE_BREAKPOINT) return 'card';
            return localStorage.getItem('feedView') || 'magazine';
        }

        function applyViewForViewport() {
            setViewMode(getEffectiveView());
        }

        function getEffectiveLanguages() {
            if (!filterConfig || !filterConfig.tribes || !filterConfig.tribes.length) {
                return ['de', 'en', 'es', 'fr', 'ja', 'zh'];
            }
            const allCodes = filterConfig.tribes.map((t) => t.code);
            if (filterConfig.is_authenticated) {
                const fromMember = filterConfig.feedlist_lang;
                if (fromMember && fromMember.length > 0) return fromMember;
                return allCodes;
            }
            const stored = localStorage.getItem(FEEDLIST_LANG_STORAGE_KEY);
            if (stored) {
                try {
                    const parsed = JSON.parse(stored);
                    if (Array.isArray(parsed) && parsed.length > 0) return parsed;
                } catch (e) { }
            }
            return allCodes;
        }

        function updateEnabledLangs(langs) {
            enabledLangs = langs;
        }

        function resetFeedList() {
            feedListEl.innerHTML = '';
            offset = 0;
            hasMore = true;
            if (loadingEl) {
                loadingEl.style.display = 'block';
                loadingEl.innerText = 'Loading...';
            }
        }

        applyViewForViewport();
        window.addEventListener('resize', applyViewForViewport);

        btnMagazine?.addEventListener('click', () => setViewMode('magazine'));
        btnCard?.addEventListener('click', () => setViewMode('card'));
        btnMasonry?.addEventListener('click', () => setViewMode('masonry'));

        async function loadFeeds() {
            if (loading || !hasMore) return;

            loading = true;
            if (loadingEl) loadingEl.style.display = 'block';

            const langsParam = enabledLangs.length ? enabledLangs.join(',') : '';
            const url = `/api/feed/list/?offset=${offset}${langsParam ? '&languages=' + encodeURIComponent(langsParam) : ''}`;

            try {
                const resp = await fetch(url);
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

                const data = await resp.json();

                if (data.length < limit) {
                    hasMore = false;
                    if (loadingEl) loadingEl.innerText = 'No more feeds';
                }

                data.forEach(renderFeedItem);
                offset += data.length;
            } catch (err) {
                console.error('Load failed:', err);
                if (loadingEl) loadingEl.innerText = 'Load failed';
            }

            loading = false;
        }

        function renderFeedItem(item) {
            const a = document.createElement('a');
            a.className = 'feed-item';
            a.href = `/feeds/${item.id}/`;

            a.innerHTML = `
            <div class="feed-cover">
                ${item.image ? `<img src="${item.image}" alt="">` : ''}
            </div>
            <div class="feed-body">
                <div class="feed-header">
                    ${item.rssLogo ? `<img src="${item.rssLogo}" class="rss-logo" alt="">` : ''}
                    <div class="feed-meta">
                        ${item.rssSitename || ''} ·
                        ${item.publishdate ? timeAgo(item.publishdate) : ''}
                    </div>
                </div>
                <h3 class="feed-title">${item.title || '(No title)'}</h3>
                <div class="feed-preview">${item.preview || ''}</div>
            </div>
        `;

            feedListEl.appendChild(a);
        }

        // Scroll handler: load feeds or bookmarks based on current mode
        window.addEventListener('scroll', () => {
            if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 120) {
                if (currentFeedMode === 'bookmarks') {
                    loadBookmarksToPage(bookmarkOffset);
                } else {
                    loadFeeds();
                }
            }
        });

        async function fetchFilterConfigAndLoad() {
            try {
                const resp = await fetch('/api/feed/filter-config/');
                filterConfig = resp.ok ? await resp.json() : null;
            } catch (e) {
                filterConfig = null;
            }
            updateEnabledLangs(getEffectiveLanguages());
            loadFeeds();
        }

        fetchFilterConfigAndLoad();

        initFilterModal({
            getFilterConfig: () => filterConfig,
            getEnabledLangs: () => enabledLangs,
            updateEnabledLangs,
            onSave: async (newLangs) => {
                updateEnabledLangs(newLangs);
                resetFeedList();
                await loadFeeds();
            },
            fetchFilterConfig: async () => {
                const resp = await fetch('/api/feed/filter-config/');
                filterConfig = resp.ok ? await resp.json() : null;
                return filterConfig;
            }
        });

        // ===== Bookmarks list (opened from toolbar btn) =====
        const btnBookmarkList = document.getElementById('btn-bookmark-list');

        const bookmarkListModalCtrl = createModalController(
            document.getElementById('bookmark-list-modal')
        );

        function renderBookmarkListItem(item) {
            const a = document.createElement('a');
            a.className = 'feed-item';
            a.href = `/feeds/${item.id}/`;
            a.innerHTML = `
            <div class="feed-cover">
                ${item.image ? `<img src="${item.image}" alt="">` : ''}
            </div>
            <div class="feed-body">
                <div class="feed-header">
                    ${item.rssLogo ? `<img src="${item.rssLogo}" class="rss-logo" alt="">` : ''}
                    <div class="feed-meta">
                        ${item.rssSitename || ''} ·
                        ${item.publishdate ? timeAgo(item.publishdate) : ''}
                    </div>
                </div>
                <h3 class="feed-title">${item.title || '(No title)'}</h3>
            </div>
        `;
            document.getElementById('bookmark-list-modal-body')?.appendChild(a);
        }

        async function loadBookmarks(offsetArg = 0) {
            if (bookmarkLoading || (!bookmarkHasMore && offsetArg !== 0)) return false;
            bookmarkLoading = true;

            const body = document.getElementById('bookmark-list-modal-body');
            const actions = document.getElementById('bookmark-list-modal-actions');
            const modal = document.getElementById('bookmark-list-modal');
            if (!body || !actions || !modal) {
                bookmarkLoading = false;
                return false;
            }

            try {
                const resp = await fetch(`/api/feed/bookmarks/?offset=${offsetArg}`);
                if (resp.status === 401 || resp.status === 403) {
                    // not logged in / forbidden -> show login prompt
                    const msg = modal.dataset.msgLoginHint || 'Please sign in to see your bookmarks';
                    const btnText = modal.dataset.btnSignin || 'Sign in with Google';

                    body.innerHTML = '';
                    const hint = document.createElement('p');
                    hint.textContent = msg;
                    hint.className = 'bookmark-login-hint';
                    body.appendChild(hint);

                    const googleBtn = createGoogleSignInButton(btnText, () => {
                        triggerGoogleSignIn(() => bookmarkListModalCtrl?.close());
                    });
                    body.appendChild(googleBtn);

                    document.getElementById('bookmark-list-modal-loadmore')?.remove();

                    bookmarkLoading = false;
                    return false;
                }

                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();

                if (offsetArg === 0) {
                    body.innerHTML = '';
                    bookmarkOffset = 0;
                    bookmarkHasMore = true;
                }

                data.forEach(renderBookmarkListItem);
                bookmarkOffset += data.length;

                if (offsetArg === 0 && data.length === 0) {
                    body.innerHTML = '<div class="feed-filter-empty">No bookmarks</div>';
                    document.getElementById('bookmark-list-modal-loadmore')?.remove();
                    bookmarkHasMore = false;
                    bookmarkLoading = false;
                    return true;
                }

                if (data.length < limit) {
                    bookmarkHasMore = false;
                }

                // ensure load more button
                let loadBtn = document.getElementById('bookmark-list-modal-loadmore');
                if (!loadBtn) {
                    loadBtn = document.createElement('button');
                    loadBtn.id = 'bookmark-list-modal-loadmore';
                    loadBtn.className = 'btn-primary';
                    loadBtn.textContent = 'Load more';
                    loadBtn.addEventListener('click', function () {
                        loadBookmarks(bookmarkOffset);
                    });
                    actions.insertBefore(loadBtn, actions.firstChild);
                }

                loadBtn.style.display = bookmarkHasMore ? '' : 'none';

                bookmarkLoading = false;
                return true;
            } catch (e) {
                console.error('Load bookmarks failed', e);
                if (body) body.innerHTML = '<div class="loading">Load failed</div>';
                bookmarkLoading = false;
                return false;
            }
        }

        function openBookmarkListModal(showLoginOnly = false) {
            const modal = document.getElementById('bookmark-list-modal');
            const body = document.getElementById('bookmark-list-modal-body');
            if (!modal || !body || !bookmarkListModalCtrl) return;

            // reset paging
            bookmarkOffset = 0;
            bookmarkHasMore = true;
            bookmarkLoading = false;

            if (showLoginOnly) {
                const msg = modal.dataset.msgLoginHint || 'Please sign in to see your bookmarks';
                const btnText = modal.dataset.btnSignin || 'Sign in with Google';

                body.innerHTML = '';
                const hint = document.createElement('p');
                hint.textContent = msg;
                hint.className = 'bookmark-login-hint';
                body.appendChild(hint);

                const googleBtn = createGoogleSignInButton(btnText, () => {
                    triggerGoogleSignIn(() => bookmarkListModalCtrl?.close());
                });
                body.appendChild(googleBtn);

                document.getElementById('bookmark-list-modal-loadmore')?.remove();
            } else {
                body.innerHTML = '<div class="loading">Loading...</div>';
                loadBookmarks(0);
            }

            bookmarkListModalCtrl.open(btnBookmarkList);
        }

        btnBookmarkList?.addEventListener('click', async function () {
            // ensure we have filterConfig loaded to check auth state
            if (!filterConfig) {
                try {
                    const resp = await fetch('/api/feed/filter-config/');
                    filterConfig = resp.ok ? await resp.json() : null;
                } catch (e) {
                    filterConfig = null;
                }
            }

            const isAuth = !!(filterConfig && filterConfig.is_authenticated);

            if (!isAuth) {
                openBookmarkListModal(true);
                return;
            }

            // Authenticated -> toggle page bookmarks view
            if (currentFeedMode === 'bookmarks') {
                closeBookmarksOnPage();
            } else {
                openBookmarksOnPage();
            }
        });

        function openBookmarksOnPage() {
            currentFeedMode = 'bookmarks';
            feedListEl.innerHTML = '';
            btnBookmarkList?.classList.add('active');
            if (feedListTitleEl) {
                feedListTitleEl.textContent =
                    document.getElementById('bookmark-list-modal-title')?.textContent || 'Bookmarks';
            }

            bookmarkOffset = 0;
            bookmarkHasMore = true;
            bookmarkLoading = false;

            loadBookmarksToPage(0);
        }

        function closeBookmarksOnPage() {
            currentFeedMode = 'feeds';
            feedListEl.innerHTML = '';
            btnBookmarkList?.classList.remove('active');
            if (feedListTitleEl) feedListTitleEl.textContent = initialFeedTitle || '';

            offset = 0;
            hasMore = true;
            loading = false;

            loadFeeds();
        }

        // Load bookmarks and render into the main feed list area
        async function loadBookmarksToPage(offsetArg = 0) {
            if (bookmarkLoading || (!bookmarkHasMore && offsetArg !== 0)) return false;
            bookmarkLoading = true;

            const body = feedListEl;
            if (!body) {
                bookmarkLoading = false;
                return false;
            }

            try {
                const resp = await fetch(`/api/feed/bookmarks/?offset=${offsetArg}`);
                if (resp.status === 401 || resp.status === 403) {
                    const modal = document.getElementById('bookmark-list-modal');
                    const msg = modal?.dataset.msgLoginHint || 'Please sign in to see your bookmarks';
                    const btnText = modal?.dataset.btnSignin || 'Sign in with Google';
                    body.innerHTML = '';

                    const hint = document.createElement('p');
                    hint.textContent = msg;
                    hint.className = 'bookmark-login-hint';
                    body.appendChild(hint);

                    const googleBtn = createGoogleSignInButton(btnText, () => {
                        triggerGoogleSignIn();
                    });
                    body.appendChild(googleBtn);
                }

                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();

                if (offsetArg === 0) {
                    body.innerHTML = '';
                    bookmarkOffset = 0;
                    bookmarkHasMore = true;
                }

                data.forEach(renderFeedItem);
                bookmarkOffset += data.length;

                if (offsetArg === 0 && data.length === 0) {
                    body.innerHTML = '<div class="feed-filter-empty">No bookmarks</div>';
                    bookmarkHasMore = false;
                    bookmarkLoading = false;
                    return true;
                }

                if (data.length < limit) {
                    bookmarkHasMore = false;
                }

                bookmarkLoading = false;
                return true;
            } catch (e) {
                console.error('Load bookmarks (page) failed', e);
                body.innerHTML = '<div class="loading">Load failed</div>';
                bookmarkLoading = false;
                return false;
            }
        }

        // ===== Add RSS modal (opened from toolbar btn) =====
        const btnAddRss = document.getElementById('btn-add-rss');
        const addRssModalCtrl = createModalController(document.getElementById('add-rss-modal'));

        function openAddRssModal(showLoginOnly = false) {
            const modal = document.getElementById('add-rss-modal');
            const body = document.getElementById('add-rss-modal-body');
            const actions = document.getElementById('add-rss-modal-actions');
            if (!modal || !body || !actions) return;

            body.innerHTML = '';
            actions.innerHTML = '';

            if (showLoginOnly) {
                const msg = modal.dataset.msgLoginHint || 'Please sign in to add RSS';
                const btnText = modal.dataset.btnSignin || 'Sign in with Google';

                const hint = document.createElement('p');
                hint.textContent = msg;
                hint.className = 'bookmark-login-hint';
                body.appendChild(hint);

                const googleBtn = createGoogleSignInButton(btnText, () => {
                    triggerGoogleSignIn(() => addRssModalCtrl?.close());
                });
                body.appendChild(googleBtn);

                document.getElementById('add-rss-modal-loadmore')?.remove();
                addRssModalCtrl.open(btnAddRss);
                return;
            }

            // authenticated: show input and add button
            // const placeholder = modal.dataset.placeholder || 'Enter blog or RSS URL';
            const placeholder = 'e.g. https://example.com or https://example.com/rss';
            const addBtnText = modal.dataset.btnAdd || 'Add';
            
            const label = document.createElement('p');
            label.textContent = modal.dataset.inputLabel || 'Enter a blog URL or RSS feed URL:';
            label.className = 'add-rss-label';
            label.style.marginBottom = '8px';
            body.appendChild(label);

            const input = document.createElement('input');
            input.type = 'text';
            input.placeholder = placeholder;
            input.className = 'add-rss-input';
            input.style.width = '100%';
            input.style.marginBottom = '8px';
            body.appendChild(input);

            const info = document.createElement('div');
            info.className = 'add-rss-info';
            body.appendChild(info);

            const addBtn = document.createElement('button');
            addBtn.className = 'btn-primary';
            addBtn.textContent = addBtnText;

            const msg_added = modal.dataset.msgAdded || 'RSS Added';
            // 定義錯誤碼對應的翻譯 key
            const msg_url_empty = modal.dataset.errorUrlEmpty || 'Please enter a URL';
            const msg_rss_invalid = modal.dataset.errorRssInvalid || 'Invalid RSS feed URL';
            // const msg_rss_exists = modal.dataset.errorRssExists || 'This RSS feed already exists';
            // const msg_network_error = modal.dataset.errorNetwork || 'Network error, please try again';

            addBtn.addEventListener('click', async function () {
                const url = input.value.trim();
                
                // 前端第一道防線
                if (!url) {
                    // showToast('Please enter a URL');
                    info.textContent = msg_url_empty;
                    return;
                }
                addBtn.disabled = true;
                // info.textContent = 'Adding...';                
                info.textContent = modal.dataset.msgAdding || 'Adding...';
                
                try {
                    const resp = await fetch('/api/feed/add_rss/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        body: JSON.stringify({ url })
                    });
                    const data = await resp.json();

                    if (!resp.ok) {
                    // if (!resp.ok || data.error) {
                        // 顯示後端返回的 detail
                        info.textContent = msg_rss_invalid;
                        addBtn.disabled = false;
                        return;
                    }

                    // 檢查是否為新建立
                    if (data.created === true || resp.status === 201) {
                        showToast(msg_added);
                        addRssModalCtrl.close();
                        return;
                    }

                    // 已存在的情況：通知使用者並保留 modal
                    info.textContent = data.detail || 'Already exists';
                    addBtn.disabled = false;
                    return;
                } catch (e) {
                    console.error('Add RSS failed', e);
                    info.textContent = 'Add failed';
                    addBtn.disabled = false;
                }
            });

            // allow Enter key to submit
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addBtn.click();
                }
            });

            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'btn-secondary';
            cancelBtn.textContent = 'Cancel';
            cancelBtn.setAttribute('data-modal-close', '');

            actions.appendChild(addBtn);
            actions.appendChild(cancelBtn);

            addRssModalCtrl.open(btnAddRss);
        }

        btnAddRss?.addEventListener('click', async function () {
            if (!filterConfig) {
                try {
                    const resp = await fetch('/api/feed/filter-config/');
                    filterConfig = resp.ok ? await resp.json() : null;
                } catch (e) {
                    filterConfig = null;
                }
            }
            const isAuth = !!(filterConfig && filterConfig.is_authenticated);
            openAddRssModal(!isAuth);
        });
    }

    /* =========================
       Filter Modal
       (保留你原邏輯，只修 msgSaveFailed 未定義 bug)
       ========================= */
    function initFilterModal(opts) {
        const modal = document.getElementById('filter-modal');
        const backdrop = modal?.querySelector('.feed-filter-modal-backdrop');
        const listEl = document.getElementById('filter-modal-list');
        const btnSave = document.getElementById('filter-modal-save');
        const btnClose = document.getElementById('filter-modal-close');
        const btnFilter = document.getElementById('btn-filter');

        if (!modal || !listEl) return;

        const {
            getFilterConfig,
            getEnabledLangs,
            updateEnabledLangs,
            onSave,
            fetchFilterConfig
        } = opts;

        let pendingLangs = [];

        function openModal() {
            const config = getFilterConfig();
            if (!config || !config.tribes || !config.tribes.length) {
                listEl.innerHTML = '<li class="feed-filter-empty">No languages available</li>';
            } else {
                const enabled = new Set(getEnabledLangs());
                pendingLangs = config.tribes.map((t) => t.code).filter((code) => enabled.has(code));
                if (pendingLangs.length === 0 && config.tribes.length > 0) {
                    pendingLangs = config.tribes.map((t) => t.code);
                }
                renderList(config, pendingLangs);
            }
            modal.classList.add('show');
            modal.setAttribute('aria-hidden', 'false');
        }

        function closeModal() {
            modal.classList.remove('show');
            modal.setAttribute('aria-hidden', 'true');
        }

        function renderList(config, enabledSet) {
            const enabled = new Set(Array.isArray(enabledSet) ? enabledSet : [enabledSet]);
            listEl.innerHTML = config.tribes
                .map((t) => {
                    const on = enabled.has(t.code);
                    return `
                    <li data-code="${t.code}" class="${on ? '' : 'dimmed'}">
                        <span class="filter-name">${t.label || t.code}</span>
                        <span class="filter-icon"><i class="fas fa-eye${on ? '' : '-slash'}"></i></span>
                    </li>
                `;
                })
                .join('');
        }

        function toggleLang(code) {
            const idx = pendingLangs.indexOf(code);
            if (idx >= 0) pendingLangs = pendingLangs.filter((c) => c !== code);
            else pendingLangs = [...pendingLangs, code];

            const config = getFilterConfig();
            if (config) renderList(config, pendingLangs);
        }

        listEl.addEventListener('click', (e) => {
            const li = e.target.closest('li[data-code]');
            if (li) toggleLang(li.dataset.code);
        });

        btnClose?.addEventListener('click', closeModal);
        backdrop?.addEventListener('click', closeModal);

        btnSave?.addEventListener('click', async () => {
            const config = getFilterConfig();
            if (!config) return;

            const msgSaveFailed = 'Save failed';

            if (config.is_authenticated) {
                try {
                    const resp = await fetch('/api/feed/save-feedlist-lang/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCsrfToken()
                        },
                        credentials: 'same-origin',
                        body: JSON.stringify({ languages: pendingLangs })
                    });

                    if (resp.ok) {
                        const data = await resp.json();
                        config.feedlist_lang = data.feedlist_lang || pendingLangs;
                        updateEnabledLangs(pendingLangs);
                        closeModal();
                        onSave(pendingLangs);
                        showToast('Saved');
                    } else if (resp.status === 401) {
                        window.location.href =
                            '/acct/login/?next=' + encodeURIComponent(window.location.pathname);
                    } else {
                        showToast(msgSaveFailed);
                    }
                } catch (e) {
                    console.error(e);
                    showToast(msgSaveFailed);
                }
            } else {
                try {
                    localStorage.setItem(FEEDLIST_LANG_STORAGE_KEY, JSON.stringify(pendingLangs));
                    updateEnabledLangs(pendingLangs);
                    closeModal();
                    onSave(pendingLangs);
                    showToast('Saved');
                } catch (e) {
                    showToast(msgSaveFailed);
                }
            }
        });

        btnFilter?.addEventListener('click', () => {
            fetchFilterConfig().then(() => openModal());
        });
    }

    /* =========================
       Feed Detail（分享、收藏）
       ========================= */
    function initFeedDetail() {
        const btnShare = document.getElementById('btn-share');
        const btnBookmark = document.getElementById('btn-bookmark');
        const container = document.querySelector('.feed-detail');
        if (!container) return;

        const shareTitle = container.dataset.shareTitle || document.title;

        const sourceDateEl = container.querySelector('.source-date');
        if (sourceDateEl && container.dataset.publishdate) {
            sourceDateEl.textContent = timeAgo(container.dataset.publishdate);
        }

        const modalEl = document.getElementById('bookmark-modal');
        const modalDataset = modalEl ? modalEl.dataset : {};

        const msgLinkCopied = container.dataset.msgLinkCopied || 'Link copied';
        const msgBookmarked = container.dataset.msgBookmarked || 'Saved';
        const msgUnbookmarked = modalDataset.msgUnbookmarked || 'Removed';

        // i18n strings for bookmark modal (fallback)
        const msgSaveConfirm = modalDataset.msgSaveConfirm || 'Save this article to your bookmarks?';
        const btnSaveText = modalDataset.btnSave || 'Save';
        const msgSaveFailed = modalDataset.msgSaveFailed || 'Save failed';
        const msgRemoveConfirm = modalDataset.msgRemoveConfirm || 'Remove bookmark?';
        const msgRemoveFailed = modalDataset.msgRemoveFailed || 'Remove failed';

        const bookmarkModalCtrl = createModalController(modalEl);

        if (btnShare) {
            btnShare.addEventListener('click', async function () {
                const shareData = {
                    title: shareTitle,
                    url: window.location.href
                };

                try {
                    if (navigator.share) {
                        await navigator.share(shareData);
                    } else {
                        await navigator.clipboard.writeText(window.location.href);
                        showToast(msgLinkCopied);
                    }
                } catch (err) {
                    if (err.name !== 'AbortError') {
                        console.error('Share failed:', err);
                    }
                }
            });
        }

        if (btnBookmark) {
            btnBookmark.addEventListener('click', async function () {
                const workId = this.dataset.workId;
                const isAuth = container.dataset.userAuth === 'true';
                const tier = container.dataset.memberTier || '';

                // if already bookmarked -> ask to unsave
                if (this.classList.contains('active')) {
                    const savedId = this.dataset.savedId;
                    if (!savedId) {
                        openBookmarkModal(workId);
                        return;
                    }
                    const ok = confirm(msgRemoveConfirm);
                    if (!ok) return;
                    await performUnsave(savedId);
                    return;
                }

                // member tier 直接儲存，不開 modal
                if (isAuth && tier === 'member') {
                    try {
                        const resp = await fetch('/api/feed/save_work/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCsrfToken()
                            },
                            body: JSON.stringify({ work: workId, label: 0 })
                        });

                        if (resp.ok) {
                            const data = await resp.json();
                            btnBookmark.classList.add('active');
                            if (data && data.id) btnBookmark.dataset.savedId = data.id;
                            showToast(msgBookmarked, 3500);
                        } else if (resp.status === 401) {
                            const globalLogin = document.getElementById('login-btn');
                            if (globalLogin) globalLogin.click();
                            else window.location.href = '/acct/login/?next=' + encodeURIComponent(window.location.pathname);
                        } else {
                            console.error('Save failed', resp.status);
                            showToast(msgSaveFailed);
                        }
                    } catch (e) {
                        console.error(e);
                        showToast(msgSaveFailed);
                    }
                    return;
                }

                // 其他情況才開 modal
                openBookmarkModal(workId);
            });

            async function performUnsave(savedId) {
                try {
                    const resp = await fetch(`/api/feed/savedwork/${savedId}/`, {
                        method: 'DELETE',
                        headers: {
                            'X-CSRFToken': getCsrfToken()
                        }
                    });

                    if (resp.ok) {
                        btnBookmark.classList.remove('active');
                        btnBookmark.removeAttribute('data-saved-id');
                        showToast(msgUnbookmarked, 2500);
                    } else if (resp.status === 401) {
                        const globalLogin = document.getElementById('login-btn');
                        if (globalLogin) globalLogin.click();
                        else window.location.href = '/acct/login/?next=' + encodeURIComponent(window.location.pathname);
                    } else {
                        console.error('Unsave failed', resp.status);
                        showToast(msgRemoveFailed);
                    }
                } catch (e) {
                    console.error(e);
                    showToast(msgRemoveFailed);
                }
            }

            function openBookmarkModal(workId) {
                const modal = document.getElementById('bookmark-modal');
                const body = document.getElementById('bookmark-modal-body');
                const actions = document.getElementById('bookmark-modal-actions');
                if (!modal || !body || !actions || !bookmarkModalCtrl) return;

                const msgLoginHint = modal.dataset.msgLoginHint || 'Please sign in';
                const btnSigninText = modal.dataset.btnSignin || 'Sign in with Google';

                body.innerHTML = '';

                // 只移除我們動態塞進 actions 的按鈕（避免把原本 close 按鈕整個清掉）
                actions.querySelectorAll('.js-dynamic-action').forEach((el) => el.remove());

                const isAuth = container.dataset.userAuth === 'true';

                async function performSave() {
                    try {
                        const resp = await fetch('/api/feed/save_work/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCsrfToken()
                            },
                            body: JSON.stringify({ work: workId, label: 0 })
                        });

                        if (resp.ok) {
                            const data = await resp.json();
                            btnBookmark.classList.add('active');
                            if (data && data.id) btnBookmark.dataset.savedId = data.id;
                            showToast(msgBookmarked, 3500);
                            bookmarkModalCtrl.close();
                        } else if (resp.status === 401) {
                            const globalLogin = document.getElementById('login-btn');
                            if (globalLogin) globalLogin.click();
                            else window.location.href = '/acct/login/?next=' + encodeURIComponent(window.location.pathname);
                        } else {
                            console.error('Save failed', resp.status);
                            showToast(msgSaveFailed);
                        }
                    } catch (e) {
                        console.error(e);
                        showToast(msgSaveFailed);
                    }
                }

                if (!isAuth) {
                    const hint = document.createElement('p');
                    hint.textContent = msgLoginHint;
                    hint.className = 'bookmark-login-hint';
                    body.appendChild(hint);

                    const googleBtn = createGoogleSignInButton(btnSigninText, () => {
                        triggerGoogleSignIn(() => bookmarkModalCtrl.close());
                    });
                    body.appendChild(googleBtn);
                } else {
                    const p = document.createElement('p');
                    p.textContent = msgSaveConfirm;
                    body.appendChild(p);

                    const saveBtn = document.createElement('button');
                    saveBtn.className = 'btn-primary js-dynamic-action';
                    saveBtn.textContent = btnSaveText;
                    saveBtn.addEventListener('click', performSave);
                    actions.insertBefore(saveBtn, actions.firstChild);
                }

                bookmarkModalCtrl.open(btnBookmark);
            }
        }
    }

    runWhenReady(function () {
        initFeedList();
        initFeedDetail();
    });
})();