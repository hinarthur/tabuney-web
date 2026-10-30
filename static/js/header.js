(function () {
    function initScrollHide() {
        var header = document.getElementById('site-header');
        if (!header) return;

        // Sync body padding-top with real header height
        function syncPadding() {
            document.documentElement.style.setProperty('--header-height', header.offsetHeight + 'px');
        }
        syncPadding();
        window.addEventListener('resize', syncPadding, { passive: true });

        var lastY = window.scrollY;
        var ticking = false;

        function onScroll() {
            var currentY = window.scrollY;
            if (currentY <= 0) {
                header.classList.remove('header-hidden');
            } else if (currentY < lastY) {
                header.classList.remove('header-hidden');
            } else if (currentY > lastY + 4) {
                header.classList.add('header-hidden');
            }
            lastY = currentY;
            ticking = false;
        }

        window.addEventListener('scroll', function () {
            if (!ticking) {
                requestAnimationFrame(onScroll);
                ticking = true;
            }
        }, { passive: true });
    }

    function initHamburger() {
        var hb = document.getElementById('hamburger-btn');
        var mobile = document.getElementById('mobile-nav');
        if (!hb || !mobile) return;

        hb.addEventListener('click', function (e) {
            e.stopPropagation();
            var open = mobile.classList.toggle('open');
            hb.setAttribute('aria-expanded', String(open));
            mobile.setAttribute('aria-hidden', String(!open));
        });

        document.addEventListener('click', function (e) {
            if (!mobile.contains(e.target) && !hb.contains(e.target)) {
                if (mobile.classList.contains('open')) {
                    mobile.classList.remove('open');
                    hb.setAttribute('aria-expanded', 'false');
                    mobile.setAttribute('aria-hidden', 'true');
                }
            }
        });

        var links = document.querySelectorAll('#mobile-nav a');
        links.forEach(function (a) {
            a.addEventListener('click', function () {
                mobile.classList.remove('open');
                hb.setAttribute('aria-expanded', 'false');
                mobile.setAttribute('aria-hidden', 'true');
            });
        });
    }

    function init() {
        initScrollHide();
        initHamburger();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();