// static/js/auth.js

(function () {
    'use strict';

    // ✅ 除錯用：記錄到 localStorage
    function debugLog(message, data = null) {
        const logs = JSON.parse(localStorage.getItem('auth_debug_logs') || '[]');
        logs.push({
            time: new Date().toISOString(),
            message: message,
            data: data
        });
        localStorage.setItem('auth_debug_logs', JSON.stringify(logs));
        console.log('[AUTH DEBUG]', message, data || '');
    }

    // ✅ 查看除錯 log 的函數
    window.viewAuthLogs = function () {
        const logs = JSON.parse(localStorage.getItem('auth_debug_logs') || '[]');
        console.table(logs);
        return logs;
    };

    // ✅ 清除除錯 log
    window.clearAuthLogs = function () {
        localStorage.removeItem('auth_debug_logs');
        console.log('Auth logs cleared');
    };

    // ========================================
    // Google Credential Callback
    // ========================================
    window.handleGoogleCredential = function (response) {
        debugLog('handleGoogleCredential called', { hasCredential: !!response.credential });

        if (!response.credential) {
            console.error('No credential in response');
            alert(window.AUTH_I18N?.loginFailedRetry || 'Login failed, please try again later');
            return;
        }

        const csrfToken = AuthHandler.getCsrfToken();
        debugLog('Sending id_token to backend', { csrfToken: !!csrfToken });

        fetch('/api/members/login/google/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            credentials: 'include',
            body: JSON.stringify({
                id_token: response.credential
            })
        })
            .then(res => {
                debugLog('Backend response received', { status: res.status, ok: res.ok });
                if (!res.ok) {
                    return res.json().then(err => Promise.reject(err));
                }
                return res.json();
            })
            .then(data => {
                debugLog('Login success', data);
                AuthHandler.handleLoginSuccess(data);
            })
            .catch(err => {
                debugLog('Login error', err);
                console.error('Login error:', err);
                alert((window.AUTH_I18N?.loginFailedPrefix || 'Login failed: ') + (err.error || err.detail || window.AUTH_I18N?.loginFailedRetry || 'please try again later'));
            });
    };

    // ========================================
    // AuthHandler Class
    // ========================================
    class AuthHandler {
        constructor() {
            this.apiBaseUrl = '/api/members';
            this.isLoggingIn = false;
            this.googleInitialized = false;
            this.tokenClient = null;

            this.loginBtn = document.getElementById('login-btn');
            this.loginBtnMobile = document.getElementById('login-btn-mobile');
            this.avatarBtn = document.getElementById('avatar-btn');
            this.userDropdown = document.getElementById('user-dropdown');
            this.logoutBtn = document.getElementById('logout-btn');
            this.logoutBtnMobile = document.getElementById('logout-btn-mobile');

            this.init();
        }

        init() {
            this.waitForGoogle(() => {
                this.initializeGSI();
                this.initializeTokenClient();
                this.renderGoogleButtons();
            });

            if (this.loginBtn) {
                this.loginBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    debugLog('Login button clicked');
                    this.handleLogin();
                });
            }
            if (this.loginBtnMobile) {
                this.loginBtnMobile.addEventListener('click', (e) => {
                    e.preventDefault();
                    debugLog('Login button mobile clicked');
                    this.handleLogin();
                });
            }

            if (this.avatarBtn) {
                this.avatarBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.toggleUserDropdown();
                });
            }

            document.addEventListener('click', (e) => {
                if (this.userDropdown &&
                    !this.userDropdown.contains(e.target) &&
                    !this.avatarBtn?.contains(e.target)) {
                    this.closeUserDropdown();
                }
            });

            // 別的 header submenu（例如語言選單）打開時，把這個也關起來
            document.addEventListener('header:dropdown-open', (e) => {
                if (e.detail?.source !== 'user') {
                    this.closeUserDropdown();
                }
            });

            if (this.logoutBtn) {
                this.logoutBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.logout();
                });
            }
            if (this.logoutBtnMobile) {
                this.logoutBtnMobile.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.logout();
                });
            }
        }

        waitForGoogle(callback, maxRetries = 50, retry = 0) {
            if (typeof google !== 'undefined' && google.accounts && google.accounts.id) {
                callback();
            } else if (retry < maxRetries) {
                setTimeout(() => this.waitForGoogle(callback, maxRetries, retry + 1), 100);
            } else {
                console.warn('Google Identity Services failed to load');
            }
        }

        initializeGSI() {
            if (this.googleInitialized || window.gsiInitialized) return;

            // If the page already includes a declarative g_id_onload element,
            // Google Identity Services has already been initialized by the library.
            if (document.querySelector('#g_id_onload')) {
                this.googleInitialized = true;
                window.gsiInitialized = true;
                return;
            }

            const clientId = this.getGoogleClientId();
            if (!clientId) {
                console.error('Google Client ID not found');
                return;
            }

            try {
                google.accounts.id.initialize({
                    client_id: clientId,
                    callback: window.handleGoogleCredential,
                    auto_select: false,
                    cancel_on_tap_outside: true,
                    context: 'signin',
                    ux_mode: 'popup',
                    itp_support: true,
                });

                this.googleInitialized = true;
                window.gsiInitialized = true;
                // console.log('GSI initialized successfully');

            } catch (error) {
                console.error('GSI initialization failed:', error);
            }
        }

        initializeTokenClient() {
            const clientId = this.getGoogleClientId();
            if (!clientId) return;

            try {
                this.tokenClient = google.accounts.oauth2.initTokenClient({
                    client_id: clientId,
                    scope: 'openid email profile',
                    // ✅ 成功的 callback
                    callback: (response) => {
                        debugLog('Token client callback', {
                            hasAccessToken: !!response.access_token,
                            error: response.error,
                            response: response  // ✅ 記錄完整 response
                        });

                        this.isLoggingIn = false;

                        if (response.error) {
                            debugLog('OAuth error in callback', response.error);
                            console.error('OAuth error:', response.error);
                            if (response.error !== 'popup_closed_by_user') {
                                alert((window.AUTH_I18N?.loginFailedPrefix || 'Login failed: ') + response.error);
                            }
                            return;
                        }

                        if (response.access_token) {
                            debugLog('Got access_token, sending to backend');
                            this.sendAccessTokenToBackend(response.access_token);
                        } else {
                            debugLog('No access_token in response', response);
                        }
                    },
                    // ✅ 新增：錯誤 callback
                    error_callback: (error) => {
                        debugLog('Token client ERROR callback', error);
                        console.error('OAuth error_callback:', error);
                        this.isLoggingIn = false;

                        if (error.type === 'popup_closed') {
                            debugLog('User closed popup');
                        } else if (error.type === 'popup_failed_to_open') {
                            debugLog('Popup blocked');
                            alert(window.AUTH_I18N?.popupBlocked || 'Popup blocked, please allow popups');
                        } else {
                            alert((window.AUTH_I18N?.loginFailedPrefix || 'Login failed: ') + (error.message || error.type || window.AUTH_I18N?.unknownError || 'Unknown error'));
                        }
                    }
                });
                // console.log('Token client initialized');
            } catch (error) {
                console.error('Token client initialization failed:', error);
            }
        }

        renderGoogleButtons() {
            const containers = document.querySelectorAll('.google-signin-button');

            containers.forEach(container => {
                const theme = container.dataset.theme || 'outline';
                const size = container.dataset.size || 'large';
                const text = container.dataset.text || 'signin_with';
                const shape = container.dataset.shape || 'rectangular';
                const width = container.dataset.width || undefined;
                const logoAlignment = container.dataset.logoAlignment || 'left';

                try {
                    google.accounts.id.renderButton(container, {
                        theme: theme,
                        size: size,
                        text: text,
                        shape: shape,
                        width: width ? parseInt(width) : undefined,
                        logo_alignment: logoAlignment,
                    });
                    console.log('Google button rendered');
                } catch (error) {
                    console.error('Failed to render Google button:', error);
                }
            });
        }

        handleLogin() {
            if (this.isLoggingIn) {
                debugLog('Login already in progress, ignoring');
                return;
            }

            this.isLoggingIn = true;

            // 授權網址由後端組（authorization code flow + PKCE）。
            // state 與 code_verifier 存在 Django session 裡由伺服器驗證，
            // 前端不再需要保管任何 OAuth 狀態，回跳路徑用 ?next= 帶過去。
            const next = window.location.pathname + window.location.search;
            const startUrl = '/api/members/login/google/start/?next=' + encodeURIComponent(next);

            debugLog('Starting server-side OAuth code flow', startUrl);
            window.location.href = startUrl;
        }

        sendAccessTokenToBackend(accessToken) {
            const csrfToken = AuthHandler.getCsrfToken();
            debugLog('sendAccessTokenToBackend', {
                hasToken: !!accessToken,
                hasCsrf: !!csrfToken
            });

            fetch('/api/members/login/google/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                credentials: 'include',
                body: JSON.stringify({ access_token: accessToken })
            })
                .then(res => {
                    debugLog('Backend response', { status: res.status, ok: res.ok });
                    if (!res.ok) {
                        return res.json().then(err => {
                            debugLog('Backend error response', err);
                            return Promise.reject(err);
                        });
                    }
                    return res.json();
                })
                .then(data => {
                    debugLog('Backend success response', data);
                    AuthHandler.handleLoginSuccess(data);
                })
                .catch(err => {
                    debugLog('Backend fetch error', err);
                    console.error('Access token login error:', err);
                    alert((window.AUTH_I18N?.loginFailedPrefix || 'Login failed: ') + (err.error || err.detail || window.AUTH_I18N?.loginFailedRetry || 'please try again later'));
                });
        }

        static handleLoginSuccess(data) {
            debugLog('handleLoginSuccess called', data);

            if (data.access) {
                localStorage.setItem('access_token', data.access);
                debugLog('Saved access_token');
            } else {
                debugLog('No access token in response!');
            }

            if (data.refresh) {
                localStorage.setItem('refresh_token', data.refresh);
                debugLog('Saved refresh_token');
            }

            if (data.tribe_language) {
                localStorage.setItem('user_language', data.tribe_language);
            }

            // One Tap 是在當前頁面完成的，重新載入這一頁即可
            const returnUrl = window.location.pathname + window.location.search;

            debugLog('Reloading', returnUrl);

            // ✅ 延遲一下確保 log 被儲存
            setTimeout(() => {
                window.location.href = returnUrl;
            }, 100);
        }

        // useOAuthRedirect() / generateNonce() 已移除：
        // 授權網址改由後端 /api/members/login/google/start/ 組出（code flow + PKCE），
        // state 與 code_verifier 存在 Django session 由伺服器驗證。

        getGoogleClientId() {
            if (window.GOOGLE_CLIENT_ID) {
                return window.GOOGLE_CLIENT_ID;
            }
            const metaTag = document.querySelector('meta[name="google-client-id"]');
            if (metaTag && metaTag.content) {
                return metaTag.content;
            }
            return null;
        }

        toggleUserDropdown() {
            if (this.userDropdown) {
                const isHidden = this.userDropdown.getAttribute('aria-hidden') === 'true';
                if (isHidden) {
                    this.openUserDropdown();
                } else {
                    this.closeUserDropdown();
                }
            }
        }

        openUserDropdown() {
            if (this.userDropdown) {
                document.dispatchEvent(new CustomEvent('header:dropdown-open', { detail: { source: 'user' } }));
                this.userDropdown.setAttribute('aria-hidden', 'false');
                this.userDropdown.classList.add('open');
            }
        }

        closeUserDropdown() {
            if (this.userDropdown) {
                this.userDropdown.setAttribute('aria-hidden', 'true');
                this.userDropdown.classList.remove('open');
            }
        }

        logout() {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('auth_debug_logs');
            sessionStorage.clear();

            if (typeof google !== 'undefined' && google.accounts && google.accounts.id) {
                google.accounts.id.disableAutoSelect();
            }

            fetch(`${this.apiBaseUrl}/logout/`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'X-CSRFToken': AuthHandler.getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            })
                .finally(() => {
                    window.location.href = '/';
                });
        }

        static getCsrfToken() {
            const match = document.cookie.match(/csrftoken=([^;]+)/);
            if (match) return match[1];
            const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
            if (input) return input.value;
            return '';
        }
    }

    // ========================================
    // 全局函數：動態渲染 Google 登入按鈕
    // ========================================
    window.renderGoogleLoginButton = function (container, options = {}) {
        if (!container) {
            console.error('renderGoogleLoginButton: container is required');
            return;
        }

        // 等待 Google GSI 載入
        function waitAndRender(retry = 0) {
            if (typeof google !== 'undefined' && google.accounts && google.accounts.id) {
                try {
                    google.accounts.id.renderButton(container, {
                        theme: options.theme || 'outline',
                        size: options.size || 'large',
                        text: options.text || 'signin_with',
                        shape: options.shape || 'rectangular',
                        width: options.width,
                        logo_alignment: options.logoAlignment || 'left',
                    });
                    console.log('Google login button rendered in container');
                } catch (error) {
                    console.error('Failed to render Google button:', error);
                }
            } else if (retry < 50) {
                setTimeout(() => waitAndRender(retry + 1), 100);
            } else {
                console.error('Google GSI not available for button render');
                // 備用：顯示一個普通按鈕
                renderFallbackButton(container);
            }
        }

        function renderFallbackButton(container) {
            const btn = document.createElement('button');
            btn.className = 'btn-google-fallback';
            btn.innerHTML = '<img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google" style="width:18px;height:18px;margin-right:8px;vertical-align:middle;"> Sign in with Google';
            btn.style.cssText = 'display:inline-flex;align-items:center;padding:10px 16px;border:1px solid #dadce0;border-radius:4px;background:#fff;color:#3c4043;font-size:14px;cursor:pointer;';
            btn.addEventListener('click', () => {
                if (window.authHandler) {
                    window.authHandler.handleLogin();
                }
            });
            container.appendChild(btn);
        }

        waitAndRender();
    };

    document.addEventListener('DOMContentLoaded', () => {
        window.authHandler = new AuthHandler();
    });

    window.AuthHandler = AuthHandler;

})();