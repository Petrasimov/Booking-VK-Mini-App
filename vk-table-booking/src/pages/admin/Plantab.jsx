/**
 * Вкладка "Тариф" в панели владельца.
 */

import { useState, useEffect } from 'react'
import { Group, Header, Button, Snackbar, SimpleCell } from '@vkontakte/vkui'

const PLANS = [
    {
        id:    'free',
        name:  'Бесплатный',
        price: '0 ₽',
        features: [
            '30 броней в месяц',
            '1 локация',
            'История 30 дней',
            'Базовые уведомления',
        ],
    },
    {
        id:    'standard',
        name:  'Стандарт',
        price: '499 ₽/мес',
        features: [
            'Безлимит броней',
            '1 локация',
            'История 6 месяцев',
            'CSV экспорт',
            'Кастомный цвет и текст',
        ],
        highlight: true,
    },
    {
        id:    'pro',
        name:  'Про',
        price: '1 299 ₽/мес',
        features: [
            'Безлимит броней',
            'До 5 локаций',
            'История 2 года',
            'CSV экспорт',
            'Полный архив',
            'Приоритетная поддержка',
        ],
    },
]

function PlanTab({ headers, venueData }) {
    const [currentPlan, setCurrentPlan] = useState(venueData?.plan || 'free')
    const [expiresAt,   setExpiresAt]   = useState(venueData?.plan_expires_at)
    const [loading,     setLoading]     = useState(null)
    const [snackbar,    setSnackbar]    = useState(null)

    // Загружаем актуальный тариф при открытии вкладки
    useEffect(() => {
        fetch('/api/venue/me', { headers })
            .then(r => r.json())
            .then(d => {
                if (d.plan) setCurrentPlan(d.plan)
                if (d.plan_expires_at) setExpiresAt(d.plan_expires_at)
            })
            .catch(() => {})
    }, [])

    const handleUpgrade = async (planId) => {
        setLoading(planId)
        try {
            const res = await fetch('/api/payments/create', {
                method:  'POST',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body:    JSON.stringify({ plan: planId, months: 1 }),
            })

            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const data = await res.json()

            // Открываем страницу оплаты
            if (data.payment_url) {
                window.open(data.payment_url, '_blank')
            } else {
                throw new Error('Нет ссылки на оплату')
            }
        } catch (e) {
            setSnackbar({ text: `❌ Ошибка: ${e.message}` })
        } finally {
            setLoading(null)
        }
    }

    return (
        <Group>
            <Header>Текущий тариф</Header>

            <SimpleCell>
                <div style={{ padding: '4px 0' }}>
                    <div style={{ fontWeight: 500, fontSize: 16 }}>
                        {PLANS.find(p => p.id === currentPlan)?.name || 'Бесплатный'}
                    </div>
                    {expiresAt && (
                        <div style={{ fontSize: 13,
                            color: 'var(--vkui--color_text_secondary)', marginTop: 2 }}>
                            Действует до: {new Date(expiresAt).toLocaleDateString('ru-RU')}
                        </div>
                    )}
                </div>
            </SimpleCell>

            <Header>Тарифные планы</Header>

            {PLANS.map(plan => (
                <div key={plan.id} style={{
                    margin: '0 16px 12px',
                    border: plan.highlight
                        ? '2px solid var(--vkui--color_accent)'
                        : '1px solid var(--vkui--color_separator_primary)',
                    borderRadius: 12,
                    padding: '14px 16px',
                    background: plan.id === currentPlan
                        ? 'var(--vkui--color_background_secondary)'
                        : 'var(--vkui--color_background_content)',
                }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between',
                        alignItems: 'center', marginBottom: 8 }}>
                        <div>
                            <div style={{ fontWeight: 600, fontSize: 16 }}>
                                {plan.name}
                                {plan.highlight && (
                                    <span style={{ fontSize: 11,
                                        background: 'var(--vkui--color_accent)',
                                        color: '#fff', borderRadius: 4,
                                        padding: '1px 6px', marginLeft: 8 }}>
                                        Популярный
                                    </span>
                                )}
                            </div>
                            <div style={{ fontSize: 18, fontWeight: 500, marginTop: 2 }}>
                                {plan.price}
                            </div>
                        </div>
                        {plan.id !== currentPlan && (
                            <Button
                                size="m"
                                mode={plan.highlight ? 'primary' : 'secondary'}
                                onClick={() => handleUpgrade(plan.id)}
                                loading={loading === plan.id}
                                disabled={!!loading}
                            >
                                Выбрать
                            </Button>
                        )}
                        {plan.id === currentPlan && (
                            <span style={{ fontSize: 13,
                                color: 'var(--vkui--color_text_positive)' }}>
                                ✓ Текущий
                            </span>
                        )}
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {plan.features.map(f => (
                            <div key={f} style={{ fontSize: 13,
                                color: 'var(--vkui--color_text_secondary)' }}>
                                ✓ {f}
                            </div>
                        ))}
                    </div>
                </div>
            ))}

            <div style={{ padding: '4px 16px 16px', fontSize: 12,
                color: 'var(--vkui--color_text_secondary)' }}>
                Оплата через ЮKassa. При смене тарифа вверх — остаток
                текущего периода засчитывается.
            </div>

            {snackbar && (
                <Snackbar onClose={() => setSnackbar(null)}>{snackbar.text}</Snackbar>
            )}
        </Group>
    )
}

export default PlanTab