"""
sheets_database.py - Mazzali Inventory, Sverka & Order Management System
Yangilangan modul: Local Excel fallback funksiyasi qo'shildi.
"""

import asyncio
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import aiosqlite
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

import config

_gspread_client = None
_spreadsheet = None


def get_spreadsheet():
    global _gspread_client, _spreadsheet
    if _spreadsheet is None:
        scopes = getattr(config, "SCOPES", ["https://www.googleapis.com/auth/spreadsheets"])
        creds = None
        
        secret_path = "/etc/secrets/credentials.json"
        if os.path.exists(secret_path):
            creds = Credentials.from_service_account_file(secret_path, scopes=scopes)
        elif os.getenv("GOOGLE_CREDENTIALS_JSON"):
            credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
            creds_info = json.loads(credentials_json)
            creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        elif os.path.exists(config.SERVICE_ACCOUNT_PATH):
            creds = Credentials.from_service_account_file(
                config.SERVICE_ACCOUNT_PATH, scopes=scopes
            )
        else:
            raise FileNotFoundError("❌ Xatolik: Google credentials ma'lumotlari topilmadi!")
        
        _gspread_client = gspread.authorize(creds)
        _spreadsheet = _gspread_client.open_by_key(config.GOOGLE_SHEET_KEY)
    return _spreadsheet


def get_current_shift_info(dt: datetime = None) -> tuple:
    if dt is None:
        dt = datetime.now()
    
    current_time = dt.time()
    morning_start = datetime.strptime("08:00:00", "%H:%M:%S").time()
    evening_start = datetime.strptime("20:00:00", "%H:%M:%S").time()

    if morning_start <= current_time < evening_start:
        shift_type = "DAY"
        shift_date = dt.strftime("%d.%m.%Y")
    else:
        shift_type = "NIGHT"
        if current_time < morning_start:
            shift_date = (dt - timedelta(days=1)).strftime("%d.%m.%Y")
        else:
            shift_date = dt.strftime("%d.%m.%Y")
            
    return shift_date, shift_type


async def init_db():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS branch_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                time TEXT,
                shift_date TEXT,
                shift_type TEXT,
                branch TEXT,
                doc_type TEXT,
                item_no TEXT,
                item_name TEXT,
                barcode TEXT,
                quantity REAL,
                cashier TEXT,
                comment TEXT,
                is_synced INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS shift_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                time TEXT,
                shift_date TEXT,
                shift_type TEXT,
                branch TEXT,
                item_name TEXT,
                total_counter_val REAL,
                cashier TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS shift_reconciliations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shift_date TEXT,
                shift_type TEXT,
                branch TEXT,
                item_name TEXT,
                start_stock REAL,
                prikxod REAL,
                transfer_in REAL,
                transfer_out REAL,
                shift_consumption REAL,
                calculated_stock REAL,
                factual_stock REAL,
                difference REAL,
                status TEXT,
                cashier TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

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
    print("✅ SQLite локальная база данных успешно инициализирована под новое ТЗ.")


async def add_branch_transaction(branch: str, doc_type: str, item_name: str, quantity: float,
                                 item_no: str = "", barcode: str = "", cashier: str = "", comment: str = ""):
    now = datetime.now()
    cur_date = now.strftime("%d.%m.%Y")
    cur_time = now.strftime("%H:%M:%S")
    shift_date, shift_type = get_current_shift_info(now)

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            INSERT INTO branch_transactions 
            (date, time, shift_date, shift_type, branch, doc_type, item_no, item_name, barcode, quantity, cashier, comment, is_synced)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (cur_date, cur_time, shift_date, shift_type, branch, doc_type, str(item_no), item_name, barcode, quantity, cashier, comment))
        await db.commit()


async def add_transfer_transaction(from_branch: str, to_branch: str, item_name: str, quantity: float, cashier: str = ""):
    comment_out = f"Transfer Out -> {to_branch}"
    await add_branch_transaction(
        branch=from_branch,
        doc_type=config.DOC_TYPES.get("TRANSFER_OUT", "Перемещение (Выбытие)"),
        item_name=item_name,
        quantity=abs(quantity),
        cashier=cashier,
        comment=comment_out
    )

    comment_in = f"Transfer In <- {from_branch}"
    await add_branch_transaction(
        branch=to_branch,
        doc_type=config.DOC_TYPES.get("TRANSFER_IN", "Перемещение (Поступление)"),
        item_name=item_name,
        quantity=abs(quantity),
        cashier=cashier,
        comment=comment_in
    )


async def record_shift_snapshot_and_reconcile(branch: str, cashier: str, items_factual: dict, current_counters: dict):
    now = datetime.now()
    cur_date = now.strftime("%d.%m.%Y")
    cur_time = now.strftime("%H:%M:%S")
    shift_date, shift_type = get_current_shift_info(now)

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        for item_name, counter_val in current_counters.items():
            await db.execute("""
                INSERT INTO shift_snapshots (date, time, shift_date, shift_type, branch, item_name, total_counter_val, cashier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (cur_date, cur_time, shift_date, shift_type, branch, item_name, counter_val, cashier))

            cursor = await db.execute("""
                SELECT total_counter_val FROM shift_snapshots
                WHERE branch = ? AND item_name = ?
                ORDER BY id DESC LIMIT 1 OFFSET 1
            """, (branch, item_name))
            prev_row = await cursor.fetchone()
            
            prev_counter_val = prev_row["total_counter_val"] if prev_row else counter_val
            shift_consumption = max(0.0, counter_val - prev_counter_val)

            cursor_start = await db.execute("""
                SELECT quantity FROM branch_transactions
                WHERE branch = ? AND item_name = ? AND doc_type IN ('Утренний остаток', 'Вечерний остаток')
                ORDER BY id DESC LIMIT 1
            """, (branch, item_name))
            start_row = await cursor_start.fetchone()
            start_stock = start_row["quantity"] if start_row else 0.0

            cursor_in = await db.execute("""
                SELECT SUM(quantity) as total FROM branch_transactions
                WHERE branch = ? AND item_name = ? AND shift_date = ? AND shift_type = ? AND doc_type = 'Приход'
            """, (branch, item_name, shift_date, shift_type))
            in_row = await cursor_in.fetchone()
            prikxod = in_row["total"] or 0.0

            cursor_tin = await db.execute("""
                SELECT SUM(quantity) as total FROM branch_transactions
                WHERE branch = ? AND item_name = ? AND shift_date = ? AND shift_type = ? AND doc_type = 'Перемещение (Поступление)'
            """, (branch, item_name, shift_date, shift_type))
            tin_row = await cursor_tin.fetchone()
            transfer_in = tin_row["total"] or 0.0

            cursor_tout = await db.execute("""
                SELECT SUM(quantity) as total FROM branch_transactions
                WHERE branch = ? AND item_name = ? AND shift_date = ? AND shift_type = ? AND doc_type = 'Перемещение (Выбытие)'
            """, (branch, item_name, shift_date, shift_type))
            tout_row = await cursor_tout.fetchone()
            transfer_out = tout_row["total"] or 0.0

            calculated_stock = start_stock + prikxod + transfer_in - shift_consumption - transfer_out
            factual_stock = items_factual.get(item_name, 0.0)
            difference = factual_stock - calculated_stock

            if difference < 0:
                status = "NEDOSTACHA"
            elif difference > 0:
                status = "IZLISHKA"
            else:
                status = "OK"

            await db.execute("""
                INSERT INTO shift_reconciliations 
                (shift_date, shift_type, branch, item_name, start_stock, prikxod, transfer_in, transfer_out, 
                 shift_consumption, calculated_stock, factual_stock, difference, status, cashier)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (shift_date, shift_type, branch, item_name, start_stock, prikxod, transfer_in, transfer_out,
                  shift_consumption, calculated_stock, factual_stock, difference, status, cashier))

            doc_type_stock = "Вечерний остаток" if shift_type == "DAY" else "Утренний остаток"
            await db.execute("""
                INSERT INTO branch_transactions 
                (date, time, shift_date, shift_type, branch, doc_type, item_name, quantity, cashier, is_synced)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (cur_date, cur_time, shift_date, shift_type, branch, doc_type_stock, item_name, factual_stock, cashier))

        await db.commit()


async def save_factory_orders_to_sheet(branch: str, orders: dict):
    target_sheet = f"Заказ_{branch}"
    
    loop = asyncio.get_running_loop()
    sh = await loop.run_in_executor(None, get_spreadsheet)
    worksheet_list = await loop.run_in_executor(None, sh.worksheets)
    sheet_names = [w.title for w in worksheet_list]

    if target_sheet not in sheet_names:
        print(f"⚠️ Лист {target_sheet} не найден в Google Sheets")
        return False

    ws = await loop.run_in_executor(None, sh.worksheet, target_sheet)
    all_vals = await loop.run_in_executor(None, ws.get_all_values)
    if not all_vals:
        return False

    item_row_map = {row[1].strip().lower(): idx + 1 for idx, row in enumerate(all_vals) if len(row) > 1}
    cur_date = datetime.now().strftime("%d.%m.%Y")

    cells_to_update = []
    for item_name, qty in orders.items():
        key = item_name.strip().lower()
        if key in item_row_map and qty > 0:
            row_idx = item_row_map[key]
            cells_to_update.append(gspread.Cell(row=row_idx, col=4, value=qty))  
            cells_to_update.append(gspread.Cell(row=row_idx, col=5, value=cur_date)) 

    if cells_to_update:
        await loop.run_in_executor(None, ws.update_cells, cells_to_update)
        return True
    return False


async def sync_pending_transactions():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM branch_transactions 
            WHERE is_synced = 0 
            ORDER BY id ASC 
            LIMIT ?
        """, (getattr(config, "SYNC_BATCH_SIZE", 50),))
        rows = await cursor.fetchall()

        if not rows:
            return 0

        sheet_rows = []
        synced_ids = []

        for row in rows:
            sheet_rows.append([
                str(row["date"] or ""),
                str(row["time"] or ""),
                str(row["shift_date"] or ""),
                str(row["shift_type"] or ""),
                str(row["branch"] or ""),
                str(row["doc_type"] or ""),
                str(row["item_no"] or ""),
                str(row["item_name"] or ""),
                str(row["barcode"] or ""),
                float(row["quantity"] or 0.0),
                str(row["cashier"] or ""),
                str(row["comment"] or "")
            ])
            synced_ids.append(row["id"])

        try:
            loop = asyncio.get_running_loop()
            sh = await loop.run_in_executor(None, get_spreadsheet)
            worksheet_list = await loop.run_in_executor(None, sh.worksheets)
            sheet_names = [w.title for w in worksheet_list]
            
            target_sheet = getattr(config, "SHEET_MASTER_LOG", "Транзакции")
            if target_sheet not in sheet_names:
                target_sheet = sheet_names[0]

            tx_sheet = await loop.run_in_executor(None, sh.worksheet, target_sheet)
            await loop.run_in_executor(None, tx_sheet.append_rows, sheet_rows)

            placeholders = ",".join("?" for _ in synced_ids)
            await db.execute(f"UPDATE branch_transactions SET is_synced = 1 WHERE id IN ({placeholders})", synced_ids)
            await db.commit()

            return len(synced_ids)

        except Exception as e:
            print(f"❌ Xatolik Google Sheets sinxronizatsiyasida: {e}")
            return 0


async def purge_old_records():
    retention_days = getattr(config, "DATA_RETENTION_DAYS", 90)
    cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime("%d.%m.%Y")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            DELETE FROM branch_transactions 
            WHERE is_synced = 1 AND date < ?
        """, (cutoff_date,))
        await db.commit()
    print("🧹 Eski sinxronizatsiya qilingan yozuvlar tozalandi.")


async def upload_excel_to_sheet(file_path: str, sheet_name: str = "Лист1"):
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        df = df.fillna("")
        
        loop = asyncio.get_running_loop()
        sh = await loop.run_in_executor(None, get_spreadsheet)
        
        worksheet_list = await loop.run_in_executor(None, sh.worksheets)
        sheet_names = [w.title for w in worksheet_list]
        
        if sheet_name not in sheet_names:
            ws = await loop.run_in_executor(None, sh.add_worksheet, sheet_name, len(df)+10, len(df.columns)+5)
        else:
            ws = await loop.run_in_executor(None, sh.worksheet, sheet_name)
            
        data_to_update = [df.columns.values.tolist()] + df.values.tolist()
        
        await loop.run_in_executor(None, ws.clear)
        await loop.run_in_executor(None, ws.update, data_to_update)
        
        print(f"✅ '{file_path}' faylidagi ma'lumotlar Google Sheets'ga muvaffaqiyatli yuklandi!")
        return True
    except Exception as e:
        print(f"❌ Excel faylni Google Sheets'ga yuklashda xatolik: {e}")
        return False


def get_dishes_from_local_excel(file_path: str = "10.10.26.xlsx") -> list[dict]:
    """
    Zaxiradagi local Excel faylidan mahsulotlar ro'yxatini o'qib qaytaradi.
    """
    try:
        if not os.path.exists(file_path):
            return []
        
        df = pd.read_excel(file_path, sheet_name="Лист1")
        dishes = []
        for idx, row in df.iterrows():
            if idx < 3:  # Sarlavha qatorlarini o'tkazib yuborish
                continue
            if len(row) > 2:
                item_no = str(row.iloc[1]) if pd.notna(row.iloc[1]) else ""
                name = str(row.iloc[2]) if pd.notna(row.iloc[2]) else ""
                barcode = str(row.iloc[3]) if pd.notna(row.iloc[3]) else ""
                
                if name and name.strip() and name.strip() != "nan":
                    dishes.append({
                        "no": item_no.strip(),
                        "name": name.strip(),
                        "barcode": barcode.strip() if barcode != "nan" else ""
                    })
        return dishes
    except Exception as e:
        print(f"❌ Local Excel faylini o'qishda xatolik: {e}")
        return []