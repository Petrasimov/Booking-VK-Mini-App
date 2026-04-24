/**
 * Вкладка "Настройки" в панели владельца.
 */

import { useState } from 'react'
import {
    Group, Header, FormItem, Input, Button, Snackbar, Textarea,
} from '@vkontakte/vkui'

function SettingsTab({ headers, venueData }) {
    const [name,     setName]     = useState(venueData?.name     || '')
    const [address,  setAddress]  = useState(venueData?.address  || '')
    const [phone,    setPhone]    = useState(venueData?.phone     || '')
    const [chatId,   setChatId]   = useState(venueData?.config?.notifications_chat_id || '')
    const [color,    setColor]    = useState(venueData?.config?.accent_color || '#FF6B35')
    const [welcome,  setWelcome]  = useState(venueData?.config?.welcome_text || '')
    const [saving,   setSaving]   = useState(false)
    const [snackbar, setSnackbar] = useState(null)

    const handleSave = async () => {
        setSaving(true)
        try {
            const newConfig = {
                ...(venueData?.config || {}),
                accent_color:          color,
                welcome_text:          welcome,
                notifications_chat_id: chatId ? parseInt(chatId) : null,
            }

            const res = await fetch('/api/venue/config', {
                method:  'PATCH',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body:    JSON.stringify({ config: newConfig, name, address, phone }),
            })

            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            setSnackbar({ text: '✅ Настройки сохранены' })

            // Применяем новый цвет сразу
            document.documentElement.style.setProperty('--accent-color', color)
        } catch (e) {
            setSnackbar({ text: `❌ Ошибка: ${e.message}` })
        } finally {
            setSaving(false)
        }
    }

    return (
        <Group>
            <Header>Основная информация</Header>

            <FormItem top="Название заведения">
                <Input value={name} onChange={e => setName(e.target.value)} maxLength={200} />
            </FormItem>

            <FormItem top="Адрес">
                <Input value={address} onChange={e => setAddress(e.target.value)} maxLength={500} />
            </FormItem>

            <FormItem top="Телефон">
                <Input value={phone} onChange={e => setPhone(e.target.value)} type="tel" />
            </FormItem>

            <Header>Уведомления</Header>

            <FormItem top="ID беседы с персоналом" bottom="Куда бот отправляет новые брони">
                <Input
                    value={chatId}
                    onChange={e => setChatId(e.target.value)}
                    type="number"
                    placeholder="2000000001"
                />
            </FormItem>

            <Header>Внешний вид формы</Header>

            <FormItem top="Приветственный текст" bottom="Заголовок кнопки бронирования">
                <Input
                    value={welcome}
                    onChange={e => setWelcome(e.target.value)}
                    placeholder="Забронировать столик"
                    maxLength={100}
                />
            </FormItem>

            <FormItem top="Акцентный цвет">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <input
                        type="color"
                        value={color}
                        onChange={e => setColor(e.target.value)}
                        style={{ width: 48, height: 36, border: 'none',
                            borderRadius: 8, cursor: 'pointer', padding: 2 }}
                    />
                    <span style={{ fontSize: 14, fontFamily: 'monospace' }}>{color}</span>
                    <div style={{
                        flex: 1, height: 36, borderRadius: 8,
                        background: color, opacity: 0.3,
                    }} />
                </div>
            </FormItem>

            <FormItem>
                <Button size="l" stretched onClick={handleSave} loading={saving}>
                    Сохранить настройки
                </Button>
            </FormItem>

            {snackbar && (
                <Snackbar onClose={() => setSnackbar(null)}>{snackbar.text}</Snackbar>
            )}
        </Group>
    )
}

export default SettingsTab