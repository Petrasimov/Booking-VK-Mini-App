import { useMemo } from 'react'
import { Button, FormItem, Group, Header, Select } from '@vkontakte/vkui'

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
        const [oh] = state.openTime.split(':').map(Number)
        const [ch] = state.closeTime.split(':').map(Number)
        const om = parseInt(state.openTime.split(':')[1])
        const cm = parseInt(state.closeTime.split(':')[1])
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
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '4px 0 8px' }}>
                    {DAYS.map(d => {
                        const active = state.workingDays.includes(d.num)
                        return (
                            <button
                                key={d.num}
                                type="button"
                                onClick={() => toggleDay(d.num)}
                                style={{
                                    width:        44,
                                    height:       44,
                                    borderRadius: 10,
                                    border:       active ? '2px solid #2688EB' : '1.5px solid #d1d5db',
                                    display:      'flex',
                                    alignItems:   'center',
                                    justifyContent: 'center',
                                    cursor:       'pointer',
                                    fontSize:     13,
                                    fontWeight:   500,
                                    background:   active ? '#2688EB' : '#ffffff',
                                    color:        active ? '#ffffff' : '#333333',
                                    transition:   'all 0.15s',
                                    outline:      'none',
                                    flexShrink:   0,
                                }}
                            >
                                {d.label}
                            </button>
                        )
                    })}
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
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '4px 0 8px' }}>
                        {slotPreview.map(s => (
                            <span key={s} style={{
                                padding:      '4px 10px',
                                background:   '#f0f2f5',
                                borderRadius: 6,
                                fontSize:     13,
                                color:        '#333',
                            }}>
                                {s}
                            </span>
                        ))}
                        <span style={{ fontSize: 13, color: '#999', alignSelf: 'center' }}>...</span>
                    </div>
                </FormItem>
            )}

            <div style={{ display: 'flex', gap: 8, padding: '8px 16px' }}>
                <Button size="l" mode="secondary" stretched onClick={back}>← Назад</Button>
                <Button
                    size="l"
                    stretched
                    onClick={next}
                    disabled={state.workingDays.length === 0}
                >
                    Далее →
                </Button>
            </div>
        </Group>
    )
}

export default StepSchedule