"""
gemini_ocr.py -> OpenAI GPT-4o OCR & AI Agent moduli
(Uzun cheklar va hisobotlarni to'liq o'qish uchun qat'iy menyu moslashtiruvchi versiya)
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

def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Rasm yoki uzun chekni OpenAI GPT-4o orqali meniga qat'iy moslab, birorta ham qatorni qoldirmasdan o'qish.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        # Uzun cheklar uchun o'lchamni kengroq va aniq saqlaymiz
        image.thumbnail((2000, 8000))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid hisobot." if branch_name else ""
        
        menu_text = ""
        if valid_menu_items:
            menu_text = (
                "\nQUYIDAGI RASMIY MENYU RO'YXATI BILAN TO'LIQ SOLISHTIRING:\n"
                "Faqat va faqat quyidagi ro'yxatda mavjud bo'lgan tovar nomlarini yozing. "
                "O'zingizdan nom o'ylab topmang yoki o'zgartirmang:\n" + 
                ", ".join([f"'{m}'" for m in valid_menu_items])
            )

        prompt = (
            f"{branch_hint}\n"
            "Bu restoran uzun kassa cheki yoki hisoboti. "
            "Rasmdagi har bir qatorni diqqat bilan o'qing: kod, блюдо (taom nomi), va кол-во (miqdori).\n"
            "Miqdorlarni (masalan 3.0, 13.0, 1.0) adashtirmasdan o'ng tarafdagi miqdor ustunidan aniq oling.\n"
            f"{menu_text}\n"
            "Barcha qatorlarni boshidan oxirigacha bittasini ham qoldirmasdan o'qib chiqib, "
            "FAQAT quyidagi JSON formatida qaytaring, boshqa hech qanday izoh yozmang:\n"
            '[\n  {"item_name": "Tovar Nomi", "quantity": 1.0}\n]'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "Siz restoran cheklari va hisobotlarini aniq raqamlar va menyu nomlari bilan o'qiydigan qat'iy buxgalter yordamchisiz."
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
            max_tokens=8000,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        print(f"🤖 OpenAI GPT-4o OCR xom javobi: {raw_text}")
        
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(clean_text)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, list):
                        return val
        except:
            pass

        items = []
        matches = re.findall(r'\{\s*["\']item_name["\']\s*:\s*["\'](.*?)["\']\s*,\s*["\']quantity["\']\s*:\s*([0-9.]+)\s*\}', raw_text, re.DOTALL)
        for name, qty in matches:
            try:
                items.append({"item_name": name.strip(), "quantity": float(qty)})
            except:
                pass
        
        if items:
            return items

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