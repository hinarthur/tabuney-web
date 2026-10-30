(function () {
    const STORAGE_KEY = 'theme';
    const DEFAULT_THEME = 'default';
    const root = document.documentElement;

    function applyTheme(theme) {
        root.dataset.theme = theme;
    }

    function readSaved() {
        try {
            return localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            return null;
        }
    }

    function saveTheme(theme) {
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (e) {
            /* 無痕模式或封鎖儲存空間時，只是不記住選擇 */
        }
    }

    function toggleTheme() {
        const current = root.dataset.theme || DEFAULT_THEME;
        const next = current === 'dark' ? 'default' : 'dark';

        applyTheme(next);
        saveTheme(next);
    }

    /* 初始主題已由 base.html <head> 的 inline script 設好（避免載入時閃亮色），
       這裡只負責綁切換按鈕；那段 script 若沒跑到，才在此補上。 */
    document.addEventListener('DOMContentLoaded', function () {
        if (!root.dataset.theme) {
            const saved = readSaved();
            if (saved === 'default' || saved === 'dark') {
                applyTheme(saved);
            } else {
                const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                applyTheme(prefersDark ? 'dark' : DEFAULT_THEME);
            }
        }

        /* ✅ 同時綁 desktop + mobile */
        document
            .querySelectorAll('#theme-toggle, #theme-toggle-mobile')
            .forEach(btn => {
                btn.addEventListener('click', toggleTheme);
            });
    });
})();
