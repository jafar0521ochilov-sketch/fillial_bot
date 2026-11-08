"""
setup_sheets.py - 10.10.26.xlsx faylidagi real ma'lumotlar asosida barcha 13 ta filial
va Остатки_Live jadvalini Google Sheets'da 0 dan mukammal sozlash va to'ldirish.
"""

import gspread
from google.oauth2.service_account import Credentials
import os
import json
import time
import pandas as pd
import config

def main():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = None
    
    secret_path = "/etc/secrets/credentials.json"
    if os.path.exists(secret_path):
        creds = Credentials.from_service_account_file(secret_path, scopes=scopes)
    elif os.getenv("GOOGLE_CREDENTIALS_JSON"):
        creds_info = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    elif os.path.exists(config.SERVICE_ACCOUNT_PATH):
        creds = Credentials.from_service_account_file(config.SERVICE_ACCOUNT_PATH, scopes=scopes)
    else:
        print("❌ Xatolik: Google credentials ma'lumotlari topilmadi!")
        return

    client = gspread.authorize(creds)
    sh = client.open_by_key(config.GOOGLE_SHEET_KEY)
    
    existing_sheets = [w.title for w in sh.worksheets()]
    all_branches = list(config.BRANCH_ORDER_SHEETS.keys())
    
    print(f"🚀 Jami filiallar soni: {len(all_branches)} ta. 10.10.26.xlsx faylidan ma'lumotlar o'qilmoqda...")
    
    # 1. 10.10.26.xlsx faylidan ma'lumotlarni o'qib olamiz
    excel_path = "10.10.26.xlsx"
    if not os.path.exists(excel_path):
        print(f"❌ Xatolik: {excel_path} fayli topilmadi!")
        return
        
    xls = pd.ExcelFile(excel_path)
    df = pd.read_excel(xls, sheet_name='Лист1', header=3)
    
    # Mahsulotlarni yig'amiz: №, Наименование, Штрих-код
    products = []
    for _, row in df.iterrows():
        item_no = row.get('№')
        item_name = row.get('Наименование')
        item_barcode = row.get('Штрих-код')
        
        if pd.notna(item_no) and pd.notna(item_name):
            # Штрих-код ni to'g'ri matn formatiga keltiramiz
            barcode_str = str(item_barcode).strip()
            if barcode_str.endswith('.0'):
                barcode_str = barcode_str[:-2]
            if barcode_str == 'nan':
                barcode_str = ''
                
            products.append([str(int(item_no) if isinstance(item_no, float) and item_no.is_integer() else item_no), 
                             str(item_name).strip(), 
                             barcode_str])

    print(f"✅ Excel'dan jami {len(products)} ta mahsulot muvaffaqiyatli o'qildi!")
    time.sleep(1)

    # 2. Har bir filial uchun Zakaz va Tranzaksiya varaqlarini yaratish
    for b in all_branches:
        order_sheet_name = config.BRANCH_ORDER_SHEETS[b]
        
        # Zakaz varag'i
        if order_sheet_name in existing_sheets:
            ws = sh.worksheet(order_sheet_name)
            ws.clear()
        else:
            ws = sh.add_worksheet(title=order_sheet_name, rows=150, cols=10)
        
        time.sleep(0.8)
        
        # Sarlavha va mahsulotlarni tayyorlaymiz
        updates = [
            {"range": "A1", "values": [[f"ЗАКАЗ ДЛЯ ФАБРИКИ — ФИЛИАЛ: {b.upper()}"]]},
            {"range": "A2", "values": [["Дата поставки:", "[Укажите дату]"]]}
        ]
        
        product_rows = [[p[0], p[1], p[2], ""] for p in products]
        headers_row = [["№", "Наименование", "Штрих-код", "Заказ (Количество)"]]
        updates.append({"range": "A4", "values": headers_row + product_rows})

        ws.batch_update(updates)
        print(f"✅ {order_sheet_name} tayyorlandi.")
        time.sleep(0.8)
            
        # Tranzaksiya varag'i
        tx_sheet_name = f"Транзакции_{b}"
        headers = [["Дата", "Время", "Филиал", "Тип документа", "№", "Наименование", "Штрих-код", "Количество", "Кассир", "Примечание"]]
        
        if tx_sheet_name in existing_sheets:
            tx_ws = sh.worksheet(tx_sheet_name)
            if not tx_ws.get_all_values():
                tx_ws.update(range_name="A1", values=headers)
        else:
            tx_ws = sh.add_worksheet(title=tx_sheet_name, rows=100, cols=10)
            time.sleep(0.8)
            tx_ws.update(range_name="A1", values=headers)
            
        print(f"✅ {tx_sheet_name} tayyorlandi.")
        time.sleep(1)

    # 3. Остатки_Live varag'ini noldan shakllantirish va barcha 13 ta filial ustunlarini qo'shish
    print("🔄 Остатки_Live varag'i yangilanmoqda...")
    live_sheet_name = getattr(config, "SHEET_LIVE_STOCK", "Остатки_Live")
    
    live_headers = ["№", "Наименование", "Штрих-код"] + all_branches
    rows_to_insert = [live_headers]
    
    for p in products:
        branch_zeros = [0] * len(all_branches)
        rows_to_insert.append([p[0], p[1], p[2]] + branch_zeros)

    existing_sheets_updated = [w.title for w in sh.worksheets()]
    if live_sheet_name in existing_sheets_updated:
        live_ws = sh.worksheet(live_sheet_name)
        live_ws.clear()
    else:
        live_ws = sh.add_worksheet(title=live_sheet_name, rows=len(rows_to_insert) + 20, cols=len(live_headers) + 5)

    time.sleep(1)
    if len(rows_to_insert) > 1:
        live_ws.update(range_name="A1", values=rows_to_insert)
        print(f"✨ Остатки_Live muvaffaqiyatli yaratildi! Jami mahsulotlar: {len(rows_to_insert)-1} ta, Filiallar: {len(all_branches)} ta.")
    else:
        print("⚠️ Diqqat: Mahsulotlar topilmadi.")
        
    print("🎉 Barcha jarayonlar muvaffaqiyatli yakunlandi!")

if __name__ == "__main__":
    main()