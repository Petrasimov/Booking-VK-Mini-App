/**
 * Главная страница — обёртка для формы бронирования.
 */

import { Group, Header } from '@vkontakte/vkui';
import BookingForm from '../components/BookingForm'

function Home({ venueConfig, onRequestConfirm, isSubmitting }) {
    const title = venueConfig?.welcome_text || '☕ Бронирование';

    return (
        <Group header={<Header>{title}</Header>}>
            <BookingForm
                venueConfig={venueConfig}
                onRequestConfirm={onRequestConfirm}
                isSubmitting={isSubmitting}
            />
        </Group>
    );
}

export default Home;