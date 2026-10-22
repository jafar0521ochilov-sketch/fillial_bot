"""
config.py - Mazzali Inventory & Order Management Bot
1-Modul: Konfiguratsiya, filiallar, tugmalar va tizim sozlamalari
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ----------------------------------------------------
# 1. ASOSIY YO'LLAR VA .ENV YUKLASH
# ----------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# Asosiy kalitlar va identifikatorlar
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_SHEET_KEY = os.getenv("GOOGLE_SHEET_KEY")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "credentials.json")

# Adminlarning Telegram ID raqamlari (vergul orqali bir nechta kiritish mumkin)
ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in os.getenv("ADMIN_IDS", "").split(",")
    if admin_id.strip().isdigit()
]

# Fayl yo'llari
SERVICE_ACCOUNT_PATH = BASE_DIR / SERVICE_ACCOUNT_FILE
DB_PATH = BASE_DIR / "bot_database.db"

# ----------------------------------------------------
# 2. XATOLIKLARNI TEKSHIRISH
# ----------------------------------------------------
missing_vars = []
if not BOT_TOKEN:
    missing_vars.append("BOT_TOKEN")
if not GEMINI_API_KEY:
    missing_vars.append("GEMINI_API_KEY")
if not GOOGLE_SHEET_KEY:
    missing_vars.append("GOOGLE_SHEET_KEY")

if missing_vars:
    print(f"❌ Diqqat: .env faylida quyidagi parametrlar to'ldirilmagan: {', '.join(missing_vars)}")

# ----------------------------------------------------
# 3. GOOGLE SHEETS HUQUQLARI VA ASOSIY VARAQLAR
# ----------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SHEET_MASTER_LOG = "Транзакции"       # Barcha kunlik amallar jurnali
SHEET_LIVE_STOCK = "Остатки_Live"     # 9 ta filialning joriy real qoldiqlari

# ----------------------------------------------------
# 4. MAZZALI 9 TA FILIAL VA ULARNING BUYURTMA VARAQLARI
# ----------------------------------------------------
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
}

BRANCHES = list(BRANCH_ORDER_SHEETS.keys())
ORDER_SHEETS = list(BRANCH_ORDER_SHEETS.values())

# ----------------------------------------------------
# 5. HUJJAT VA AMALLAR TURLARI
# ----------------------------------------------------
DOC_TYPES = {
    "MORNING_STOCK": "Утренний остаток",           # Ertalabki sanash
    "INCOME": "Приход",                             # Fabrikadan kirim
    "EVENING_STOCK": "Вечерний остаток",           # Kechki yakuniy sanash
    "EXPENSE_DISHES": "Общий расход блюд",         # Kunlik sotilgan/ishlatilgan taomlar
    "EXTRA_GOODS": "Дополнительный товар",         # 135 taomdan tashqari mahsulotlar (matnli)
    "FINISHED_DISHES": "Закончившиеся блюда",      # Smena oxirida rasm orqali tushgan ro'yxat
    "WRITE_OFF": "Списание",                       # Yaroqsiz/to'kilgan
    "TRANSFER": "Перемещение"                      # Filiallararo ko'chirish
}

# ----------------------------------------------------
# 6. TELEGRAM BOT MENYULARI VA TUGMALARI
# ----------------------------------------------------
# Kassirlar menyusi (filial xodimlari uchun):
CASHIER_BUTTONS = [
    "🌅 Утренний остаток",
    "📥 Приход",
    "🍽 Общий расход блюд",
    "✍️ Дополнительный товар (вручную)",
    "📸 Закончившиеся блюда",
    "🗑 Списание",
    "🌙 Вечерний остаток",
    "📋 Заказ для фабрики"
]

# Boshqaruvchi va admin menyusi:
ADMIN_BUTTONS = [
    "📊 Сверка / Недостача",
    "📈 Живые остатки (Live)",
    "⚙️ Управление"
]

# ----------------------------------------------------
# 7. MATNLI KIRITISH VA ANALITIKA SOZLAMALARI
# ----------------------------------------------------
# Qo'shimcha tovar kiritishda kassirga ko'rsatiladigan shablon:
EXTRA_GOODS_HELP_TEXT = (
    "✍️ *Iltimos, qo'shimcha tovarlarni quyidagi formatda kiriting:*\n\n"
    "`Tovar nomi - Miqdori`\n\n"
    "*Misol:*\n"
    "Konteyner 500ml - 100\n"
    "Salfetka - 10\n"
    "Bir martalik qoshiq - 200"
)

# Smena davomida tugagan taomlarni keyingi zakazda avtomatik oshirish koeffitsiyenti (%):
ORDER_INCREASE_PERCENT = 20

# Ma'lumotlarni saqlash va sinxronizatsiya limitlari:
DATA_RETENTION_DAYS = 90       # 3 oy (90 kun)dan eski tranzaksiyalar arxivlanadi/tozalanadi
SYNC_BATCH_SIZE = 50           # Google Sheets'ga bir vaqtda uzatish paketi (batch)
SYNC_INTERVAL_SECONDS = 5      # Lokal bazadan Google Sheets'ga uzatish oraliq vaqti