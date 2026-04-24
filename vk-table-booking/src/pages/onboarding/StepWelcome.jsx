import { Button, Group, Placeholder } from '@vkontakte/vkui'

function StepWelcome({ next }) {
    return (
        <Group>
            <Placeholder
                icon={<span style={{ fontSize: 64 }}>🏪</span>}
                header="Подключите систему бронирования"
                action={
                    <Button size="l" stretched onClick={next}>
                        Начать настройку →
                    </Button>
                }
            >
                Настройте онлайн-запись для вашего заведения за 5 минут.
                Гости смогут бронировать прямо ВКонтакте.
            </Placeholder>
        </Group>
    )
}

export default StepWelcome