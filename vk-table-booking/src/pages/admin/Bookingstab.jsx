/**
 * Вкладка "Брони" в панели владельца.
 * Список броней с фильтрами, пагинацией, действиями.
 */

import { useState, useEffect, useCallback } from 'react'
import {
    Group, Header, Button, Select,
    SimpleCell, Pagination, FormItem,
    Snackbar, Avatar,
} from '@vkontakte/vkui'

const STATUS_LABELS = {
    null:  { label: 'Ожидает',    color: '#FFA500' },
    true:  { label: 'Пришёл',     color: '#4CAF50' },
    false: { label: 'Не пришёл',  color: '#F44336' },
}

function BookingsTab({ headers, venueData }) {
    const [bookings,   setBookings]   = useState([])
    const [total,      setTotal]      = useState(0)
    const [pages,      setPages]      = useState(1)
    const [page,       setPage]       = useState(1)
    const [loading,    setLoading]    = useState(true)
    const [appeared,   setAppeared]   = useState('')
    const [snackbar,   setSnackbar]   = useState(null)
    const [exporting,  setExporting]  = useState(false)

    const canExport = ['standard', 'pro'].includes(venueData?.plan)

    const fetchBookings = useCallback(async () => {
        setLoading(true)
        try {
            const params = new URLSearchParams({ page, page_size: 20 })
            if (appeared) params.set('appeared', appeared)

            const res = await fetch(`/api/admin/bookings?${params}`, { headers })
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const data = await res.json()

            setBookings(data.items)
            setTotal(data.total)
            setPages(data.pages || 1)
        } catch (e) {
            setSnackbar({ text: `Ошибка загрузки: ${e.message}` })
        } finally {
            setLoading(false)
        }
    }, [page, appeared, headers])

    useEffect(() => { fetchBookings() }, [fetchBookings])

    const updateBooking = async (id, appearedVal) => {
        try {
            await fetch(`/api/admin/bookings/${id}`, {
                method:  'PATCH',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body:    JSON.stringify({ appeared: appearedVal }),
            })
            setSnackbar({ text: appearedVal ? '✅ Отмечен пришедшим' : '❌ Отмечен как не пришёл' })
            fetchBookings()
        } catch (e) {
            setSnackbar({ text: `Ошибка: ${e.message}` })
        }
    }

    const handleExport = async () => {
        setExporting(true)
        try {
            // Передаём текущий фильтр в экспорт
            const params = new URLSearchParams()
            if (appeared) params.set('appeared', appeared)

            const res = await fetch(`/api/admin/export/csv?${params}`, { headers })
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const blob = await res.blob()
            const url  = URL.createObjectURL(blob)
            const a    = document.createElement('a')
            a.href     = url

            // Имя файла отражает примененный фильтр
            const filterSuffix = appeared ? `_${appeared}` : '_all'
            a.download = `bookings${filterSuffix}_${new Date().toISOString().slice(0,10)}.csv`
            a.click()
            URL.revokeObjectURL(url)
        } catch (e) {
            setSnackbar({ text: `Ошибка экспорта: ${e.message}` })
        } finally {
            setExporting(false)
        }
    }

    return (
        <Group>
            {/* Фильтры */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '8px 16px' }}>
                <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, color: 'var(--vkui--color_text_secondary)', marginBottom: 4 }}>
                        Статус
                    </div>
                    <Select
                        value={appeared}
                        onChange={e => { setAppeared(e.target.value); setPage(1) }}
                        options={[
                            { label: 'Все',       value: '' },
                            { label: 'Ожидает',   value: 'null' },
                            { label: 'Пришёл',    value: 'true' },
                            { label: 'Не пришёл', value: 'false' },
                        ]}
                    />
                </div>
                {canExport && appeared === '' && (
                    <Button
                        size="m"
                        mode="secondary"
                        onClick={handleExport}
                        loading={exporting}
                        style={{ whiteSpace: 'nowrap', marginTop: 20 }}
                    >
                        📥 Экспорт CSV
                    </Button>
                )}
            </div>

            <Header mode="secondary">
                Всего: {total}
            </Header>

            {loading ? (
                <div style={{ padding: 32, textAlign: 'center',
                    color: 'var(--vkui--color_text_secondary)' }}>
                    Загрузка...
                </div>
            ) : bookings.length === 0 ? (
                <div style={{ padding: 32, textAlign: 'center',
                    color: 'var(--vkui--color_text_secondary)', fontSize: 14 }}>
                    Броней нет
                </div>
            ) : (
                bookings.map(b => {
                    const statusKey = b.appeared === null ? 'null' : String(b.appeared)
                    const status    = STATUS_LABELS[statusKey] || STATUS_LABELS['null']
                    const extraStr  = Object.entries(b.extra_data || {})
                        .map(([k, v]) => `${k}: ${v}`).join(' · ')

                    return (
                        <SimpleCell
                            key={b.id}
                            before={
                                <Avatar size={40} style={{ background: status.color }}>
                                    <span style={{ color: '#fff', fontSize: 16 }}>
                                        {b.name?.[0]?.toUpperCase() || '?'}
                                    </span>
                                </Avatar>
                            }
                            subtitle={`${b.date} · ${b.time} · ${b.phone}${extraStr ? ' · ' + extraStr : ''}${b.comment ? ' · ' + b.comment : ''}`}
                            after={
                                b.appeared === null && (
                                    <div style={{ display: 'flex', gap: 4 }}>
                                        <Button size="s" mode="positive"
                                            onClick={() => updateBooking(b.id, true)}>✓</Button>
                                        <Button size="s" mode="destructive"
                                            onClick={() => updateBooking(b.id, false)}>✗</Button>
                                    </div>
                                )
                            }
                            multiline
                        >
                            {b.name} · {b.guests} гост.
                            <span style={{ fontSize: 12, color: status.color, marginLeft: 8 }}>
                                {status.label}
                            </span>
                        </SimpleCell>
                    )
                })
            )}

            {pages > 1 && (
                <div style={{ padding: '8px 16px' }}>
                    <Pagination
                        currentPage={page}
                        totalPages={pages}
                        onChange={setPage}
                    />
                </div>
            )}

            {snackbar && (
                <Snackbar onClose={() => setSnackbar(null)}>
                    {snackbar.text}
                </Snackbar>
            )}
        </Group>
    )
}

export default BookingsTab