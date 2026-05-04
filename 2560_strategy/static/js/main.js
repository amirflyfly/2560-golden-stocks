document.addEventListener('DOMContentLoaded', function() {
    patchFetchWithCsrf();
    attachCsrfTokensToForms();
    initFlashMessages();
    initSidebar();
    initFormValidation();
});

function getCookieValue(name) {
    const cookie = document.cookie
        .split('; ')
        .find(row => row.startsWith(name + '='));
    return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : '';
}

function getCsrfToken() {
    const cookieName = window.APP_CSRF_COOKIE_NAME || 'promo_panel_csrf';
    return getCookieValue(cookieName);
}

function patchFetchWithCsrf() {
    if (window.__csrfFetchPatched || typeof window.fetch !== 'function') {
        return;
    }

    const originalFetch = window.fetch.bind(window);
    window.fetch = function(resource, options = {}) {
        const nextOptions = {...options};
        const method = (nextOptions.method || 'GET').toUpperCase();
        const headers = new Headers(nextOptions.headers || {});
        const targetUrl = typeof resource === 'string' ? resource : resource?.url || window.location.href;
        const resolvedUrl = new URL(targetUrl, window.location.origin);
        const isSameOrigin = resolvedUrl.origin === window.location.origin;

        if (isSameOrigin && !nextOptions.credentials) {
            nextOptions.credentials = 'same-origin';
        }
        if (isSameOrigin && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
            const csrfToken = getCsrfToken();
            if (csrfToken && !headers.has('X-CSRF-Token')) {
                headers.set('X-CSRF-Token', csrfToken);
            }
        }

        nextOptions.headers = headers;
        return originalFetch(resource, nextOptions);
    };

    window.__csrfFetchPatched = true;
    window.getCsrfToken = getCsrfToken;
}

function attachCsrfTokensToForms() {
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        return;
    }

    document.querySelectorAll('form').forEach(function(form) {
        const method = (form.getAttribute('method') || 'GET').toUpperCase();
        if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
            return;
        }
        let input = form.querySelector('input[name="csrf_token"]');
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            form.appendChild(input);
        }
        input.value = csrfToken;
    });
}

function initFlashMessages() {
    const messages = document.querySelectorAll('.flash-message');
    messages.forEach(function(msg) {
        setTimeout(function() {
            msg.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(function() {
                msg.remove();
            }, 300);
        }, 5000);
    });
}

function initSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const toggleBtn = document.querySelector('.sidebar-toggle');
    
    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', function() {
            sidebar.classList.toggle('open');
        });
    }
    
    document.addEventListener('click', function(e) {
        if (sidebar && sidebar.classList.contains('open')) {
            if (!sidebar.contains(e.target) && !toggleBtn?.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        }
    });
}

function initFormValidation() {
    const forms = document.querySelectorAll('form[data-validate]');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let valid = true;
            
            requiredFields.forEach(function(field) {
                if (!field.value.trim()) {
                    valid = false;
                    field.classList.add('error');
                } else {
                    field.classList.remove('error');
                }
            });
            
            if (!valid) {
                e.preventDefault();
                alert('请填写所有必填项');
            }
        });
    });
}

function formatDate(date) {
    const d = new Date(date);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function formatNumber(num) {
    if (num === null || num === undefined) return '-';
    return Number(num).toLocaleString('zh-CN');
}

function formatPercent(num) {
    if (num === null || num === undefined) return '-';
    return Number(num).toFixed(2) + '%';
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function showLoading() {
    const loader = document.createElement('div');
    loader.className = 'loading-overlay';
    loader.innerHTML = '<div class="loading-spinner"></div>';
    document.body.appendChild(loader);
}

function hideLoading() {
    const loader = document.querySelector('.loading-overlay');
    if (loader) {
        loader.remove();
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('已复制到剪贴板', 'success');
    }).catch(() => {
        showToast('复制失败', 'error');
    });
}

function downloadFile(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}
