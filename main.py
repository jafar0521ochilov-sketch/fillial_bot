"""
main.py - Mazzali Telegram Mini App & Bot (Webhook Rejimi)
Yangi operatsiyalar (Списание по сроку, Списание по порче, Общий расход блюд) bilan to'liq versiya
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
WEBAPP_URL = f"{RENDER_EXTERNAL_URL}/?v=7"

# ====================================================
# WEBHOOK SOZLAMALARI
# ====================================================
WEBHOOK_PATH = f"/webhook/{config.BOT_TOKEN}"
WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"

@app.on_event("startup")
async def on_startup():
    await db.init_db()
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook o'rnatildi: {WEBHOOK_URL}")

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    json_data = await request.json()
    update = types.Update(**json_data)
    await dp.feed_update(bot, update)
    return {"status": "ok"}


# ====================================================
# 1. AIOGRAM BOT HANDLERLARI
# ====================================================
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

@dp.message(F.text == "📱 Mazzali Mini App'ni ochish")
async def cmd_open_webapp(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Mini App'ni ochish", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer("Mini App'ni ochish uchun quyidagi tugmani bosing:", reply_markup=kb)

@dp.message(F.text)
async def handle_text_messages(message: types.Message):
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
    local_dishes = db.get_dishes_from_local_excel()
    if local_dishes:
        return local_dishes
    
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

    return []


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
                doc_type="Заказ для фабрики",
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


class SubmitParsedPhotoRequest(BaseModel):
    branch: str
    target_branch: str = ""
    doc_type: str
    items_json: str

@app.post("/api/submit_photo_parsed")
async def api_submit_photo_parsed(req: SubmitParsedPhotoRequest):
    try:
        items = json.loads(req.items_json)
        # config.DOC_TYPES orqali texnik nomni to'g'ri ruscha nomga o'tkazamiz
        readable_doc_type = config.DOC_TYPES.get(req.doc_type, req.doc_type)

        for item in items:
            item_name = item.get("item_name")
            qty = item.get("quantity", 0.0)
            if item_name and qty > 0:
                await db.add_branch_transaction(
                    branch=req.branch,
                    doc_type=readable_doc_type,
                    item_name=item_name,
                    quantity=qty,
                    comment="Mini App OCR orqali"
                )
        asyncio.create_task(db.sync_pending_transactions())
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ OCR natijalarini saqlashda xatolik: {e}")
        return {"status": "error", "message": str(e)}


class SubmitExtraRequest(BaseModel):
    branch: str
    text: str

@app.post("/api/submit_extra")
async def api_submit_extra(req: SubmitExtraRequest):
    try:
        lines = req.text.split("\n")
        for line in lines:
            if "-" in line:
                parts = line.split("-")
                item_name = parts[0].strip()
                try:
                    qty = float(parts[1].strip())
                except ValueError:
                    qty = 1.0
                if item_name:
                    await db.add_branch_transaction(
                        branch=req.branch,
                        doc_type="Дополнительный товар",
                        item_name=item_name,
                        quantity=qty,
                        comment="Qo'shimcha tovar"
                    )
        asyncio.create_task(db.sync_pending_transactions())
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ Qo'shimcha tovarlarni saqlashda xatolik: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/parse_photo")
async def api_parse_photo(branch: str = Form(...), doc_type: str = Form(...), photo: UploadFile = File(...)):
    image_bytes = await photo.read()
    valid_menu = []
    
    try:
        local_dishes = db.get_dishes_from_local_excel()
        valid_menu = [d["name"] for d in local_dishes if d.get("name")]
    except Exception as e:
        print(f"⚠️ Lokal Excel'dan menyu olishda xatolik: {e}")

    if not valid_menu:
        try:
            loop = asyncio.get_running_loop()
            sh = await loop.run_in_executor(None, db.get_spreadsheet)
            shota_sheet = await loop.run_in_executor(None, sh.worksheet, "Заказ_Шота")
            rows = await loop.run_in_executor(None, shota_sheet.get_all_values)
            valid_menu = [r[1].strip() for r in rows[1:] if len(r) >= 2 and r[1].strip()]
        except Exception as e:
            print(f"⚠️ Google Sheets'dan menyu yuklashda xatolik: {e}")

    # Operatsiya turiga qarab mos keluvchi OCR funksiyasini tanlaymiz
    if doc_type in ["Закончившиеся блюда", "FINISHED_DISHES"]:
        finished_list = ocr.parse_finished_dishes_photo(image_bytes, valid_menu_items=valid_menu)
        items = [{"item_name": name, "quantity": 1.0} for name in finished_list]
    else:
        # Приход, Остатки, Расход блюд, Списание по сроку/порче va boshqalar
        items = ocr.parse_receipt_photo(image_bytes, branch_name=branch, valid_menu_items=valid_menu)

    return {"status": "ok", "items": items}


# ====================================================
# 4. SERVERNI ISHGA TUSHIRISH
# ====================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)