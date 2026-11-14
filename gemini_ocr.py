"""
gemini_ocr.py -> OpenAI GPT-4o-mini OCR & AI Agent moduli (Excel menyusiga tayanib ishlaydi)
"""
import base64
import io
import json
import pandas as pd
from PIL import Image
from openai import OpenAI

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)
MODEL_NAME = "gpt-4o-mini"

def get_valid_menu_items_from_excel(excel_path: str = "10.10.26.xlsx") -> list[str]:
    """
    Excel fayldan tasdiqlangan taomlar va mahsulotlar ro'yxatini o'qib qaytaradi.
    """
    try:
        df = pd.read_excel(excel_path, header=3)
        if 'Наименование' in df.columns:
            items = df['Наименование'].dropna().astype(str).tolist()
            # "ИТОГО КОЛИЧЕСТВО:" kabi jami qatorlarni olib tashlaymiz
            items = [item for item in items if "ИТОГО" not in item.upper()]
            return items
    except Exception as e:
        print(f"❌ Excel faylni o'qishda xatolik: {e}")
    return []


def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Rasm yoki chekni OpenAI GPT-4o-mini orqali o'qib, mahsulotlarni Excel menyusiga moslab qaytaradi.
    """
    try:
        # Agar valid_menu_items berilmagan bo'lsa, Excel fayldan o'qib olamiz
        if not valid_menu_items:
            valid_menu_items = get_valid_menu_items_from_excel()

        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid ma'lumotlarni o'qing." if branch_name else ""
        
        menu_str = ", ".join([f'"{item}"' for item in valid_menu_items])
        menu_hint = (
            f"\nDiqqat! Mahsulot nomlarini aniqlashda FAQAT va FAQAT quyidagi tasdiqlangan menyu ro'yxatidan foydalaning. "
            f"Rasmdagi yozuvlarni shartli ravishda quyidagi ro'yxatdagi eng o'xshash nomlarga to'liq moslang:\n[{menu_str}]\n"
        )

        prompt = (
            f"{branch_hint}\n"
            f"{menu_hint}\n"
            "Ushbu rasmda ko'rsatilgan mahsulot nomlari va ularning miqdorlarini aniqlang. "
            "Javobni FAQAT sof JSON massivi ko'rinishida qaytaring, boshqa hech qanday izoh yozmang:\n"
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
            max_tokens=1000
        )

        raw_text = response.choices[0].message.content.strip()
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        data = json.loads(clean_text)

        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            for k in ["items", "products", "result", "data", "list"]:
                if k in data and isinstance(data[k], list):
                    return data[k]
            for val in data.values():
                if isinstance(val, list):
                    return val

    except Exception as e:
        print(f"❌ OpenAI OCR xatolik: {e}")

    return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    try:
        if not valid_menu_items:
            valid_menu_items = get_valid_menu_items_from_excel()

        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        menu_str = ", ".join([f'"{item}"' for item in valid_menu_items])
        menu_hint = f"\nMavjud taomlar ro'yxati:\n[{menu_str}]\n"

        prompt = (
            f"{menu_hint}\n"
            "Bu fotosuratda smena davomida tugagan taomlar ko'rsatilgan. "
            "Yuqoridagi ro'yxatga tayanib, barcha tugagan taom nomlarini aniqlang va FAQAT sof JSON massivi ko'rinishida qaytaring:\n"
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
            for k in ["dishes", "items", "result", "list"]:
                if k in data and isinstance(data[k], list):
                    return data[k]
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