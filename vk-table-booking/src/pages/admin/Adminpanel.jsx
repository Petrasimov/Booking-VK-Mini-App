/**
 * Панель управления заведением для владельца.
 * Вкладки: Брони | Статистика | Настройки | Тариф
 */

import { useState } from 'react'
import {
    Group, TabsItem, Tabs, PanelHeader,
} from '@vkontakte/vkui'
import BookingsTab  from './BookingsTab'
import StatsTab     from './StatsTab'
import SettingsTab  from './SettingsTab'
import PlanTab      from './PlanTab'

function AdminPanel({ venueData, groupId, vkUserId }) {
    const [tab, setTab] = useState('bookings')

    const headers = {}
    if (groupId)  headers['X-VK-Group-ID'] = groupId
    if (vkUserId) headers['X-VK-User-ID']  = vkUserId

    const venueName = venueData?.name || 'Панель управления'

    return (
        <div>
            <PanelHeader>{venueName}</PanelHeader>

            <Tabs>
                <TabsItem selected={tab === 'bookings'} onClick={() => setTab('bookings')}>
                    📋 Брони
                </TabsItem>
                <TabsItem selected={tab === 'stats'} onClick={() => setTab('stats')}>
                    📊 Статистика
                </TabsItem>
                <TabsItem selected={tab === 'settings'} onClick={() => setTab('settings')}>
                    ⚙️ Настройки
                </TabsItem>
                <TabsItem selected={tab === 'plan'} onClick={() => setTab('plan')}>
                    💳 Тариф
                </TabsItem>
            </Tabs>

            {tab === 'bookings'  && <BookingsTab  headers={headers} venueData={venueData} />}
            {tab === 'stats'     && <StatsTab     headers={headers} />}
            {tab === 'settings'  && <SettingsTab  headers={headers} venueData={venueData} />}
            {tab === 'plan'      && <PlanTab      headers={headers} venueData={venueData} />}
        </div>
    )
}

export default AdminPanel