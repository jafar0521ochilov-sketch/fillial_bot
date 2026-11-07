"""
gemini_ocr.py - Mazzali Inventory & Order Management Bot
3-Modul: Gemini Vision (OCR) va AI Agent (Chat Yordamchisi) + Excel Fallback Mekanizmi + Timeout (20s) + Auto-Splitting
"""

import io
import json
import time
import re
import os
import asyncio
import concurrent.futures
from difflib import get_close_matches
from PIL import Image
from google import genai
from google.genai import types

import config
import sheets_database  # Excel fallback uchun ulash

ai_client = genai.Client(api_key=config.GEMINI_API_KEY)

# Foydalaniladigan Gemini modellari ro'yxati
AVAILABLE_MODELS = [
    "gemini-1.5-flash",  # To'g'ri ishlaydigan standart model nomi bilan almashtirildi
]


def _clean_json_response(raw_text: str) -> str:
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()


def match_with_menu(recognized_name: str, valid_menu_items: list[str], cutoff: float = 0.6) -> str:
    if not valid_menu_items:
        return recognized_name
    matches = get_close_matches(recognized_name, valid_menu_items, n=1, cutoff=cutoff)
    return matches[0] if matches else recognized_name


def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Katta rasmni avtomatik ravishda bo'laklarga bo'lib, Gemini orqali tezkor o'qiydi.
    Agar 20 sekund ichida javob bo'lmasa, Excel fallback'ga o'tadi.
    """
    image = Image.open(io.BytesIO(image_bytes))
    image.thumbnail((1024, 1024))  # Hajmini kichiklashtirish
    
    width, height = image.size
    
    # Rasm uzun bo'lsa, uni avtomatik ravishda 2 qismga (yuqori va pastki) bo'lamiz
    images_to_process = [image]
    if height > 600:
        half_height = height // 2
        img_top = image.crop((0, 0, width, half_height + 50))
        img_bottom = image.crop((0, half_height - 50, width, height))
        images_to_process = [img_top, img_bottom]

    branch_instruction = (
        f"Bu genel çok şubeli bir rapor veya sütunlu bir faturadır. "
        f"'{branch_name}' şubesine ait olan sütunu dikkatlice bul. "
        f"Diğer şubelerin verilerini dikkate almadan, yalnızca '{branch_name}' şubesinin sütunundaki miktarları oku. "
        if branch_name else 
        "Görüntüdeki TÜM satırları ve sütunları dikkatlice incele. "
    )

    prompt = (
        f"{branch_instruction}\n"
        "Yemeklerin/ürünlerin adlarını ve bunlara karşılık gelen miktarları çıkar.\n"
        "Sonucu Kesinlikle saf JSON dizi formatında döndür:\n"
        '[{"item_name": "Yemek Adı", "quantity": 10.0}]'
    )

    def _call_gemini_for_part(img_part):
        for model_name in AVAILABLE_MODELS:
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=[img_part, prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=4096,
                        response_mime_type="application/json"
                    )
                )
                clean_text = _clean_json_response(response.text)
                items = json.loads(clean_text)
                if isinstance(items, list):
                    return items
            except Exception as e:
                print(f"⚠️ Bo'lakni o'qishda xatolik: {e}")
        return []

    all_items = []

    # 20 sekundlik taymer (timeout) bilan bo'laklarni parallel qayta ishlash
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_call_gemini_for_part, img) for img in images_to_process]
            for future in concurrent.futures.as_completed(futures, timeout=20):
                part_items = future.result()
                if part_items:
                    all_items.extend(part_items)
    except Exception as e:
        print(f"⚠️ Gemini vaqti tugadi yoki xato berdi: {e}")

    # Agar ma'lumotlar topilsa, ularni menyu bo'yicha moslab qaytaramiz
    if all_items:
        if valid_menu_items:
            for item in all_items:
                item["item_name"] = match_with_menu(item.get("item_name", ""), valid_menu_items)
        return all_items

    # B variant (Fallback): Gemini o'qiy olmasa yoki vaqt tugasa, Excel orqali yuborish
    print("⚠️ B variant (Excel fallback) ishga tushirilmoqda...")
    try:
        fallback_file = "10.10.26.xlsx"
        if os.path.exists(fallback_file):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                success = asyncio.run_coroutine_threadsafe(
                    sheets_database.upload_excel_to_sheet(fallback_file, sheet_name="Лист1"),
                    loop
                ).result()
            else:
                success = asyncio.run(sheets_database.upload_excel_to_sheet(fallback_file, sheet_name="Лист1"))
            
            if success:
                print("✅ B variant muvaffaqiyatli bajarildi: Excel ma'lumotlari Google Sheets'ga yuborildi.")
    except Exception as ex:
        print(f"❌ B variantni bajarishda xatolik: {ex}")

    return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    image = Image.open(io.BytesIO(image_bytes))
    image.thumbnail((1024, 1024))

    prompt = (
        "Bu fotoğrafta vardiya sırasında tükenen yemekler gösterilmektedir. "
        "Tüm yemek isimlerini tespit et ve saf JSON dizisi olarak döndür:\n"
        '["Yemek 1", "Yemek 2"]'
    )
    
    for model_name in AVAILABLE_MODELS:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=[image, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=4096,
                    response_mime_type="application/json"
                )
            )
            clean_text = _clean_json_response(response.text)
            dish_names = json.loads(clean_text)

            if valid_menu_items and isinstance(dish_names, list):
                return [match_with_menu(dish, valid_menu_items) for dish in dish_names]

            return dish_names if isinstance(dish_names, list) else []
        except Exception:
            continue
            
    return []


def ask_gemini_agent(user_query: str, context_data: str = "") -> str:
    system_instruction = (
        "Sen 'Mazzali' gıda ve restoran zincirinin yapay zeka asistanısın. "
        "Kullanıcılara şube hesaplamaları, stoklar ve eksikler hakkında net ve profesyonel bir dille cevap ver."
    )
    full_prompt = f"Bağlam verileri:\n{context_data}\n\nKullanıcı sorusu: {user_query}"
    
    for model_name in AVAILABLE_MODELS:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=[full_prompt],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3
                )
            )
            return response.text
        except Exception:
            continue
            
    return "⚠️ AI asistanı ile bağlantı kurulamadı."