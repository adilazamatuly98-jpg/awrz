# -*- coding: utf-8 -*-
"""
АВРЗ — Система учёта и ремонта вагонов и колёсных пар.
Flask backend с ролевым доступом, маршрутом утверждения ОПЗС,
складом, заявками на перемещение и хранением в JSON.
"""
import json
import os
import random
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, request, jsonify, session,
    render_template, redirect, url_for, abort
)

app = Flask(__name__)
app.secret_key = "avrz-secret-change-me"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db.json")

# ---------------------------------------------------------------------------
#  Пользователи и роли
# ---------------------------------------------------------------------------
# ─────────────────────────────────────────────────────────────────
# Структура по цехам:
# КТЦ: Колесный, Роликовый, Тележка
# ВРЦ: АКП, Автосцепка, Кузов
# ─────────────────────────────────────────────────────────────────
USERS = {
    # ── Управление ──
    "admin":           {"password": "1", "name": "Администратор (Бюро описи)", "role": "admin",          "uchastok": None,         "cex": None},
    "nachalnik":       {"password": "1", "name": "Начальник ВРЦ",               "role": "nachalnik",      "uchastok": None,         "cex": "vrc"},
    "nachalnik_ktc":   {"password": "1", "name": "Начальник КТЦ",               "role": "nachalnik_ktc",  "uchastok": None,         "cex": "ktc"},
    # ── ВРЦ — Вагоноремонтный цех ──
    "master_auto":     {"password": "1", "name": "Мастер · Автосцепка",         "role": "master",         "uchastok": "avtoscepka", "cex": "vrc"},
    "master_akp":      {"password": "1", "name": "Мастер · АКП",                "role": "master",         "uchastok": "akp",        "cex": "vrc"},
    "master_kuzov":    {"password": "1", "name": "Мастер · Кузов",              "role": "master",         "uchastok": "kuzov",      "cex": "vrc"},
    # ── КТЦ — Колёсно-тележечный цех ──
    "master_telega":   {"password": "1", "name": "Мастер · Тележечный",         "role": "master",         "uchastok": "telega",     "cex": "ktc"},
    "master_roller":   {"password": "1", "name": "Мастер · Роликовый",          "role": "master_roller",  "uchastok": "roller",     "cex": "ktc"},
    # ── Дефектоскопист (один, видит всё) ──
    "defekt1":         {"password": "1", "name": "Дефектоскопист",              "role": "defektoskopist", "uchastok": "all",        "cex": None},
}

UCHASTOK_LABEL = {
    "avtoscepka": "Автосцепка",
    "telega":     "Тележечный",
    "akp":        "АКП",
    "roller":     "Роликовый",
    "kolesny":    "Колёсный",
    "kuzov":      "Кузов",
    "vrc_def":    "Деф. ВРЦ (Авт.+Тел.)",
    "wagon_def":  "Деф. ВРЦ",  # alias
}

# ---------------------------------------------------------------------------
#  Виды ремонта КП (вместо "результата дефектоскопии")
# ---------------------------------------------------------------------------
REPAIR_TYPES_KP = ["НОНК", "СОНК", "НОСК", "СОСК"]

# ---------------------------------------------------------------------------
#  Номенклатура из Excel (справочник номен + спецификация)
# ---------------------------------------------------------------------------

# ---- АКП: Главная часть (270) ----
AKP_MAIN_270 = [
    {"name": "Клапан 270.093",              "qty": 1},
    {"name": "Клапан 270.065-1",            "qty": 1},
    {"name": "Упорка направляющая 270.358", "qty": 1},
    {"name": "Седло клапана 270.386",       "qty": 1},
    {"name": "Толкатель 270.361/270.361-1", "qty": 1},
    {"name": "Поршень 270.303",             "qty": 1},
    {"name": "Шток поршня 270.569",         "qty": 1},
    {"name": "Упорка регулирующая 270.323", "qty": 1},
    {"name": "Упорка регулирующая 270.324", "qty": 1},
    {"name": "Гайка М10 ГОСТ 5915-70",      "qty": 4},
    {"name": "Упор 270.772",                "qty": 1},
    {"name": "Диафрагма 270-773",           "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Прокладка 270-330-1",         "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Прокладка 270-326",           "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Прокладка 270-549",           "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Манжета 270-397-3",           "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Манжета 270-313",             "qty": 6, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Манжета 270-317",             "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Уплотнение 270-357",          "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Уплотнение 270-311",          "qty": 1},
    {"name": "Пружина 270.322-1",           "qty": 1},
    {"name": "Пружина 270.321-2",           "qty": 1},
    {"name": "Пружина 270.327",             "qty": 1},
    {"name": "Пружина 270.364",             "qty": 1},
    {"name": "Пружина 270.355",             "qty": 1},
    {"name": "Пружина 270.315",             "qty": 1},
    {"name": "Пружина 270-319",             "qty": 1},
]

# ---- АКП: Магистральная часть (483) ----
AKP_MAG_483 = [
    {"name": "Заглушка 483-007-2",          "qty": 1},
    {"name": "Гайка М6",                    "qty": 1},
    {"name": "Клапан 483.080",              "qty": 1},
    {"name": "Клапан 483.015",              "qty": 1},
    {"name": "Диск направляющий 483.014",   "qty": 1},
    {"name": "Плунжер 483 М.120",           "qty": 1},
    {"name": "Гайка М10 ГОСТ 5915-70",      "qty": 5},
    {"name": "Седло 483 М.050",             "qty": 1},
    {"name": "Седло 483М.012",              "qty": 1},
    {"name": "Седло 483.011",               "qty": 1},
    {"name": "Клапан 483.090-1",            "qty": 1},
    {"name": "Гнездо 483.027",              "qty": 1},
    {"name": "Седло 484М.026",              "qty": 1},
    {"name": "Гайка 483.028",              "qty": 1},
    {"name": "Седло 483.023",              "qty": 1},
    {"name": "Втулка 483.022-2",           "qty": 1},
    {"name": "Кольцо стопорное 150.03.121","qty": 1},
    {"name": "Фиксатор 270-372",           "qty": 1},
    {"name": "Диафрагма 270-379",          "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Диафрагма 483А.043",         "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Прокладка 270-399-2",        "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Прокладка 270-549",          "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Прокладка 183-9",            "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Уплотнение 305-134",         "qty": 2, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Клапан 483.110-1",           "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Манжета 305-156",            "qty": 2, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Манжета 270-769",            "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Уплотнение 334.1729А-1",     "qty": 2, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Уплотнение 270-751",         "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Пружина 270.605-1",          "qty": 1},
    {"name": "Пружина 483.025-2",          "qty": 1},
    {"name": "Пружина 270.371",            "qty": 1},
    {"name": "Пружина 483.004",            "qty": 1},
    {"name": "Пружина 483.029",            "qty": 1},
]

# ---- АКП: Авторежим (265А-1) ----
AKP_AVTOREZHIM = [
    {"name": "Упор 265.225-1",             "qty": 1},
    {"name": "Гайка 265-227",              "qty": 1},
    {"name": "Контргайка 265.228-1",       "qty": 1},
    {"name": "Вилка 265.039-1",            "qty": 1},
    {"name": "Направляющая 265.252-1",     "qty": 1},
    {"name": "Ползун 265.253-1",           "qty": 1},
    {"name": "Сальник 265.239-2",          "qty": 1},
    {"name": "Гайка М8 ГОСТ 5915-70",      "qty": 6},
    {"name": "Гайка М10 ГОСТ 5915-70",     "qty": 4},
    {"name": "Гайка М12 ГОСТ 5915-70",     "qty": 2},
    {"name": "Демпфер 265.029-6",          "qty": 1},
    {"name": "Рычаг 265.339",              "qty": 1},
    {"name": "Сухарь 265.336",             "qty": 1},
    {"name": "Ниппель 265.248",            "qty": 1},
    {"name": "Поршень 265.237-3",          "qty": 1},
    {"name": "Стержень 265.251",           "qty": 1},
    {"name": "Поршень верхний 265А.212-5", "qty": 1},
    {"name": "Толкатель 265А.267-1",       "qty": 1},
    {"name": "Втулка 265А.265",            "qty": 1},
    {"name": "Поршень нижний 265А.213-3",  "qty": 1},
    {"name": "Прокладка крышки 265-223",   "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Прокладка 265-246",          "qty": 2, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Манжета поршня 265-242",     "qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Манжета 270-397",            "qty": 2, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Манжета 135.05.021А",        "qty": 2, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Прокладка авторежима 265-341","qty": 1, "default_snato": "забраковано", "default_postav": "новый"},
    {"name": "Пружина 265.346",            "qty": 1},
    {"name": "Пружина 643.132",            "qty": 1},
    {"name": "Пружина 265.231-1",          "qty": 1},
    {"name": "Пружина 265А.268",           "qty": 1},
    {"name": "Пружина 265.345",            "qty": 1},
    {"name": "Пружина 265.232",            "qty": 1},
]

# ---- АКП: Авторегулятор (574Б) ----
AKP_AVTOREGULATOR = [
    {"name": "Стакан 574Б.300",                "qty": 1},
    {"name": "Гайка предохранительная 574Б.003-1", "qty": 1},
    {"name": "Подшипник 8109",                 "qty": 2},
    {"name": "Втулка упорная 574Б.302",        "qty": 1},
    {"name": "Пружина 574Б.305",               "qty": 1},
    {"name": "Пружина 559.302-01",             "qty": 1},
]

# ---- Тележечный участок (из спецификации) ----
TELEGA_NUMBERED = [
    {"name": "Балка надрессорная чер.100.00.010-6"},
    {"name": "Рама боковая черт.100.00.002-4 ГОСТ 32400"},
    {"name": "Авторежим 265А-1"},
    {"name": "Авторежим 265А-4"},
    {"name": "Авторегулятор 574Б"},
    {"name": "Цилиндр тормозной"},
    {"name": "Кран разобщительный"},
    {"name": "Кран концевой"},
    {"name": "Рычаг тормозной передачи"},
    {"name": "Колёсная пара"},
]
TELEGA_UNNUMBERED = [
    {"name": "Планка фрикционная М1698.02.004 (подвижная)",    "qty": 8},
    {"name": "Планка фрикционная М1698.02.001 (неподвижная)",  "qty": 8},
    {"name": "Клин чугунный фрикционный М1698.00.002",         "qty": 8},
    {"name": "Прокладка сменная М1698.03.100СБ",               "qty": 8},
    {"name": "Прокладка М1698.01.005 (подпятника)",            "qty": 2},
    {"name": "Колпак скользуна М1698.01 100СБ",                "qty": 4},
    {"name": "Чека 100-40-014-0",                              "qty": 8},
    {"name": "Валик 220х32 (100.40.013-1)",                    "qty": 8},
    {"name": "Колодка тормозная",                              "qty": 8},
    {"name": "Втулка полимерная 100.00.009-0",                 "qty": 8},
    {"name": "Предохранитель 4384",                            "qty": 8},
    {"name": "Подвеска тормозного башмака",                    "qty": 8},
    {"name": "Шплинт 8х71",                                   "qty": 1},
    {"name": "Шплинт 8х90",                                   "qty": 1},
    {"name": "Пружина рессорного подвешивания внутренняя 1272.3045858007", "qty": 28},
    {"name": "Пружина рессорного подвешивания наружная 1272.3045858008",   "qty": 28},
    {"name": "Триангель 100.40.010-2СБ",                       "qty": 4},
    {"name": "Втулка КПМ 50х40.2х24",                         "qty": 16},
    {"name": "Втулка КПМ 50х40.2х12",                         "qty": 12},
    {"name": "Заклёпка 20х58",                                 "qty": 10},
    {"name": "Заклёпка 24х100 ГОСТ 10299-80",                  "qty": 1},
]

# ---- Автосцепка ----
AVTOSCEPKA_NUMBERED = [
    {"name": "Корпус автосцепки СА-3"},
    {"name": "Тяговый хомут"},
    {"name": "Поглощающий аппарат Ш-2-Т"},
    {"name": "Поглощающий аппарат Ш-6-ТО-4"},
    {"name": "Клин тягового хомута"},
    {"name": "Упорная плита"},
]
AVTOSCEPKA_UNNUMBERED = [
    {"name": "Замок автосцепки",           "qty": 1},
    {"name": "Замкодержатель",             "qty": 1},
    {"name": "Предохранитель замка",       "qty": 1},
    {"name": "Подъёмник замка",            "qty": 1},
    {"name": "Валик подъёмника",           "qty": 1},
    {"name": "Центрирующая балочка",       "qty": 1},
    {"name": "Маятниковая подвеска",       "qty": 2},
    {"name": "Расцепной рычаг",            "qty": 1},
    {"name": "Кронштейн расцепного рычага","qty": 1},
    {"name": "Цепочка расцепного привода", "qty": 1},
    {"name": "Болт М20х90",                "qty": 4},
    {"name": "Гайка М20",                  "qty": 4},
    {"name": "Шплинт 6,3х63",              "qty": 4},
    {"name": "Электрод д-4 мм",            "qty": 1},
]

# Общий справочник номенклатуры (для поиска/автозаполнения)
NOMENCLATURE = {
    "akp": {
        "Главная часть (270)":     AKP_MAIN_270,
        "Магистральная часть (483)": AKP_MAG_483,
        "Авторежим (265А)":        AKP_AVTOREZHIM,
        "Авторегулятор (574Б)":    AKP_AVTOREGULATOR,
    },
    "telega": {
        "Номерные":   TELEGA_NUMBERED,
        "Неномерные": TELEGA_UNNUMBERED,
    },
    "avtoscepka": {
        "Номерные":   AVTOSCEPKA_NUMBERED,
        "Неномерные": AVTOSCEPKA_UNNUMBERED,
    },
}

# Старые поля (для обратной совместимости opzs.html)
PART_TYPES = {
    "avtoscepka": [x["name"] for x in AVTOSCEPKA_NUMBERED + AVTOSCEPKA_UNNUMBERED],
    "telega":     [x["name"] for x in TELEGA_NUMBERED + TELEGA_UNNUMBERED],
    "akp":        list(NOMENCLATURE["akp"].keys()),
}
CONDITIONS = ["в оборот", "забраковано", "отсутствовало"]
CONDITIONS_POSTAV = ["из оборота", "новый", "давальческий"]

NUMBERED_DETAILS = {
    "avtoscepka": [x["name"] for x in AVTOSCEPKA_NUMBERED],
    "telega":     [x["name"] for x in TELEGA_NUMBERED],
    "akp":        [],
}
UNNUMBERED_DETAILS = {
    "avtoscepka": [x["name"] for x in AVTOSCEPKA_UNNUMBERED],
    "telega":     [x["name"] for x in TELEGA_UNNUMBERED],
    "akp":        [],
}

ZAVODY = ["НКМЗ", "ВМЗ", "УКВЗ", "УЗТМ", "ФАНПАС", "СКТБ", "Бежицкий СЗ", "Промлит"]

# Полный справочник деталей вагона (для автодополнения в ОПЗС и заявках)
ALL_WAGON_PARTS = [
    # ── Автосцепное устройство ──
    "Корпус автосцепки СА-3",
    "Замок автосцепки",
    "Замкодержатель",
    "Предохранитель замка",
    "Подъёмник замка",
    "Валик подъёмника",
    "Тяговый хомут",
    "Клин тягового хомута",
    "Поглощающий аппарат Ш-2-Т",
    "Поглощающий аппарат Ш-6-ТО-4",
    "Упорная плита",
    "Центрирующая балочка",
    "Маятниковая подвеска",
    "Расцепной рычаг",
    "Кронштейн расцепного рычага",
    "Цепочка расцепного привода",
    # ── Тележка ──
    "Балка надрессорная чер.100.00.010-6",
    "Рама боковая черт.100.00.002-4",
    "Планка фрикционная подвижная М1698.02.004",
    "Планка фрикционная неподвижная М1698.02.001",
    "Клин фрикционный чугунный М1698.00.002",
    "Прокладка сменная М1698.03.100",
    "Прокладка подпятника М1698.01.005",
    "Колпак скользуна М1698.01.100",
    "Чека 100-40-014",
    "Валик 220х32 (100.40.013-1)",
    "Пружина рессорная внутренняя 1272.3045858007",
    "Пружина рессорная наружная 1272.3045858008",
    "Втулка полимерная 100.00.009-0",
    "Предохранитель 4384",
    "Подвеска тормозного башмака",
    "Триангель 100.40.010-2",
    "Втулка КПМ 50х40.2х24",
    # ── Тормозное оборудование ──
    "Авторежим 265А-1",
    "Авторежим 265А-4",
    "Авторегулятор 574Б",
    "Цилиндр тормозной",
    "Кран разобщительный",
    "Кран концевой",
    "Кран шаровый",
    "Воздухораспределитель 483",
    "Главная часть воздухораспределителя 270",
    "Магистральная часть воздухораспределителя 483",
    "Рабочая камера",
    "Рычаг тормозной передачи",
    "Колодка тормозная",
    "Башмак тормозной",
    "Подвеска башмака",
    "Шплинт 8х71",
    "Шплинт 8х90",
    # ── Буксовый узел ──
    "Корпус буксы",
    "Крышка крепительная",
    "Крышка смотровая",
    "Лабиринтное кольцо",
    "Подшипник 30-232726",
    "Подшипник 30-42726Л",
    "Стопорная планка",
    "Болт М20х90",
    "Болт М22х90",
    "Гайка М20",
    "Гайка М22",
    "Гайка корончатая М30",
    # ── Кузов и рама ──
    "Хребтовая балка",
    "Шкворневая балка",
    "Концевая балка",
    "Боковая стойка",
    "Раскос",
    "Пол вагона",
    "Крышка люка",
    "Петля крышки люка",
    "Скоба крышки люка",
    "Кронштейн",
    "Скоба",
]

# ---------------------------------------------------------------------------
#  Хранилище (JSON)
# ---------------------------------------------------------------------------
def _seed():
    today = date.today().isoformat()
    return {
        "counters": {"wagons": 3, "opzs": 12, "nakatka": 1, "naryady": 0,
                     "kp_arrival": 2, "kp_departure": 1, "roller": 1,
                     "warehouse": 4, "transfers": 1},
        "wagons": [
            {"id": 1, "number": "43857294", "incoming_number": "ВХ-2024-001", "date": today, "status": "В ремонте"},
            {"id": 2, "number": "55012387", "incoming_number": "ВХ-2024-002", "date": today, "status": "В ремонте"},
            {"id": 3, "number": "61140052", "incoming_number": "ВХ-2024-003", "date": today, "status": "В ремонте"},
        ],
        "opzs": [
            _mk_opzs(1,  1, "43857294", "avtoscepka"),
            _mk_opzs(2,  1, "43857294", "telega"),
            _mk_opzs(3,  1, "43857294", "akp"),
            _mk_opzs(4,  1, "43857294", "kuzov"),
            _mk_opzs(5,  2, "55012387", "avtoscepka"),
            _mk_opzs(6,  2, "55012387", "telega"),
            _mk_opzs(7,  2, "55012387", "akp"),
            _mk_opzs(8,  2, "55012387", "kuzov"),
            _mk_opzs(9,  3, "61140052", "avtoscepka"),
            _mk_opzs(10, 3, "61140052", "telega"),
            _mk_opzs(11, 3, "61140052", "akp"),
            _mk_opzs(12, 3, "61140052", "kuzov"),
        ],
        "nakatka": [],
        "kp_arrival":   [],
        "kp_departure": [],
        "roller":       [],
        "warehouse": [
            {"id": 1, "owner": "master_auto",   "name": "Замок автосцепки",   "type": "Замок",                        "qty": 12, "note": ""},
            {"id": 2, "owner": "master_telega", "name": "Пружина рессорного подвешивания наружная 1272.3045858008", "type": "Пружина", "qty": 40, "note": ""},
            {"id": 3, "owner": "master_akp",    "name": "Манжета 270-313",     "type": "Манжета",                      "qty": 25, "note": ""},
            {"id": 4, "owner": "master_roller", "name": "Подшипник 30-232726", "type": "Подшипник",                    "qty": 18, "note": ""},
        ],
        "transfers": [],
        "naryady": [],
    }


def _seed_with_demo():
    """Создаёт стартовую БД с полным набором демо-данных."""
    db = _seed()
    db = _generate_demo_data(db)
    return db


def _mk_opzs(_id, wagon_id, wagon_number, uchastok):
    return {
        "id":           _id,
        "wagon_id":     wagon_id,
        "wagon_number": wagon_number,
        "uchastok":     uchastok,
        "status":       "Черновик",
        "parts":        [],
        "comment":      "",
        "history":      [],
        "comments":     [],
        "created_at":   datetime.now().isoformat(timespec="seconds"),
        "updated_at":   datetime.now().isoformat(timespec="seconds"),
    }


def _log(doc, action, note=""):
    u = current_user() or {}
    doc.setdefault("history", []).append({
        "ts":     datetime.now().isoformat(timespec="seconds"),
        "user":   u.get("name", "—"),
        "action": action,
        "note":   note,
    })


def load_db():
    if not os.path.exists(DB_PATH):
        db = _seed_with_demo()
        save_db(db)
        return db
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def next_id(db, key):
    db["counters"][key] = db["counters"].get(key, 0) + 1
    return db["counters"][key]


# ---------------------------------------------------------------------------
#  Авторизация
# ---------------------------------------------------------------------------
def current_user():
    u = session.get("user")
    if not u or u not in USERS:
        return None
    info = USERS[u].copy()
    info["username"] = u
    return info


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login_page"))
        return f(*a, **kw)
    return wrapper


def ctx():
    u = current_user()
    return {
        "user":          u["name"],
        "username":      u["username"],
        "role":          u["role"],
        "uchastok":      u["uchastok"],
        "uchastok_label": UCHASTOK_LABEL.get(u["uchastok"], ""),
        "cex":           u.get("cex", ""),
    }


# ---------------------------------------------------------------------------
#  Страницы
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user() else url_for("login_page"))


@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_action():
    data = request.get_json(force=True, silent=True) or {}
    u = (data.get("username") or "").strip()
    p = data.get("password") or ""
    if u in USERS and USERS[u]["password"] == p:
        session["user"] = u
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Неверный логин или пароль"})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", **ctx())


@app.route("/wagons")
@login_required
def wagons_page():
    return render_template("wagons.html", **ctx())


@app.route("/opzs")
@login_required
def opzs_page():
    return render_template("opzs.html", **ctx())


@app.route("/kp")
@login_required
def kp_page():
    return render_template("kp.html", **ctx())


@app.route("/nakatka")
@login_required
def nakatka_page():
    return render_template("nakatka.html", **ctx())


@app.route("/sklad")
@login_required
def sklad_page():
    return render_template("sklad.html", **ctx())


@app.route("/transfers")
@login_required
def transfers_page():
    return render_template("transfers.html", **ctx())


@app.route("/naryady")
@login_required
def naryady_page():
    return render_template("naryady.html", **ctx())


# ---------------------------------------------------------------------------
#  Справочники / Номенклатура
# ---------------------------------------------------------------------------
@app.route("/api/meta")
@login_required
def api_meta():
    return jsonify({
        "part_types":    PART_TYPES,
        "numbered":      NUMBERED_DETAILS,
        "unnumbered":    UNNUMBERED_DETAILS,
        "zavody":        ZAVODY,
        "conditions":    CONDITIONS,
        "conditions_postav": CONDITIONS_POSTAV,
        "repair_types_kp": REPAIR_TYPES_KP,
        "all_wagon_parts": ALL_WAGON_PARTS,
        "uchastok_label": UCHASTOK_LABEL,
        "users": {k: {"name": v["name"], "uchastok": v["uchastok"], "cex": v.get("cex")} for k, v in USERS.items()},
    })


@app.route("/api/nomenclature")
@login_required
def api_nomenclature():
    """Полная номенклатура из Excel по участкам и секциям."""
    return jsonify(NOMENCLATURE)


# ---------------------------------------------------------------------------
#  Вагоны
# ---------------------------------------------------------------------------
@app.route("/api/wagons", methods=["GET"])
@login_required
def api_wagons():
    return jsonify(load_db()["wagons"])


@app.route("/api/wagons", methods=["POST"])
@login_required
def api_wagons_create():
    # FIX: и admin (Бюро описи) и nachalnik могут добавлять вагоны
    u = current_user()
    if u["role"] not in ("nachalnik", "admin"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(force=True) or {}
    db = load_db()
    wid = next_id(db, "wagons")
    wagon = {
        "id":              wid,
        "number":          (data.get("number") or "").strip(),
        "incoming_number": (data.get("incoming_number") or "").strip(),
        "date":            data.get("date") or date.today().isoformat(),
        "status":          "В ремонте",
    }
    db["wagons"].append(wagon)
    # авто-создание ОПЗС по участкам (кроме Роликового — он на смену, не на вагон)
    for uch in ("avtoscepka", "telega", "akp", "kuzov"):
        oid = next_id(db, "opzs")
        db["opzs"].append(_mk_opzs(oid, wid, wagon["number"], uch))
    save_db(db)
    return jsonify({"ok": True, "wagon": wagon})


@app.route("/api/wagons/<int:wagon_id>", methods=["PUT"])
@login_required
def api_wagons_update(wagon_id):
    u = current_user()
    if u["role"] not in ("nachalnik", "admin"):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(force=True) or {}
    db = load_db()
    w = next((x for x in db["wagons"] if x["id"] == wagon_id), None)
    if not w:
        return jsonify({"error": "not found"}), 404
    for k in ("number", "incoming_number", "date", "status"):
        if k in data:
            w[k] = data[k]
    for d in db["opzs"]:
        if d.get("wagon_id") == wagon_id:
            d["wagon_number"] = w["number"]
    save_db(db)
    return jsonify({"ok": True, "wagon": w})


@app.route("/api/wagons/<int:wagon_id>", methods=["DELETE"])
@login_required
def api_wagons_delete(wagon_id):
    u = current_user()
    if u["role"] not in ("nachalnik", "admin"):
        return jsonify({"error": "forbidden"}), 403
    db = load_db()
    db["wagons"] = [x for x in db["wagons"] if x["id"] != wagon_id]
    db["opzs"]   = [d for d in db["opzs"]   if d.get("wagon_id") != wagon_id]
    save_db(db)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
#  ОПЗС (маршрут утверждения)
# ---------------------------------------------------------------------------
@app.route("/api/opzs", methods=["GET"])
@login_required
def api_opzs():
    db = load_db()
    docs = db["opzs"]
    u = current_user()
    uch = request.args.get("uchastok")
    if uch:
        docs = [d for d in docs if d["uchastok"] == uch]
    if u["role"] == "master" and not uch:
        docs = [d for d in docs if d["uchastok"] == u["uchastok"]]
    # Мастер роликовый — видит только Роликовый ОПЗС
    elif u["role"] == "master_roller" and not uch:
        docs = [d for d in docs if d["uchastok"] == "roller"]
    # Дефектоскопист — видит ОПЗС по Автосцепке и Тележечному (для осмотра)
    elif u["role"] == "defektoskopist" and not uch:
        docs = [d for d in docs if d["uchastok"] in ("avtoscepka", "telega")]
    # Начальник КТЦ — видит только КТЦ участки
    elif u["role"] == "nachalnik_ktc" and not uch:
        docs = [d for d in docs if d["uchastok"] in ("telega", "roller", "kolesny")]
    return jsonify(docs)


@app.route("/api/opzs/<int:doc_id>", methods=["GET"])
@login_required
def api_opzs_get(doc_id):
    db = load_db()
    doc = next((d for d in db["opzs"] if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(doc)


@app.route("/api/opzs/<int:doc_id>", methods=["PUT"])
@login_required
def api_opzs_update(doc_id):
    data = request.get_json(force=True) or {}
    action = data.get("action", "save")
    db = load_db()
    doc = next((d for d in db["opzs"] if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    if doc.get("status") in ("На утверждении", "Утверждён"):
        return jsonify({"error": "locked",
                        "message": "Документ уже отправлен на утверждение"}), 409
    doc["parts"]      = data.get("parts", doc.get("parts", []))
    doc["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if action == "submit":
        doc["status"]  = "На утверждении"
        doc["comment"] = ""
        _log(doc, "Проведён", "Отправлен на утверждение")
    else:
        doc["status"] = "Черновик"
        _log(doc, "Записан", "Сохранён черновик")
    save_db(db)
    return jsonify({"ok": True, "doc": doc})


@app.route("/api/opzs/<int:doc_id>/review", methods=["POST"])
@login_required
def api_opzs_review(doc_id):
    if current_user()["role"] not in ("nachalnik", "nachalnik_ktc", "admin"):
        return jsonify({"error": "forbidden"}), 403
    data   = request.get_json(force=True) or {}
    action = data.get("action")
    db     = load_db()
    doc    = next((d for d in db["opzs"] if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    if action == "approve":
        doc["status"]  = "Утверждён"
        doc["comment"] = ""
        _log(doc, "Утверждён", "Документ утверждён начальником")
    elif action == "reject":
        doc["status"]  = "На доработке"
        doc["comment"] = data.get("comment", "")
        _log(doc, "На доработку", data.get("comment", ""))
    doc["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_db(db)
    return jsonify({"ok": True, "doc": doc})


@app.route("/api/opzs/<int:doc_id>/comment", methods=["POST"])
@login_required
def api_opzs_comment(doc_id):
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400
    db  = load_db()
    doc = next((d for d in db["opzs"] if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    u = current_user()
    doc.setdefault("comments", []).append({
        "ts":   datetime.now().isoformat(timespec="seconds"),
        "user": u.get("name", "—"),
        "role": u.get("role", ""),
        "text": text[:1000],
    })
    save_db(db)
    return jsonify({"ok": True, "comments": doc["comments"]})


# ---------------------------------------------------------------------------
#  Колёсные пары — универсальная фабрика коллекций
# ---------------------------------------------------------------------------
def _kp_collection(name):
    def _dup(db, num, exclude_id=None):
        n = (num or "").strip().lower()
        if not n:
            return False
        return any(
            (r.get("num", "").strip().lower() == n) and r.get("id") != exclude_id
            for r in db[name]
        )

    @login_required
    def getter():
        return jsonify(load_db()[name])

    @login_required
    def creator():
        data = request.get_json(force=True) or {}
        db   = load_db()
        if _dup(db, data.get("num")):
            return jsonify({"error": "duplicate",
                            "message": f"КП №{data.get('num')} уже есть в этом разделе"}), 409
        _id = next_id(db, name)
        rec = dict(data)
        rec["id"]         = _id
        rec["status"]     = rec.get("status", "Черновик")
        rec["created_at"] = datetime.now().isoformat(timespec="seconds")
        db[name].append(rec)
        save_db(db)
        return jsonify({"ok": True, "doc": rec})

    @login_required
    def updater(item_id):
        data = request.get_json(force=True) or {}
        db   = load_db()
        rec  = next((r for r in db[name] if r.get("id") == item_id), None)
        if not rec:
            return jsonify({"error": "not found"}), 404
        if _dup(db, data.get("num"), exclude_id=item_id):
            return jsonify({"error": "duplicate",
                            "message": f"КП №{data.get('num')} уже есть в этом разделе"}), 409
        for k, v in data.items():
            if k not in ("id", "created_at"):
                rec[k] = v
        rec["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_db(db)
        return jsonify({"ok": True, "doc": rec})

    return getter, creator, updater


for _coll in ("kp_arrival", "kp_departure", "roller"):
    _g, _c, _u = _kp_collection(_coll)
    app.add_url_rule(f"/api/{_coll}",             f"api_{_coll}_get",  _g, methods=["GET"])
    app.add_url_rule(f"/api/{_coll}",             f"api_{_coll}_post", _c, methods=["POST"])
    app.add_url_rule(f"/api/{_coll}/<int:item_id>", f"api_{_coll}_put", _u, methods=["PUT"])


# ---------------------------------------------------------------------------
#  Натурный лист
# ---------------------------------------------------------------------------
@app.route("/api/nakatka", methods=["GET"])
@login_required
def api_nakatka():
    return jsonify(load_db()["nakatka"])


@app.route("/api/nakatka/<int:doc_id>", methods=["GET"])
@login_required
def api_nakatka_get(doc_id):
    db  = load_db()
    doc = next((d for d in db["nakatka"] if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(doc)


@app.route("/api/nakatka", methods=["POST"])
@login_required
def api_nakatka_create():
    data = request.get_json(force=True) or {}
    db   = load_db()
    _id  = next_id(db, "nakatka")
    doc  = {
        "id":            _id,
        "wagon_number":  data.get("wagon_number", ""),
        "telega_number": data.get("telega_number", ""),
        "vagon_type":    data.get("vagon_type", ""),
        "kontragent":    data.get("kontragent", ""),
        "remont_type":   data.get("remont_type", "ТР-1"),
        "kp_rows":       data.get("kp_rows", []),
        "status":        data.get("status", "Черновик"),
        "created_at":    datetime.now().isoformat(timespec="seconds"),
    }
    db["nakatka"].append(doc)
    save_db(db)
    return jsonify({"ok": True, "doc": doc})


@app.route("/api/nakatka/<int:doc_id>", methods=["PUT"])
@login_required
def api_nakatka_update(doc_id):
    data = request.get_json(force=True) or {}
    db   = load_db()
    doc  = next((d for d in db["nakatka"] if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    for k in ("wagon_number", "telega_number", "vagon_type",
              "kontragent", "remont_type", "kp_rows", "status"):
        if k in data:
            doc[k] = data[k]
    save_db(db)
    return jsonify({"ok": True, "doc": doc})


# ---------------------------------------------------------------------------
#  Склад
# ---------------------------------------------------------------------------
@app.route("/api/warehouse", methods=["GET"])
@login_required
def api_warehouse():
    db    = load_db()
    u     = current_user()
    items = db["warehouse"]
    # Начальники и admin видят общий склад (все позиции всех мастеров)
    if u["role"] not in ("nachalnik", "nachalnik_ktc", "admin"):
        items = [i for i in items if i.get("owner") == u["username"]]
    return jsonify(items)


@app.route("/api/warehouse", methods=["POST"])
@login_required
def api_warehouse_create():
    data = request.get_json(force=True) or {}
    db   = load_db()
    _id  = next_id(db, "warehouse")
    item = {
        "id":    _id,
        "owner": current_user()["username"],
        "name":  data.get("name", ""),
        "type":  data.get("type", ""),
        "qty":   int(data.get("qty") or 0),
        "note":  data.get("note", ""),
    }
    db["warehouse"].append(item)
    save_db(db)
    return jsonify({"ok": True, "item": item})


@app.route("/api/warehouse/<int:item_id>", methods=["PUT"])
@login_required
def api_warehouse_update(item_id):
    data = request.get_json(force=True) or {}
    u    = current_user()
    db   = load_db()
    it   = next((x for x in db["warehouse"] if x["id"] == item_id), None)
    if not it:
        return jsonify({"error": "not found"}), 404
    if u["role"] not in ("nachalnik", "nachalnik_ktc", "admin") and it.get("owner") != u["username"]:
        return jsonify({"error": "forbidden"}), 403
    for k in ("name", "type", "note"):
        if k in data:
            it[k] = data[k]
    if "qty" in data:
        it["qty"] = int(data.get("qty") or 0)
    save_db(db)
    return jsonify({"ok": True, "item": it})


@app.route("/api/warehouse/<int:item_id>", methods=["DELETE"])
@login_required
def api_warehouse_delete(item_id):
    u  = current_user()
    db = load_db()
    it = next((x for x in db["warehouse"] if x["id"] == item_id), None)
    if not it:
        return jsonify({"error": "not found"}), 404
    if u["role"] not in ("nachalnik", "nachalnik_ktc", "admin") and it.get("owner") != u["username"]:
        return jsonify({"error": "forbidden"}), 403
    db["warehouse"] = [x for x in db["warehouse"] if x["id"] != item_id]
    save_db(db)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
#  Перемещения
# ---------------------------------------------------------------------------
@app.route("/api/transfers", methods=["GET"])
@login_required
def api_transfers():
    db    = load_db()
    u     = current_user()
    items = db["transfers"]
    if u["role"] not in ("nachalnik", "admin"):
        items = [t for t in items
                 if t.get("from_user") == u["username"] or t.get("to_user") == u["username"]]
    return jsonify(items)


@app.route("/api/transfers", methods=["POST"])
@login_required
def api_transfers_create():
    data = request.get_json(force=True) or {}
    db   = load_db()
    _id  = next_id(db, "transfers")
    # Support both old peer-to-peer and new request-from-warehouse mode
    from_source = data.get("from_source", "")  # e.g. sklad_metal
    to_user = data.get("to_user") or current_user()["username"]
    # Multi-item support: prefer items array, fall back to single item/qty
    items_arr = data.get("items") or []
    if not items_arr and data.get("item"):
        items_arr = [{"item": data.get("item", ""), "qty": int(data.get("qty") or 0)}]
    # Normalize qty to int
    norm_items = []
    for it in items_arr:
        if (it.get("item") or "").strip():
            norm_items.append({
                "item": it["item"].strip(),
                "qty":  int(it.get("qty") or 1),
            })

    rec = {
        "id":          _id,
        "from_user":   current_user()["username"],
        "from_name":   current_user()["name"],
        "from_source": from_source,
        "to_user":     to_user,
        "to_name":     USERS.get(to_user, {}).get("name", to_user),
        "items":       norm_items,                # ВСЕ позиции
        "item":        norm_items[0]["item"] if norm_items else "",   # для обратной совместимости
        "qty":         norm_items[0]["qty"]  if norm_items else 0,
        "note":        data.get("note", ""),
        "status":      "Создана",
        "created_at":  datetime.now().isoformat(timespec="seconds"),
    }
    db["transfers"].append(rec)
    save_db(db)
    return jsonify({"ok": True, "transfer": rec})


@app.route("/api/transfers/<int:tid>", methods=["POST"])
@login_required
def api_transfers_action(tid):
    data   = request.get_json(force=True) or {}
    action = data.get("action")
    db     = load_db()
    rec    = next((t for t in db["transfers"] if t["id"] == tid), None)
    if not rec:
        return jsonify({"error": "not found"}), 404
    u = current_user()
    if u["role"] not in ("nachalnik", "admin") and rec.get("to_user") != u["username"]:
        return jsonify({"error": "forbidden"}), 403
    if rec["status"] != "Создана":
        return jsonify({"error": "already processed"}), 400

    if action == "accept":
        rec["status"] = "Принята"
        # Берём массив items, либо строим из старых полей (back-compat)
        items_list = rec.get("items") or []
        if not items_list and rec.get("item"):
            items_list = [{"item": rec.get("item", ""), "qty": int(rec.get("qty") or 0)}]

        total_moved = 0
        for it in items_list:
            name = (it.get("item") or "").strip()
            qty  = int(it.get("qty") or 0)
            if not name or qty <= 0:
                continue

            # Списать у отправителя (если у него такая позиция есть)
            src = next((i for i in db["warehouse"]
                        if i.get("owner") == rec.get("from_user") and i.get("name") == name), None)
            moved = qty
            if src:
                moved = min(qty, int(src.get("qty") or 0))
                src["qty"] = int(src.get("qty") or 0) - moved
            total_moved += moved

            # Зачислить получателю
            dst = next((i for i in db["warehouse"]
                        if i.get("owner") == rec.get("to_user") and i.get("name") == name), None)
            if dst:
                dst["qty"] = int(dst.get("qty") or 0) + qty
            else:
                nid = next_id(db, "warehouse")
                db["warehouse"].append({
                    "id": nid,
                    "owner": rec.get("to_user"),
                    "name":  name,
                    "type":  (src.get("type") if src else ""),
                    "qty":   qty,
                    "note":  "Получено по заявке",
                })
        rec["moved_qty"] = total_moved
    elif action == "reject":
        rec["status"] = "Отклонена"
    save_db(db)
    return jsonify({"ok": True, "transfer": rec})


# ---------------------------------------------------------------------------
#  Наряды
# ---------------------------------------------------------------------------
NARYADY_DEFAULT_RABOTY = [
    {"op": "Слесарные работы",   "qty": 0},
    {"op": "Погрузка металлолома","qty": 0},
    {"op": "Сварочные работы",    "qty": 0},
]
NARYADY_DEFAULT_BRIGADA = [
    {"fio": "Ахметов А.А.",  "ktu": 1.0},
    {"fio": "Серікбаев Б.Н.", "ktu": 1.0},
    {"fio": "Жаксыбеков Е.С.", "ktu": 1.0},
    {"fio": "Нурланов Д.К.", "ktu": 0.9},
    {"fio": "Қасымов М.Т.", "ktu": 0.9},
]


@app.route("/api/naryady", methods=["GET"])
@login_required
def api_naryady_get():
    db = load_db()
    docs = db.get("naryady", [])
    u = current_user()
    uch_filter = request.args.get("uchastok")
    if uch_filter:
        docs = [d for d in docs if d.get("uchastok") == uch_filter]
    elif u["role"] == "master":
        docs = [d for d in docs if d.get("uchastok") == u["uchastok"]]
    elif u["role"] == "nachalnik_ktc":
        docs = [d for d in docs if d.get("uchastok") in ("telega", "roller", "kolesny")]
    elif u["role"] == "nachalnik":
        docs = [d for d in docs if d.get("uchastok") in ("avtoscepka", "akp", "kuzov")]
    return jsonify(docs)


@app.route("/api/naryady/<int:doc_id>", methods=["GET"])
@login_required
def api_naryady_one(doc_id):
    db = load_db()
    doc = next((d for d in db.get("naryady", []) if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(doc)


@app.route("/api/naryady", methods=["POST"])
@login_required
def api_naryady_create():
    data = request.get_json(force=True) or {}
    u = current_user()
    db = load_db()
    _id = next_id(db, "naryady")
    doc = {
        "id":       _id,
        "uchastok": data.get("uchastok") or u.get("uchastok") or "",
        "date":     data.get("date") or date.today().isoformat(),
        "smena":    data.get("smena", 1),
        "raboty":   data.get("raboty", [r.copy() for r in NARYADY_DEFAULT_RABOTY]),
        "brigada":  data.get("brigada", [b.copy() for b in NARYADY_DEFAULT_BRIGADA]),
        "status":   data.get("status", "Черновик"),
        "owner":    u["username"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    db.setdefault("naryady", []).append(doc)
    save_db(db)
    return jsonify({"ok": True, "doc": doc})


@app.route("/api/naryady/<int:doc_id>", methods=["PUT"])
@login_required
def api_naryady_update(doc_id):
    data = request.get_json(force=True) or {}
    db = load_db()
    doc = next((d for d in db.get("naryady", []) if d["id"] == doc_id), None)
    if not doc:
        return jsonify({"error": "not found"}), 404
    for k in ("uchastok", "date", "smena", "raboty", "brigada", "status"):
        if k in data:
            doc[k] = data[k]
    doc["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_db(db)
    return jsonify({"ok": True, "doc": doc})


@app.route("/api/naryady/<int:doc_id>", methods=["DELETE"])
@login_required
def api_naryady_delete(doc_id):
    db = load_db()
    db["naryady"] = [d for d in db.get("naryady", []) if d["id"] != doc_id]
    save_db(db)
    return jsonify({"ok": True})


@app.route("/api/naryady_defaults", methods=["GET"])
@login_required
def api_naryady_defaults():
    return jsonify({
        "raboty":  NARYADY_DEFAULT_RABOTY,
        "brigada": NARYADY_DEFAULT_BRIGADA,
    })


# ---------------------------------------------------------------------------
#  Синхронизация с Бюро описи (FIX: перемещено выше __main__)
# ---------------------------------------------------------------------------
def _generate_demo_data(db):
    """Генерирует богатые демо-данные: 10 вагонов с полным комплектом
    ОПЗС, нарядов, КП, натурных листов и складских остатков.
    Принимает db, возвращает обновлённый db. Не сохраняет в файл — caller сохраняет."""
    today = date.today()
    today_iso = today.isoformat()

    # Очищаем старые seed-данные перед демо
    db["wagons"] = []
    db["opzs"] = []
    db["nakatka"] = []
    db["kp_arrival"] = []
    db["kp_departure"] = []
    db["roller"] = []
    db["naryady"] = []
    db["transfers"] = []
    db["counters"] = {
        "wagons": 0, "opzs": 0, "nakatka": 0,
        "kp_arrival": 0, "kp_departure": 0, "roller": 0,
        "warehouse": db["counters"].get("warehouse", 4), "transfers": 0,
        "naryady": 0,
    }

    # ── Демо: 10 вагонов с реальными номерами ──
    wagon_numbers = ["43857294", "55012387", "61140052", "42337811", "59873145",
                     "63204891", "47125063", "52639874", "68745120", "55401267"]
    kontragenty = ["КТЖ", "ТОО «АСТАНА ВАГОН СЕРВИС»", "АО «ТРАНСХОЛДИНГ»",
                   "ТОО «КАЗТЕМИРТРАНС»", "Народный логистик"]

    # Реалистичные русские/казахские ФИО для бригад
    brigada_pool = [
        "Ахметов А.А.", "Серікбаев Б.Н.", "Жаксыбеков Е.С.", "Нурланов Д.К.",
        "Қасымов М.Т.", "Иванов П.С.", "Петров И.В.", "Сидоров А.М.",
        "Бектұров Ғ.Қ.", "Орынбаев Е.Б.", "Турсунов Б.А.", "Кудайбергенов Н.С.",
        "Алиев С.К.", "Жумабаев К.Т.", "Молдабеков А.Е.", "Сапаров Д.Ж.",
    ]

    parts_avtoscepka = [
        ("Замок автосцепки", "забраковано"),
        ("Замкодержатель", "в оборот"),
        ("Предохранитель замка", "в оборот"),
        ("Подъёмник замка", "в оборот"),
        ("Валик подъёмника", "забраковано"),
        ("Тяговый хомут", "в оборот"),
    ]
    parts_telega = [
        ("Балка надрессорная чер.100.00.010-6", "в оборот"),
        ("Рама боковая черт.100.00.002-4", "в оборот"),
        ("Клин фрикционный чугунный М1698.00.002", "забраковано"),
        ("Пружина рессорная наружная 1272.3045858008", "в оборот"),
        ("Колодка тормозная", "забраковано"),
        ("Триангель 100.40.010-2", "в оборот"),
    ]
    parts_akp = [
        ("Авторежим 265А-1", "забраковано"),
        ("Авторегулятор 574Б", "в оборот"),
        ("Цилиндр тормозной", "в оборот"),
        ("Кран концевой", "в оборот"),
        ("Воздухораспределитель 483", "забраковано"),
    ]
    parts_kuzov = [
        ("Хребтовая балка", "в оборот"),
        ("Крышка люка", "забраковано"),
        ("Петля крышки люка", "в оборот"),
        ("Боковая стойка", "в оборот"),
    ]

    statuses_pool = ["Утверждён", "Утверждён", "На утверждении", "Черновик", "На доработке"]

    for i, num in enumerate(wagon_numbers):
        wid = next_id(db, "wagons")
        wdate = today_iso
        wagon = {
            "id": wid, "number": num,
            "incoming_number": f"ВХ-{today.year}-{wid:03d}",
            "date": wdate, "status": "В ремонте",
        }
        db["wagons"].append(wagon)

        # Для каждого вагона: ОПЗС по 4 участкам с уже заполненными деталями
        for uch_name, parts_pool in [
            ("avtoscepka", parts_avtoscepka),
            ("telega",     parts_telega),
            ("akp",        parts_akp),
            ("kuzov",      parts_kuzov),
        ]:
            oid = next_id(db, "opzs")
            opzs = _mk_opzs(oid, wid, num, uch_name)
            opzs["status"] = random.choice(statuses_pool)
            # Заполняем 3-5 деталей случайно
            parts_used = random.sample(parts_pool, min(len(parts_pool), random.randint(3, 5)))
            opzs_parts = []
            for pname, cond in parts_used:
                # Половина — номерные, половина — неномерные
                if random.random() > 0.5:
                    p = {
                        "kind": "num", "type": pname,
                        "number": f"{random.randint(10,99)}-{random.randint(1000,9999)}",
                        "number_after": f"{random.randint(10,99)}-{random.randint(1000,9999)}" if cond == "в оборот" else "",
                        "zavod": random.choice(ZAVODY),
                        "god": str(random.randint(2015, 2024)),
                        "cond": cond,
                        "installed_from": random.choice(["из оборота", "новый"]) if cond == "забраковано" else "из оборота",
                        "reject_reason": "Износ выше нормы" if cond == "забраковано" else "",
                    }
                else:
                    p = {
                        "kind": "unnum", "type": pname,
                        "qty": random.randint(1, 4),
                        "cond": cond,
                        "installed_from": random.choice(["из оборота", "новый"]) if cond == "забраковано" else "из оборота",
                        "reject_reason": "Поверхностные дефекты" if cond == "забраковано" else "",
                    }
                opzs_parts.append(p)
            opzs["parts"] = opzs_parts
            if opzs["status"] == "На доработке":
                opzs["comment"] = "Проверьте корректность номера после"
            db["opzs"].append(opzs)

    # ── Колёсные пары: Приход ──
    for i in range(8):
        kid = next_id(db, "kp_arrival")
        db["kp_arrival"].append({
            "id": kid,
            "num": f"01-{random.randint(100000, 999999)}",
            "tip": random.choice(["РУ1-950", "РУ1Ш-950"]),
            "god": str(random.randint(2014, 2024)),
            "zavod": random.choice(ZAVODY),
            "vhod": f"ВХ-КП-{kid:03d}",
            "remont": random.choice(REPAIR_TYPES_KP),
            "tlev": round(random.uniform(26.5, 32.0), 1),
            "tprav": round(random.uniform(26.5, 32.0), 1),
            "note": "",
            "status": random.choice(["Проведён", "Проведён", "Черновик"]),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })

    # ── Колёсные пары: Выход ──
    for i in range(6):
        kid = next_id(db, "kp_departure")
        m_y = today.replace(day=1)
        db["kp_departure"].append({
            "id": kid,
            "num": f"02-{random.randint(100000, 999999)}",
            "tip": random.choice(["РУ1-950", "РУ1Ш-950"]),
            "god": str(random.randint(2015, 2024)),
            "zavod": random.choice(ZAVODY),
            "remont": random.choice(REPAIR_TYPES_KP),
            "mg_osvid": m_y.isoformat(),
            "note": "",
            "status": "Проведён",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })

    # ── Роликовый участок ──
    for i in range(5):
        kid = next_id(db, "roller")
        db["roller"].append({
            "id": kid,
            "num": f"03-{random.randint(100000, 999999)}",
            "tip": random.choice(["РУ1-950", "РУ1Ш-950"]),
            "god": str(random.randint(2015, 2024)),
            "zavod": random.choice(ZAVODY),
            "remont": random.choice(REPAIR_TYPES_KP),
            "note": "",
            "status": "Проведён",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })

    # ── Натурный колёсный лист (4 шт) ──
    for i in range(4):
        nid = next_id(db, "nakatka")
        wn = wagon_numbers[i]
        kp_rows = []
        for k in range(4):  # 4 КП на вагон
            kp_rows.append({
                "num": f"04-{random.randint(100000, 999999)}",
                "god": str(random.randint(2015, 2024)),
                "zavod": random.choice(ZAVODY),
                "ustanovleno": today_iso,
                "proish": random.choice(["Новая", "После ремонта", "Переставная"]),
                "vhod": f"ВХ-{random.randint(100,999)}",
                "tip": random.choice(["РУ1-950", "РУ1Ш-950"]),
                "punkt_form": "АВРЗ Акмола",
                "kod_sobst": "1042",
                "kod_osvid": "1042",
                "mg_form": today.replace(day=1).isoformat(),
                "mg_osvid": today.replace(day=1).isoformat(),
            })
        db["nakatka"].append({
            "id": nid,
            "wagon_number": wn,
            "telega_number": f"{random.randint(10000,99999)}",
            "vagon_type": random.choice(["Полувагон", "Цистерна", "Хоппер"]),
            "kontragent": random.choice(kontragenty),
            "remont_type": random.choice(["ТР-1", "ТР-2", "СР"]),
            "kp_rows": kp_rows,
            "status": random.choice(["Проведён", "Проведён", "Черновик"]),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })

    # ── Наряды по всем участкам ──
    naryady_data = [
        ("avtoscepka", [("Слесарные работы по автосцепке", 12), ("Сварочные работы", 4), ("Погрузка металлолома", 2)]),
        ("akp",        [("Слесарные работы по тормозам", 18), ("Регулировка АКП", 6), ("Сварочные работы", 2)]),
        ("kuzov",      [("Слесарные работы по кузову", 15), ("Сварочные работы", 10), ("Погрузка металлолома", 5)]),
        ("telega",     [("Слесарные работы по тележкам", 22), ("Сварочные работы", 6)]),
        ("roller",     [("Ремонт буксовых узлов", 8), ("Слесарные работы", 12)]),
        ("kolesny",    [("Дефектоскопия КП", 14), ("Приём КП", 8)]),
    ]
    for uch, raboty in naryady_data:
        for shift in [1, 2]:
            nid = next_id(db, "naryady")
            brigada = []
            for fio in random.sample(brigada_pool, random.randint(4, 6)):
                brigada.append({"fio": fio, "ktu": round(random.uniform(0.8, 1.2), 1)})
            db["naryady"].append({
                "id": nid,
                "uchastok": uch,
                "date": today_iso,
                "smena": shift,
                "raboty": [{"op": op, "qty": qty} for op, qty in raboty],
                "brigada": brigada,
                "status": "Проведён",
                "owner": "admin",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            })

    # ── Склад: заполняем у каждого пользователя ──
    warehouse_per_user = {
        # ── Мастер Автосцепка (10 позиций) ──
        "master_auto": [
            ("Замок автосцепки", "Замок", 15),
            ("Замкодержатель", "Замок", 12),
            ("Предохранитель замка", "Замок", 22),
            ("Подъёмник замка", "Замок", 8),
            ("Валик подъёмника", "Деталь", 14),
            ("Тяговый хомут", "Узел", 4),
            ("Клин тягового хомута", "Деталь", 18),
            ("Центрирующая балочка", "Деталь", 9),
            ("Маятниковая подвеска", "Деталь", 16),
            ("Электрод д-4 мм", "Расходник", 250),
        ],
        # ── Мастер Тележка (10 позиций) ──
        "master_telega": [
            ("Пружина рессорная внутренняя 1272.3045858007", "Пружина", 35),
            ("Пружина рессорная наружная 1272.3045858008", "Пружина", 32),
            ("Клин фрикционный чугунный М1698.00.002", "Клин", 24),
            ("Планка фрикционная подвижная М1698.02.004", "Планка", 28),
            ("Планка фрикционная неподвижная М1698.02.001", "Планка", 28),
            ("Колодка тормозная", "Колодка", 48),
            ("Триангель 100.40.010-2", "Деталь", 6),
            ("Подвеска тормозного башмака", "Деталь", 18),
            ("Чека 100-40-014", "Деталь", 32),
            ("Колпак скользуна М1698.01.100", "Колпак", 16),
        ],
        # ── Мастер АКП (10 позиций) ──
        "master_akp": [
            ("Манжета 270-313", "Манжета", 45),
            ("Манжета 305-156", "Манжета", 28),
            ("Манжета 270-397-3", "Манжета", 22),
            ("Прокладка 270-330-1", "Прокладка", 38),
            ("Прокладка 270-326", "Прокладка", 30),
            ("Авторежим 265А-1", "Прибор", 4),
            ("Авторегулятор 574Б", "Прибор", 6),
            ("Воздухораспределитель 483", "Прибор", 3),
            ("Кран концевой", "Прибор", 8),
            ("Кран разобщительный", "Прибор", 10),
        ],
        # ── Мастер Кузов (8 позиций) ──
        "master_kuzov": [
            ("Крышка люка", "Деталь", 12),
            ("Петля крышки люка", "Деталь", 24),
            ("Скоба крышки люка", "Деталь", 36),
            ("Болт М22х90", "Метиз", 180),
            ("Гайка М22", "Метиз", 200),
            ("Кронштейн", "Деталь", 14),
            ("Скоба", "Деталь", 28),
            ("Электрод д-4 мм", "Расходник", 180),
        ],
        # ── Мастер Роликовый (9 позиций) ──
        "master_roller": [
            ("Подшипник 30-232726", "Подшипник", 22),
            ("Подшипник 30-42726Л", "Подшипник", 18),
            ("Корпус буксы", "Корпус", 8),
            ("Крышка крепительная", "Крышка", 12),
            ("Крышка смотровая", "Крышка", 15),
            ("Лабиринтное кольцо", "Кольцо", 16),
            ("Стопорная планка", "Деталь", 24),
            ("Гайка корончатая М30", "Метиз", 30),
            ("Болт М20х90", "Метиз", 80),
        ],
        # ── Дефектоскопист (5 расходников) ──
        "defekt1": [
            ("Магнитный порошок", "Расходник", 25),
            ("Дефектоскопическая жидкость", "Расходник", 18),
            ("Электроды для МПД", "Расходник", 10),
            ("Калибр-кольцо К-1", "Инструмент", 4),
            ("Шаблон ВЦБ-3", "Инструмент", 2),
        ],
        # ── Общий склад начальника ВРЦ (12 позиций) ──
        "nachalnik": [
            ("Корпус автосцепки СА-3", "Узел", 6),
            ("Поглощающий аппарат Ш-2-Т", "Узел", 4),
            ("Поглощающий аппарат Ш-6-ТО-4", "Узел", 3),
            ("Тяговый хомут", "Узел", 8),
            ("Воздухораспределитель 483", "Прибор", 12),
            ("Авторежим 265А-1", "Прибор", 10),
            ("Авторегулятор 574Б", "Прибор", 14),
            ("Цилиндр тормозной", "Прибор", 6),
            ("Хребтовая балка", "Деталь", 4),
            ("Шкворневая балка", "Деталь", 6),
            ("Электрод д-4 мм", "Расходник", 500),
            ("Болт М22х90", "Метиз", 350),
        ],
        # ── Общий склад начальника КТЦ (12 позиций) ──
        "nachalnik_ktc": [
            ("Балка надрессорная чер.100.00.010-6", "Узел", 10),
            ("Рама боковая черт.100.00.002-4", "Узел", 12),
            ("Колёсная пара РУ1-950", "КП", 18),
            ("Колёсная пара РУ1Ш-950", "КП", 14),
            ("Подшипник 30-232726", "Подшипник", 60),
            ("Подшипник 30-42726Л", "Подшипник", 48),
            ("Корпус буксы", "Корпус", 24),
            ("Колодка тормозная", "Колодка", 120),
            ("Пружина рессорная наружная 1272.3045858008", "Пружина", 80),
            ("Пружина рессорная внутренняя 1272.3045858007", "Пружина", 80),
            ("Клин фрикционный чугунный М1698.00.002", "Клин", 60),
            ("Триангель 100.40.010-2", "Деталь", 18),
        ],
    }
    # Очищаем старый склад (кроме того что уже было если нужно)
    db["warehouse"] = []
    db["counters"]["warehouse"] = 0
    for owner, items in warehouse_per_user.items():
        for name, typ, qty in items:
            wid_w = next_id(db, "warehouse")
            db["warehouse"].append({
                "id": wid_w, "owner": owner, "name": name,
                "type": typ, "qty": qty, "note": "",
            })

    # ── Заявки на получение (несколько примеров) ──
    sample_requests = [
        ("master_auto", "sklad_metal", [
            {"item": "Замок автосцепки", "qty": 5},
            {"item": "Замкодержатель", "qty": 3},
        ], "Создана"),
        ("master_akp", "sklad_metal", [
            {"item": "Воздухораспределитель 483", "qty": 2},
        ], "Принята"),
        ("master_telega", "sklad_rashodniki", [
            {"item": "Колодка тормозная", "qty": 16},
            {"item": "Триангель 100.40.010-2", "qty": 4},
        ], "Создана"),
        ("master_kuzov", "sklad_main", [
            {"item": "Болт М22х90", "qty": 50},
            {"item": "Гайка М22", "qty": 50},
        ], "Принята"),
    ]
    for from_user, src, items, status in sample_requests:
        tid = next_id(db, "transfers")
        rec = {
            "id": tid,
            "from_user": from_user,
            "from_name": USERS.get(from_user, {}).get("name", from_user),
            "from_source": src,
            "to_user": from_user,
            "to_name": USERS.get(from_user, {}).get("name", from_user),
            "items": items,
            "item": items[0]["item"],
            "qty": items[0]["qty"],
            "note": "Демо-заявка",
            "status": status,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        db["transfers"].append(rec)

    return db


@app.route("/api/sync_bureau", methods=["POST"])
@login_required
def sync_bureau():
    u = current_user()
    if u["role"] != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403
    db = load_db()
    db = _generate_demo_data(db)
    save_db(db)
    return jsonify({
        "ok": True,
        "message": f"Импортировано {len(db['wagons'])} вагонов из Бюро описи",
        "wagons": len(db["wagons"]),
        "opzs": len(db["opzs"]),
        "naryady": len(db["naryady"]),
        "kp": len(db["kp_arrival"]) + len(db["kp_departure"]) + len(db["roller"]),
        "nakatka": len(db["nakatka"]),
        "warehouse": len(db["warehouse"]),
    })


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    load_db()
    app.run(host="0.0.0.0", port=5001, debug=True)
