/* 首頁「From the tabletop world」的縮圖。
   文章配圖來自 RSS，常是來源站產生的縮圖；伺服器端已盡量把網址推回原圖（見 home/views.py
   的 _full_size_image），推錯、原圖不存在時這裡退回存的縮圖網址。
   最後仍然偏小（寬度不到顯示寬度的 2 倍，高解析螢幕也夠清晰的門檻）的圖標成 is-small，
   讓 CSS 改用等比顯示＋模糊底圖，而不是用 cover 硬放大撐滿。 */
(function () {
    const MIN_SHARP_WIDTH = 760;

    function mark(img) {
        const box = img.closest('.world-img');
        if (!box || !img.naturalWidth) return;
        box.classList.toggle('is-small', img.naturalWidth < MIN_SHARP_WIDTH);
        if (img.naturalWidth < MIN_SHARP_WIDTH) {
            box.style.setProperty('--world-bg', 'url("' + img.currentSrc.replace(/"/g, '%22') + '")');
        }
    }

    document.querySelectorAll('.world-img img').forEach((img) => {
        img.addEventListener('error', () => {
            const fallback = img.dataset.fallback;
            if (fallback && img.getAttribute('src') !== fallback) img.src = fallback;
        });
        img.addEventListener('load', () => mark(img));
        if (img.complete) mark(img);
    });
})();
