"""
gemini_ocr.py - Mazzali Inventory & Order Management Bot
3-Modul: Gemini Vision (OCR), chek/nakladnoy va tugagan taomlar rasmini tahlil qilish
"""

import io
import json
from difflib import get_close_matches
from PIL import Image
from google import genai
from google.genai import types

import config

# Google GenAI mijozi
ai_client = genai.Client(api_key=config.GEMINI_API_KEY)


def _clean_json_response(raw_text: str) -> str:
    """Modeldan qaytgan matndan markdown belgilarni tozalash"""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def match_with_menu(recognized_name: str, valid_menu_items: list[str], cutoff: float = 0.6) -> str:
    """
    Rasmdan o'qilgan nomni 135 ta taom ro'yxatiga eng yaqinini topib bog'lash.
    Agar mos kelmasa, o'qilgan nomning o'zini qoldiradi.
    """
    if not valid_menu_items:
        return recognized_name

    matches = get_close_matches(recognized_name, valid_menu_items, n=1, cutoff=cutoff)
    return matches[0] if matches else recognized_name


def parse_receipt_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[dict]:
    """
    1. Nakladnoy yoki kirim cheki rasmini tahlil qilish.
    Qaytaradi: [{'item_name': 'Борщ', 'quantity': 15.0}, ...]
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))

        prompt = (
            "Sen umumiy ovqatlanish tarmog'i uchun nakladnoy va cheklarni o'quvchi mutaxassissan. "
            "Suratdagi jadvaldan taomlar/tovarlar nomini va ularning sonini (miqdorini/kol-vo) aniqla. "
            "Javobni FAQAT toza JSON formatida quyidagi strukturada qaytar:\n"
            "[\n"
            "  {\"item_name\": \"Taom nomi\", \"quantity\": 10.0}\n"
            "]\n"
            "Hech qanday qo'shimcha so'z, tushuntirish yoki belgilar yozma."
        )

        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )

        clean_text = _clean_json_response(response.text)
        items = json.loads(clean_text)

        # 135 ta menyu bilan tekshirib, nomlarni to'g'rilash
        if valid_menu_items:
            for item in items:
                item["item_name"] = match_with_menu(item.get("item_name", ""), valid_menu_items)

        return items

    except Exception as e:
        print(f"❌ Nakladnoyni o'qishda xatolik yuz berdi: {e}")
        return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    """
    2. Smena oxirida tugagan taomlar («Закончившиеся блюда») varaqasini o'qish.
    Qaytaradi: ['Плов', 'Манты', 'Лагман']
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))

        prompt = (
            "Ushbu fotosuratda smena davomida tugab qolgan taomlar (Закончившиеся блюда/Стоп-лист) "
            "ro'yxati ko'rsatilgan (chek yoki qog'ozga qo'lda yozilgan bo'lishi mumkin). "
            "Barcha ko'rsatilgan taomlar nomlarini aniqla va FAQAT toza JSON massivi ko'rinishida qaytar:\n"
            "[\"Taom 1\", \"Taom 2\"]\n"
            "Hech qanday boshqa matn kiritma."
        )

        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image, prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )

        clean_text = _clean_json_response(response.text)
        dish_names = json.loads(clean_text)

        # Menyu bilan nomlarni solishtirish
        if valid_menu_items and isinstance(dish_names, list):
            matched_dishes = [match_with_menu(dish, valid_menu_items) for dish in dish_names]
            return matched_dishes

        return dish_names if isinstance(dish_names, list) else []

    except Exception as e:
        print(f"❌ Tugagan taomlar rasmini o'qishda xatolik: {e}")
        return []