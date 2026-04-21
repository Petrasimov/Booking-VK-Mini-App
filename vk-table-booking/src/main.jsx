/**
 * Точка входа VK Mini App.
 *
 * 1. Инициализирует Sentry (если задан VITE_SENTRY_DSN)
 * 2. Инициализирует VK Bridge
 * 3. Ждёт ответа (VKWebAppInit) перед рендером — исключает race condition с VKUI
 * 4. Настраивает глобальный перехват ошибок → отправка на /api/error-report
 * 5. Рендерит приложение, обёрнутое в ErrorBoundary
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@vkontakte/vkui/dist/vkui.css'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import bridge from '@vkontakte/vk-bridge';

// --- Sentry (опционально — включается только при наличии VITE_SENTRY_DSN) ---
const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
if (SENTRY_DSN) {
    import('@sentry/react').then((Sentry) => {
        Sentry.init({
            dsn: SENTRY_DSN,
            environment: import.meta.env.MODE,
            tracesSampleRate: 0.1,
        });
    }).catch(() => {});
}

// --- Отправка ошибки на бэкенд ---
function reportError(message, details) {
    fetch('/api/error-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, details, source: 'frontend' }),
    }).catch(() => {});
}

// --- Глобальный перехват JS-ошибок ---
window.onerror = (message, source, lineno, colno, error) => {
    const details = `${source}:${lineno}:${colno}\n${error?.stack || ''}`;
    reportError(String(message), details);
};

// --- Перехват необработанных промисов ---
window.onunhandledrejection = (event) => {
    const reason = event.reason;
    reportError(
        `Unhandled Promise: ${reason?.message || reason}`,
        reason?.stack || ''
    );
};

// --- Рендер приложения ---
function renderApp() {
    createRoot(document.getElementById('root')).render(
        <StrictMode>
            <ErrorBoundary>
                <App />
            </ErrorBoundary>
        </StrictMode>,
    )
}

// --- Инициализация VK Bridge, затем рендер ---
const bridgeInit = bridge.send('VKWebAppInit')
    .then(() => {
        console.log('VK Bridge initialized');
        // User info — в фоне, рендер не ждёт
        bridge.send('VKWebAppGetUserInfo')
            .then((userInfo) => {
                window.vkUser = userInfo;
                console.log('User:', userInfo.first_name, userInfo.last_name);
            })
            .catch(() => {});
    })
    .catch((error) => {
        console.warn('VK Bridge not available:', error?.error_data?.error_reason || error);
    });

// Рендерим сразу после VKWebAppInit ИЛИ через 1.5с (если вне VK)
Promise.race([
    bridgeInit,
    new Promise((resolve) => setTimeout(resolve, 1500)),
]).finally(() => {
    renderApp();
});
