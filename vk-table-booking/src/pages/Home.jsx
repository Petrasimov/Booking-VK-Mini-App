/**
 * Главная страница — обёртка для формы бронирования.
 * Содержит Group-контейнер из VKUI.
 */

import { Group, Header } from '@vkontakte/vkui';
import BookingForm from '../components/BookingForm'

function Home({ onRequestConfirm, isSubmitting }) {
    return (
        <Group header={<Header>☕ Шоколадница (Спасская 18)</Header>}>
            <BookingForm
                onRequestConfirm={onRequestConfirm}
                isSubmitting={isSubmitting}
            />
        </Group>
    );
}

export default Home;
