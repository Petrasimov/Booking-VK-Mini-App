/**
 * Корневой компонент приложения.
 *
 * Управляет модальными окнами:
 *   - welcome  — приветствие при первом открытии
 *   - confirm  — подтверждение данных перед отправкой
 *   - success  — успешное бронирование с данными
 *   - error    — сообщение об ошибке
 *
 * Логика отправки формы находится здесь (не в BookingForm),
 * чтобы показать окно подтверждения до реального запроса к API.
 */

import { useState, useRef } from 'react'
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
    if (status === 409) return 'Бронирование на этот день с таким телефоном уже существует.'
    if (status === 422) return 'Некорректные данные бронирования. Проверьте заполненные поля.'
    if (status === 429) return 'Слишком много запросов. Подождите минуту и попробуйте снова.'
    if (status === 500) return 'Внутренняя ошибка сервера. Попробуйте ещё раз.'
    if (status === 502 || status === 503) return 'Сервер временно недоступен. Попробуйте через несколько секунд.'
    return defaultMsg || 'Не удалось отправить бронь. Попробуйте ещё раз.'
}

function App() {
    // Читаем цветовую схему VK из URL-параметров (vk_color_scheme=space_gray/bright_light)
    const vkColorScheme = new URLSearchParams(window.location.search).get('vk_color_scheme')
    const appearance = vkColorScheme === 'space_gray' ? 'dark' : 'light'

    const [activeModal, setActiveModal] = useState('welcome')
    const [reservationData, setReservationData] = useState(null)
    const [errorMessage, setErrorMessage] = useState('')
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [canRetry, setCanRetry] = useState(false)

    // Данные ожидающей отправки брони: { payload, displayData }
    const [pendingFormData, setPendingFormData] = useState(null)

    // Инкремент при успешной брони — заставляет BookingForm сброситься через key=
    const [formResetKey, setFormResetKey] = useState(0)

    // Счётчик retry-попыток (сбрасывается при каждом новом подтверждении)
    const retryCount = useRef(0)

    const openModal = (name) => setActiveModal(name)
    const closeModal = () => setActiveModal(null)

    /**
     * Вызывается из BookingForm после валидации.
     * Показывает модальное окно подтверждения.
     */
    const handleRequestConfirm = ({ payload, displayData }) => {
        retryCount.current = 0
        setPendingFormData({ payload, displayData })
        openModal('confirm')
    }

    /** Пользователь нажал "Изменить данные" — возвращаемся к форме. */
    const handleCancelConfirm = () => {
        setPendingFormData(null)
        closeModal()
    }

    /** Пользователь подтвердил бронирование — отправляем запрос к API. */
    const handleConfirmSubmit = async () => {
        if (!pendingFormData || isSubmitting) return

        // Проверяем наличие сети до отправки
        if (!navigator.onLine) {
            setErrorMessage('Нет подключения к интернету. Проверьте соединение и попробуйте снова.')
            setCanRetry(false)
            openModal('error')
            return
        }

        closeModal()
        setIsSubmitting(true)

        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)

        try {
            const response = await fetch('/api/reservation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pendingFormData.payload),
                signal: controller.signal,
            })

            clearTimeout(timeoutId)

            // 5xx — retry с exponential backoff
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
                    setTimeout(() => {
                        closeModal()
                        handleConfirmSubmit()
                    }, delay)
                    return
                }
                // Все попытки исчерпаны
                throw new Error('Сервер временно недоступен. Пожалуйста, попробуйте позже.')
            }

            if (!response.ok) {
                throw Object.assign(new Error(getErrorMessage(response.status)), { status: response.status })
            }

            const data = await response.json()

            setIsSubmitting(false)
            setReservationData(data)
            setPendingFormData(null)
            retryCount.current = 0
            setFormResetKey((k) => k + 1)  // сбрасываем форму
            openModal('success')

        } catch (error) {
            clearTimeout(timeoutId)
            setIsSubmitting(false)

            let message = error.message || 'Не удалось отправить бронь. Попробуйте ещё раз.'
            let showRetry = false

            if (error.name === 'AbortError') {
                message = 'Превышено время ожидания. Проверьте соединение и попробуйте снова.'
                showRetry = true
            } else if (!navigator.onLine) {
                message = 'Соединение с сервером потеряно. Проверьте интернет и повторите попытку.'
                showRetry = true
            }

            setErrorMessage(message)
            setCanRetry(showRetry)
            openModal('error')
        }
    }

    /** Повторная попытка из error modal */
    const handleRetry = () => {
        closeModal()
        handleConfirmSubmit()
    }

    return (
        <ConfigProvider appearance={appearance}>
            <AppRoot>
                <SplitLayout>
                    <SplitCol autoSpaced>
                        <View activePanel='home'>
                            <Panel id='home'>
                                <Home
                                    key={formResetKey}
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
                    title="☕ Добро пожаловать в Шоколадницу!"
                    description="🍰 Здесь вы можете быстро и удобно забронировать столик. Заполните форму — это займёт меньше минуты."
                    actions={
                        <Button size="l" mode="primary" stretched onClick={closeModal}>
                            Отлично, приступим! ☕
                        </Button>
                    }
                />

                {/* Подтверждение бронирования */}
                <ModalCard
                    open={activeModal === 'confirm'}
                    onClose={handleCancelConfirm}
                    title="📋 Проверьте данные"
                    description="Убедитесь, что всё верно, прежде чем подтвердить бронирование."
                    actions={
                        <>
                            <Button size="l" mode="primary" stretched onClick={handleConfirmSubmit}>
                                ✅ Подтвердить
                            </Button>
                            <Button
                                size="l"
                                mode="secondary"
                                stretched
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
                            <b>👥 Гостей:</b> {pendingFormData.displayData.guests}<br />
                            <b>📱 Телефон:</b> {pendingFormData.displayData.phone}<br />
                            <b>📅 Дата:</b> {pendingFormData.displayData.date}<br />
                            <b>⏰ Время:</b> {pendingFormData.displayData.time}
                            {pendingFormData.displayData.comment && (
                                <><br /><b>💬 Комментарий:</b> {pendingFormData.displayData.comment}</>
                            )}
                        </Text>
                    )}
                </ModalCard>

                {/* Успешное бронирование */}
                <ModalCard
                    open={activeModal === 'success'}
                    onClose={closeModal}
                    title="🎉 Бронирование подтверждено!"
                    description="🍰 Ждём вас в кафе «Шоколадница»! До встречи ☕"
                    actions={
                        <Button
                            size="l"
                            stretched
                            mode="commerce"
                            component="a"
                            href="https://vk.com/shokokirov?w=app5898182_-156166947"
                            target="_blank"
                        >
                            🎁 Получить подарок
                        </Button>
                    }
                >
                    {reservationData && (
                        <Text>
                            <b>👤 Имя:</b> {reservationData.name}<br />
                            <b>👥 Гостей:</b> {reservationData.guests}<br />
                            <b>📱 Телефон:</b> {reservationData.phone}<br />
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
                                    size="l"
                                    mode="secondary"
                                    stretched
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
