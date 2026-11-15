"""
gemini_ocr.py -> OpenAI GPT-4o-mini OCR & AI Agent moduli (Kuchaytirilgan versiya)
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
    Rasm yoki chekni OpenAI GPT-4o-mini orqali o'qib, faqat bazadagi haqiqiy taomlar nomlari bilan taqqoslab qaytaradi.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid nakladnoy yoki qoldiq rasmi." if branch_name else ""
        
        menu_text = ""
        if valid_menu_items:
            menu_text = f"\nQuyida ushbu filialning rasmiy menyusi keltirilgan. Rasmdagi tovar nomlarini FAQAT SHU RO'YXATdagi aniq nomlarga moslang:\n" + ", ".join([f"'{m}'" for m in valid_menu_items[:150]])

        prompt = (
            f"{branch_hint}\n"
            "Ushbu nakladnoy yoki qoldiq rasmidagi barcha tovar va taomlarning miqdorlarini aniqlang.\n"
            f"{menu_text}\n"
            "DIQQAT: Aslo o'zingizdan nom o'ylab topmang! Faqat qog'ozdagi yozuvga eng mos keladigan haqiqiy nomni yozing.\n"
            "Javobni FAQAT quyidagi JSON massivi formatida qaytaring, boshqa hech qanday izoh yozmang:\n"
            '[\n  {"item_name": "Tovar Nomi", "quantity": 1.0}\n]'
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
            max_tokens=2000
        )

        raw_text = response.choices[0].message.content.strip()
        print(f"🤖 OpenAI OCR xom javobi: {raw_text}")
        
        # 1. Tozalab o'qishga urinish
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

        # 2. Zaxira: Regex orqali barcha {} bloklarini topib yig'ib olish
        items = []
        matches = re.findall(r'\{\s*["\']item_name["\']\s*:\s*["\'](.*?)["\']\s*,\s*["\']quantity["\']\s*:\s*([0-9.]+)\s*\}', raw_text, re.DOTALL)
        for name, qty in matches:
            try:
                items.append({"item_name": name.strip(), "quantity": float(qty)})
            except:
                pass
        
        if items:
            return items

        # 3. Umumiyroq massivni qidirish
        match = re.search(r'\[\s*\{.*?\}\s*\]', raw_text, re.DOTALL)
        if match:
            array_str = match.group(0)
            parsed_items = json.loads(array_str)
            if isinstance(parsed_items, list):
                cleaned_items = []
                for it in parsed_items:
                    name = it.get("item_name") or it.get("name") or it.get("title")
                    qty = it.get("quantity") if it.get("quantity") is not None else it.get("qty", 1.0)
                    if name:
                        cleaned_items.append({"item_name": str(name).strip(), "quantity": float(qty or 1.0)})
                return cleaned_items

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
            max_tokens=800
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