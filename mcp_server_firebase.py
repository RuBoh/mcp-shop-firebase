# =============================================================================
# MCP-СЕРВЕР v2 — Магазин курса "AI с нуля"
# База данных: Google Firebase (Firestore)
# =============================================================================
#
# Чем эта версия отличается от предыдущей?
# ─────────────────────────────────────────
# Версия 1 (mcp_server.py):
#   Данные хранились прямо в коде — в Python-словарях.
#   Это учебный пример. В реальности так не делают.
#
# Версия 2 (этот файл):
#   Данные хранятся в Firebase Firestore — это облачная база данных Google.
#   Сервер только читает данные оттуда. Меняешь данные в Firebase —
#   Claude сразу видит изменения. Это уже настоящая архитектура.
#
# Схема:
#   Firebase Firestore (база данных)
#          ↓
#   mcp_server_firebase.py  ←── Claude через MCP-коннектор
#          ↓
#   shop_firebase.html      ←── браузер пользователя
#
# =============================================================================

from fastmcp import FastMCP
import uvicorn
import os

# firebase_admin — официальная библиотека Google для работы с Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# ── ПОДКЛЮЧЕНИЕ К FIREBASE ────────────────────────────────────────────────────
#
# Firebase Admin SDK использует сервисный аккаунт для авторизации.
# Файл serviceAccountKey.json ты скачаешь из Firebase Console (шаг 2).
# Храни его рядом с этим файлом — НЕ загружай в публичный GitHub!
#
# На Railway файл передаётся через переменную окружения GOOGLE_CREDENTIALS
# (шаг 5 в инструкции).

import json

# Читаем credentials: сначала пробуем переменную окружения (Railway),
# если нет — ищем файл локально (для тестирования на своём компьютере)
creds_json = os.environ.get("GOOGLE_CREDENTIALS")

if creds_json:
    # Railway: credentials переданы как JSON-строка в переменной окружения
    creds_dict = json.loads(creds_json)
    cred = credentials.Certificate(creds_dict)
else:
    # Локально: читаем из файла
    cred = credentials.Certificate("serviceAccountKey.json")

# Инициализируем Firebase — это нужно сделать один раз при запуске
firebase_admin.initialize_app(cred)

# Получаем объект для работы с базой данных Firestore
db = firestore.client()

# ── СОЗДАНИЕ MCP-СЕРВЕРА ──────────────────────────────────────────────────────

mcp = FastMCP("Магазин курса AI с нуля 🎓 (Firebase)")

# ── ИНСТРУМЕНТЫ ───────────────────────────────────────────────────────────────
#
# Логика такая же как в версии 1, но вместо Python-словарей
# данные теперь читаются из Firebase Firestore.
#
# Firestore устроен так:
#   - Коллекция (collection) — как таблица в обычной БД
#   - Документ (document) — как строка в таблице
#   - Поле (field) — как ячейка
#
# У нас две коллекции: "products" и "orders"

@mcp.tool()
def get_all_products() -> dict:
    """
    Возвращает полный список всех продуктов из базы данных Firebase.
    Используй когда нужно показать каталог или покупатель спрашивает что есть.
    """
    # Читаем все документы из коллекции "products"
    products_ref = db.collection("products")
    docs = products_ref.stream()

    products_list = []
    for doc in docs:
        data = doc.to_dict()
        products_list.append({
            "id": doc.id,
            "name": data.get("name"),
            "price": f"{data.get('price')} {data.get('currency', 'PLN')}",
            "category": data.get("category"),
            "level": data.get("level"),
            "in_stock": data.get("in_stock"),
            "rating": data.get("rating"),
        })

    return {
        "total_products": len(products_list),
        "products": products_list,
    }


@mcp.tool()
def get_product_details(product_id: str) -> dict:
    """
    Возвращает подробную информацию о конкретном продукте из Firebase.

    Args:
        product_id: ID документа в Firestore (например: ai-course-basic)
    """
    doc_ref = db.collection("products").document(product_id)
    doc = doc_ref.get()

    if not doc.exists:
        # Получаем список доступных ID для подсказки
        all_docs = db.collection("products").stream()
        available = [d.id for d in all_docs]
        return {
            "error": f"Продукт '{product_id}' не найден в базе данных.",
            "available_ids": available,
        }

    data = doc.to_dict()
    data["id"] = doc.id
    return data


@mcp.tool()
def find_products_by_category(category: str) -> dict:
    """
    Находит все продукты в указанной категории.
    Категории: 'courses' (онлайн-курсы), 'workshops' (живые воркшопы).

    Args:
        category: 'courses' или 'workshops'
    """
    # Firestore поддерживает фильтрацию через .where()
    docs = db.collection("products").where("category", "==", category).stream()

    found = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        found.append(data)

    if not found:
        return {
            "error": f"Категория '{category}' не найдена или пуста.",
            "tip": "Доступные категории: courses, workshops",
        }

    return {"category": category, "count": len(found), "products": found}


@mcp.tool()
def check_stock(product_id: str) -> dict:
    """
    Проверяет наличие и остаток мест/товара в реальном времени из Firebase.

    Args:
        product_id: ID продукта для проверки
    """
    doc = db.collection("products").document(product_id).get()

    if not doc.exists:
        return {"error": f"Продукт '{product_id}' не найден."}

    data = doc.to_dict()
    stock_count = data.get("stock_count", 0)

    if not data.get("in_stock"):
        status, message = "out_of_stock", "Товар закончился"
    elif stock_count <= 5:
        status, message = "low_stock", f"Осталось всего {stock_count} мест — торопись!"
    elif stock_count <= 20:
        status, message = "limited", f"Осталось {stock_count} мест"
    else:
        status, message = "available", "В наличии"

    return {
        "product_id": product_id,
        "product_name": data.get("name"),
        "in_stock": data.get("in_stock"),
        "stock_count": stock_count,
        "status": status,
        "message": message,
    }


@mcp.tool()
def get_order_status(order_id: str) -> dict:
    """
    Возвращает статус заказа из Firebase по его номеру.

    Args:
        order_id: Номер заказа (например: ORD-001)
    """
    doc = db.collection("orders").document(order_id).get()

    if not doc.exists:
        return {
            "error": f"Заказ '{order_id}' не найден.",
            "tip": "Проверь номер заказа — он приходит на email после оформления.",
        }

    order = doc.to_dict()

    # Получаем название продукта
    product_doc = db.collection("products").document(order.get("product_id", "")).get()
    product_name = product_doc.to_dict().get("name", "Неизвестный продукт") if product_doc.exists else "Неизвестный продукт"

    status_messages = {
        "pending":    "⏳ Ожидает оплаты",
        "processing": "🔄 Обрабатывается",
        "completed":  "✅ Выполнен — доступ открыт",
        "cancelled":  "❌ Отменён",
    }

    return {
        "order_id": order_id,
        "product": product_name,
        "customer": order.get("customer"),
        "status": order.get("status"),
        "status_message": status_messages.get(order.get("status"), order.get("status")),
        "date": order.get("date"),
        "amount": f"{order.get('amount')} PLN",
    }


@mcp.tool()
def get_discount_code(email: str) -> dict:
    """
    Генерирует персональный промокод на скидку 15%.
    Используй когда покупатель сомневается или спрашивает о скидке.

    Args:
        email: Email покупателя
    """
    username = email.split("@")[0].upper()[:6]
    code = f"BOHO-{username}-15"
    return {
        "discount_code": code,
        "discount_percent": 15,
        "valid_until": "2025-12-31",
        "message": f"Твой промокод: {code} — скидка 15% на любой курс!"
    }


# ── ЗАПУСК ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app = mcp.http_app(path="/mcp")
    print(f"🚀 MCP-сервер v2 (Firebase) запущен на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
