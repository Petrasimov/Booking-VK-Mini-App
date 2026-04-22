/**
 * Корневой компонент приложения.
 *
 * При старте загружает конфиг заведения (GET /api/config).
 * Если заведение не зарегистрировано — показывает онбординг (TODO: Этап 4).
 * Если зарегистрировано — передаёт venueConfig в форму бронирования.
 *
 * Управляет модальными окнами:
 *   - welcome  — приветствие при первом открытии
 *   - confirm  — подтверждение данных перед отправкой
 *   - success  — успешное бронирование
 *   - error    — сообщение об ошибке
 */

import { useState, useRef, useEffect } from 'react'
import {
    ConfigProvider,
    AppRoot,
    SplitLayout,
    SplitCol,
    View,
    Panel,
    ModalCard,
    Button,
    Text,
    ScreenSpinner,
} from '@vkontakte/vkui'
import Home from './pages/Home'

/** Таймаут запроса к API (мс) */
const FETCH_TIMEOUT_MS = 10_000

/** Задержки retry для 5xx: 1с -> 2с -> 4с */
const RETRY_DELAYS_MS = [1000, 2000, 4000]

/** Коды статусов, при которых выполняется retry */
const RETRYABLE_STATUSES = new Set([500, 502, 503])

/** Человекочитаемое сообщение по HTTP-статусу */
function getErrorMessage(status, defaultMsg) {
    if (status === 402) return 'Лимит бронирований на этот месяц исчерпан. Обратитесь к владельцу заведения.'
    if (status === 409) return 'Бронирование на этот день с таким телефоном уже существует.'
    if (status === 422) return 'Некорректные данные бронирования. Проверьте заполненные поля.'
    if (status === 429) return 'Слишком много запросов. Подождите минуту и попробуйте снова.'
    if (status === 500) return 'Внутренняя ошибка сервера. Попробуйте ещё раз.'
    if (status === 502 || status === 503) return 'Сервер временно недоступен. Попробуйте через несколько секунд.'
    return defaultMsg || 'Не удалось отправить бронь. Попробуйте ещё раз.'
}

/** Получить group_id из URL-параметров VK */
function getVkGroupId() {
    const params = new URLSearchParams(window.location.search)
    return params.get('vk_group_id') || params.get('group_id') || null
}

function App() {
    // Цветовая схема VK
    const vkColorScheme = new URLSearchParams(window.location.search).get('vk_color_scheme')
    const appearance = vkColorScheme === 'space_gray' ? 'dark' : 'light'

    // ── Конфиг заведения ──────────────────────────────────────────────────
    const [venueConfig, setVenueConfig]   = useState(null)
    const [configLoading, setConfigLoading] = useState(true)
    const [isRegistered, setIsRegistered] = useState(true)

    // ── Состояние формы и модалок ─────────────────────────────────────────
    const [activeModal,     setActiveModal]     = useState('welcome')
    const [reservationData, setReservationData] = useState(null)
    const [errorMessage,    setErrorMessage]    = useState('')
    const [isSubmitting,    setIsSubmitting]    = useState(false)
    const [canRetry,        setCanRetry]        = useState(false)
    const [pendingFormData, setPendingFormData] = useState(null)
    const [formResetKey,    setFormResetKey]    = useState(0)

    const retryCount = useRef(0)
    const groupId    = getVkGroupId()

    // Сохраняем group_id глобально для BookingForm (VKWebAppAllowMessagesFromGroup)
    if (groupId) window.vkGroupId = Number(groupId)

    // ── Загрузка конфига заведения при старте ────────────────────────────
    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const headers = {}
                if (groupId) headers['X-VK-Group-ID'] = groupId

                const res = await fetch('/api/config', { headers })
                if (!res.ok) throw new Error(`HTTP ${res.status}`)

                const data = await res.json()

                if (!data.is_registered) {
                    setIsRegistered(false)
                    setConfigLoading(false)
                    return
                }

                setVenueConfig(data.config)
                setIsRegistered(true)

                // Применяем акцентный цвет заведения
                if (data.config?.accent_color) {
                    document.documentElement.style.setProperty(
                        '--accent-color',
                        data.config.accent_color
                    )
                }
            } catch (e) {
                // При ошибке загрузки конфига — используем дефолтный
                console.warn('Failed to load venue config:', e)
                setVenueConfig(null)
            } finally {
                setConfigLoading(false)
            }
        }

        fetchConfig()
    }, [groupId])

    const openModal  = (name) => setActiveModal(name)
    const closeModal = () => setActiveModal(null)

    // ── Логика подтверждения и отправки ──────────────────────────────────

    const handleRequestConfirm = ({ payload, displayData }) => {
        retryCount.current = 0
        setPendingFormData({ payload, displayData })
        openModal('confirm')
    }

    const handleCancelConfirm = () => {
        setPendingFormData(null)
        closeModal()
    }

    const handleConfirmSubmit = async () => {
        if (!pendingFormData || isSubmitting) return

        if (!navigator.onLine) {
            setErrorMessage('Нет подключения к интернету. Проверьте соединение и попробуйте снова.')
            setCanRetry(false)
            openModal('error')
            return
        }

        closeModal()
        setIsSubmitting(true)

        const controller = new AbortController()
        const timeoutId  = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)

        // Добавляем group_id в заголовок запроса
        const headers = { 'Content-Type': 'application/json' }
        if (groupId) headers['X-VK-Group-ID'] = groupId

        try {
            const response = await fetch('/api/reservation', {
                method:  'POST',
                headers,
                body:    JSON.stringify(pendingFormData.payload),
                signal:  controller.signal,
            })

            clearTimeout(timeoutId)

            if (RETRYABLE_STATUSES.has(response.status)) {
                const attempt = retryCount.current
                if (attempt < RETRY_DELAYS_MS.length) {
                    retryCount.current += 1
                    const delay = RETRY_DELAYS_MS[attempt]
                    setIsSubmitting(false)
                    setErrorMessage(
                        `${getErrorMessage(response.status)}\n\nПовторная попытка ${retryCount.current} из ${RETRY_DELAYS_MS.length} через ${delay / 1000} сек...`
                    )
                    setCanRetry(false)
                    openModal('error')
                    setTimeout(() => { closeModal(); handleConfirmSubmit() }, delay)
                    return
                }
                throw new Error('Сервер временно недоступен. Пожалуйста, попробуйте позже.')
            }

            if (!response.ok) {
                throw Object.assign(
                    new Error(getErrorMessage(response.status)),
                    { status: response.status }
                )
            }

            const data = await response.json()
            setIsSubmitting(false)
            setReservationData(data)
            setPendingFormData(null)
            retryCount.current = 0
            setFormResetKey(k => k + 1)
            openModal('success')

        } catch (error) {
            clearTimeout(timeoutId)
            setIsSubmitting(false)

            let message   = error.message || 'Не удалось отправить бронь. Попробуйте ещё раз.'
            let showRetry = false

            if (error.name === 'AbortError') {
                message   = 'Превышено время ожидания. Проверьте соединение и попробуйте снова.'
                showRetry = true
            } else if (!navigator.onLine) {
                message   = 'Соединение с сервером потеряно. Проверьте интернет и повторите попытку.'
                showRetry = true
            }

            setErrorMessage(message)
            setCanRetry(showRetry)
            openModal('error')
        }
    }

    const handleRetry = () => { closeModal(); handleConfirmSubmit() }

    // ── Загрузка конфига ─────────────────────────────────────────────────
    if (configLoading) {
        return (
            <ConfigProvider appearance={appearance}>
                <AppRoot>
                    <ScreenSpinner />
                </AppRoot>
            </ConfigProvider>
        )
    }

    // ── Заведение не зарегистрировано — TODO Этап 4: онбординг ──────────
    // Пока показываем заглушку
    if (!isRegistered) {
        return (
            <ConfigProvider appearance={appearance}>
                <AppRoot>
                    <SplitLayout>
                        <SplitCol autoSpaced>
                            <View activePanel="stub">
                                <Panel id="stub">
                                    <div style={{ padding: 24, textAlign: 'center' }}>
                                        <p>Заведение не подключено к системе бронирования.</p>
                                        <p>Обратитесь к администратору группы для настройки.</p>
                                    </div>
                                </Panel>
                            </View>
                        </SplitCol>
                    </SplitLayout>
                </AppRoot>
            </ConfigProvider>
        )
    }

    // Текст успешного экрана из конфига или дефолт
    const venueName    = venueConfig?.welcome_text || 'Шоколадницу'
    const successTitle = `🎉 Бронирование подтверждено!`
    const successDesc  = `Ждём вас! До встречи ☕`

    // ── Основной рендер ──────────────────────────────────────────────────
    return (
        <ConfigProvider appearance={appearance}>
            <AppRoot>
                <SplitLayout>
                    <SplitCol autoSpaced>
                        <View activePanel='home'>
                            <Panel id='home'>
                                <Home
                                    key={formResetKey}
                                    venueConfig={venueConfig}
                                    onRequestConfirm={handleRequestConfirm}
                                    isSubmitting={isSubmitting}
                                />
                            </Panel>
                        </View>
                    </SplitCol>
                </SplitLayout>

                {/* Приветственное окно */}
                <ModalCard
                    open={activeModal === 'welcome'}
                    onClose={closeModal}
                    title="👋 Добро пожаловать!"
                    description="Заполните форму, чтобы забронировать место. Это займёт меньше минуты."
                    actions={
                        <Button size="l" mode="primary" stretched onClick={closeModal}>
                            Отлично, приступим!
                        </Button>
                    }
                />

                {/* Подтверждение бронирования */}
                <ModalCard
                    open={activeModal === 'confirm'}
                    onClose={handleCancelConfirm}
                    title="📋 Проверьте данные"
                    description="Убедитесь, что всё верно, прежде чем подтвердить."
                    actions={
                        <>
                            <Button size="l" mode="primary" stretched onClick={handleConfirmSubmit}>
                                ✅ Подтвердить
                            </Button>
                            <Button
                                size="l" mode="secondary" stretched
                                onClick={handleCancelConfirm}
                                style={{ marginTop: 8 }}
                            >
                                ✏️ Изменить данные
                            </Button>
                        </>
                    }
                >
                    {pendingFormData && (
                        <Text>
                            <b>👤 Имя:</b> {pendingFormData.displayData.name}<br />
                            {pendingFormData.displayData.guests != null && (
                                <><b>👥 Гостей:</b> {pendingFormData.displayData.guests}<br /></>
                            )}
                            <b>📱 Телефон:</b> {pendingFormData.displayData.phone}<br />
                            <b>📅 Дата:</b> {pendingFormData.displayData.date}<br />
                            <b>⏰ Время:</b> {pendingFormData.displayData.time}
                            {pendingFormData.displayData.extra && (
                                <><br />{pendingFormData.displayData.extra}</>
                            )}
                            {pendingFormData.displayData.comment && (
                                <><br /><b>💬</b> {pendingFormData.displayData.comment}</>
                            )}
                        </Text>
                    )}
                </ModalCard>

                {/* Успешное бронирование */}
                <ModalCard
                    open={activeModal === 'success'}
                    onClose={closeModal}
                    title={successTitle}
                    description={successDesc}
                    actions={
                        <Button size="l" stretched mode="primary" onClick={closeModal}>
                            Закрыть
                        </Button>
                    }
                >
                    {reservationData && (
                        <Text>
                            <b>👤 Имя:</b> {reservationData.name}<br />
                            <b>📅 Дата:</b> {reservationData.date}<br />
                            <b>⏰ Время:</b> {reservationData.time}
                        </Text>
                    )}
                </ModalCard>

                {/* Ошибка */}
                <ModalCard
                    open={activeModal === 'error'}
                    onClose={closeModal}
                    title="⚠️ Ошибка"
                    description={errorMessage}
                    actions={
                        <>
                            <Button size="l" mode="primary" stretched onClick={closeModal}>
                                Понятно
                            </Button>
                            {canRetry && (
                                <Button
                                    size="l" mode="secondary" stretched
                                    onClick={handleRetry}
                                    style={{ marginTop: 8 }}
                                >
                                    🔄 Попробовать снова
                                </Button>
                            )}
                        </>
                    }
                />

                {isSubmitting && <ScreenSpinner />}
            </AppRoot>
        </ConfigProvider>
    )
}

export default App