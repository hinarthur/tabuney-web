// Rulesbot 分頁（/games/<slug>/）的 JavaScript。
//
// flowchart / script / info 現在各自是獨立頁面，不再有前端分頁切換，
// 所以這支檔案只剩 chat 用得到的東西（tooltip / lightbox / initializeChat）。
// 功能追蹤搬到 edition_track.js（只在 flowchart / script 兩頁載入）。

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
}

// Status indicator tooltip (tapped on narrow viewports)
document.querySelectorAll('.status-indicator').forEach(indicator => {
    let hideTimeout;
    
    indicator.addEventListener('click', () => {
        // Clear any existing timeout
        if (hideTimeout) {
            clearTimeout(hideTimeout);
        }
        
        // Toggle tooltip
        const isShowing = indicator.classList.contains('show-tooltip');
        
        if (isShowing) {
            indicator.classList.remove('show-tooltip');
        } else {
            indicator.classList.add('show-tooltip');
            
            // Auto-hide after 2 seconds
            hideTimeout = setTimeout(() => {
                indicator.classList.remove('show-tooltip');
            }, 2000);
        }
    });
});

// Lightbox
const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightbox-img');
const lightboxCaption = document.getElementById('lightbox-caption');
const lightboxClose = document.getElementById('lightbox-close');

function openLightbox(src, caption = '') {
    if (!lightbox) { return; }
    lightboxImg.src = src;
    lightboxCaption.textContent = caption;
    lightbox.classList.add('active');
}

function closeLightbox() {
    if (!lightbox) { return; }
    lightbox.classList.remove('active');
    lightboxImg.src = '';
}

// #lightbox 只存在於這一頁。沒有 guard 的話，將來誤在別的頁面載入
// 這支檔案會在這裡 TypeError，連帶把下面的 initializeChat 一起拖下水。
if (lightbox && lightboxClose) {
    lightboxClose.addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', (e) => {
        if (e.target === lightbox) closeLightbox();
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeLightbox();
    });
}

// Chat functionality (initialized if edition exists)
function initializeChat(editionId, translations, pageLang) {
    let sessionId = null;

    // /api/ 沒有語言網址前綴，後端的 request.lang 走 ?lang= → session → 預設
    // （見 translation/middleware.py）。頁面語言在這裡明講，chat 才不會因為
    // session 沒存過語言就一律用英文選規則書。
    const chatApiBase = `/api/game/editions/${editionId}/chat/`;
    const langQuery = pageLang ? `?lang=${encodeURIComponent(pageLang)}` : '';

    const chatWindow = document.getElementById('chat-window');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');

    // Save initial opening message (already rendered by Django)
    let initialMessage = chatWindow ? chatWindow.innerHTML : '';

    // Chat mode/provider radio (staff only; these controls only exist for staff).
    // Three-way: RAG / Whole-Gemini / Whole-Claude. There is a single radio group on
    // the page now — the desktop/mobile pair that had to be kept in sync by hand is
    // gone along with the duplicated DOM.

    // Request-body overrides for the chat API. Non-staff pages have no radios at all,
    // so this returns {} — the server then does what it does for everyone by default:
    // whole-context + classification routing. Only staff can override.
    function getChatModeAndProvider() {
        const checked = document.querySelector('input[name="chat-mode"]:checked');
        const value = checked ? checked.value : 'auto';
        if (value === 'rag') return { mode: 'rag' };
        if (value === 'whole-gemini') return { provider: 'gemini' };
        if (value === 'whole-claude') return { provider: 'claude' };
        return {};  // auto — let the classifier pick the provider
    }

    // Load chat history on page load
    async function loadChatHistory() {
        try {
            const response = await fetch(`${chatApiBase}${langQuery}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                if (response.status === 429) {
                    console.warn('Rate limit exceeded, skipping chat history load');
                }
                return;
            }

            const data = await response.json();
            if (data.messages && data.messages.length > 0) {
                sessionId = data.session_id;
                
                // Clear default opening message
                chatWindow.innerHTML = '';

                data.messages.forEach(msg => {
                    addMessage(
                        msg.content,
                        msg.role === 'assistant' ? 'bot' : msg.role,
                        msg.sources || [],
                        msg.figures || [],
                        msg.id,
                        msg.feedback || 0,
                        msg.feedback_text || ''
                    );
                });
            }
            if (data.limits) {
                updateChatLimits(data.limits);
            }
        } catch (err) {
            console.error('Failed to load chat history:', err);
        }
    }

    function updateChatLimits(limits) {
        if (!limits || limits.total === -1) return; // Unlimited

        const infoEl = document.getElementById('chat-limit-info');

        let message = '';
        let disableInput = false;

        const prefix = translations.limitRemainPrefix !== "game.chat.remain.prefix" ? translations.limitRemainPrefix : "Remaining:";
        const suffix = translations.limitRemainSuffix !== "game.chat.remain.suffix" ? translations.limitRemainSuffix : "prompts";
        const reach = translations.limitReachLimit !== "game.chat.reach_limit" ? translations.limitReachLimit : "Limit reached. Resets at:";
        const btnUpgrade = translations.btnUpgrade !== "membership.btn.upgrade" ? translations.btnUpgrade : "Upgrade";
        const urlUpgrade = translations.membershipUrl || "/member/membership/";

        if (limits.remaining <= 0) {
            disableInput = true;
            let resetDateStr = '';
            if (limits.reset_time) {
                const resetDate = new Date(limits.reset_time);
                resetDateStr = resetDate.toLocaleString([], {
                    year: 'numeric', month: '2-digit', day: '2-digit',
                    hour: '2-digit', minute: '2-digit'
                });
            }
            message = `${reach} ${resetDateStr}`;
            message += ` <a href="${urlUpgrade}" style="margin-left: 8px; padding: 2px 8px; font-size: 0.9em; background: var(--color-primary, #007bff); color: white; border-radius: 4px; text-decoration: none; display: inline-block;">${btnUpgrade}</a>`;
            if (infoEl) infoEl.style.color = "red";
        } else {
            message = `${prefix} ${limits.remaining} ${suffix}`;
            if (infoEl) infoEl.style.color = "var(--color-text-minor, gray)";
        }

        if (infoEl) infoEl.innerHTML = message;

        if (userInput) userInput.disabled = disableInput;
        if (sendBtn) sendBtn.disabled = disableInput;
    }

    function createLoadingBubble(chatWin, text) {
        const div = document.createElement('div');
        div.className = 'chat-bubble chat-bubble-bot';
        div.innerHTML = `<div class="bot-content"><span class="model-icon">🧔🏼</span><span class="loading-typewriter"></span></div>`;
        chatWin.appendChild(div);
        chatWin.scrollTop = chatWin.scrollHeight;

        const textEl = div.querySelector('.loading-typewriter');
        let stopped = false;
        let timer = null;

        function typeLoop() {
            if (stopped) return;
            let i = 0;
            textEl.textContent = '';
            (function typeChar() {
                if (stopped) return;
                if (i < text.length) {
                    textEl.textContent += text[i++];
                    timer = setTimeout(typeChar, 120);
                } else {
                    timer = setTimeout(typeLoop, 1000);
                }
            })();
        }

        typeLoop();
        return { stop() { stopped = true; clearTimeout(timer); div.remove(); } };
    }

    async function sendMessage() {
        const message = userInput.value.trim();
        if (!message) return;

        addMessage(message, 'user');
        userInput.value = '';
        const loadingBubble = createLoadingBubble(chatWindow, translations.loading);

        try {
            const response = await fetch(`${chatApiBase}${langQuery}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    message: message,
                    session_id: sessionId,
                    ...getChatModeAndProvider()
                })
            });

            const data = await response.json();
            
            if (data.limits) {
                updateChatLimits(data.limits);
            }
            
            if (!response.ok) throw new Error(data.error || 'Server error');

            sessionId = data.session_id;
            addMessage(data.answer, data.model || 'bot', data.sources, data.figures, data.message_id);

        } catch (err) {
            console.error(err);
            addMessage(translations.error, 'bot');
        } finally {
            loadingBubble.stop();
        }
    }

    function addMessage(text, role, sources = [], figures = [], messageId = null, feedback = 0, feedbackText = '') {
        console.group(`Message from ${role}`);
        console.log("Sources:", sources);
        console.groupEnd();

        const window = chatWindow;
        const div = document.createElement('div');
        
        // Normalize role for CSS class. `role` holds the provider label the API
        // returned (e.g. "Claude (claude-haiku-4-5)"); anything not recognised here
        // falls through to the user bubble, so every provider must be listed.
        const isBot = role.startsWith('Gemini') || role.startsWith('OpenAI')
            || role.startsWith('Claude') || role === 'bot' || role === 'assistant';
        div.className = `chat-bubble chat-bubble-${isBot ? 'bot' : 'user'}`;

        // Determine Icon
        let icon = '';
        if (isBot) {
            if (role.startsWith('OpenAI')) {
                icon = '<span class="model-icon">👩🏼‍🦰</span>';
            } else if (role.startsWith('Claude')) {
                icon = '<span class="model-icon">🎅🏼</span>';
            } else {
                // Default to Gemini for anything else bot-related
                icon = '<span class="model-icon">🧔🏼</span>';
            }
        }

        let html = '';
        if (isBot) {
            // Use marked for markdown to HTML
            html = `<div class="bot-content">${icon}${marked.parse(text)}</div>`;
        } else {
            html = `<div>${text.replace(/\n/g, '<br>')}</div>`;
        }

        // Figures
        if (figures && figures.length) {
            html += `
            <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 0.75rem; opacity: 0.8; margin-bottom: 8px;">
                    <strong>📷 ${translations.relatedFigures}:</strong>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                    ${figures.map(f => {
                        const caption = [
                            f.figure_label || '',
                            f.page_number ? `p.${f.page_number}` : '',
                            f.caption || ''
                        ].filter(Boolean).join(' - ');
                        
                        return f.image_url
                            ? `<img src="${f.image_url}" 
                                    alt="${f.figure_label || 'Figure'}"
                                    class="thumb-img"
                                    onclick="openLightbox('${f.image_url}', '${caption.replace(/'/g, "\\'")}')\" />`
                            : '';
                    }).join('')}
                </div>
            </div>`;
        }

        // Sources
        if (sources && sources.length) {
            // doc_index 只有在這一則回答用了多份規則書時才有值（見
            // RagService._extract_sources_whole）。單本回答與上線前的舊訊息都沒有
            // 這個欄位，走的是與以前一字不差的 "[1] P.5" 顯示。
            const docs = new Map();
            sources.forEach(s => {
                if (s.doc_index && !docs.has(s.doc_index)) {
                    docs.set(s.doc_index, s.doc_title || '');
                }
            });

            const sourceList = sources.map(s => {
                let page = '';
                if (s.start_page) {
                    page = s.end_page && s.end_page !== s.start_page
                        ? `P.${s.start_page}-${s.end_page}`
                        : `P.${s.start_page}`;
                }
                const ref = s.doc_index
                    ? `<span class="source-doc-ref" title="${escapeHtml(s.doc_title || '')}">Ref ${s.doc_index}</span> `
                    : '';
                return `[${s.index}]${ref || page ? ' ' : ''}${ref}${page}`;
            }).join(', ');

            // 手機沒有 hover，光靠 title 屬性看不到書名，所以多份文件時把對照表
            // 直接列出來
            let legend = '';
            if (docs.size) {
                const rows = [...docs.entries()]
                    .sort((a, b) => a[0] - b[0])
                    .map(([i, title]) => `Ref ${i} = ${escapeHtml(title)}`)
                    .join('<br>');
                legend = `<div style="font-size: 0.7rem; opacity: 0.6; margin-top: 6px;">${rows}</div>`;
            }

            html += `
            <div class="sources-container" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1);">
                <div style="font-size: 0.75rem; opacity: 0.8;">
                    <strong>🔖 ${translations.sources}:</strong>
                    <span style="font-family: monospace; margin-left: 4px;">${sourceList}</span>
                </div>
                ${legend}
            </div>`;
        }

        // Feedback
        if (isBot && messageId) {
            const likeActive = feedback === 1 ? ' active' : '';
            const dislikeActive = feedback === -1 ? ' active' : '';
            html += `
            <div class="feedback-container" id="feedback-${messageId}">
                <div class="feedback-buttons">
                    <span class="feedback-invite">${translations.feedbackInvite}</span>
                    <button class="feedback-btn${likeActive}" data-message-id="${messageId}" data-value="1" data-tooltip="${translations.feedbackHelpful}">✅</button>
                    <button class="feedback-btn${dislikeActive}" data-message-id="${messageId}" data-value="-1" data-tooltip="${translations.feedbackNotHelpful}">👎</button>
                </div>
                <div class="feedback-text-area" id="feedback-text-area-${messageId}">
                    <textarea class="feedback-input" placeholder="Any comments? (Optional)">${escapeHtml(feedbackText)}</textarea>
                    <button class="feedback-submit" data-message-id="${messageId}">Submit</button>
                </div>
            </div>`;
        }

        div.innerHTML = html;
        window.appendChild(div);
        window.scrollTop = window.scrollHeight;

        // Attach feedback listeners
        if (isBot && messageId) {
            const container = div.querySelector('.feedback-container');
            const btns = container.querySelectorAll('.feedback-btn');
            const textArea = container.querySelector('.feedback-text-area');
            const submitBtn = container.querySelector('.feedback-submit');
            const input = container.querySelector('.feedback-input');

            btns.forEach(btn => {
                btn.addEventListener('click', async () => {
                    const value = parseInt(btn.dataset.value);
                    btns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    textArea.classList.add('visible');
                    
                    // Instant vote save
                    await sendFeedback(messageId, value, '');
                });
            });

            submitBtn.addEventListener('click', async () => {
                const activeBtn = container.querySelector('.feedback-btn.active');
                const value = activeBtn ? parseInt(activeBtn.dataset.value) : 0;
                const text = input.value.trim();

                await sendFeedback(messageId, value, text);

                // Collapse the comment box but keep the buttons so the user can still change their vote later
                textArea.classList.remove('visible');
                const originalLabel = submitBtn.textContent;
                submitBtn.disabled = true;
                submitBtn.textContent = 'Saved ✓';
                setTimeout(() => {
                    submitBtn.textContent = originalLabel;
                    submitBtn.disabled = false;
                }, 2000);
            });
        }
    }

    async function sendFeedback(messageId, value, text) {
        try {
            await fetch(`/api/game/messages/${messageId}/feedback/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    feedback: value,
                    feedback_text: text
                })
            });
        } catch (err) {
            console.error('Feedback failed:', err);
        }
    }

    async function clearChat() {
        if (!confirm(translations.clearConfirm)) {
            return;
        }

        try {
            const response = await fetch(`${chatApiBase}clear/${langQuery}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                credentials: 'same-origin'
            });

            if (response.ok) {
                // Restore initial message
                chatWindow.innerHTML = initialMessage;

                // Reset session
                sessionId = null;
                
                alert(translations.clearSuccess);
            } else {
                throw new Error('Failed to clear chat history');
            }
        } catch (err) {
            console.error('Failed to clear chat:', err);
            alert(translations.clearError);
        }
    }

    // Event listeners
    if (sendBtn) {
        sendBtn.addEventListener('click', () => sendMessage());
    }
    if (userInput) {
        userInput.addEventListener('keypress', e => {
            if (e.key === 'Enter') sendMessage();
        });
    }

    const clearBtn = document.getElementById('clear-chat-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', clearChat);
    }

    // Load previous chat history on page load
    loadChatHistory();
}
