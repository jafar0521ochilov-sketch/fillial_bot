"""
main.py - Mazzali Telegram Mini App & Bot
5-Modul: FastAPI veb-serveri + Aiogram 3 bot + Gemini OCR + 24/7 sinxronizator
"""

import asyncio
import os
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

import config
import sheets_database as db
import gemini_ocr as ocr

app = FastAPI(title="Mazzali Mini App")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# Render'dagi doimiy domen yoki muhit o'zgaruvchisidan olish
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "https://fillial-bot.onrender.com")
WEBAPP_URL = RENDER_EXTERNAL_URL

# ====================================================
# 1. 24/7 MONITORING VA ASOSIY SAHIFA
# ====================================================
@app.get("/health")
async def health_check():
    """cron-job.org orqali serverni 24/7 uyg'oq saqlash manzili"""
    return {"status": "ok", "service": "Mazzali Bot"}


@app.get("/")
async def serve_mini_app(request: Request):
    """Mini App bosh oynasi"""
    return templates.TemplateResponse(request, "index.html", {"request": request})


# ====================================================
# 2. REST API: TAOMLARNI YUKLASH VA QABUL QILISH
# ====================================================
@app.get("/api/dishes")
async def get_dishes_list():
    """Google Sheets'dan 135 ta taom va shtrix-kodlarni yuklab berish"""
    try:
        loop = asyncio.get_running_loop()
        sh = await loop.run_in_executor(None, db.get_spreadsheet)
        shota_sheet = await loop.run_in_executor(None, sh.worksheet, "Заказ_Шота")
        rows = await loop.run_in_executor(None, shota_sheet.get_all_values)

        dishes = []
        for r in rows[1:]:
            if len(r) >= 2 and r[1].strip():
                barcode = r[2].strip() if len(r) > 2 else ""
                dishes.append({
                    "no": r[0].strip(),
                    "name": r[1].strip(),
                    "barcode": barcode
                })
        return dishes
    except Exception as e:
        print(f"⚠️ Taomlarni yuklashda xatolik: {e}")
        return []


class SubmitItemsRequest(BaseModel):
    branch: str
    doc_type: str
    items: dict  # {"Taom nomi": soni}


@app.post("/api/submit_items")
async def api_submit_items(req: SubmitItemsRequest):
    """Standart taomlar bo'yicha amallarni saqlash"""
    for item_name, qty in req.items.items():
        if qty > 0:
            await db.add_transaction(
                branch=req.branch,
                doc_type=req.doc_type,
                item_name=item_name,
                quantity=qty,
                comment="Mini App orqali kiritildi"
            )
    return {"status": "ok"}


class SubmitExtraRequest(BaseModel):
    branch: str
    text: str


@app.post("/api/submit_extra")
async def api_submit_extra(req: SubmitExtraRequest):
    """Qo'shimcha tovarlarni (matnli) tahlil qilib saqlash"""
    lines = req.text.strip().split("\n")
    for line in lines:
        if "-" in line:
            parts = line.split("-", 1)
            name = parts[0].strip()
            qty_part = parts[1].strip()
            try:
                qty = float(qty_part.split()[0].replace(",", "."))
            except (ValueError, IndexError):
                qty = 1.0

            await db.add_transaction(
                branch=req.branch,
                doc_type=config.DOC_TYPES["EXTRA_GOODS"],
                item_name=name,
                quantity=qty,
                comment="Qo'lda kiritildi"
            )
    return {"status": "ok"}


@app.post("/api/submit_photo")
async def api_submit_photo(branch: str = Form(...), doc_type: str = Form(...), photo: UploadFile = File(...)):
    """Nakladnoy yoki tugagan taomlar suratini Gemini orqali o'qish"""
    image_bytes = await photo.read()

    # 135 ta taom nomlarini bazadan olish
    loop = asyncio.get_running_loop()
    sh = await loop.run_in_executor(None, db.get_spreadsheet)
    shota_sheet = await loop.run_in_executor(None, sh.worksheet, "Заказ_Шота")
    rows = await loop.run_in_executor(None, shota_sheet.get_all_values)
    valid_menu = [r[1].strip() for r in rows[1:] if len(r) >= 2 and r[1].strip()]

    if doc_type == "Приход_Фото":
        # Nakladnoydagi taomlar va sonini aniqlash
        items = ocr.parse_receipt_photo(image_bytes, valid_menu_items=valid_menu)
        for it in items:
            name = it.get("item_name")
            qty = it.get("quantity", 0.0)
            if name and qty > 0:
                await db.add_transaction(
                    branch=branch,
                    doc_type=config.DOC_TYPES["INCOME"],
                    item_name=name,
                    quantity=qty,
                    comment="Gemini Vision (nakladnoy fotosi)"
                )
        return {"status": "ok", "items_count": len(items)}

    elif doc_type == "Закончившиеся блюда":
        # Smena davomida tugagan taomlar ro'yxatini aniqlash
        finished_list = ocr.parse_finished_dishes_photo(image_bytes, valid_menu_items=valid_menu)
        for dish_name in finished_list:
            await db.save_finished_dish(branch=branch, item_name=dish_name)
        return {"status": "ok", "finished_count": len(finished_list)}

    return {"status": "unknown_type"}


# ====================================================
# 3. TELEGRAM BOT HANDLERLARI
# ====================================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Kassir va rahbarlarga Mini App oynasini chiqarish"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Mazzali tizimini ochish", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        "👋 **Assalomu alaykum!**\n\n"
        "Mazzali filiallari hisob-kitob tizimiga xush kelibsiz.\n"
        "Qoldiq, kirim, umumiy rasxod va buyurtmalarni kiritish uchun pastdagi tugmani bosing:",
        reply_markup=kb,
        parse_mode="Markdown"
    )


# ====================================================
# 4. FONDAGI GOOGLE SHEETS SINXRONIZATORI
# ====================================================
async def sync_background_worker():
    """Lokal bazadagi navbatni doimiy Google Sheets'ga yuklash"""
    while True:
        try:
            count = await db.sync_pending_transactions()
            if count > 0:
                print(f"🔄 Google Sheets'ga {count} ta operatsiya uzatildi.")
        except Exception as e:
            print(f"⚠️ Sinxronizatsiya vaqtinchalik to'xtadi: {e}")
        await asyncio.sleep(config.SYNC_INTERVAL_SECONDS)


# ====================================================
# 5. SERVER VA BOTni ISHGA TUSHIRISH
# ====================================================
async def main():
    # 1. Lokal bazani tayyorlash
    await db.init_db()

    # 2. Sinxronizatorni orqa fonda yoqish
    asyncio.create_task(sync_background_worker())

    # 3. FastAPI veb-serverini ishga tushirish
    port = int(os.getenv("PORT", 8000))
    server_config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(server_config)
    asyncio.create_task(server.serve())

    print(f"🚀 FastAPI server {port}-portda ishga tushdi.")
    print("🤖 Telegram bot xabarlarni qabul qilishga tayyor...")

    # 4. Aiogram botini ishga tushirish
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())