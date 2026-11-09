"""
gemini_ocr.py - Mazzali Inventory & Order Management Bot
Gemini Vision (OCR) va AI Agent moduli (Lokal Excel menyusi bilan ishlashga moslashtirilgan)
"""

import io
import json
import os
from PIL import Image
from google import genai
from google.genai import types

import config
import sheets_database

ai_client = genai.Client(api_key=config.GEMINI_API_KEY)

# Google talab qilgan eng so'nggi va ishlaydigan model
MODEL_NAME = "gemini-3.8-flash"


def _clean_json_response(raw_text: str) -> str:
    text = raw_text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return text


def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Rasm yoki chekni Gemini orqali o'qib, lokal Excel menyusiga tayangan holda mahsulotlar va miqdorlarni qaytaradi.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))

        branch_hint = f"'{branch_name}' filialiga oid ma'lumotlarni o'qing." if branch_name else ""
        
        # Lokal Excel'dan kelgan menyu elementlarini Gemini promptiga qo'shamiz
        menu_hint = ""
        if valid_menu_items:
            menu_str = ", ".join([f'"{item}"' for item in valid_menu_items])
            menu_hint = (
                f"\nDiqqat! Mahsulot nomlarini aniqlashda FAQAT quyidagi tasdiqlangan menyu ro'yxatidan foydalaning. "
                f"Rasmdagi yozuvlarni ushbu ro'yxatdagi eng o'xshash nomlarga moslang:\n[{menu_str}]\n"
            )

        prompt = (
            f"{branch_hint}\n"
            f"{menu_hint}\n"
            "Ushbu rasmda ko'rsatilgan mahsulot nomlari va ularning miqdorlarini aniqlang. "
            "Javobni faqat quyidagi formatdagi sof JSON massivi ko'rinishida qaytaring, boshqa hech qanday matn yozmang:\n"
            '[{"item_name": "Mahsulot Nomi", "quantity": 1.0}]'
        )

        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=[image, prompt]
        )

        raw_text = _clean_json_response(response.text)
        if "[" in raw_text and "]" in raw_text:
            start = raw_text.find("[")
            end = raw_text.rfind("]") + 1
            items = json.loads(raw_text[start:end])
            if isinstance(items, list):
                return items
    except Exception as e:
        print(f"❌ Gemini OCR tahlil qilishda xatolik: {e}")

    return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    """
    Tugagan taomlar rasmini lokal Excel menyusi asosida o'qiydi.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))

        menu_hint = ""
        if valid_menu_items:
            menu_str = ", ".join([f'"{item}"' for item in valid_menu_items])
            menu_hint = f"\nMavjud taomlar ro'yxati:\n[{menu_str}]\n"

        prompt = (
            f"{menu_hint}\n"
            "Bu fotosuratda smena davomida tugagan taomlar ko'rsatilgan. "
            "Yuqoridagi ro'yxatga tayanib, barcha tugagan taom nomlarini aniqlang va faqat sof JSON massivi ko'rinishida qaytaring:\n"
            '["Taom 1", "Taom 2"]'
        )
        
        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=[image, prompt]
        )

        raw_text = _clean_json_response(response.text)
        if "[" in raw_text and "]" in raw_text:
            start = raw_text.find("[")
            end = raw_text.rfind("]") + 1
            dish_names = json.loads(raw_text[start:end])
            if isinstance(dish_names, list):
                return dish_names
    except Exception as e:
        print(f"❌ Tugagan taomlar rasmini o'qishda xatolik: {e}")

    return []


def ask_gemini_agent(user_query: str, context_data: str = "") -> str:
    try:
        full_prompt = f"Kontekst ma'lumotlari:\n{context_data}\n\nFoydalanuvchi savoli: {user_query}"
        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=[full_prompt]
        )
        return response.text
    except Exception as e:
        print(f"❌ Gemini AI javob berishda xatolik: {e}")
        return "⚠️ AI yordamchi bilan bog'lanishda xatolik yuz berdi."