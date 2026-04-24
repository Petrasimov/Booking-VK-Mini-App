import { Button, FormItem, Group, Header, Input, Select } from '@vkontakte/vkui'

const TIMEZONES = [
    { label: 'Москва (UTC+3)',       value: 'Europe/Moscow' },
    { label: 'Екатеринбург (UTC+5)', value: 'Asia/Yekaterinburg' },
    { label: 'Новосибирск (UTC+7)',  value: 'Asia/Novosibirsk' },
    { label: 'Красноярск (UTC+7)',   value: 'Asia/Krasnoyarsk' },
    { label: 'Иркутск (UTC+8)',      value: 'Asia/Irkutsk' },
    { label: 'Якутск (UTC+9)',       value: 'Asia/Yakutsk' },
    { label: 'Владивосток (UTC+10)', value: 'Asia/Vladivostok' },
    { label: 'Минск (UTC+3)',        value: 'Europe/Minsk' },
    { label: 'Алматы (UTC+6)',       value: 'Asia/Almaty' },
    { label: 'Ташкент (UTC+5)',      value: 'Asia/Tashkent' },
]

function StepInfo({ state, set, next, back }) {
    const canNext = state.name.trim().length >= 2

    return (
        <Group header={<Header>Информация о заведении</Header>}>
            <FormItem top="Название *">
                <Input
                    value={state.name}
                    onChange={e => set('name', e.target.value)}
                    placeholder="Например: Кафе Уют"
                    maxLength={200}
                />
            </FormItem>

            <FormItem top="Адрес">
                <Input
                    value={state.address}
                    onChange={e => set('address', e.target.value)}
                    placeholder="ул. Примерная, 1"
                    maxLength={500}
                />
            </FormItem>

            <FormItem top="Телефон для гостей">
                <Input
                    value={state.phone}
                    onChange={e => set('phone', e.target.value)}
                    placeholder="+7 (___) ___-__-__"
                    type="tel"
                />
            </FormItem>

            <FormItem top="Часовой пояс">
                <Select
                    value={state.timezone}
                    onChange={e => set('timezone', e.target.value)}
                    options={TIMEZONES}
                />
            </FormItem>

            <div style={{ display: 'flex', gap: 8, padding: '8px 16px' }}>
                <Button size="l" mode="secondary" stretched onClick={back}>← Назад</Button>
                <Button size="l" stretched onClick={next} disabled={!canNext}>
                    Далее →
                </Button>
            </div>
        </Group>
    )
}

export default StepInfo