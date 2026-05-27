# -*- coding: utf-8 -*-
"""
АВРЗ — Система учёта и ремонта вагонов и колёсных пар.
Flask backend с ролевым доступом, маршрутом утверждения ОПЗС,
складом, заявками на перемещение и хранением в JSON.
"""
import json
import os
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
USERS = {
    "admin":         {"password": "1", "name": "Администратор (Бюро)",      "role": "admin",          "uchastok": None},
    "nachalnik":     {"password": "1", "name": "Начальник цеха",             "role": "nachalnik",      "uchastok": None},
    "master_auto":   {"password": "1", "name": "Мастер (Автосцепка)",        "role": "master",         "uchastok": "avtoscepka"},
    "master_telega": {"password": "1", "name": "Мастер (Тележечный)",        "role": "master",         "uchastok": "telega"},
    "master_akp":    {"password": "1", "name": "Мастер (АКП)",               "role": "master",         "uchastok": "akp"},
    "master_roller": {"password": "1", "name": "Мастер (Роликовый)",         "role": "master_roller",  "uchastok": "roller"},
    "defekt1":       {"password": "1", "name": "Дефектоскопист (Колёсный)",  "role": "defektoskopist", "uchastok": "kolesny"},
    "defekt2":       {"password": "1", "name": "Дефектоскопист (Вагонный)", "role": "defektoskopist", "uchastok": "wagon_def"},
}

UCHASTOK_LABEL = {
    "avtoscepka": "Автосцепка",
    "telega":     "Тележечный",
    "akp":        "АКП",
    "roller":     "Роликовый",
    "kolesny":    "Колёсный",
    "wagon_def":  "Вагонный (Деф.)",
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
    {"name": "Балка надрессорная чер.100.00.010-6",       "qty": 1},
    {"name": "Рама боковая черт.100.00.002-4 ГОСТ 32400", "qty": 1},
    {"name": "Колёсная пара",                              "qty": 1},
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
    {"name": "Корпус автосцепки"},
    {"name": "Тяговый хомут"},
    {"name": "Поглощающий аппарат"},
    {"name": "Клин тягового хомута"},
]
AVTOSCEPKA_UNNUMBERED = [
    {"name": "Замок автосцепки",         "qty": 1},
    {"name": "Замкодержатель",           "qty": 1},
    {"name": "Предохранитель замка",     "qty": 1},
    {"name": "Подъёмник замка",          "qty": 1},
    {"name": "Валик подъёмника",         "qty": 1},
    {"name": "Упорная плита",            "qty": 1},
    {"name": "Болт М20х90",              "qty": 4},
    {"name": "Гайка М20",                "qty": 4},
    {"name": "Шплинт 6,3х63",            "qty": 4},
    {"name": "Электрод д-4 мм",          "qty": 1},
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

# ---------------------------------------------------------------------------
#  Хранилище (JSON)
# ---------------------------------------------------------------------------
def _seed():
    today = date.today().isoformat()
    return {
        "counters": {"wagons": 3, "opzs": 6, "nakatka": 1,
                     "kp_arrival": 2, "kp_departure": 1, "roller": 1,
                     "warehouse": 4, "transfers": 1},
        "wagons": [
            {"id": 1, "number": "43857294", "incoming_number": "ВХ-2024-001", "date": today, "status": "В ремонте"},
            {"id": 2, "number": "55012387", "incoming_number": "ВХ-2024-002", "date": today, "status": "В ремонте"},
            {"id": 3, "number": "61140052", "incoming_number": "ВХ-2024-003", "date": today, "status": "В ремонте"},
        ],
        "opzs": [
            _mk_opzs(1, 1, "43857294", "avtoscepka"),
            _mk_opzs(2, 1, "43857294", "telega"),
            _mk_opzs(3, 2, "55012387", "avtoscepka"),
            _mk_opzs(4, 2, "55012387", "telega"),
            _mk_opzs(5, 3, "61140052", "avtoscepka"),
            _mk_opzs(6, 3, "61140052", "akp"),
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
    }


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
        db = _seed()
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
        "uchastok_label": UCHASTOK_LABEL,
        "users": {k: {"name": v["name"], "uchastok": v["uchastok"]} for k, v in USERS.items()},
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
    # авто-создание ОПЗС для Автосцепки и Тележечного
    for uch in ("avtoscepka", "telega"):
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
    if current_user()["role"] != "nachalnik":
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
    if u["role"] != "nachalnik":
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
    if u["role"] != "nachalnik" and it.get("owner") != u["username"]:
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
    if u["role"] != "nachalnik" and it.get("owner") != u["username"]:
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
    if u["role"] != "nachalnik":
        items = [t for t in items
                 if t.get("from_user") == u["username"] or t.get("to_user") == u["username"]]
    return jsonify(items)


@app.route("/api/transfers", methods=["POST"])
@login_required
def api_transfers_create():
    data = request.get_json(force=True) or {}
    db   = load_db()
    _id  = next_id(db, "transfers")
    rec  = {
        "id":         _id,
        "from_user":  current_user()["username"],
        "from_name":  current_user()["name"],
        "to_user":    data.get("to_user", ""),
        "to_name":    USERS.get(data.get("to_user", ""), {}).get("name", data.get("to_user", "")),
        "item":       data.get("item", ""),
        "qty":        int(data.get("qty") or 0),
        "note":       data.get("note", ""),
        "status":     "Создана",
        "created_at": datetime.now().isoformat(timespec="seconds"),
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
    if u["role"] != "nachalnik" and rec.get("to_user") != u["username"]:
        return jsonify({"error": "forbidden"}), 403
    if rec["status"] != "Создана":
        return jsonify({"error": "already processed"}), 400

    if action == "accept":
        rec["status"] = "Принята"
        qty  = int(rec.get("qty") or 0)
        name = rec.get("item", "")
        src  = next((i for i in db["warehouse"]
                     if i.get("owner") == rec.get("from_user") and i.get("name") == name), None)
        moved = qty
        if src:
            moved = min(qty, int(src.get("qty") or 0))
            src["qty"] = int(src.get("qty") or 0) - moved
        dst = next((i for i in db["warehouse"]
                    if i.get("owner") == rec.get("to_user") and i.get("name") == name), None)
        if dst:
            dst["qty"] = int(dst.get("qty") or 0) + qty
        else:
            nid = next_id(db, "warehouse")
            db["warehouse"].append({
                "id": nid, "owner": rec.get("to_user"), "name": name,
                "type": (src.get("type") if src else ""), "qty": qty, "note": "Получено по перемещению",
            })
        rec["moved_qty"] = moved
    elif action == "reject":
        rec["status"] = "Отклонена"
    save_db(db)
    return jsonify({"ok": True, "transfer": rec})


# ---------------------------------------------------------------------------
#  Синхронизация с Бюро описи (FIX: перемещено выше __main__)
# ---------------------------------------------------------------------------
@app.route("/api/sync_bureau", methods=["POST"])
@login_required
def sync_bureau():
    u = current_user()
    if u["role"] != "admin":
        return jsonify({"ok": False, "error": "forbidden"}), 403
    # В реальном проекте здесь был бы обмен с 1С/внешней системой
    return jsonify({"ok": True, "message": "Синхронизация выполнена"})


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    load_db()
    app.run(host="0.0.0.0", port=5001, debug=True)
