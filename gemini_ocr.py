"""
gemini_ocr.py -> OpenAI GPT-4o OCR & AI Agent moduli
(Rasmdan to'g'ridan-to'g'ri o'qiydigan toza versiya)
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
    Uzun kassa cheklarini rasmdan bevosita matn va miqdor bo'yicha o'qish.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        image.thumbnail((2000, 8000))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid hisobot." if branch_name else ""

        prompt = (
            f"{branch_hint}\n"
            "Bu restoran kassa cheki. Rasmdagi har bir qatorni TEPADAN PASTGA qarab diqqat bilan o'qing.\n"
            "Har bir qatordan quyidagilarni aniqlang:\n"
            "1. 'item_name': Chekdagi 'блюдо' ustunida yozilgan taom yoki tovar nomi (aynan chekda qanday yozilgan bo'lsa shunday yozing).\n"
            "2. 'quantity': 'кол-во' ustunidagi raqam (masalan 3.0, 13.0, 1.0 va hokazo. Aslo hammasiga 1 yozmang, chekdagi haqiqiy miqdorni qo'ying!)\n\n"
            "Javobni FAQAT quyidagi JSON formatida, 'items' kaliti ostida massiv ko'rinishida qaytaring, boshqa hech qanday matn yozmang:\n"
            '{\n  "items": [\n    {"item_name": "Tovar Nomi", "quantity": 3.0}\n  ]\n}'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Siz cheklardagi yozuvlar va raqamlarni aniq ko'chirib o'qiydigan buxgalter yordamchisiz."
                },
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
            max_tokens=4000,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        print(f"\n================ 🤖 OPENAI OCR XOM JAVOBI ================")
        print(raw_text)
        print(f"==========================================================\n")
        
        data = json.loads(raw_text)
        
        if isinstance(data, dict):
            if "items" in data and isinstance(data["items"], list):
                items = data["items"]
                # Agar valid_menu_items berilgan bo'lsa, nomlarini bazadagiga moslab olamiz
                if valid_menu_items:
                    cleaned_items = []
                    for it in items:
                        name = it.get("item_name", "").strip()
                        qty = float(it.get("quantity", 1.0))
                        # Aniq yoki o'xshash nomni qidiramiz
                        matched_name = name
                        for vm in valid_menu_items:
                            if name.lower() == vm.lower():
                                matched_name = vm
                                break
                        cleaned_items.append({"item_name": matched_name, "quantity": qty})
                    return cleaned_items
                return items
                
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