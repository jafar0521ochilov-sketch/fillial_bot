"""
gemini_ocr.py -> OpenAI GPT-4o OCR moduli
(Uzun cheklarni OpenAI token limitiga sig'adigan qilib xavfsiz bo'laklarga bo'lib o'qish)
"""
import base64
import io
import json
from PIL import Image
from openai import OpenAI

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)
MODEL_NAME = "gpt-4o"

def _parse_single_chunk(image_bytes: bytes, branch_name: str = "") -> list[dict]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        # OpenAI uchun tasvirni xavfsiz hajmga keltiramiz
        image.thumbnail((1200, 2000))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=90)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid hisobot." if branch_name else ""

        prompt = (
            f"{branch_hint}\n"
            "Bu restoran kassa cheki bo'lagi. Rasmdagi barcha qatorlarni o'qing:\n"
            "1. 'item_name': Tovar yoki taom nomi\n"
            "2. 'quantity': 'кол-во' ustunidagi raqam (masalan 3.0, 13.0, 1.0 va hokazo. Aslo hammasiga 1 yozmang!)\n\n"
            "Javobni FAQAT quyidagi JSON formatida, 'items' kaliti ostida massiv ko'rinishida qaytaring:\n"
            '{\n  "items": [\n    {"item_name": "Tovar Nomi", "quantity": 3.0}\n  ]\n}'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Siz cheklardagi yozuvlar va raqamlarni aniq o'qiydigan buxgalter yordamchisiz."
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
            max_tokens=2000,  # Token limitidan oshib ketmasligi uchun cheklangan
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
        print(f"❌ Chunk o'qishda xatolik: {e}")

    return []


def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Uzun chekni avtomatik ravishda qismlarga bo'lib, OpenAI orqali xavfsiz o'qish.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        width, height = image.size
        all_items = []

        # Agar chek uzun bo'lsa, uni har biri taxminan 1.2 nisbatdagi bo'laklarga bo'lamiz
        if height > width * 1.3:
            chunk_height = int(width * 1.2)
            overlap = 100
            
            y = 0
            chunk_index = 1
            while y < height:
                box = (0, max(0, y - (overlap if y > 0 else 0)), width, min(height, y + chunk_height))
                chunk_img = image.crop(box)
                
                chunk_buffered = io.BytesIO()
                chunk_img.save(chunk_buffered, format="JPEG", quality=90)
                chunk_bytes = chunk_buffered.getvalue()
                
                print(f"🔄 Uzun chekning {chunk_index}-bo'lagi OpenAI ga yuborilmoqda...")
                chunk_items = _parse_single_chunk(chunk_bytes, branch_name)
                
                for item in chunk_items:
                    if item not in all_items:
                        all_items.append(item)
                
                y += chunk_height
                chunk_index += 1
        else:
            all_items = _parse_single_chunk(image_bytes, branch_name)
            
        # Menyu nomlarini moslash
        if valid_menu_items and all_items:
            cleaned_items = []
            for it in all_items:
                name = it.get("item_name", "").strip()
                qty = float(it.get("quantity", 1.0))
                matched_name = name
                for vm in valid_menu_items:
                    if name.lower() == vm.lower():
                        matched_name = vm
                        break
                cleaned_items.append({"item_name": matched_name, "quantity": qty})
            return cleaned_items

        return all_items

    except Exception as e:
        print(f"❌ OpenAI OCR umumiy xatolik: {e}")

    return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        prompt = "Bu fotosuratda smena davomida tugagan taomlar ko'rsatilgan. Barcha tugagan taom nomlarini aniqlang va FAQAT JSON formatida qaytaring:\n{\"dishes\": [\"Taom 1\"]}"
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Siz restoran yordamchisiz."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}
                    ]
                }
            ],
            max_tokens=1500,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        data = json.loads(raw_text)
        if isinstance(data, dict) and "dishes" in data:
            return [str(x) for x in data["dishes"]]
    except Exception as e:
        print(f"❌ Xatolik: {e}")
    return []


def ask_gemini_agent(user_query: str, context_data: str = "") -> str:
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Siz Mazzali restorani uchun yordamchisiz."},
                {"role": "user", "content": f"Kontekst:\n{context_data}\n\nSavol: {user_query}"}
            ],
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return "⚠️ Xatolik yuz berdi."