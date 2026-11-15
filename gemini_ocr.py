"""
gemini_ocr.py -> OpenAI GPT-4o OCR & AI Agent moduli
(Uzun cheklarni avtomatik bo'laklarga bo'lib, mukammal o'qiydigan versiya)
"""
import base64
import io
import json
import re
from PIL import Image
from openai import OpenAI

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)
MODEL_NAME = "gpt-4o"

def _parse_single_chunk(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Bitta rasm bo'lagini (chunk) OpenAI orqali aniq o'qish.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        image.thumbnail((1600, 4000))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid hisobot." if branch_name else ""
        
        menu_text = ""
        if valid_menu_items:
            menu_text = (
                "\nMENYU RO'YXATI BILAN SOLISHTIRING:\n"
                "Faqat quyidagi ro'yxatda mavjud bo'lgan tovar nomlarini yozing. O'zingizdan nom o'ylab topmang:\n" + 
                ", ".join([f"'{m}'" for m in valid_menu_items])
            )

        prompt = (
            f"{branch_hint}\n"
            "Bu restoran cheki yoki uning bir qismi. Rasmdagi barcha qatorlarni o'qing: taom nomi va miqdori (кол-во).\n"
            f"{menu_text}\n"
            "Barcha qatorlarni to'liq o'qib chiqib, FAQAT quyidagi JSON formatida qaytaring, boshqa matn yozmang:\n"
            '[\n  {"item_name": "Tovar Nomi", "quantity": 1.0}\n]'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "Siz restoran cheklari va hisobotlarini aniq raqamlar va menyu nomlari bilan o'qiydigan yordamchisiz."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4000,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(clean_text)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    return val
    except Exception as e:
        print(f"❌ Chunk o'qishda xatolik: {e}")

    return []


def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Agar rasm juda uzun bo'lsa, uni avtomatik ravishda bir nechta bo'lakka bo'lib o'qiydi va birlashtiradi.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        width, height = image.size
        all_items = []

        # Agar chek uzunligi enidan 1.5 barobar ko'p bo'lsa, uni bo'laklarga bo'lamiz
        if height > width * 1.5:
            chunk_height = int(width * 1.6)  # Har bir bo'lak balandligi
            overlap = 150  # Qatorlar tushib qolmasligi uchun qismdan-qismga o'tish chegarasi
            
            y = 0
            chunk_index = 1
            while y < height:
                box = (0, max(0, y - (overlap if y > 0 else 0)), width, min(height, y + chunk_height))
                chunk_img = image.crop(box)
                
                chunk_buffered = io.BytesIO()
                chunk_img.save(chunk_buffered, format="JPEG", quality=95)
                chunk_bytes = chunk_buffered.getvalue()
                
                print(f"🔄 Uzun chekning {chunk_index}-bo'lagi tahlil qilinmoqda...")
                chunk_items = _parse_single_chunk(chunk_bytes, branch_name, valid_menu_items)
                
                # Takrorlangan elementlar chiqib qolsa, ularni qo'shib yubormasdan to'g'rilaymiz
                for item in chunk_items:
                    if item not in all_items:
                        all_items.append(item)
                
                y += chunk_height
                chunk_index += 1
        else:
            all_items = _parse_single_chunk(image_bytes, branch_name, valid_menu_items)
            
        return all_items

    except Exception as e:
        print(f"❌ OpenAI GPT-4o OCR xatolik: {e}")

    return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        prompt = (
            "Bu fotosuratda smena davomida tugagan taomlar ko'rsatilgan. "
            "Barcha tugagan taom nomlarini aniqlang va FAQAT sof JSON massivi ko'rinishida qaytaring:\n"
            '["Taom 1", "Taom 2"]'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Siz restoran yordamchisiz. Tugagan taomlar ro'yxatini aniqlang."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(clean_text)
        if isinstance(data, list):
            return [str(x) for x in data]
        elif isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    return [str(x) for x in val]
    except Exception as e:
        print(f"❌ OpenAI tugagan taomlarni o'qishda xatolik: {e}")

    return []


def app_gemini_agent(user_query: str, context_data: str = "") -> str:
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Siz Mazzali restorani uchun aqlli yordamchisiz."},
                {"role": "user", "content": f"Kontekst ma'lumotlari:\n{context_data}\n\nFoydalanuvchi savoli: {user_query}"}
            ],
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ OpenAI AI yordamchi xatolik: {e}")
        return "⚠️ AI yordamchi bilan bog'lanishda xatolik yuz berdi."