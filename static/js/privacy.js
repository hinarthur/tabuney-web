// (function () {
//   window.acceptAnalytics = function () {
//     gtag('consent', 'update', {
//       analytics_storage: 'granted'
//     });
//     localStorage.setItem('analytics_consent', 'granted');
//   };
// })();

(function () {
    const STORAGE_KEY = 'cookie_consent';

    function getConsent() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {
                analytics: 'denied',
                ads: 'denied'
            };
        } catch {
            return { analytics: 'denied', ads: 'denied' };
        }
    }

    function saveConsent(consent) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(consent));
    }

    function applyConsent(consent) {
        // Analytics
        gtag('consent', 'update', {
            analytics_storage: consent.analytics
        });

        // Ads (future-ready)
        gtag('consent', 'update', {
            ad_storage: consent.ads,
            ad_user_data: consent.ads,
            ad_personalization: consent.ads
        });
    }

    // ===== Modal Logic =====

    function openModal() {
        const modal = document.getElementById('cookie-modal');
        const consent = getConsent();

        document.getElementById('consent-analytics').checked =
            consent.analytics === 'granted';
        document.getElementById('consent-ads').checked =
            consent.ads === 'granted';

        modal.classList.add('show');
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeModal() {
        const modal = document.getElementById('cookie-modal');
        modal.classList.remove('show');
        modal.setAttribute('aria-hidden', 'true');
    }

    document.addEventListener('DOMContentLoaded', function () {
        const openBtn = document.getElementById('open-cookie-settings');
        const saveBtn = document.getElementById('save-cookie-settings');
        const closeBtn = document.getElementById('close-cookie-settings');
        const backdrop = document.querySelector('.cookie-modal-backdrop');

        if (openBtn) openBtn.addEventListener('click', e => {
            e.preventDefault();
            openModal();
        });

        if (closeBtn) closeBtn.addEventListener('click', closeModal);
        if (backdrop) backdrop.addEventListener('click', closeModal);

        if (saveBtn) {
            saveBtn.addEventListener('click', function () {
                const consent = {
                    analytics: document.getElementById('consent-analytics').checked
                        ? 'granted'
                        : 'denied',
                    ads: document.getElementById('consent-ads').checked
                        ? 'granted'
                        : 'denied'
                };

                saveConsent(consent);
                applyConsent(consent);
                closeModal();
            });
        }

        // ✅ 初始化時套用已存的 consent
        const saved = getConsent();
        applyConsent(saved);
    });
})();