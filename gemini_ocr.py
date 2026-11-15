"""
gemini_ocr.py -> OpenAI GPT-4o OCR & AI Agent moduli
(Yuqori aniqlikdagi detail: high rejimi bilan uzun cheklarni o'qish)
"""
import base64
import io
import json
from PIL import Image
from openai import OpenAI

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)
MODEL_NAME = "gpt-4o"

def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Uzun kassa cheklarini detail: high yordamida bitta ham qatorni qoldirmasdan aniq o'qish.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        # Rasmni hajmini mutanosib saqlaymiz (juda kichraytirmaymiz)
        image.thumbnail((2000, 8000))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid hisobot." if branch_name else ""
        
        menu_text = ""
        if valid_menu_items:
            menu_text = (
                "\nRASMIY MENYU RO'YXATI:\n"
                "Faqat quyidagi ro'yxatda mavjud bo'lgan tovar nomlarini yozing. O'zingizdan nom o'ylab topmang:\n" + 
                ", ".join([f"'{m}'" for m in valid_menu_items])
            )

        prompt = (
            f"{branch_hint}\n"
            "Bu restoran uzun kassa cheki (Obshiy rasxod blyud). "
            "Rasmdagi har bir qatorni TEPADAN PASTGA qarab diqqat bilan o'qing: "
            "1-ustun: Kod, 2-ustun: Taom nomi (блюдо), 3-ustun: Miqdori (кол-во, masalan 3.0, 1.0, 13.0).\n"
            "Miqdorlarni boshqa ustunlardagi summalar (summa) bilan adashtirib yubormang! Faqat 'кол-во' ustunidagi haqiqiy miqdorni oling.\n"
            f"{menu_text}\n"
            "Barcha qatorlarni to'liq o'qib chiqib, FAQAT quyidagi JSON formatida qaytaring, boshqa hech qanday izoh yozmang:\n"
            '{\n  "items": [\n    {"item_name": "Tovar Nomi", "quantity": 1.0}\n  ]\n}'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Siz restoran cheklari va hisobotlarini raqamlari va menyu nomlari bilan 100% aniqlikda o'qiydigan professional buxgalter yordamchisiz."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"  # <-- ENG MUHIM QISM: Mayda harflar va raqamlarni aniq o'qish uchun yuqori aniqlik
                            }
                        }
                    ]
                }
            ],
            max_tokens=4000,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        data = json.loads(raw_text)
        
        if isinstance(data, dict):
            if "items" in data and isinstance(data["items"], list):
                return data["items"]
            for val in data.values():
                if isinstance(val, list):
                    return val
        elif isinstance(data, list):
            return data
            
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
            "Barcha tugagan taom nomlarini aniqlang va FAQAT quyidagi JSON formatida qaytaring:\n"
            '{\n  "dishes": ["Taom 1", "Taom 2"]\n}'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Siz restoran yordamchisiz. Tugagan taomlar ro'yxatini aniqlang."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        data = json.loads(raw_text)
        if isinstance(data, dict) and "dishes" in data:
            return [str(x) for x in data["dishes"]]
    except Exception as e:
        print(f"❌ Tugagan taomlarni o'qishda xatolik: {e}")

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