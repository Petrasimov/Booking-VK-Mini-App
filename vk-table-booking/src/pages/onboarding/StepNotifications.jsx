import { useState } from 'react'
import {
    Button, FormItem, Group, Header,
    Input, Spinner, Banner,
} from '@vkontakte/vkui'

function StepNotifications({ state, set, back, onFinish }) {
    const [verifying,  setVerifying]  = useState(false)
    const [verified,   setVerified]   = useState(false)
    const [verifyErr,  setVerifyErr]  = useState('')

    const handleVerify = async () => {
        if (!state.chatId || !state.botToken) {
            setVerifyErr('Укажите ID беседы и токен бота')
            return
        }
        setVerifying(true)
        setVerifyErr('')
        setVerified(false)

        try {
            const res = await fetch('/api/venue/verify-bot', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-VK-Group-ID': window.vkGroupId || '0',
                    'X-VK-User-ID':  window.vkUserId  || '0',
                },
            })
            const data = await res.json()
            if (data.status === 'ok') {
                setVerified(true)
            } else {
                setVerifyErr(data.detail || 'Ошибка проверки')
            }
        } catch (e) {
            setVerifyErr('Не удалось проверить подключение', e)
        } finally {
            setVerifying(false)
        }
    }

    return (
        <Group header={<Header>Уведомления для персонала</Header>}>
            <Banner
                header="Как подключить бота"
                subheader="Добавьте бот вашей группы в беседу с персоналом, затем скопируйте ID беседы из URL и вставьте ниже."
            />

            <FormItem top="Токен группы (vk_group_token)">
                <Input
                    value={state.botToken}
                    onChange={e => set('botToken', e.target.value)}
                    placeholder="vk1.a...."
                    type="password"
                />
            </FormItem>

            <FormItem top="ID беседы с персоналом" bottom="Например: 2000000001">
                <Input
                    value={state.chatId}
                    onChange={e => {
                        set('chatId', e.target.value)
                        setVerified(false)
                        setVerifyErr('')
                    }}
                    placeholder="2000000001"
                    type="number"
                />
            </FormItem>

            {verifyErr && (
                <FormItem>
                    <span style={{ color: 'var(--vkui--color_text_negative)', fontSize: 13 }}>
                        ❌ {verifyErr}
                    </span>
                </FormItem>
            )}

            {verified && (
                <FormItem>
                    <span style={{ color: 'var(--vkui--color_text_positive)', fontSize: 13 }}>
                        ✅ Бот подключён успешно!
                    </span>
                </FormItem>
            )}

            {(state.chatId || state.botToken) && !verified && (
                <FormItem>
                    <Button
                        size="m"
                        mode="secondary"
                        onClick={handleVerify}
                        disabled={verifying}
                        before={verifying ? <Spinner size="small" /> : null}
                    >
                        {verifying ? 'Проверяю...' : 'Проверить подключение'}
                    </Button>
                </FormItem>
            )}

            {state.loading && (
                <FormItem>
                    <span style={{ color: 'var(--vkui--color_text_secondary)', fontSize: 13 }}>
                        <Spinner size="small" /> Регистрируем заведение...
                    </span>
                </FormItem>
            )}

            {state.error && (
                <FormItem>
                    <span style={{ color: 'var(--vkui--color_text_negative)', fontSize: 13 }}>
                        ❌ {state.error}
                    </span>
                </FormItem>
            )}

            <div style={{ display: 'flex', gap: 8, padding: '8px 16px' }}>
                <Button size="l" mode="secondary" stretched onClick={back}
                    disabled={state.loading}>
                    ← Назад
                </Button>
                <Button size="l" stretched onClick={onFinish}
                    disabled={state.loading}
                    loading={state.loading}>
                    ✅ Готово
                </Button>
            </div>

            <div style={{ padding: '4px 16px 16px', fontSize: 12,
                color: 'var(--vkui--color_text_secondary)' }}>
                Уведомления можно настроить позже в панели управления
            </div>
        </Group>
    )
}

export default StepNotifications