import { Button, Group, Header, SimpleCell, Radio } from '@vkontakte/vkui'

const CATEGORIES = [
    { value: 'cafe',         label: 'Кафе / Ресторан',  icon: '☕' },
    { value: 'barbershop',   label: 'Барбершоп',         icon: '✂️' },
    { value: 'clinic',       label: 'Клиника',            icon: '🏥' },
    { value: 'fitness',      label: 'Фитнес-студия',      icon: '💪' },
    { value: 'beauty',       label: 'Салон красоты',      icon: '💅' },
    { value: 'photo_studio', label: 'Фотостудия',         icon: '📷' },
    { value: 'coworking',    label: 'Коворкинг',          icon: '💼' },
    { value: 'other',        label: 'Другое',             icon: '🏢' },
]

function StepCategory({ state, set, next, back }) {
    return (
        <Group header={<Header>Тип заведения</Header>}>
            {CATEGORIES.map(cat => (
                <SimpleCell
                    key={cat.value}
                    before={<span style={{ fontSize: 24, width: 32 }}>{cat.icon}</span>}
                    after={
                        <Radio
                            name="category"
                            value={cat.value}
                            checked={state.category === cat.value}
                            onChange={() => set('category', cat.value)}
                        />
                    }
                    onClick={() => set('category', cat.value)}
                >
                    {cat.label}
                </SimpleCell>
            ))}

            <div style={{ display: 'flex', gap: 8, padding: '8px 16px' }}>
                <Button size="l" mode="secondary" stretched onClick={back}>← Назад</Button>
                <Button size="l" stretched onClick={next} disabled={!state.category}>
                    Далее →
                </Button>
            </div>
        </Group>
    )
}

export default StepCategory