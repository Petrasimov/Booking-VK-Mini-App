/**
 * Онбординг-визард — подключение нового заведения.
 * 5 шагов: Приветствие → Категория → Информация → Расписание → Уведомления
 */

import { useReducer } from 'react'
import StepWelcome       from './StepWelcome'
import StepCategory      from './StepCategory'
import StepInfo          from './StepInfo'
import StepSchedule      from './StepSchedule'
import StepNotifications from './StepNotifications'

const STEPS = ['welcome', 'category', 'info', 'schedule', 'notifications']

const STEP_LABELS = ['', 'Тип', 'Инфо', 'График', 'Уведом.']

const INITIAL_STATE = {
    step:     'welcome',
    category: '',
    name:     '',
    address:  '',
    phone:    '',
    timezone: 'Europe/Moscow',
    workingDays:   [1, 2, 3, 4, 5, 6, 7],
    openTime:      '10:00',
    closeTime:     '22:00',
    slotInterval:  60,
    chatId:        '',
    botToken:      '',
    loading:       false,
    error:         '',
}

function reducer(state, action) {
    switch (action.type) {
        case 'SET_STEP':    return { ...state, step: action.payload, error: '' }
        case 'SET_FIELD':   return { ...state, [action.field]: action.value }
        case 'SET_LOADING': return { ...state, loading: action.payload }
        case 'SET_ERROR':   return { ...state, error: action.payload }
        default:            return state
    }
}

function getStepIndex(step) { return STEPS.indexOf(step) }

function buildConfig(state) {
    const slots = []
    const [oh, om] = state.openTime.split(':').map(Number)
    const [ch, cm] = state.closeTime.split(':').map(Number)
    let cur = oh * 60 + om
    const end = ch * 60 + cm
    while (cur + state.slotInterval <= end) {
        const h = Math.floor(cur / 60), m = cur % 60
        slots.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`)
        cur += state.slotInterval
    }
    return {
        time_slots:            slots,
        slot_duration_minutes: state.slotInterval,
        working_days:          state.workingDays,
        working_hours:         { default: { open: state.openTime, close: state.closeTime } },
        max_guests_per_slot:   1,
        fields: {
            guests:  { enabled: true,  required: true,  max: 8 },
            comment: { enabled: true,  required: false },
            service: { enabled: false, options: [] },
            master:  { enabled: false, options: [] },
            zone:    { enabled: false, options: [] },
        },
        notifications_chat_id: state.chatId   ? parseInt(state.chatId) : null,
        vk_group_token:        state.botToken || null,
        logo_url:              null,
        accent_color:          '#FF6B35',
        welcome_text:          'Онлайн-запись',
    }
}

// ─────────────────────────────────────────────
// Прогресс-бар (только шаги 1–4, шаг 0 = welcome скрыт)
// ─────────────────────────────────────────────
function ProgressBar({ step }) {
    const currentIdx = getStepIndex(step)
    // Показываем шаги 1-4 (не включая welcome)
    const visibleSteps = STEPS.slice(1)

    return (
        <div style={{ padding: '16px 16px 0' }}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
                {visibleSteps.map((s, i) => {
                    const stepIdx   = i + 1  // реальный индекс в STEPS
                    const isDone    = stepIdx < currentIdx
                    const isCurrent = stepIdx === currentIdx
                    const isFuture  = stepIdx > currentIdx

                    return (
                        <div key={s} style={{ display: 'flex', alignItems: 'center', flex: i < visibleSteps.length - 1 ? 1 : 'none' }}>
                            {/* Круг с номером */}
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                                <div style={{
                                    width:        32,
                                    height:       32,
                                    borderRadius: '50%',
                                    display:      'flex',
                                    alignItems:   'center',
                                    justifyContent: 'center',
                                    fontSize:     13,
                                    fontWeight:   500,
                                    transition:   'all 0.3s',
                                    // Цвет зависит от состояния
                                    background: isDone
                                        ? '#2688EB'
                                        : isCurrent
                                        ? '#2688EB'
                                        : 'var(--vkui--color_background_secondary)',
                                    color: isDone || isCurrent
                                        ? '#ffffff'
                                        : 'var(--vkui--color_text_secondary)',
                                    // Текущий шаг — чуть крупнее и с кольцом
                                    boxShadow: isCurrent
                                        ? '0 0 0 3px rgba(38,136,235,0.25)'
                                        : 'none',
                                }}>
                                    {isDone
                                        ? <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                                            <path d="M2.5 7L5.5 10L11.5 4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                          </svg>
                                        : stepIdx
                                    }
                                </div>
                                <div style={{
                                    fontSize:  10,
                                    color:     isDone || isCurrent
                                        ? '#2688EB'
                                        : 'var(--vkui--color_text_secondary)',
                                    fontWeight: isCurrent ? 500 : 400,
                                    whiteSpace: 'nowrap',
                                }}>
                                    {STEP_LABELS[stepIdx]}
                                </div>
                            </div>

                            {/* Линия между шагами */}
                            {i < visibleSteps.length - 1 && (
                                <div style={{
                                    flex:     1,
                                    height:   2,
                                    margin:   '0 4px',
                                    marginBottom: 16,
                                    borderRadius: 1,
                                    background: isDone
                                        ? '#2688EB'
                                        : 'var(--vkui--color_background_secondary)',
                                    transition: 'background 0.3s',
                                }} />
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

function OnboardingWizard({ groupId, vkUserId, onComplete }) {
    const [state, dispatch] = useReducer(reducer, INITIAL_STATE)

    const next = () => {
        const idx = getStepIndex(state.step)
        if (idx < STEPS.length - 1)
            dispatch({ type: 'SET_STEP', payload: STEPS[idx + 1] })
    }

    const back = () => {
        const idx = getStepIndex(state.step)
        if (idx > 0)
            dispatch({ type: 'SET_STEP', payload: STEPS[idx - 1] })
    }

    const set = (field, value) => dispatch({ type: 'SET_FIELD', field, value })

    const handleFinish = async () => {
        dispatch({ type: 'SET_LOADING', payload: true })
        dispatch({ type: 'SET_ERROR',   payload: '' })

        try {
            const config = buildConfig(state)
            const headers = {
                'Content-Type':  'application/json',
                'X-VK-Group-ID': groupId   || '0',
                'X-VK-User-ID':  vkUserId  || '0',
            }
            const res = await fetch('/api/venue/register', {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    name:     state.name,
                    category: state.category,
                    address:  state.address  || null,
                    phone:    state.phone    || null,
                    timezone: state.timezone,
                    config,
                }),
            })

            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || `Ошибка ${res.status}`)
            }

            const cfgRes  = await fetch('/api/config', { headers })
            const cfgData = cfgRes.ok ? await cfgRes.json() : { config }

            onComplete(cfgData)
        } catch (e) {
            dispatch({ type: 'SET_ERROR',   payload: e.message })
            dispatch({ type: 'SET_LOADING', payload: false })
        }
    }

    const props = { state, set, next, back, onFinish: handleFinish }

    return (
        <div>
            {state.step !== 'welcome' && <ProgressBar step={state.step} />}
            {state.step === 'welcome'       && <StepWelcome       {...props} />}
            {state.step === 'category'      && <StepCategory      {...props} />}
            {state.step === 'info'          && <StepInfo          {...props} />}
            {state.step === 'schedule'      && <StepSchedule      {...props} />}
            {state.step === 'notifications' && <StepNotifications {...props} />}
        </div>
    )
}

export default OnboardingWizard