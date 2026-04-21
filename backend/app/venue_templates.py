"""
Шаблоны конфигурации по умолчанию для каждой категории бизнеса.

При онбординге владелец выбирает категорию → получает готовый конфиг,
который можно дополнительно настроить в панели управления.

Структура config (единая для всех категорий):
{
    # Расписание
    "time_slots":            list[str]   — список слотов "HH:MM"
    "slot_duration_minutes": int         — длительность слота в минутах
    "working_days":          list[int]   — рабочие дни (1=пн, 7=вс)
    "working_hours": {
        "default": {"open": "HH:MM", "close": "HH:MM"},
        "sat":     {"open": "HH:MM", "close": "HH:MM"},  # переопределение
    }
    "max_guests_per_slot":   int         — одновременных броней на один слот

    # Поля формы гостя
    "fields": {
        "guests":  {"enabled": bool, "required": bool, "max": int},
        "comment": {"enabled": bool, "required": bool},
        "service": {"enabled": bool, "options": list[str]},
        "master":  {"enabled": bool, "options": list[str]},
        "zone":    {"enabled": bool, "options": list[str]},
    }

    # Уведомления (заполняются при онбординге)
    "notifications_chat_id": int | None
    "vk_group_token":        str | None

    # Брендинг (Standard+)
    "logo_url":      str | None
    "accent_color":  str         — HEX цвет кнопок и акцентов
    "welcome_text":  str         — заголовок формы
}
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательная функция генерации слотов
# ─────────────────────────────────────────────────────────────────────────────

def _make_slots(open_h: int, close_h: int, step: int) -> list[str]:
    """
    Генерирует список временных слотов с заданным шагом.

    Пример: _make_slots(10, 22, 60) → ["10:00", "11:00", ..., "21:00"]
    Последний слот не позднее чем за `step` минут до закрытия.
    """
    slots = []
    total_open  = open_h  * 60
    total_close = close_h * 60
    current     = total_open
    while current + step <= total_close:
        h = current // 60
        m = current % 60
        slots.append(f"{h:02d}:{m:02d}")
        current += step
    return slots


# ─────────────────────────────────────────────────────────────────────────────
# Шаблоны по категориям
# ─────────────────────────────────────────────────────────────────────────────

VENUE_TEMPLATES: dict[str, dict[str, Any]] = {

    # ── Кафе / Ресторан ───────────────────────────────────────────────────────
    "cafe": {
        "time_slots":            _make_slots(10, 22, 60),
        "slot_duration_minutes": 60,
        "working_days":          [1, 2, 3, 4, 5, 6, 7],
        "working_hours": {
            "default": {"open": "10:00", "close": "22:00"},
            "fri":     {"open": "10:00", "close": "23:00"},
            "sat":     {"open": "11:00", "close": "23:00"},
            "sun":     {"open": "11:00", "close": "22:00"},
        },
        "max_guests_per_slot": 3,
        "fields": {
            "guests":  {"enabled": True,  "required": True,  "max": 20},
            "comment": {"enabled": True,  "required": False},
            "service": {"enabled": False, "options": []},
            "master":  {"enabled": False, "options": []},
            "zone":    {"enabled": True,  "options": ["Основной зал", "Терраса", "VIP"]},
        },
        "notifications_chat_id": None,
        "vk_group_token":        None,
        "logo_url":              None,
        "accent_color":          "#8B4513",
        "welcome_text":          "Забронировать столик",
    },

    # ── Барбершоп ─────────────────────────────────────────────────────────────
    "barbershop": {
        "time_slots":            _make_slots(10, 21, 30),
        "slot_duration_minutes": 30,
        "working_days":          [1, 2, 3, 4, 5, 6, 7],
        "working_hours": {
            "default": {"open": "10:00", "close": "21:00"},
            "sun":     {"open": "11:00", "close": "20:00"},
        },
        "max_guests_per_slot": 1,
        "fields": {
            "guests":  {"enabled": False, "required": False, "max": 1},
            "comment": {"enabled": True,  "required": False},
            "service": {
                "enabled": True,
                "options": ["Стрижка", "Стрижка + борода", "Борода", "Бритьё", "Детская стрижка"],
            },
            "master":  {"enabled": True,  "options": []},
            "zone":    {"enabled": False, "options": []},
        },
        "notifications_chat_id": None,
        "vk_group_token":        None,
        "logo_url":              None,
        "accent_color":          "#2C3E50",
        "welcome_text":          "Записаться к мастеру",
    },

    # ── Клиника / Медцентр ────────────────────────────────────────────────────
    "clinic": {
        "time_slots":            _make_slots(8, 20, 30),
        "slot_duration_minutes": 30,
        "working_days":          [1, 2, 3, 4, 5, 6],
        "working_hours": {
            "default": {"open": "08:00", "close": "20:00"},
            "sat":     {"open": "09:00", "close": "16:00"},
        },
        "max_guests_per_slot": 1,
        "fields": {
            "guests":  {"enabled": False, "required": False, "max": 1},
            "comment": {"enabled": True,  "required": False},
            "service": {
                "enabled": True,
                "options": ["Первичный приём", "Повторный приём", "Консультация", "Процедура"],
            },
            "master":  {"enabled": True,  "options": []},
            "zone":    {"enabled": False, "options": []},
        },
        "notifications_chat_id": None,
        "vk_group_token":        None,
        "logo_url":              None,
        "accent_color":          "#0077CC",
        "welcome_text":          "Записаться на приём",
    },

    # ── Фитнес-студия / Спортзал ──────────────────────────────────────────────
    "fitness": {
        "time_slots":            _make_slots(7, 22, 60),
        "slot_duration_minutes": 60,
        "working_days":          [1, 2, 3, 4, 5, 6, 7],
        "working_hours": {
            "default": {"open": "07:00", "close": "22:00"},
            "sat":     {"open": "09:00", "close": "21:00"},
            "sun":     {"open": "09:00", "close": "20:00"},
        },
        "max_guests_per_slot": 10,
        "fields": {
            "guests":  {"enabled": False, "required": False, "max": 1},
            "comment": {"enabled": True,  "required": False},
            "service": {
                "enabled": True,
                "options": ["Персональная тренировка", "Групповое занятие", "Йога", "Пилатес", "Бокс"],
            },
            "master":  {"enabled": True,  "options": []},
            "zone":    {"enabled": False, "options": []},
        },
        "notifications_chat_id": None,
        "vk_group_token":        None,
        "logo_url":              None,
        "accent_color":          "#E74C3C",
        "welcome_text":          "Записаться на тренировку",
    },

    # ── Салон красоты ─────────────────────────────────────────────────────────
    "beauty": {
        "time_slots":            _make_slots(9, 21, 30),
        "slot_duration_minutes": 60,
        "working_days":          [1, 2, 3, 4, 5, 6, 7],
        "working_hours": {
            "default": {"open": "09:00", "close": "21:00"},
            "sun":     {"open": "10:00", "close": "19:00"},
        },
        "max_guests_per_slot": 1,
        "fields": {
            "guests":  {"enabled": False, "required": False, "max": 1},
            "comment": {"enabled": True,  "required": False},
            "service": {
                "enabled": True,
                "options": ["Маникюр", "Педикюр", "Маникюр + педикюр", "Наращивание ресниц",
                            "Брови", "Макияж", "Окрашивание волос", "Стрижка"],
            },
            "master":  {"enabled": True,  "options": []},
            "zone":    {"enabled": False, "options": []},
        },
        "notifications_chat_id": None,
        "vk_group_token":        None,
        "logo_url":              None,
        "accent_color":          "#E91E8C",
        "welcome_text":          "Записаться к мастеру",
    },

    # ── Фотостудия ────────────────────────────────────────────────────────────
    "photo_studio": {
        "time_slots":            _make_slots(9, 22, 60),
        "slot_duration_minutes": 60,
        "working_days":          [1, 2, 3, 4, 5, 6, 7],
        "working_hours": {
            "default": {"open": "09:00", "close": "22:00"},
        },
        "max_guests_per_slot": 1,
        "fields": {
            "guests":  {"enabled": True,  "required": False, "max": 20},
            "comment": {"enabled": True,  "required": False},
            "service": {
                "enabled": True,
                "options": ["Портретная съёмка", "Семейная съёмка", "Предметная съёмка",
                            "Видеосъёмка", "Аренда зала"],
            },
            "master":  {"enabled": False, "options": []},
            "zone":    {
                "enabled": True,
                "options": ["Зал А", "Зал Б", "Лофт", "Студия"],
            },
        },
        "notifications_chat_id": None,
        "vk_group_token":        None,
        "logo_url":              None,
        "accent_color":          "#6C3483",
        "welcome_text":          "Забронировать студию",
    },

    # ── Коворкинг ─────────────────────────────────────────────────────────────
    "coworking": {
        "time_slots":            _make_slots(8, 22, 60),
        "slot_duration_minutes": 60,
        "working_days":          [1, 2, 3, 4, 5, 6, 7],
        "working_hours": {
            "default": {"open": "08:00", "close": "22:00"},
            "sat":     {"open": "09:00", "close": "21:00"},
            "sun":     {"open": "10:00", "close": "20:00"},
        },
        "max_guests_per_slot": 20,
        "fields": {
            "guests":  {"enabled": True,  "required": False, "max": 20},
            "comment": {"enabled": True,  "required": False},
            "service": {
                "enabled": True,
                "options": ["Рабочее место", "Переговорная комната", "Конференц-зал",
                            "Приватный офис", "День", "Неделя", "Месяц"],
            },
            "master":  {"enabled": False, "options": []},
            "zone":    {"enabled": False, "options": []},
        },
        "notifications_chat_id": None,
        "vk_group_token":        None,
        "logo_url":              None,
        "accent_color":          "#1ABC9C",
        "welcome_text":          "Забронировать место",
    },

    # ── Другое (универсальный шаблон) ─────────────────────────────────────────
    "other": {
        "time_slots":            _make_slots(9, 21, 60),
        "slot_duration_minutes": 60,
        "working_days":          [1, 2, 3, 4, 5, 6],
        "working_hours": {
            "default": {"open": "09:00", "close": "21:00"},
        },
        "max_guests_per_slot": 1,
        "fields": {
            "guests":  {"enabled": False, "required": False, "max": 1},
            "comment": {"enabled": True,  "required": False},
            "service": {"enabled": False, "options": []},
            "master":  {"enabled": False, "options": []},
            "zone":    {"enabled": False, "options": []},
        },
        "notifications_chat_id": None,
        "vk_group_token":        None,
        "logo_url":              None,
        "accent_color":          "#FF6B35",
        "welcome_text":          "Онлайн-запись",
    },
}

# Список всех допустимых категорий
VENUE_CATEGORIES = list(VENUE_TEMPLATES.keys())


def get_default_config(category: str) -> dict[str, Any]:
    """
    Возвращает копию конфига по умолчанию для указанной категории.

    Использует deepcopy — каждый вызов возвращает независимый объект,
    изменения не затронут исходный шаблон.

    Raises:
        ValueError: если категория не найдена в VENUE_TEMPLATES.
    """
    if category not in VENUE_TEMPLATES:
        valid = ", ".join(VENUE_CATEGORIES)
        raise ValueError(
            f"Неизвестная категория '{category}'. Допустимые значения: {valid}"
        )
    return deepcopy(VENUE_TEMPLATES[category])


def get_templates_list() -> list[dict[str, Any]]:
    """
    Возвращает список всех шаблонов для отображения на экране онбординга.

    Каждый элемент содержит: category, welcome_text, accent_color —
    достаточно для рендера карточки выбора категории.
    """
    labels = {
        "cafe":         {"label": "Кафе / Ресторан",  "icon": "☕"},
        "barbershop":   {"label": "Барбершоп",         "icon": "✂️"},
        "clinic":       {"label": "Клиника",            "icon": "🏥"},
        "fitness":      {"label": "Фитнес-студия",      "icon": "💪"},
        "beauty":       {"label": "Салон красоты",      "icon": "💅"},
        "photo_studio": {"label": "Фотостудия",         "icon": "📷"},
        "coworking":    {"label": "Коворкинг",          "icon": "💼"},
        "other":        {"label": "Другое",             "icon": "🏢"},
    }
    result = []
    for category, tmpl in VENUE_TEMPLATES.items():
        info = labels.get(category, {"label": category, "icon": "🏢"})
        result.append({
            "category":    category,
            "label":       info["label"],
            "icon":        info["icon"],
            "accent_color": tmpl["accent_color"],
            "welcome_text": tmpl["welcome_text"],
        })
    return result