"""
main.py - Mazzali Telegram Mini App & Bot
Обновлённый модуль: FastAPI веб-сервер + Aiogram 3 бот + Планировщик уведомлений + AI Yordamchi va Rasm handler'lari
"""

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

import config
import sheets_database as db
import gemini_ocr as ocr

app = FastAPI(title="Mazzali Mini App")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://fillial-bot.onrender.com")
WEBAPP_URL = RENDER_EXTERNAL_URL


# ====================================================
# 1. AIOGRAM BOT HANDLERLARI (START, MENU VA TUGMALAR)
# ====================================================

# Asosiy doimiy pastki klaviatura (ReplyKeyboardMarkup)
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Сверка / Недостача"), KeyboardButton(text="📈 Живые остатки (Live)")],
        [KeyboardButton(text="🤖 Gemini AI Yordamchi"), KeyboardButton(text="🧹 Bazani tozalash")],
        [KeyboardButton(text="📱 Mazzali Mini App'ni ochish")]
    ],
    resize_keyboard=True
)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Mini App'ni ochish", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        "Assalomu alaykum! Mazzali filial boshqaruv tizimiga xush kelibsiz.\n\n"
        "Quyidagi tugma orqali Mini App'ni ochib, smena topshirish, sverka qilish yoki fabrikaga zakaz berishingiz mumkin:",
        reply_markup=main_kb
    )

# Pastdagi matnli tugmalar uchun handlerlar
@dp.message(F.text == "📊 Сверка / Недостача")
async def cmd_sverka(message: types.Message):
    await message.answer("📊 Sverka va nedostacha bo'limi tez orada ishga tushadi yoki Mini App orqali amalga oshiriladi.", reply_markup=main_kb)

@dp.message(F.text == "📈 Живые остатки (Live)")
async def cmd_live(message: types.Message):
    await message.answer("📈 Jonli qoldiqlar (Live) ma'lumotlari yuklanmoqda...", reply_markup=main_kb)

@dp.message(F.text == "🤖 Gemini AI Yordamchi")
async def cmd_ai(message: types.Message):
    await message.answer("🤖 Menga savolingizni yuboring, filiallar bo'yicha ma'lumot topishga yordam beraman.", reply_markup=main_kb)

@dp.message(F.text == "🧹 Bazani tozalash")
async def cmd_clear(message: types.Message):
    await message.answer("🧹 Bazani tozalash amaliyoti faqat adminlar uchun.", reply_markup=main_kb)

@dp.message(F.text == "📱 Mazzali Mini App'ni ochish")
async def cmd_open_webapp(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Mini App'ni ochish", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer("Mini App'ni ochish uchun quyidagi tugmani bosing:", reply_markup=kb)


# Telegram botga rasm tashlanganda ishlaydigan handler
@dp.message(F.photo)
async def handle_photo_messages(message: types.Message):
    await message.answer("⏳ Rasm qabul qilindi, Gemini va Excel orqali tahlil qilinmoqda...")
    
    try:
        # Telegramdan rasmni yuklab olish
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        file_bytes_io = await bot.download_file(file_info.file_path)
        image_bytes = file_bytes_io.read()
        
        # OCR orqali tahlil qilish (yoki Excel fallback'ga o'tish)
        items = ocr.parse_receipt_photo(image_bytes, branch_name="", valid_menu_items=None)
        
        if items:
            text = "✅ **Muvaffaqiyatli aniqlandi:**\n\n"
            for it in items[:20]:  # Xabar uzun bo'lib ketmasligi uchun
                text += f"• {it.get('item_name')}: <b>{it.get('quantity')}</b>\n"
            if len(items) > 20:
                text += f"\n... va yana {len(items) - 20} ta mahsulot."
            await message.answer(text, reply_markup=main_kb, parse_mode="HTML")
        else:
            await message.answer("⚠️ Rasmdan ma'lumot o'qib bo'lmadi, lekin Excel fallback (zaxira) orqali Google Sheets'ga yuborildi.", reply_markup=main_kb)
            
    except Exception as e:
        print(f"❌ Rasmni qayta ishlashda xatolik: {e}")
        await message.answer("❌ Rasmni qayta ishlashda xatolik yuz berdi.", reply_markup=main_kb)


# Har qanday boshqa matnli xabarlarni Gemini AI orqali qayta ishlash (AI Yordamchi)
@dp.message(F.text)
async def handle_text_messages(message: types.Message):
    # Agar maxsus tugmalar bosilgan bo'lsa, ularni o'tkazib yuborish
    if message.text in ["📊 Сверка / Недостача", "📈 Живые остатки (Live)", "🤖 Gemini AI Yordamchi", "🧹 Bazani tozalash", "📱 Mazzali Mini App'ni ochish"]:
        return
    
    await message.answer("⏳ Gemini AI javob tayyorlamoqda...")
    ai_response = ocr.ask_gemini_agent(message.text, context_data="Mazzali restoran va ombor tizimi.")
    await message.answer(ai_response, reply_markup=main_kb)


# ====================================================
# 2. MONITORING VA ASOSIY SAHIFA
# ====================================================
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Mazzali Bot"}


@app.get("/")
async def serve_mini_app(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


# ====================================================
# 3. REST API ENDPOINTLARI
# ====================================================
@app.get("/api/dishes")
async def get_dishes_list():
    try:
        loop = asyncio.get_running_loop()
        sh = await loop.run_in_executor(None, db.get_spreadsheet)
        worksheet_list = await loop.run_in_executor(None, sh.worksheets)
        sheet_names = [w.title for w in worksheet_list]

        target_sheet_name = "Заказ_Шота" if "Заказ_Шота" in sheet_names else ("Лист1" if "Лист1" in sheet_names else sheet_names[0])
        sheet = await loop.run_in_executor(None, sh.worksheet, target_sheet_name)
        rows = await loop.run_in_executor(None, sheet.get_all_values)

        dishes = []
        for r in rows[1:]:
            if len(r) >= 2 and r[1].strip() and r[1].strip() != "Наименование":
                dishes.append({
                    "no": r[0].strip() if len(r) > 0 else "",
                    "name": r[1].strip(),
                    "barcode": r[2].strip() if len(r) > 2 else ""
                })
        if dishes:
            return dishes
    except Exception as e:
        print(f"⚠️ Google Sheets'dan taomlarni yuklashda xatolik: {e}")

    return db.get_dishes_from_local_excel()


class SubmitItemsRequest(BaseModel):
    branch: str
    doc_type: str
    items: dict


@app.post("/api/submit_items")
async def api_submit_items(req: SubmitItemsRequest):
    for item_name, qty in req.items.items():
        if qty > 0:
            await db.add_branch_transaction(
                branch=req.branch,
                doc_type=req.doc_type,
                item_name=item_name,
                quantity=qty,
                comment="Mini App orqali kiritildi"
            )
    asyncio.create_task(db.sync_pending_transactions())
    return {"status": "ok"}


class SubmitTransferRequest(BaseModel):
    from_branch: str
    to_branch: str
    items: dict


@app.post("/api/submit_transfer")
async def api_submit_transfer(req: SubmitTransferRequest):
    for item_name, qty in req.items.items():
        if qty > 0:
            await db.add_transfer_transaction(
                from_branch=req.from_branch,
                to_branch=req.to_branch,
                item_name=item_name,
                quantity=qty
            )
    asyncio.create_task(db.sync_pending_transactions())
    return {"status": "ok"}


class SubmitFactoryOrderRequest(BaseModel):
    branch: str
    items: dict


@app.post("/api/submit_factory_order")
async def api_submit_factory_order(req: SubmitFactoryOrderRequest):
    success = await db.save_factory_orders_to_sheet(req.branch, req.items)
    for item_name, qty in req.items.items():
        if qty > 0:
            await db.add_branch_transaction(
                branch=req.branch,
                doc_type="Заказ Fabrika",
                item_name=item_name,
                quantity=qty,
                comment="Fabrika zakazi"
            )
    asyncio.create_task(db.sync_pending_transactions())
    return {"status": "ok" if success else "sheet_not_found"}


class ShiftCloseRequest(BaseModel):
    branch: str
    cashier: str
    factual_items: dict
    current_counters: dict


@app.post("/api/close_shift_reconcile")
async def api_close_shift_reconcile(req: ShiftCloseRequest):
    """Smena topshirish, snapshot yozish va nedostacha/izlishka hisoblash"""
    try:
        await db.record_shift_snapshot_and_reconcile(
            branch=req.branch,
            cashier=req.cashier,
            items_factual=req.factual_items,
            current_counters=req.current_counters
        )
        asyncio.create_task(db.sync_pending_transactions())
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/parse_photo")
async def api_parse_photo(branch: str = Form(...), doc_type: str = Form(...), photo: UploadFile = File(...)):
    image_bytes = await photo.read()
    loop = asyncio.get_running_loop()
    valid_menu = []
    
    try:
        sh = await loop.run_in_executor(None, db.get_spreadsheet)
        shota_sheet = await loop.run_in_executor(None, sh.worksheet, "Заказ_Шота")
        rows = await loop.run_in_executor(None, shota_sheet.get_all_values)
        valid_menu = [r[1].strip() for r in rows[1:] if len(r) >= 2 and r[1].strip()]
    except Exception as e:
        print(f"⚠️ Menyu ro'yxatini yuklashda xatolik: {e}")

    if doc_type == "Закончившиеся блюда" or doc_type == "FINISHED_DISHES":
        finished_list = ocr.parse_finished_dishes_photo(image_bytes, valid_menu_items=valid_menu)
        items = [{"item_name": name, "quantity": 1.0} for name in finished_list]
    else:
        items = ocr.parse_receipt_photo(image_bytes, branch_name=branch, valid_menu_items=valid_menu)

    return {"status": "ok", "items": items}


# ====================================================
# 4. SERVER VA BOTni BIRGALIKDA ISHGA TUSHIRISH
# ====================================================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    
    port = int(os.environ.get("PORT", 10000))
    config_uvicorn = uvicorn.Config("main:app", host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config_uvicorn)
    
    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())