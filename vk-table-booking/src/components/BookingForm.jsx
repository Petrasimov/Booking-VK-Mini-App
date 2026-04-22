/**
 * Форма бронирования — динамическая версия.
 *
 * Поля формы генерируются из venueConfig.fields:
 *   - guests  — количество гостей (если enabled)
 *   - service — тип услуги / Select (если enabled)
 *   - master  — выбор мастера / Select (если enabled)
 *   - zone    — зона / Select (если enabled)
 *   - comment — комментарий (если enabled)
 *
 * Базовые поля (всегда): имя, телефон, дата, время.
 * Чекбоксы (всегда): согласие с документами, уведомления (опционально).
 *
 * Props:
 *   venueConfig     — объект конфига заведения из GET /api/config
 *   onRequestConfirm({ payload, displayData }) — callback отправки
 *   isSubmitting    — флаг загрузки
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
} from '@vkontakte/vkui';
import {
    validateName,
    validatePhone,
    validateDate,
    validateTime,
} from '../utils/validators';
import {
    TERMS_OF_USE_TEXT,
    USER_AGREEMENT_TEXT,
    PERSONAL_DATA_CONSENT_TEXT,
    PRIVACY_POLICY_TEXT,
} from '../utils/legalTexts';

// ─────────────────────────────────────────────
// Вспомогательные функции (без изменений)
// ─────────────────────────────────────────────

const getTodayStr = () => new Date().toISOString().split('T')[0];
const isToday = (dateStr) => !!dateStr && dateStr === getTodayStr();

const dateStrToDate = (str) => {
    if (!str) return undefined;
    const [y, m, d] = str.split('-').map(Number);
    return new Date(y, m - 1, d);
};

const dateToStr = (date) => {
    if (!date) return '';
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
};

const formatPhone = (digits) => {
    if (digits.length === 0) return '+7';
    if (digits.length < 3)  return `+7 (${digits}`;
    if (digits.length === 3) return `+7 (${digits})`;
    if (digits.length <= 6)  return `+7 (${digits.slice(0, 3)}) ${digits.slice(3)}`;
    if (digits.length <= 8)  return `+7 (${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
    return `+7 (${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 8)}-${digits.slice(8, 10)}`;
};

// ─────────────────────────────────────────────
// Конфиг по умолчанию (кафе) — используется если venueConfig не передан
// ─────────────────────────────────────────────

const DEFAULT_CONFIG = {
    time_slots: (() => {
        const slots = [];
        for (let h = 8; h <= 20; h++)
            for (let m = 0; m < 60; m += 30)
                slots.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
        return slots;
    })(),
    fields: {
        guests:  { enabled: true,  required: true,  max: 8 },
        comment: { enabled: true,  required: false },
        service: { enabled: false, options: [] },
        master:  { enabled: false, options: [] },
        zone:    { enabled: false, options: [] },
    },
    welcome_text: 'Забронировать',
    accent_color: '#FF6B35',
};

// ─────────────────────────────────────────────
// Константы модальных окон
// ─────────────────────────────────────────────

const MODAL_TERMS_OF_USE   = 'modal-terms-of-use';
const MODAL_PRIVACY_POLICY = 'modal-privacy-policy';
const MODAL_PUBLIC_OFFER   = 'modal-public-offer';
const MODAL_CONSENT        = 'modal-consent';

const INITIAL_AGREEMENTS = {
    agreeToTerms:  false,
    agreeToPrivacy: false,
    notifications:  false,
};

// ─────────────────────────────────────────────
// Компонент
// ─────────────────────────────────────────────

function BookingForm({ venueConfig, onRequestConfirm, isSubmitting }) {
    const cfg = venueConfig || DEFAULT_CONFIG;
    const fields = cfg.fields || DEFAULT_CONFIG.fields;
    const timeSlots = cfg.time_slots || DEFAULT_CONFIG.time_slots;

    // ── Начальное состояние формы ──────────────────────────────────────────
    const [form, setForm] = useState({
        name:    '',
        phone:   '',
        date:    '',
        time:    '',
        // Базовые опциональные поля
        guests:  1,
        comment: '',
        // Динамические поля ниши
        service: '',
        master:  '',
        zone:    '',
    });

    const [errors,        setErrors]        = useState({});
    const [agreements,    setAgreements]    = useState(INITIAL_AGREEMENTS);
    const [consentErrors, setConsentErrors] = useState({});
    const [activeModal,   setActiveModal]   = useState(null);

    // Рандомный плейсхолдер для комментария
    const [commentPlaceholder] = useState(() => {
        const variants = ['У окна', 'В уголочке', 'На диване', 'Не возле входа', 'У розетки'];
        return variants[Math.floor(Math.random() * variants.length)];
    });

    // ── Активные слоты времени (фильтруем прошедшие если дата = сегодня) ──
    const availableTimeSlots = useMemo(() => {
        if (!isToday(form.date)) return timeSlots;
        const now = new Date();
        const currentMinutes = now.getHours() * 60 + now.getMinutes();
        return timeSlots.filter(slot => {
            const [h, m] = slot.split(':').map(Number);
            return h * 60 + m > currentMinutes;
        });
    }, [form.date, timeSlots]);

    // ── Кнопка активна когда заполнены обязательные поля ──────────────────
    const canSubmit = useMemo(() => {
        const phoneDigits = form.phone.replace(/\D/g, '');
        const baseOk = (
            form.name.trim().length > 0 &&
            phoneDigits.length >= 10 &&
            form.date.length > 0 &&
            form.time.length > 0 &&
            agreements.agreeToTerms &&
            agreements.agreeToPrivacy
        );
        // Дополнительные обязательные поля ниши
        const serviceOk = !fields.service?.enabled || !fields.service?.required || form.service;
        const masterOk  = !fields.master?.enabled  || !fields.master?.required  || form.master;
        return baseOk && serviceOk && masterOk;
    }, [form, agreements, fields]);

    // ── Обработчики ────────────────────────────────────────────────────────

    const handleChange = (field) => (e) => {
        const value = e.target?.value ?? e;
        setForm(prev => ({ ...prev, [field]: value }));
        if (errors[field]) setErrors(prev => ({ ...prev, [field]: null }));
    };

    const handlePhoneChange = (e) => {
        const allDigits = e.target.value.replace(/\D/g, '');
        let cleaned = allDigits;
        if (cleaned.startsWith('7') || cleaned.startsWith('8')) cleaned = cleaned.slice(1);
        cleaned = cleaned.slice(0, 10);
        setForm(prev => ({ ...prev, phone: cleaned.length > 0 ? formatPhone(cleaned) : '' }));
        if (errors.phone) setErrors(prev => ({ ...prev, phone: null }));
    };

    const handleDateChange = (date) => {
        setForm(prev => ({ ...prev, date: dateToStr(date) }));
        if (errors.date) setErrors(prev => ({ ...prev, date: null }));
    };

    // ── Валидация ──────────────────────────────────────────────────────────

    const validateFormData = () => {
        const newErrors = {
            name:  validateName(form.name),
            phone: validatePhone(form.phone),
            date:  validateDate(form.date),
            time:  validateTime(form.time),
        };
        // Валидация количества гостей
        if (fields.guests?.enabled && fields.guests?.required && !form.guests) {
            newErrors.guests = 'Укажите количество гостей';
        }
        // Валидация обязательных полей ниши
        if (fields.service?.enabled && fields.service?.required && !form.service) {
            newErrors.service = 'Выберите услугу';
        }
        if (fields.master?.enabled && fields.master?.required && !form.master) {
            newErrors.master = 'Выберите мастера';
        }
        Object.keys(newErrors).forEach(k => newErrors[k] === null && delete newErrors[k]);
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    // ── Отправка ───────────────────────────────────────────────────────────

    const handleSubmit = () => {
        if (isSubmitting) return;

        const newConsentErrors = {};
        if (!agreements.agreeToTerms)
            newConsentErrors.agreeToTerms = 'Необходимо принять пользовательское соглашение';
        if (!agreements.agreeToPrivacy)
            newConsentErrors.agreeToPrivacy = 'Необходимо дать согласие на обработку персональных данных';
        setConsentErrors(newConsentErrors);
        if (Object.keys(newConsentErrors).length > 0) return;
        if (!validateFormData()) return;

        const cleanPhone = form.phone.replace(/\D/g, '');

        // Собираем extra_data из динамических полей
        const extra_data = {};
        if (fields.service?.enabled && form.service) extra_data.service = form.service;
        if (fields.master?.enabled  && form.master)  extra_data.master  = form.master;
        if (fields.zone?.enabled    && form.zone)    extra_data.zone    = form.zone;

        // Строка для показа в модальном окне подтверждения
        const extraLines = Object.entries(extra_data)
            .map(([k, v]) => {
                const labels = { service: 'Услуга', master: 'Мастер', zone: 'Зона' };
                return `${labels[k] || k}: ${v}`;
            })
            .join('\n');

        onRequestConfirm({
            payload: {
                name:             form.name,
                guests:           fields.guests?.enabled ? Number(form.guests) : 1,
                phone:            cleanPhone,
                date:             form.date,
                time:             form.time,
                comment:          form.comment || null,
                extra_data,
                vk_user_id:       window.vkUser?.id ?? null,
                vk_notifications: agreements.notifications,
            },
            displayData: {
                name:    form.name,
                guests:  fields.guests?.enabled ? form.guests : null,
                phone:   form.phone,
                date:    form.date,
                time:    form.time,
                comment: form.comment || null,
                extra:   extraLines || null,
            },
        });
    };

    // ── Документ для модального окна ──────────────────────────────────────

    const DOCS = {
        [MODAL_TERMS_OF_USE]:   { title: 'Условия использования',          text: TERMS_OF_USE_TEXT   },
        [MODAL_PRIVACY_POLICY]: { title: 'Политика конфиденциальности',    text: PRIVACY_POLICY_TEXT },
        [MODAL_PUBLIC_OFFER]:   { title: 'Публичная оферта',               text: USER_AGREEMENT_TEXT },
        [MODAL_CONSENT]:        { title: 'Согласие на обработку ПД',       text: PERSONAL_DATA_CONSENT_TEXT },
    };
    const activeDoc = activeModal ? DOCS[activeModal] : null;

    // ── Рендер ─────────────────────────────────────────────────────────────

    return (
        <>
            {/* Модальное окно с юридическим документом */}
            {activeDoc && (
                <div style={{
                    position: 'fixed', inset: 0, zIndex: 9999,
                    backgroundColor: 'rgba(0,0,0,0.5)',
                    display: 'flex', flexDirection: 'column',
                }}>
                    <div style={{
                        backgroundColor: 'var(--vkui--color_background_content)',
                        padding: '12px 16px',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        fontWeight: 600,
                    }}>
                        <span>{activeDoc.title}</span>
                        <button
                            onClick={() => setActiveModal(null)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20 }}
                        >✕</button>
                    </div>
                    <div style={{
                        flex: 1, overflowY: 'auto', padding: '16px',
                        backgroundColor: 'var(--vkui--color_background_content)',
                    }}>
                        <pre style={{
                            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                            fontFamily: 'inherit', fontSize: 13, lineHeight: 1.6,
                            color: 'var(--vkui--color_text_primary)', margin: 0,
                        }}>
                            {activeDoc.text}
                        </pre>
                    </div>
                </div>
            )}

            {/* ── Базовые поля ── */}
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

                {fields.guests?.enabled && (
                    <FormItem
                        top="👥 Гостей"
                        status={errors.guests ? 'error' : 'default'}
                        bottom={errors.guests}
                    >
                        <Select
                            value={form.guests}
                            onChange={handleChange('guests')}
                            options={Array.from(
                                { length: fields.guests.max || 8 },
                                (_, i) => ({ label: String(i + 1), value: i + 1 })
                            )}
                        />
                    </FormItem>
                )}
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

            {/* ── Динамические поля ниши ── */}

            {fields.service?.enabled && fields.service.options?.length > 0 && (
                <FormItem
                    top="✨ Услуга"
                    status={errors.service ? 'error' : 'default'}
                    bottom={errors.service}
                >
                    <Select
                        value={form.service}
                        onChange={handleChange('service')}
                        placeholder="Выберите услугу"
                        options={fields.service.options.map(o => ({ label: o, value: o }))}
                    />
                </FormItem>
            )}

            {fields.master?.enabled && fields.master.options?.length > 0 && (
                <FormItem
                    top="👨‍🎨 Мастер"
                    status={errors.master ? 'error' : 'default'}
                    bottom={errors.master}
                >
                    <Select
                        value={form.master}
                        onChange={handleChange('master')}
                        placeholder="Выберите мастера"
                        options={[
                            { label: 'Любой свободный', value: '' },
                            ...fields.master.options.map(o => ({ label: o, value: o })),
                        ]}
                    />
                </FormItem>
            )}

            {fields.zone?.enabled && fields.zone.options?.length > 0 && (
                <FormItem top="🗺 Зона">
                    <Select
                        value={form.zone}
                        onChange={handleChange('zone')}
                        placeholder="Любая зона"
                        options={[
                            { label: 'Любая зона', value: '' },
                            ...fields.zone.options.map(o => ({ label: o, value: o })),
                        ]}
                    />
                </FormItem>
            )}

            {fields.comment?.enabled !== false && (
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
            )}

            {/* ── Чекбоксы ── */}

            <FormItem
                status={consentErrors.agreeToTerms ? 'error' : 'default'}
                bottom={consentErrors.agreeToTerms}
            >
                <Checkbox
                    checked={agreements.agreeToTerms}
                    onChange={(e) => {
                        setAgreements(prev => ({ ...prev, agreeToTerms: e.target.checked }));
                        if (e.target.checked && consentErrors.agreeToTerms)
                            setConsentErrors(prev => ({ ...prev, agreeToTerms: undefined }));
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

            <FormItem
                status={consentErrors.agreeToPrivacy ? 'error' : 'default'}
                bottom={consentErrors.agreeToPrivacy}
            >
                <Checkbox
                    checked={agreements.agreeToPrivacy}
                    onChange={(e) => {
                        setAgreements(prev => ({ ...prev, agreeToPrivacy: e.target.checked }));
                        if (e.target.checked && consentErrors.agreeToPrivacy)
                            setConsentErrors(prev => ({ ...prev, agreeToPrivacy: undefined }));
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
                                const groupId = window.vkGroupId
                                    || Number(import.meta.env.VITE_VK_GROUP_ID);
                                await bridge.send('VKWebAppAllowMessagesFromGroup', {
                                    group_id: groupId,
                                });
                                setAgreements(prev => ({ ...prev, notifications: true }));
                            } catch {
                                setAgreements(prev => ({ ...prev, notifications: false }));
                            }
                        } else {
                            setAgreements(prev => ({ ...prev, notifications: false }));
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
                    {cfg.welcome_text || 'Забронировать'}
                </Button>
            </FormItem>
        </>
    );
}

export default BookingForm;