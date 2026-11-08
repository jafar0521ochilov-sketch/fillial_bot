"""
gemini_ocr.py - Mazzali Inventory & Order Management Bot
Gemini Vision (OCR) va AI Agent (Chat Yordamchisi) moduli
"""

import io
import json
import os
import asyncio
from difflib import get_close_matches
from PIL import Image
from google import genai
from google.genai import types

import config
import sheets_database

ai_client = genai.Client(api_key=config.GEMINI_API_KEY)

# Google tomonidan tavsiya etilgan eng so'nggi va ishlaydigan model
MODEL_NAME = "gemini-3.8-flash"


def _clean_json_response(raw_text: str) -> str:
    text = raw_text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return text


def match_with_menu(recognized_name: str, valid_menu_items: list[str], cutoff: float = 0.6) -> str:
    if not valid_menu_items:
        return recognized_name
    matches = get_close_matches(recognized_name, valid_menu_items, n=1, cutoff=cutoff)
    return matches[0] if matches else recognized_name


def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Rasm yoki chekni Gemini orqali o'qib, mahsulotlar va miqdorlarni qaytaradi.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))

        branch_hint = f"'{branch_name}' filialiga oid ma'lumotlarni o'qing." if branch_name else ""
        prompt = (
            f"{branch_hint}\n"
            "Ushbu rasmda ko'rsatilgan mahsulot nomlari va ularning miqdorlarini aniqlang. "
            "Javobni faqat quyidagi formatdagi sof JSON massivi ko'rinishida qaytaring, boshqa hech qanday matn yozmang:\n"
            '[{"item_name": "Mahsulot Nomi", "quantity": 1.0}]'
        )

        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
            )
        )

        raw_text = _clean_json_response(response.text)
        if "[" in raw_text and "]" in raw_text:
            start = raw_text.find("[")
            end = raw_text.rfind("]") + 1
            items = json.loads(raw_text[start:end])
            if isinstance(items, list):
                if valid_menu_items:
                    for item in items:
                        item["item_name"] = match_with_menu(item.get("item_name", ""), valid_menu_items)
                return items
    except Exception as e:
        print(f"❌ Gemini OCR tahlil qilishda xatolik: {e}")

    return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    """
    Tugagan taomlar rasmini tahlil qilish.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))

        prompt = (
            "Bu fotosuratda smena davomida tugagan taomlar ko'rsatilgan. "
            "Barcha taom nomlarini aniqlang va faqat sof JSON massivi ko'rinishida qaytaring:\n"
            '["Taom 1", "Taom 2"]'
        )
        
        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
            )
        )

        raw_text = _clean_json_response(response.text)
        if "[" in raw_text and "]" in raw_text:
            start = raw_text.find("[")
            end = raw_text.rfind("]") + 1
            dish_names = json.loads(raw_text[start:end])
            if isinstance(dish_names, list):
                if valid_menu_items:
                    return [match_with_menu(dish, valid_menu_items) for dish in dish_names]
                return dish_names
    except Exception as e:
        print(f"❌ Tugagan taomlar rasmini o'qishda xatolik: {e}")

    return []


def ask_gemini_agent(user_query: str, context_data: str = "") -> str:
    try:
        system_instruction = (
            "Siz 'Mazzali' oziq-ovqat va restoran tarmog'ining sun'iy intellekt yordamchisiz. "
            "Foydalanuvchilarga filial hisob-kitoblari, ombor qoldiqlari va buyurtmalar haqida aniq va professional javob bering."
        )
        full_prompt = f"Kontekst ma'lumotlari:\n{context_data}\n\nFoydalanuvchi savoli: {user_query}"
        
        response = ai_client.models.generate_content(
            model=MODEL_NAME,
            contents=[full_prompt],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3
            )
        )
        return response.text
    except Exception as e:
        print(f"❌ Gemini AI javob berishda xatolik: {e}")
        return "⚠️ AI yordamchi bilan bog'lanishda xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring."