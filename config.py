"""
config.py - Mazzali Inventory & Order Management Bot
1-Modul: Konfiguratsiya, filiallar, tugmalar va tizim sozlamalari
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Xavfsiz o'qish (GitHub bloklamasligi uchun)
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")

SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "credentials.json")

ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in os.getenv("ADMIN_IDS", "").split(",")
    if admin_id.strip().isdigit()
]

SERVICE_ACCOUNT_PATH = BASE_DIR / SERVICE_ACCOUNT_FILE
DB_PATH = BASE_DIR / "bot_database.db"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SHEET_MASTER_LOG = "Транзакции"
SHEET_LIVE_STOCK = "Остатки_Live"

BRANCH_ORDER_SHEETS = {
    "Паркент": "Заказ_Паркент",
    "Ц-6": "Заказ_Ц-6",
    "Шота": "Заказ_Шота",
    "Ц-1": "Заказ_Ц-1",
    "КФС": "Заказ_КФС",
    "Ардус": "Заказ_Ардус",
    "Аския": "Заказ_Аския",
    "Махтумкули": "Заказ_Махтумкули",
    "Чехов": "Заказ_Чехов",
    "Чилонзор": "Заказ_Чилонзор",
    "Бунёдкор": "Заказ_Бунёдкор",
    "Шевченко": "Заказ_Шевченко",
    "Саракулка": "Заказ_Саракулка",
}

BRANCHES = list(BRANCH_ORDER_SHEETS.keys())
ORDER_SHEETS = list(BRANCH_ORDER_SHEETS.values())

DOC_TYPES = {
    "MORNING_STOCK": "Утренний остаток",
    "INCOME": "Приход по накладной",
    "EVENING_STOCK": "Вечерний остаток",
    "EXPENSE_DISHES": "Общий расход блюд",
    "EXTRA_GOODS": "Дополнительный товар",
    "FINISHED_DISHES": "Закончившиеся блюда",
    "WRITE_OFF": "Списание",
    "TRANSFER": "Перемещение",
    "FACTORY_ORDER": "Заказ для фабрики"
}

CASHIER_BUTTONS = [
    "🌅 Утренний остаток",
    "📥 Приход по накладной",
    "🍽️ Общий расход блюд",
    "✍️ Дополнительный товар (вручную)",
    "📸 Закончившиеся блюда",
    "🗑️ Списание",
    "🔄 Перемещение",
    "🌙 Вечерний остаток",
    "🏭 Заказ для фабрики"
]

ADMIN_BUTTONS = [
    "📊 Сверка / Недостача",
    "📈 Живые остатки (Live)",
    "🤖 Gemini AI Yordamchi",
    "🧹 Bazani tozalash"
]

EXTRA_GOODS_HELP_TEXT = (
    "✍️ *Iltimos, qo'shimcha tovarlarni quyidagi formatda kiriting:*\\n\\n"
    "`Tovar nomi - Miqdori`\\n\\n"
    "*Misol:*\\n"
    "Konteyner 500ml - 100\\n"
    "Salfetka - 10"
)

ORDER_INCREASE_PERCENT = 20
DATA_RETENTION_DAYS = 90
SYNC_BATCH_SIZE = 50
SYNC_INTERVAL_SECONDS = 5