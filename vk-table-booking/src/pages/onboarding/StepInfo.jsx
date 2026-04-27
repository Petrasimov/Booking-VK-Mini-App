import { useState } from 'react'
import { Button, FormItem, Group, Header, Input, Select } from '@vkontakte/vkui'

// Уникальные часовые пояса России — один город на смещение
const TIMEZONES = [
    { label: 'Калининград (UTC+2)',  value: 'Europe/Kaliningrad' },
    { label: 'Москва (UTC+3)',       value: 'Europe/Moscow'      },
    { label: 'Самара (UTC+4)',       value: 'Europe/Samara'      },
    { label: 'Екатеринбург (UTC+5)', value: 'Asia/Yekaterinburg' },
    { label: 'Омск (UTC+6)',         value: 'Asia/Omsk'          },
    { label: 'Красноярск (UTC+7)',   value: 'Asia/Krasnoyarsk'   },
    { label: 'Иркутск (UTC+8)',      value: 'Asia/Irkutsk'       },
    { label: 'Якутск (UTC+9)',       value: 'Asia/Yakutsk'       },
    { label: 'Владивосток (UTC+10)', value: 'Asia/Vladivostok'   },
    { label: 'Магадан (UTC+11)',     value: 'Asia/Magadan'       },
    { label: 'Камчатка (UTC+12)',    value: 'Asia/Kamchatka'     },
]

const NAME_MIN = 2
const NAME_MAX = 60
const ADDR_MAX = 200

// Форматирование телефона: 10 цифр → +7 (XXX) XXX-XX-XX
function formatPhone(digits) {
    const d = digits.slice(0, 10)
    if (d.length === 0) return ''
    let result = '+7'
    if (d.length > 0) result += ' (' + d.slice(0, 3)
    if (d.length >= 3) result += ') ' + d.slice(3, 6)
    else return result
    if (d.length >= 6) result += '-' + d.slice(6, 8)
    if (d.length >= 8) result += '-' + d.slice(8, 10)
    return result
}

// Извлекаем только цифры (кроме ведущей 7/8)
function extractDigits(value) {
    const digits = value.replace(/\D/g, '')
    if (digits.startsWith('7') || digits.startsWith('8')) {
        return digits.slice(1)
    }
    return digits
}

function StepInfo({ state, set, next, back }) {
    const [touched, setTouched] = useState({ name: false, phone: false })

    // Валидация имени
    const nameLen   = state.name.trim().length
    const nameError = touched.name && (nameLen < NAME_MIN
        ? `Минимум ${NAME_MIN} символа`
        : nameLen > NAME_MAX
        ? `Максимум ${NAME_MAX} символов`
        : null)

    // Валидация телефона: должно быть ровно 10 цифр
    const phoneDigits = extractDigits(state.phone)
    const phoneError  = touched.phone && phoneDigits.length > 0 && phoneDigits.length < 10
        ? 'Введите полный номер — 10 цифр после +7'
        : null

    const phoneComplete = phoneDigits.length === 10

    const canNext = nameLen >= NAME_MIN && nameLen <= NAME_MAX

    // Обработчик поля телефона
    const handlePhoneChange = (e) => {
        const raw    = e.target.value
        const digits = extractDigits(raw)
        const capped = digits.slice(0, 10)
        set('phone', capped.length > 0 ? formatPhone(capped) : '')
    }

    return (
        <Group header={<Header>Информация о заведении</Header>}>

            {/* Название */}
            <FormItem
                top="Название"
                status={nameError ? 'error' : 'default'}
                bottom={
                    nameError
                        ? nameError
                        : <span style={{
                            float: 'right',
                            fontSize: 12,
                            color: nameLen > NAME_MAX
                                ? 'var(--vkui--color_text_negative)'
                                : 'var(--vkui--color_text_secondary)',
                          }}>
                            {nameLen}/{NAME_MAX}
                          </span>
                }
            >
                <Input
                    value={state.name}
                    onChange={e => set('name', e.target.value)}
                    onBlur={() => setTouched(t => ({ ...t, name: true }))}
                    placeholder="Кафе Уют"
                    maxLength={NAME_MAX}
                />
            </FormItem>

            {/* Адрес */}
            <FormItem
                top="Адрес"
                bottom={
                    <span style={{
                        float: 'right',
                        fontSize: 12,
                        color: (state.address?.length || 0) > ADDR_MAX
                            ? 'var(--vkui--color_text_negative)'
                            : 'var(--vkui--color_text_secondary)',
                    }}>
                        {state.address?.length || 0}/{ADDR_MAX}
                    </span>
                }
            >
                <Input
                    value={state.address}
                    onChange={e => set('address', e.target.value)}
                    placeholder="ул. Примерная, 1"
                    maxLength={ADDR_MAX}
                />
            </FormItem>

            {/* Телефон */}
            <FormItem
                top="Телефон для гостей"
                status={phoneError ? 'error' : 'default'}
                bottom={phoneError || undefined}
            >
                <Input
                    type="tel"
                    value={state.phone || ''}
                    onChange={handlePhoneChange}
                    onBlur={() => setTouched(t => ({ ...t, phone: true }))}
                    placeholder="+7 (___) ___-__-__"
                />
            </FormItem>

            {/* Часовой пояс */}
            <FormItem top="Часовой пояс">
                <Select
                    value={state.timezone}
                    onChange={e => set('timezone', e.target.value)}
                    options={TIMEZONES}
                />
            </FormItem>

            <div style={{ display: 'flex', gap: 8, padding: '8px 16px' }}>
                <Button size="l" mode="secondary" stretched onClick={back}>← Назад</Button>
                <Button
                    size="l"
                    stretched
                    onClick={() => {
                        setTouched({ name: true, phone: true })
                        if (canNext) next()
                    }}
                    disabled={!canNext}
                >
                    Далее →
                </Button>
            </div>
        </Group>
    )
}

export default StepInfo