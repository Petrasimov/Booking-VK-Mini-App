import { useMemo } from 'react'
import { Button, Checkbox, FormItem, Group, Header, Select } from '@vkontakte/vkui'

const DAYS = [
    { num: 1, label: 'Пн' }, { num: 2, label: 'Вт' }, { num: 3, label: 'Ср' },
    { num: 4, label: 'Чт' }, { num: 5, label: 'Пт' }, { num: 6, label: 'Сб' },
    { num: 7, label: 'Вс' },
]

const INTERVALS = [
    { label: '15 мин', value: 15 },
    { label: '30 мин', value: 30 },
    { label: '60 мин', value: 60 },
    { label: '90 мин', value: 90 },
]

function makeTimeOptions(from, to, step = 30) {
    const opts = []
    for (let t = from; t <= to; t += step) {
        const h = Math.floor(t / 60), m = t % 60
        const label = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`
        opts.push({ label, value: label })
    }
    return opts
}

const TIME_OPTS = makeTimeOptions(0, 23 * 60 + 30, 30)

function StepSchedule({ state, set, next, back }) {
    const toggleDay = (num) => {
        const days = state.workingDays.includes(num)
            ? state.workingDays.filter(d => d !== num)
            : [...state.workingDays, num].sort()
        set('workingDays', days)
    }

    const slotPreview = useMemo(() => {
        const slots = []
        const [oh, om] = state.openTime.split(':').map(Number)
        const [ch, cm] = state.closeTime.split(':').map(Number)
        let cur = oh * 60 + om
        const end = ch * 60 + cm
        while (cur + state.slotInterval <= end && slots.length < 5) {
            const h = Math.floor(cur / 60), m = cur % 60
            slots.push(`${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`)
            cur += state.slotInterval
        }
        return slots
    }, [state.openTime, state.closeTime, state.slotInterval])

    return (
        <Group header={<Header>Расписание</Header>}>
            <FormItem top="Рабочие дни">
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', padding: '0 0 8px' }}>
                    {DAYS.map(d => (
                        <div
                            key={d.num}
                            onClick={() => toggleDay(d.num)}
                            style={{
                                width: 40, height: 40, borderRadius: 8,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                cursor: 'pointer', fontSize: 13, fontWeight: 500,
                                background: state.workingDays.includes(d.num)
                                    ? 'var(--vkui--color_accent)'
                                    : 'var(--vkui--color_background_secondary)',
                                color: state.workingDays.includes(d.num)
                                    ? '#fff'
                                    : 'var(--vkui--color_text_primary)',
                            }}
                        >
                            {d.label}
                        </div>
                    ))}
                </div>
            </FormItem>

            <FormItem top="Время открытия">
                <Select
                    value={state.openTime}
                    onChange={e => set('openTime', e.target.value)}
                    options={TIME_OPTS}
                />
            </FormItem>

            <FormItem top="Время закрытия">
                <Select
                    value={state.closeTime}
                    onChange={e => set('closeTime', e.target.value)}
                    options={TIME_OPTS}
                />
            </FormItem>

            <FormItem top="Интервал слотов">
                <Select
                    value={state.slotInterval}
                    onChange={e => set('slotInterval', Number(e.target.value))}
                    options={INTERVALS}
                />
            </FormItem>

            {slotPreview.length > 0 && (
                <FormItem top="Первые слоты">
                    <div style={{
                        display: 'flex', gap: 6, flexWrap: 'wrap',
                        padding: '4px 0 8px',
                    }}>
                        {slotPreview.map(s => (
                            <span key={s} style={{
                                padding: '3px 10px',
                                background: 'var(--vkui--color_background_secondary)',
                                borderRadius: 6, fontSize: 13,
                            }}>
                                {s}
                            </span>
                        ))}
                        <span style={{ fontSize: 13, color: 'var(--vkui--color_text_secondary)' }}>
                            ...
                        </span>
                    </div>
                </FormItem>
            )}

            <div style={{ display: 'flex', gap: 8, padding: '8px 16px' }}>
                <Button size="l" mode="secondary" stretched onClick={back}>← Назад</Button>
                <Button size="l" stretched onClick={next}
                    disabled={state.workingDays.length === 0}>
                    Далее →
                </Button>
            </div>
        </Group>
    )
}

export default StepSchedule