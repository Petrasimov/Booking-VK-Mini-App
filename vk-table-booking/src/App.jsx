/**
 * Корневой компонент приложения.
 *
 * При старте:
 *   1. Загружает конфиг заведения (GET /api/config)
 *   2. Определяет роль пользователя (владелец / гость)
 *   3. Показывает нужный экран:
 *      - Не зарегистрировано + владелец → OnboardingWizard
 *      - Зарегистрировано + владелец    → AdminPanel
 *      - Зарегистрировано + гость       → Home (форма бронирования)
 *      - Не зарегистрировано + гость    → заглушка
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
import Home            from './pages/Home'
import OnboardingWizard from './pages/onboarding/OnboardingWizard'
import AdminPanel      from './pages/admin/AdminPanel'

const FETCH_TIMEOUT_MS   = 10_000
const RETRY_DELAYS_MS    = [1000, 2000, 4000]
const RETRYABLE_STATUSES = new Set([500, 502, 503])

function getErrorMessage(status, defaultMsg) {
    if (status === 402) return 'Лимит бронирований на этот месяц исчерпан. Обратитесь к владельцу заведения.'
    if (status === 409) return 'Бронирование на этот день с таким телефоном уже существует.'
    if (status === 422) return 'Некорректные данные бронирования. Проверьте заполненные поля.'
    if (status === 429) return 'Слишком много запросов. Подождите минуту и попробуйте снова.'
    if (status === 500) return 'Внутренняя ошибка сервера. Попробуйте ещё раз.'
    if (status === 502 || status === 503) return 'Сервер временно недоступен. Попробуйте через несколько секунд.'
    return defaultMsg || 'Не удалось отправить бронь. Попробуйте ещё раз.'
}

function getVkGroupId() {
    const p = new URLSearchParams(window.location.search)
    return p.get('vk_group_id') || p.get('group_id') || null
}

function getVkUserId() {
    const p = new URLSearchParams(window.location.search)
    return p.get('vk_user_id') || null
}

function App() {
    const vkColorScheme = new URLSearchParams(window.location.search).get('vk_color_scheme')
    const appearance    = vkColorScheme === 'space_gray' ? 'dark' : 'light'

    // ── Конфиг и состояние загрузки ──────────────────────────────────────
    const [venueConfig,    setVenueConfig]    = useState(null)
    const [venueData,      setVenueData]      = useState(null)   // полный ответ /api/config
    const [configLoading,  setConfigLoading]  = useState(true)
    const [isRegistered,   setIsRegistered]   = useState(true)
    const [isOwner,        setIsOwner]        = useState(false)

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
    const vkUserId   = getVkUserId()

    if (groupId)  window.vkGroupId = Number(groupId)
    if (vkUserId) window.vkUserId  = Number(vkUserId)

    // ── Загрузка конфига при старте ───────────────────────────────────────
    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const headers = {}
                if (groupId)  headers['X-VK-Group-ID'] = groupId
                if (vkUserId) headers['X-VK-User-ID']  = vkUserId

                const res = await fetch('/api/config', { headers })
                if (!res.ok) throw new Error(`HTTP ${res.status}`)
                const data = await res.json()

                setVenueData(data)

                if (!data.is_registered) {
                    setIsRegistered(false)
                    // Если пришёл с vk_user_id — возможно владелец хочет зарегистрировать
                    setIsOwner(!!vkUserId)
                    setConfigLoading(false)
                    return
                }

                setVenueConfig(data.config)
                setIsRegistered(true)

                // Определяем является ли пользователь владельцем
                if (vkUserId && data.owner_vk_id) {
                    setIsOwner(Number(vkUserId) === Number(data.owner_vk_id))
                }

                if (data.config?.accent_color) {
                    document.documentElement.style.setProperty(
                        '--accent-color', data.config.accent_color
                    )
                }
            } catch (e) {
                console.warn('Failed to load venue config:', e)
                setVenueConfig(null)
            } finally {
                setConfigLoading(false)
            }
        }
        fetchConfig()
    }, [groupId, vkUserId])

    const openModal  = (name) => setActiveModal(name)
    const closeModal = () => setActiveModal(null)

    // ── Логика бронирования ───────────────────────────────────────────────
    const handleRequestConfirm = ({ payload, displayData }) => {
        retryCount.current = 0
        setPendingFormData({ payload, displayData })
        openModal('confirm')
    }

    const handleCancelConfirm = () => { setPendingFormData(null); closeModal() }

    const handleConfirmSubmit = async () => {
        if (!pendingFormData || isSubmitting) return

        if (!navigator.onLine) {
            setErrorMessage('Нет подключения к интернету.')
            setCanRetry(false)
            openModal('error')
            return
        }

        closeModal()
        setIsSubmitting(true)

        const controller = new AbortController()
        const timeoutId  = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)

        const headers = { 'Content-Type': 'application/json' }
        if (groupId)  headers['X-VK-Group-ID'] = groupId
        if (vkUserId) headers['X-VK-User-ID']  = vkUserId

        try {
            const response = await fetch('/api/reservation', {
                method: 'POST', headers,
                body:   JSON.stringify(pendingFormData.payload),
                signal: controller.signal,
            })
            clearTimeout(timeoutId)

            if (RETRYABLE_STATUSES.has(response.status)) {
                const attempt = retryCount.current
                if (attempt < RETRY_DELAYS_MS.length) {
                    retryCount.current += 1
                    const delay = RETRY_DELAYS_MS[attempt]
                    setIsSubmitting(false)
                    setErrorMessage(`${getErrorMessage(response.status)}\n\nПовтор через ${delay / 1000} сек...`)
                    setCanRetry(false)
                    openModal('error')
                    setTimeout(() => { closeModal(); handleConfirmSubmit() }, delay)
                    return
                }
                throw new Error('Сервер временно недоступен.')
            }

            if (!response.ok)
                throw Object.assign(new Error(getErrorMessage(response.status)), { status: response.status })

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
            let message = error.message || 'Не удалось отправить бронь.'
            let showRetry = false
            if (error.name === 'AbortError') { message = 'Превышено время ожидания.'; showRetry = true }
            else if (!navigator.onLine)       { message = 'Нет соединения.';            showRetry = true }
            setErrorMessage(message)
            setCanRetry(showRetry)
            openModal('error')
        }
    }

    const handleRetry = () => { closeModal(); handleConfirmSubmit() }

    // ── Обработчик завершения онбординга ─────────────────────────────────
    const handleOnboardingComplete = (newVenueData) => {
        setVenueData(newVenueData)
        setVenueConfig(newVenueData.config)
        setIsRegistered(true)
        setIsOwner(true)
    }

    // ── Загрузка ─────────────────────────────────────────────────────────
    if (configLoading) {
        return (
            <ConfigProvider appearance={appearance}>
                <AppRoot><ScreenSpinner /></AppRoot>
            </ConfigProvider>
        )
    }

    // ── Роутинг ───────────────────────────────────────────────────────────

    // 1. Заведение не зарегистрировано + пользователь (возможный владелец)
    if (!isRegistered) {
        return (
            <ConfigProvider appearance={appearance}>
                <AppRoot>
                    <SplitLayout>
                        <SplitCol autoSpaced>
                            <View activePanel="onboarding">
                                <Panel id="onboarding">
                                    <OnboardingWizard
                                        groupId={groupId}
                                        vkUserId={vkUserId}
                                        onComplete={handleOnboardingComplete}
                                    />
                                </Panel>
                            </View>
                        </SplitCol>
                    </SplitLayout>
                </AppRoot>
            </ConfigProvider>
        )
    }

    // 2. Заведение зарегистрировано + владелец → панель управления
    if (isRegistered && isOwner) {
        return (
            <ConfigProvider appearance={appearance}>
                <AppRoot>
                    <SplitLayout>
                        <SplitCol autoSpaced>
                            <View activePanel="admin">
                                <Panel id="admin">
                                    <AdminPanel
                                        venueData={venueData}
                                        groupId={groupId}
                                        vkUserId={vkUserId}
                                    />
                                </Panel>
                            </View>
                        </SplitCol>
                    </SplitLayout>
                </AppRoot>
            </ConfigProvider>
        )
    }

    // 3. Гость → форма бронирования
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

                {/* Приветствие */}
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

                {/* Подтверждение */}
                <ModalCard
                    open={activeModal === 'confirm'}
                    onClose={handleCancelConfirm}
                    title="📋 Проверьте данные"
                    description="Убедитесь, что всё верно."
                    actions={
                        <>
                            <Button size="l" mode="primary" stretched onClick={handleConfirmSubmit}>
                                ✅ Подтвердить
                            </Button>
                            <Button size="l" mode="secondary" stretched onClick={handleCancelConfirm}
                                style={{ marginTop: 8 }}>
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

                {/* Успех */}
                <ModalCard
                    open={activeModal === 'success'}
                    onClose={closeModal}
                    title="🎉 Бронирование подтверждено!"
                    description="Ждём вас! До встречи ☕"
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
                                <Button size="l" mode="secondary" stretched onClick={handleRetry}
                                    style={{ marginTop: 8 }}>
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