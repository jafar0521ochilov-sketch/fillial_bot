"""
sheets_database.py - Mazzali Inventory & Order Management Bot
2-Modul: SQLite lokal bazasi, Google Sheets sinxronizatori, analitika va sverka
"""

import asyncio
from datetime import datetime, timedelta
import aiosqlite
import gspread
from google.oauth2.service_account import Credentials

import config

# Google Sheets ulanish mijozi
_gspread_client = None
_spreadsheet = None


def get_spreadsheet():
    """Google Sheets hujjatiga xavfsiz ulanish"""
    global _gspread_client, _spreadsheet
    if _spreadsheet is None:
        creds = Credentials.from_service_account_file(
            config.SERVICE_ACCOUNT_PATH, scopes=config.SCOPES
        )
        _gspread_client = gspread.authorize(creds)
        _spreadsheet = _gspread_client.open_by_key(config.GOOGLE_SHEET_KEY)
    return _spreadsheet


# ====================================================
# 1. BAZANI INIZALIZATSIYA QILISH
# ====================================================
async def init_db():
    """Lokal SQLite jadvallarini yaratish"""
    async with aiosqlite.connect(config.DB_PATH) as db:
        # Barcha kiritilgan harakatlar navbati
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                time TEXT,
                branch TEXT,
                doc_type TEXT,
                item_no INTEGER,
                item_name TEXT,
                barcode TEXT,
                quantity REAL,
                cashier TEXT,
                comment TEXT,
                is_synced INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tugagan taomlar hisobi (keyingi zakazni oshirish uchun)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS finished_dishes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                branch TEXT,
                item_name TEXT,
                is_processed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()
    print("✅ SQLite lokal ma'lumotlar bazasi tayyor.")


# ====================================================
# 2. TRANZAKSIYALARNI QABUL QILISH VA SAQLASH
# ====================================================
async def add_transaction(branch: str, doc_type: str, item_name: str, quantity: float,
                          item_no: int = 0, barcode: str = "", cashier: str = "", comment: str = ""):
    """Yangi tranzaksiyani lokal bazaga saqlash"""
    now = datetime.now()
    cur_date = now.strftime("%d.%m.%Y")
    cur_time = now.strftime("%H:%M:%S")

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO transactions (date, time, branch, doc_type, item_no, item_name, barcode, quantity, cashier, comment, is_synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (cur_date, cur_time, branch, doc_type, item_no, item_name, barcode, quantity, cashier, comment))
        await db.commit()


async def save_finished_dish(branch: str, item_name: str):
    """Smenada tugagan taomni belgilash"""
    cur_date = datetime.now().strftime("%d.%m.%Y")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO finished_dishes (date, branch, item_name)
            VALUES (?, ?, ?)
        """, (cur_date, branch, item_name))
        await db.commit()


# ====================================================
# 3. GOOGLE SHEETS BILAN ASINXRON SINXRONIZATSIYA
# ====================================================
async def sync_pending_transactions():
    """Sinxronizatsiya qilinmagan qatorlarni Google Sheets'ga uzatish"""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM transactions 
            WHERE is_synced = 0 
            ORDER BY id ASC 
            LIMIT ?
        """, (config.SYNC_BATCH_SIZE,))
        rows = await cursor.fetchall()

        if not rows:
            return 0

        # Google Sheets'ga uzatish uchun qatorlarni yig'ish
        sheet_rows = []
        synced_ids = []
        live_updates = []  # (branch, item_name, new_qty)

        for row in rows:
            sheet_rows.append([
                row["date"],
                row["time"],
                row["branch"],
                row["doc_type"],
                row["item_no"],
                row["item_name"],
                row["barcode"],
                row["quantity"],
                row["cashier"],
                row["comment"]
            ])
            synced_ids.append(row["id"])

            # Agar bu ertalabki yoki kechki qoldiq bo'lsa, Остатки_Live ni ham yangilash
            if row["doc_type"] in [config.DOC_TYPES["MORNING_STOCK"], config.DOC_TYPES["EVENING_STOCK"]]:
                live_updates.append((row["branch"], row["item_name"], row["quantity"]))

        # 1. 'Транзакции' varag'iga yangi qatorlarni qo'shish
        loop = asyncio.get_running_loop()
        sh = await loop.run_in_executor(None, get_spreadsheet)
        tx_sheet = await loop.run_in_executor(None, sh.worksheet, config.SHEET_MASTER_LOG)
        await loop.run_in_executor(None, tx_sheet.append_rows, sheet_rows)

        # 2. 'Остатки_Live' varag'ini yangilash
        if live_updates:
            await _update_live_stock_batch(sh, live_updates)

        # 3. Lokal bazada sinxronizatsiya qilinganini belgilash
        placeholders = ",".join("?" for _ in synced_ids)
        await db.execute(f"UPDATE transactions SET is_synced = 1 WHERE id IN ({placeholders})", synced_ids)
        await db.commit()

        return len(synced_ids)


async def _update_live_stock_batch(spreadsheet, updates):
    """Остатки_Live varag'idagi filial ustunlaridagi qoldiqlarni yangilash"""
    loop = asyncio.get_running_loop()
    live_sheet = await loop.run_in_executor(None, spreadsheet.worksheet, config.SHEET_LIVE_STOCK)
    
    # Bir marta butun jadvalni o'qib olish (API so'rovlarini kamaytirish uchun)
    all_values = await loop.run_in_executor(None, live_sheet.get_all_values)
    if not all_values:
        return

    headers = [h.strip().upper() for h in all_values[0]]
    # Mahsulot nomi qaysi qatorda ekanini topish (2-qatordan boshlab)
    item_row_map = {row[1].strip().lower(): idx + 1 for idx, row in enumerate(all_values) if len(row) > 1}

    cells_to_update = []
    for branch, item_name, qty in updates:
        branch_key = branch.strip().upper()
        if branch_key in headers and item_name.strip().lower() in item_row_map:
            col_idx = headers.index(branch_key) + 1
            row_idx = item_row_map[item_name.strip().lower()]
            cells_to_update.append(gspread.Cell(row=row_idx, col=col_idx, value=qty))

    if cells_to_update:
        await loop.run_in_executor(None, live_sheet.update_cells, cells_to_update)


# ====================================================
# 4. SVERKA / ANALITIKA (NEDOSTACHA VA IZLISHKA)
# ====================================================
async def calculate_reconciliation(branch: str, days: int = 1):
    """
    Belgilangan filial va davr uchun kamomad/ortiqchalikni hisoblash:
    Farq = Haqiqiy kechki qoldiq - (Boshlang'ich qoldiq + Kirim - Rasxod - Spisaniye)
    """
    start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%d.%m.%Y")
    
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Barcha tegishli harakatlarni olish
        cursor = await db.execute("""
            SELECT item_name, doc_type, SUM(quantity) as total_qty
            FROM transactions
            WHERE branch = ? AND date >= ?
            GROUP BY item_name, doc_type
        """, (branch, start_date))
        rows = await cursor.fetchall()

    data_by_item = {}
    for r in rows:
        item = r["item_name"]
        if item not in data_by_item:
            data_by_item[item] = {
                "morning": 0.0,
                "income": 0.0,
                "expense": 0.0,
                "write_off": 0.0,
                "evening": 0.0
            }
        
        dt = r["doc_type"]
        qty = r["total_qty"]
        if dt == config.DOC_TYPES["MORNING_STOCK"]:
            data_by_item[item]["morning"] += qty
        elif dt == config.DOC_TYPES["INCOME"]:
            data_by_item[item]["income"] += qty
        elif dt == config.DOC_TYPES["EXPENSE_DISHES"]:
            data_by_item[item]["expense"] += qty
        elif dt == config.DOC_TYPES["WRITE_OFF"]:
            data_by_item[item]["write_off"] += qty
        elif dt == config.DOC_TYPES["EVENING_STOCK"]:
            data_by_item[item]["evening"] += qty

    results = []
    for item, val in data_by_item.items():
        expected = val["morning"] + val["income"] - val["expense"] - val["write_off"]
        actual = val["evening"]
        diff = actual - expected

        status = "NORMA"
        if diff < 0:
            status = "NEDOSTACHA"
        elif diff > 0:
            status = "IZLISHKA"

        results.append({
            "item_name": item,
            "morning": val["morning"],
            "income": val["income"],
            "expense": val["expense"],
            "write_off": val["write_off"],
            "expected": expected,
            "actual": actual,
            "diff": diff,
            "status": status
        })

    return results


# ====================================================
# 5. ESKI MA'LUMOTLARNI TOZALASH (90 KUN)
# ====================================================
async def purge_old_records():
    """90 kundan oshgan sinxronizatsiya bo'lgan ma'lumotlarni o'chirish"""
    cutoff_date = (datetime.now() - timedelta(days=config.DATA_RETENTION_DAYS)).strftime("%d.%m.%Y")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            DELETE FROM transactions 
            WHERE is_synced = 1 AND date < ?
        """, (cutoff_date,))
        await db.commit()