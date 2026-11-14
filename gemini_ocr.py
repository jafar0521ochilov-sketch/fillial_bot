"""
gemini_ocr.py -> OpenAI GPT-4o-mini OCR & AI Agent moduli
"""
import base64
import io
import json
import re
from PIL import Image
from openai import OpenAI

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)
MODEL_NAME = "gpt-4o-mini"

def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Rasm yoki chekni OpenAI GPT-4o-mini orqali o'qib, mahsulotlar va miqdorlarni qaytaradi.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid ma'lumotlarni o'qing." if branch_name else ""

        prompt = (
            f"{branch_hint}\n"
            "Ushbu rasmda ko'rsatilgan taomlar yoki mahsulotlar nomlari va ularning miqdorlarini aniqlang. "
            "Javobni FAQAT va FAQAT quyidagi formatdagi sof JSON massivi shaklida qaytaring, boshqa hech qanday izoh yozmang:\n"
            '[{"item_name": "Mahsulot Nomi", "quantity": 1.0}]'
        )

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
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
            max_tokens=1500
        )

        raw_text = response.choices[0].message.content.strip()
        print(f"🤖 OpenAI OCR xom javobi: {raw_text}")
        
        # 1-usul: To'g'ridan-to'g'ri tozalab o'qish
        try:
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, list):
                        return val
        except:
            pass

        # 2-usul (Zaxira): Matn ichidan '[' va ']' orasidagi JSON massivini qidirib topish
        match = re.search(r'\[\s*\{.*?\}\s*\]', raw_text, re.DOTALL)
        if match:
            array_str = match.group(0)
            items = json.loads(array_str)
            if isinstance(items, list):
                return items

    except Exception as e:
        print(f"❌ OpenAI OCR xatolik: {e}")

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
            max_tokens=500
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
        print(f"❌ OpenAI tugagan taomlarni o'qishda xatolik: {e}")

    return []


def ask_gemini_agent(user_query: str, context_data: str = "") -> str:
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