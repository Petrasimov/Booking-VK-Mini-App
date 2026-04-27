/**
 * Вкладка "Статистика" в панели владельца.
 */

import { useState, useEffect } from 'react'
import { Group, Header, Spinner, Select, FormItem, SimpleCell } from '@vkontakte/vkui'
import {
    LineChart, Line, BarChart, Bar,
    XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

function StatCard({ label, value, sub }) {
    return (
        <div style={{
            flex: 1, minWidth: 100,
            background: 'var(--vkui--color_background_secondary)',
            borderRadius: 10, padding: '12px 14px',
            textAlign: 'center',
        }}>
            <div style={{ fontSize: 24, fontWeight: 600,
                color: 'var(--vkui--color_text_primary)' }}>{value}</div>
            <div style={{ fontSize: 12,
                color: 'var(--vkui--color_text_secondary)', marginTop: 2 }}>{label}</div>
            {sub && <div style={{ fontSize: 11,
                color: 'var(--vkui--color_text_secondary)' }}>{sub}</div>}
        </div>
    )
}

function StatsTab({ headers }) {
    const [stats,   setStats]   = useState(null)
    const [period,  setPeriod]  = useState('30d')
    const [loading, setLoading] = useState(true)
    const [error,   setError]   = useState('')

    useEffect(() => {
        const fetch_ = async () => {
            setLoading(true)
            setError('')
            try {
                const res  = await fetch(`/api/admin/stats?period=${period}`, { headers })
                if (!res.ok) throw new Error(`HTTP ${res.status}`)
                setStats(await res.json())
            } catch (e) {
                setError(e.message)
            } finally {
                setLoading(false)
            }
        }
        fetch_()
    }, [period])

    if (loading) return (
        <Group><div style={{ padding: 40, textAlign: 'center' }}><Spinner /></div></Group>
    )

    if (error) return (
        <Group>
            <div style={{ padding: 24, textAlign: 'center',
                color: 'var(--vkui--color_text_negative)' }}>
                Ошибка: {error}
            </div>
        </Group>
    )

    return (
        <Group>
            <FormItem style={{ padding: '8px 16px' }}>
                <Select
                    value={period}
                    onChange={e => setPeriod(e.target.value)}
                    options={[
                        { label: '7 дней',  value: '7d'  },
                        { label: '30 дней', value: '30d' },
                        { label: '90 дней', value: '90d' },
                        { label: 'Всё',     value: 'all' },
                    ]}
                />
            </FormItem>

            {/* Карточки метрик */}
            <div style={{ display: 'flex', gap: 8, padding: '0 16px 12px', flexWrap: 'wrap' }}>
                <StatCard label="Броней"   value={stats.total}    />
                <StatCard label="Гостей"   value={stats.guests}   />
                <StatCard label="Пришли"   value={stats.came}     sub={`${stats.conversion}%`} />
                <StatCard label="Не пришли" value={stats.no_show} />
            </div>

            {/* График по дням */}
            {stats.daily?.length > 0 && (
                <>
                    <Header mode="secondary" style={{ padding: '0 16px' }}>
                        Брони по дням
                    </Header>
                    <div style={{ padding: '0 8px 16px' }}>
                        <ResponsiveContainer width="100%" height={180}>
                            <LineChart data={stats.daily}
                                margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--vkui--color_separator_primary)" />
                                <XAxis dataKey="date"
                                    tickFormatter={d => d.slice(5)}
                                    tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 11 }} />
                                <Tooltip
                                    labelFormatter={d => `Дата: ${d}`}
                                    formatter={(v, n) => [v, n === 'bookings' ? 'Броней' : 'Гостей']}
                                />
                                <Line type="monotone" dataKey="bookings"
                                    stroke="var(--vkui--color_accent)"
                                    strokeWidth={2} dot={false} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </>
            )}

            {/* Популярные часы */}
            {stats.popular_hours?.length > 0 && (
                <>
                    <Header mode="secondary" style={{ padding: '0 16px' }}>
                        Популярные часы
                    </Header>
                    <div style={{ padding: '0 8px 16px' }}>
                        <ResponsiveContainer width="100%" height={140}>
                            <BarChart data={stats.popular_hours}
                                margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--vkui--color_separator_primary)" />
                                <XAxis dataKey="hour"
                                    tickFormatter={h => `${h}:00`}
                                    tick={{ fontSize: 11 }} />
                                <YAxis tick={{ fontSize: 11 }} />
                                <Tooltip
                                    labelFormatter={h => `${h}:00`}
                                    formatter={v => [v, 'Броней']}
                                />
                                <Bar dataKey="count" fill="var(--vkui--color_accent)" radius={[4,4,0,0]} maxBarSize={60} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </>
            )}

            {stats.daily?.length === 0 && stats.total === 0 && (
                <div style={{ padding: 32, textAlign: 'center',
                    color: 'var(--vkui--color_text_secondary)', fontSize: 14 }}>
                    Нет данных за выбранный период
                </div>
            )}
        </Group>
    )
}

export default StatsTab