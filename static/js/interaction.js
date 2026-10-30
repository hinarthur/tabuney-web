/**
 * Interaction Handling for Edition Detail
 * Handles Rating Bar and Collection Status
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log("Interaction JS: DOMContentLoaded fired.");
    const context = window.editionInteraction;
    if (!context) {
        console.error("Interaction JS: window.editionInteraction not found.");
        return;
    }

    const interactionHeaders = document.querySelectorAll('.interaction-header');
    console.log("Interaction JS: Found interaction headers:", interactionHeaders.length);

    interactionHeaders.forEach(header => {
        const toggleBtn = header.querySelector('.status-toggle-btn');
        const optionsContainer = header.querySelector('.status-options');
        
        // --- Status Toggle ---
        if (toggleBtn) {
            toggleBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                // Close other open options first
                document.querySelectorAll('.status-options').forEach(opt => {
                    if (opt !== optionsContainer) opt.classList.remove('show');
                });
                optionsContainer.classList.toggle('show');
            });
        }

        // Close on click outside
        document.addEventListener('click', () => {
            if (optionsContainer) optionsContainer.classList.remove('show');
        });

        // --- Select Status ---
        header.querySelectorAll('.status-option').forEach(option => {
            option.addEventListener('click', (e) => {
                e.stopPropagation();
                if (!context.isAuthenticated) {
                    showLoginPrompt();
                    return;
                }
                const status = option.getAttribute('data-status');
                const isActive = option.classList.contains('active');
                
                // If clicking already selected status, reset to NULL (except Clear option)
                if (isActive && status !== '') {
                    saveInteraction({ status: null }, header);
                } else {
                    saveInteraction({ status: status }, header);
                }
                optionsContainer.classList.remove('show');
            });
        });

        // --- Select Rating ---
        header.querySelectorAll('.rating-emoji').forEach(emoji => {
            emoji.addEventListener('click', (e) => {
                e.stopPropagation();
                if (!context.isAuthenticated) {
                    showLoginPrompt();
                    return;
                }
                const rating = emoji.getAttribute('data-rating');
                const isActive = emoji.classList.contains('active');
                
                // If clicking already selected emoji, reset to NULL
                if (isActive) {
                    saveInteraction({ rating: null }, header);
                } else {
                    saveInteraction({ rating: rating }, header);
                }
            });
        });

        function showLoginPrompt() {
            if (window.authHandler) {
                window.authHandler.handleLogin();
            } else {
                const currentPath = window.location.pathname;
                window.location.href = "/acct/login/?next=" + encodeURIComponent(currentPath);
            }
        }

        function saveInteraction(data, currentHeader) {
            const formData = new FormData();
            formData.append('edition_id', context.editionId);
            formData.append('csrfmiddlewaretoken', context.csrfToken);

            if (data.rating !== undefined) formData.append('rating', data.rating);
            if (data.status !== undefined) formData.append('status', data.status);

            fetch(context.updateUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    updateUI(result.rating, result.status);
                    showToast(currentHeader, data);
                }
            })
            .catch(error => console.error('Error saving interaction:', error));
        }

        function updateToolboxIcon(status, header) {
            const toggleBtn = header.querySelector('.status-toggle-btn');
            if (!toggleBtn) return;
            
            const statusEmojis = JSON.parse(toggleBtn.getAttribute('data-status-emojis') || '{}');
            const icon = toggleBtn.querySelector('i');
            
            if (!icon) return;

            const targetClass = status && statusEmojis[status]
                ? statusEmojis[status]
                : 'fa-solid fa-box-open';

            const targetClasses = targetClass.split(' ').filter(Boolean);
            const currentClasses = Array.from(icon.classList).filter(c => c !== 'animate-change');
            const newClassString = targetClasses.join(' ');
            const currentClassString = currentClasses.join(' ');

            if (currentClassString !== newClassString) {
                icon.className = '';
                targetClasses.forEach(c => icon.classList.add(c));
                icon.classList.add('animate-change');
                window.setTimeout(() => icon.classList.remove('animate-change'), 250);
            }

            const translations = window.statusTranslations || {};
            toggleBtn.title = (status && status !== null && status !== undefined && status !== '' && status !== 'null') 
                ? (translations[status] || status) 
                : (window.editionInteraction?.collectionTitle || 'Collection');
        }

        function updateUI(rating, status) {
            // Track must end at the centre of the selected emoji (see .rating-emoji offsets in edition_detail.css)
            const ratingMap = {
                'nightmare': '14px',
                'nah': '37.5%',
                'nice': '62.5%',
                'amazing': 'calc(100% - 14px)'
            };

            // Update ALL interaction headers on the page (desktop and mobile)
            document.querySelectorAll('.interaction-header').forEach(h => {
                // Update Track
                const track = h.querySelector('.rating-track');
                if (track) {
                    track.style.width = ratingMap[rating] !== undefined ? ratingMap[rating] : '0';
                }

                // Update Emojis
                h.querySelectorAll('.rating-emoji').forEach(em => {
                    if (em.getAttribute('data-rating') === rating) {
                        em.classList.add('active');
                    } else {
                        em.classList.remove('active');
                    }
                });

                // Update Status Options
                h.querySelectorAll('.status-option').forEach(opt => {
                    if (opt.getAttribute('data-status') === status) {
                        opt.classList.add('active');
                    } else {
                        opt.classList.remove('active');
                    }
                });
                
                // Update toolbox icon based on status
                updateToolboxIcon(status, h);
                
                // Update Thumbnail filter if nightmare
                const infoCard = h.closest('.info-card');
                if (infoCard) {
                    const img = infoCard.querySelector('.info-image');
                    if (img) {
                        if (rating === 'nightmare') {
                            img.style.filter = "grayscale(0.5) opacity(0.8)";
                        } else {
                            img.style.filter = "";
                        }
                    }
                }
            });
        }

        function showToast(h, savedData) {
            const t = h.querySelector('.interaction-toast');
            if (!t) return;

            // Build icon + label content based on what was saved
            let html = '';
            const status = savedData && savedData.status;
            const rating = savedData && savedData.rating;

            if (status) {
                const iconClass = (window.statusIconClasses || {})[status] || 'fa-solid fa-check';
                const color     = (window.statusIconColors  || {})[status] || 'inherit';
                const label     = (window.statusTranslations || {})[status] || status;
                html = `<i class="${iconClass}" style="color:${color};margin-right:7px;"></i>${label}`;
            } else if (rating) {
                const emoji = (window.ratingEmojis       || {})[rating] || '';
                const label = (window.ratingTranslations || {})[rating] || rating;
                html = `<span style="margin-right:6px;">${emoji}</span>${label}`;
            } else {
                // Cleared — show default saved text
                html = t.dataset.default || 'Saved!';
            }

            t.innerHTML = html;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 1500);
        }
        
        // Initialize toolbox icons on page load
        function initializeToolboxIcons() {
            document.querySelectorAll('.interaction-header').forEach(h => {
                const activeStatusOption = h.querySelector('.status-option.active');
                const currentStatus = activeStatusOption ? activeStatusOption.getAttribute('data-status') : '';
                updateToolboxIcon(currentStatus, h);
            });
        }
        
        // Call initialization
        initializeToolboxIcons();
    });
});
