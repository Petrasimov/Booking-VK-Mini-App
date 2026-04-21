/**
 * Форма бронирования столика.
 *
 * Поля: имя, гостей, телефон, дата, время, комментарий.
 * Чекбоксы: согласие с пользовательским соглашением, согласие на обработку ПД,
 *            разрешение уведомлений (VK Bridge, опционально).
 * Уведомления — опциональны, бронирование работает и без них.
 *
 * После валидации вызывает onRequestConfirm({ payload, displayData }) —
 * фактическая отправка запроса происходит в App.jsx.
 */

import { useState, useMemo } from 'react';
import bridge from '@vkontakte/vk-bridge';
import {
    Checkbox,
    FormItem,
    Input,
    Button,
    Textarea,
    Select,
    FormLayoutGroup,
    DateInput,
    IconButton,
} from '@vkontakte/vkui';
import { Icon24Dismiss } from '@vkontakte/icons';
import {
    validateName,
    validateGuests,
    validatePhone,
    validateDate,
    validateTime,
} from '../utils/validators';
import { TERMS_OF_USE_TEXT, USER_AGREEMENT_TEXT, PERSONAL_DATA_CONSENT_TEXT, PRIVACY_POLICY_TEXT } from '../utils/legalTexts';

// Генерация слотов времени: 08:00, 08:30, ..., 20:00
const ALL_TIME_SLOTS = (() => {
    const slots = [];
    for (let h = 8; h <= 20; h++) {
        for (let m = 0; m < 60; m += 30) {
            slots.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
        }
    }
    return slots;
})();

/** Минимальная дата — сегодня (в формате YYYY-MM-DD) */
const getTodayStr = () => new Date().toISOString().split('T')[0];

/** Проверяет, является ли строка датой сегодняшнего дня */
const isToday = (dateStr) => {
    if (!dateStr) return false;
    return dateStr === getTodayStr();
};

/** Конвертирует строку YYYY-MM-DD в объект Date (полночь локального времени) */
const dateStrToDate = (str) => {
    if (!str) return undefined;
    const [y, m, d] = str.split('-').map(Number);
    return new Date(y, m - 1, d);
};

/** Конвертирует объект Date в строку YYYY-MM-DD */
const dateToStr = (date) => {
    if (!date) return '';
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
};

/** Форматирует цифры телефона в читаемый вид: +7 (XXX) XXX-XX-XX */
const formatPhone = (digits) => {
    if (digits.length === 0) return '+7';
    if (digits.length < 3) return `+7 (${digits}`;
    if (digits.length === 3) return `+7 (${digits})`;
    if (digits.length <= 6) return `+7 (${digits.slice(0, 3)}) ${digits.slice(3)}`;
    if (digits.length <= 8) return `+7 (${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
    return `+7 (${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 8)}-${digits.slice(8, 10)}`;
};

const INITIAL_FORM = {
    name: '',
    guests: 1,
    phone: '',
    date: '',
    time: '',
    comment: '',
};

const INITIAL_AGREEMENTS = {
    agreeToTerms: false,
    agreeToPrivacy: false,
    notifications: false,
};

const MODAL_TERMS_OF_USE   = 'modal-terms-of-use';    // Условия использования
const MODAL_PRIVACY_POLICY = 'modal-privacy-policy';  // Политика конфиденциальности
const MODAL_PUBLIC_OFFER   = 'modal-public-offer';    // Публичная оферта
const MODAL_CONSENT        = 'modal-consent';         // Согласие на обработку ПД

function BookingForm({ onRequestConfirm, isSubmitting }) {
    const [form, setForm] = useState(INITIAL_FORM);
    const [errors, setErrors] = useState({});

    // Рандомный плейсхолдер для комментария
    const [commentPlaceholder] = useState(() => {
        const variants = [
            'У окна',
            'В уголочке',
            'На диване',
            'Не возле входа',
            'У розетки',
        ];
        return variants[Math.floor(Math.random() * variants.length)];
    });

    const [agreements, setAgreements] = useState(INITIAL_AGREEMENTS);
    const [consentErrors, setConsentErrors] = useState({});
    const [activeModal, setActiveModal] = useState(null);

    // Кнопка активна только когда заполнены все обязательные поля + два обязательных чекбокса
    // Уведомления — опциональны: бронирование работает без них
    const canSubmit = useMemo(() => {
        const phoneDigits = form.phone.replace(/\D/g, '');
        return (
            form.name.trim().length > 0 &&
            phoneDigits.length >= 10 &&
            form.date.length > 0 &&
            form.time.length > 0 &&
            agreements.agreeToTerms &&
            agreements.agreeToPrivacy
        );
    }, [form.name, form.phone, form.date, form.time, agreements.agreeToTerms, agreements.agreeToPrivacy]);

    // Фильтрация слотов времени: если дата — сегодня, убираем прошедшие
    const availableTimeSlots = useMemo(() => {
        if (!isToday(form.date)) return ALL_TIME_SLOTS;
        const now = new Date();
        const currentMinutes = now.getHours() * 60 + now.getMinutes();
        return ALL_TIME_SLOTS.filter(slot => {
            const [h, m] = slot.split(':').map(Number);
            return h * 60 + m > currentMinutes;
        });
    }, [form.date]);

    /** Валидация всех полей формы */
    const validateFormData = () => {
        const newErrors = {
            name: validateName(form.name),
            guests: validateGuests(form.guests),
            phone: validatePhone(form.phone),
            date: validateDate(form.date),
            time: validateTime(form.time),
        };

        // Удаляем поля без ошибок
        Object.keys(newErrors).forEach(
            key => newErrors[key] === null && delete newErrors[key]
        );

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    /** Обработчик выбора даты из DateInput (получаем объект Date, сохраняем как YYYY-MM-DD) */
    const handleDateChange = (date) => {
        const str = dateToStr(date);
        setForm({ ...form, date: str });
        if (errors.date) {
            setErrors({ ...errors, date: null });
        }
    };

    /** Универсальный обработчик изменения текстового поля */
    const handleChange = (field) => (e) => {
        setForm({ ...form, [field]: e.target.value });
        if (errors[field]) {
            setErrors({ ...errors, [field]: null });
        }
    };

    /** Обработчик телефона: автоформатирование, удаление кода +7/8 */
    const handlePhoneChange = (e) => {
        const allDigits = e.target.value.replace(/\D/g, '');
        let cleaned = allDigits;
        if (cleaned.startsWith('7') || cleaned.startsWith('8')) {
            cleaned = cleaned.slice(1);
        }
        cleaned = cleaned.slice(0, 10);
        const formatted = cleaned.length > 0 ? formatPhone(cleaned) : '';
        setForm({ ...form, phone: formatted });
        if (errors.phone) {
            setErrors({ ...errors, phone: null });
        }
    };

    /**
     * Валидирует форму, формирует payload и displayData,
     * передаёт их в App через onRequestConfirm — реальная отправка там.
     */
    const handleSubmit = () => {
        if (isSubmitting) return;

        // Проверяем два обязательных чекбокса (уведомления — опциональны)
        const newConsentErrors = {};
        if (!agreements.agreeToTerms) {
            newConsentErrors.agreeToTerms = 'Необходимо принять пользовательское соглашение';
        }
        if (!agreements.agreeToPrivacy) {
            newConsentErrors.agreeToPrivacy = 'Необходимо дать согласие на обработку персональных данных';
        }
        setConsentErrors(newConsentErrors);

        if (Object.keys(newConsentErrors).length > 0) return;
        if (!validateFormData()) return;

        const cleanPhone = form.phone.replace(/\D/g, '');

        onRequestConfirm({
            payload: {
                name: form.name,
                guests: form.guests,
                phone: cleanPhone,
                date: form.date,
                time: form.time,
                comment: form.comment || null,
                vk_user_id: window.vkUser?.id ?? null,
                vk_notifications: agreements.notifications,
            },
            displayData: {
                name: form.name,
                guests: form.guests,
                phone: form.phone,  // отформатированный для отображения
                date: form.date,
                time: form.time,
                comment: form.comment || null,
            },
        });
    };

    const DOC_MODALS = {
        [MODAL_TERMS_OF_USE]:   { title: 'Условия использования',        text: TERMS_OF_USE_TEXT },
        [MODAL_PRIVACY_POLICY]: { title: 'Политика конфиденциальности',  text: PRIVACY_POLICY_TEXT },
        [MODAL_PUBLIC_OFFER]:   { title: 'Публичная оферта',             text: USER_AGREEMENT_TEXT },
        [MODAL_CONSENT]:        { title: 'Согласие на обработку данных', text: PERSONAL_DATA_CONSENT_TEXT },
    };

    const activeDoc = activeModal ? DOC_MODALS[activeModal] : null;

    return (
        <>
            {activeDoc && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                    backgroundColor: 'var(--vkui--color_background_modal_inverse)',
                    zIndex: 100,
                    display: 'flex',
                    flexDirection: 'column',
                }}>
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        padding: '12px 16px',
                        borderBottom: '1px solid var(--vkui--color_separator_primary)',
                        backgroundColor: 'var(--vkui--color_background_content)',
                    }}>
                        <span style={{ flex: 1, fontWeight: 600, fontSize: 16 }}>
                            {activeDoc.title}
                        </span>
                        <IconButton onClick={() => setActiveModal(null)}>
                            <Icon24Dismiss />
                        </IconButton>
                    </div>
                    <div style={{
                        flex: 1,
                        overflowY: 'auto',
                        padding: '16px',
                        backgroundColor: 'var(--vkui--color_background_content)',
                    }}>
                        <pre style={{
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            fontFamily: 'inherit',
                            fontSize: 13,
                            lineHeight: 1.6,
                            color: 'var(--vkui--color_text_primary)',
                            margin: 0,
                        }}>
                            {activeDoc.text}
                        </pre>
                    </div>
                </div>
            )}

            <FormLayoutGroup mode="horizontal">
                <FormItem
                    top="👤 Имя"
                    status={errors.name ? 'error' : 'default'}
                    bottom={errors.name}
                >
                    <Input
                        value={form.name}
                        onChange={handleChange('name')}
                        maxLength={100}
                    />
                </FormItem>

                <FormItem
                    top="👥 Гостей"
                    status={errors.guests ? 'error' : 'default'}
                    bottom={errors.guests}
                >
                    <Select
                        value={form.guests}
                        onChange={handleChange('guests')}
                        options={Array.from({ length: 5 }, (_, i) => ({
                            label: String(i + 1),
                            value: i + 1,
                        }))}
                    />
                </FormItem>
            </FormLayoutGroup>

            <FormItem
                top="📱 Телефон"
                status={errors.phone ? 'error' : 'default'}
                bottom={errors.phone}
            >
                <Input
                    type="tel"
                    value={form.phone}
                    onChange={handlePhoneChange}
                    placeholder="+7 (___) ___-__-__"
                />
            </FormItem>

            <FormLayoutGroup mode="horizontal">
                <FormItem
                    top="📅 Дата"
                    status={errors.date ? 'error' : 'default'}
                    bottom={errors.date}
                >
                    <DateInput
                        value={dateStrToDate(form.date)}
                        onChange={handleDateChange}
                        disablePast
                        minDateTime={new Date()}
                        closeOnChange
                    />
                </FormItem>

                <FormItem
                    top="⏰ Время"
                    status={errors.time ? 'error' : 'default'}
                    bottom={errors.time}
                >
                    <Select
                        value={form.time}
                        onChange={handleChange('time')}
                        placeholder="Выберите время"
                        options={availableTimeSlots.map(t => ({ label: t, value: t }))}
                    />
                </FormItem>
            </FormLayoutGroup>

            <FormItem
                top="💬 Комментарий"
                bottom={
                    <span style={{
                        float: 'right',
                        color: form.comment.length > 450
                            ? 'var(--vkui--color_text_negative)'
                            : 'var(--vkui--color_text_secondary)',
                        fontSize: 13,
                    }}>
                        {form.comment.length}/500
                    </span>
                }
            >
                <Textarea
                    value={form.comment}
                    onChange={handleChange('comment')}
                    placeholder={commentPlaceholder}
                    rows={3}
                    maxLength={500}
                />
            </FormItem>

            {/* Чекбокс 1: три документа в одной строке (как на скриншоте) */}
            <FormItem
                status={consentErrors.agreeToTerms ? 'error' : 'default'}
                bottom={consentErrors.agreeToTerms}
            >
                <Checkbox
                    checked={agreements.agreeToTerms}
                    onChange={(e) => {
                        setAgreements({ ...agreements, agreeToTerms: e.target.checked });
                        if (e.target.checked && consentErrors.agreeToTerms) {
                            setConsentErrors({ ...consentErrors, agreeToTerms: undefined });
                        }
                    }}
                >
                    {'Я принимаю '}
                    <span style={{ textDecoration: 'underline', cursor: 'pointer' }}
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setActiveModal(MODAL_TERMS_OF_USE); }}>
                        условия использования
                    </span>
                    {', '}
                    <span style={{ textDecoration: 'underline', cursor: 'pointer' }}
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setActiveModal(MODAL_PRIVACY_POLICY); }}>
                        политику конфиденциальности
                    </span>
                    {' и '}
                    <span style={{ textDecoration: 'underline', cursor: 'pointer' }}
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setActiveModal(MODAL_PUBLIC_OFFER); }}>
                        публичную оферту
                    </span>
                </Checkbox>
            </FormItem>

            {/* Чекбокс 2: согласие на обработку ПД */}
            <FormItem
                status={consentErrors.agreeToPrivacy ? 'error' : 'default'}
                bottom={consentErrors.agreeToPrivacy}
            >
                <Checkbox
                    checked={agreements.agreeToPrivacy}
                    onChange={(e) => {
                        setAgreements({ ...agreements, agreeToPrivacy: e.target.checked });
                        if (e.target.checked && consentErrors.agreeToPrivacy) {
                            setConsentErrors({ ...consentErrors, agreeToPrivacy: undefined });
                        }
                    }}
                >
                    {'Я даю согласие на '}
                    <span style={{ textDecoration: 'underline', cursor: 'pointer' }}
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setActiveModal(MODAL_CONSENT); }}>
                        обработку моих персональных данных
                    </span>
                </Checkbox>
            </FormItem>

            <FormItem>
                <Checkbox
                    checked={agreements.notifications}
                    onChange={async (e) => {
                        if (e.target.checked) {
                            try {
                                await bridge.send('VKWebAppAllowMessagesFromGroup', {
                                    group_id: Number(import.meta.env.VITE_VK_GROUP_ID),
                                });
                                setAgreements({ ...agreements, notifications: true });
                            } catch {
                                // User declined — leave unchecked, booking still works
                                setAgreements({ ...agreements, notifications: false });
                            }
                        } else {
                            setAgreements({ ...agreements, notifications: false });
                        }
                    }}
                >
                    🔔 Получать уведомления о бронировании
                </Checkbox>
            </FormItem>

            <FormItem>
                <Button
                    size="l"
                    stretched
                    onClick={handleSubmit}
                    disabled={!canSubmit || isSubmitting}
                    loading={isSubmitting}
                >
                    ☕ Забронировать
                </Button>
            </FormItem>
        </>
    );
}

export default BookingForm;
