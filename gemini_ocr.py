"""
gemini_ocr.py - Mazzali Inventory & Order Management Bot
3-Modul: Gemini Vision (OCR) va AI Agent (Chat Yordamchisi)
"""

import io
import json
import time
import re
from difflib import get_close_matches
from PIL import Image
from google import genai
from google.genai import types

import config

ai_client = genai.Client(api_key=config.GEMINI_API_KEY)

# gemini_ocr.py ichidagi AVAILABLE_MODELS qismini shunga almashtiring:
AVAILABLE_MODELS = [
    "gemini-3.8-flash",
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
    image = Image.open(io.BytesIO(image_bytes))
    
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

    # Modeller arasında otomatik geçiş (Fallback mechanism)
    for model_name in AVAILABLE_MODELS:
        for attempt in range(2):
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=[image, prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=8192,
                        response_mime_type="application/json"
                    )
                )
                
                clean_text = _clean_json_response(response.text)
                items = json.loads(clean_text)

                if valid_menu_items and isinstance(items, list):
                    for item in items:
                        item["item_name"] = match_with_menu(item.get("item_name", ""), valid_menu_items)

                return items if isinstance(items, list) else []

            except Exception as e:
                print(f"⚠️ Model {model_name} (Deneme {attempt + 1}) hata verdi: {e}")
                time.sleep(1)

    print("❌ Hiçbir modelden yanıt alınamadı.")
    return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    image = Image.open(io.BytesIO(image_bytes))
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