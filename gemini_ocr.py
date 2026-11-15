"""
gemini_ocr.py -> OpenAI GPT-4o OCR & AI Agent moduli
(Uzun kassa cheklari va ProFood nakladnoylarini to'liq o'qish uchun optimallashtirilgan versiya)
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
    OpenAI GPT-4o yordamida uzun kassa cheklari va nakladnoy rasmlarini aniq o'qish.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        # Rasmni OpenAI uchun optimal o'lchamga keltiramiz (sifatini saqlagan holda)
        image.thumbnail((2000, 8000))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid hisobot." if branch_name else ""

        prompt = (
            f"{branch_hint}\n"
            "Bu restoran kassa cheki yoki nakladnoy. Rasmdagi BARCHA qatorlarni tepadan pastga qarab diqqat bilan o'qing.\n"
            "Har bir qatordan quyidagilarni aniqlang:\n"
            "1. 'item_name': Taom yoki tovar nomi (aynan rasmda qanday yozilgan bo'lsa shunday).\n"
            "2. 'quantity': Miqdori ('кол-во' yoki 'Остаток' yoki kataklardagi sonlar, masalan 3.0, 13.0, 1.0 va hokazo. Aslo hammasiga 1 yozmang, rasmdagi haqiqiy sonni qo'ying!)\n\n"
            "Javobni FAQAT quyidagi JSON formatida, 'items' kaliti ostida massiv ko'rinishida qaytaring, boshqa matn yozmang:\n"
            '{\n  "items": [\n    {"item_name": "Tovar Nomi", "quantity": 3.0}\n  ]\n}'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Siz restoran hujjatlari va cheklardagi yozuvlar hamda raqamlarni 100% aniqlikda ko'chirib o'qiydigan professional buxgalter yordamchisiz."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"  # Mayda raqamlar va harflar uchun yuqori aniqlik
                            }
                        }
                    ]
                }
            ],
            max_tokens=4096,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        print(f"\n================ 🤖 OPENAI OCR XOM JAVOBI ================")
        print(raw_text[:500] + "..." if len(raw_text) > 500 else raw_text)
        print(f"==========================================================\n")
        
        # JSON'ni tozalab o'qishga harakat qilamiz
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        items = []
        try:
            data = json.loads(clean_text)
            if isinstance(data, dict):
                items = data.get("items", [])
                if not items:
                    for val in data.values():
                        if isinstance(val, list):
                            items = val
                            break
            elif isinstance(data, list):
                items = data
        except Exception:
            # Agar JSON qismida kichik xatolik bo'lsa, regex orqali item_name va quantity larni sug'urib olamiz
            matches = re.findall(r'["\']item_name["\']\s*:\s*["\'](.*?)["\']\s*,\s*["\']quantity["\']\s*:\s*([0-9.]+)', raw_text)
            for name, qty in matches:
                try:
                    items.append({"item_name": name.strip(), "quantity": float(qty)})
                except:
                    pass

        # Menyu nomlari bilan solishtirib to'g'rilash
        if valid_menu_items and items:
            cleaned_items = []
            for it in items:
                name = str(it.get("item_name", "")).strip()
                try:
                    qty = float(it.get("quantity", 1.0))
                except:
                    qty = 1.0
                    
                matched_name = name
                for vm in valid_menu_items:
                    if name.lower() == vm.lower():
                        matched_name = vm
                        break
                cleaned_items.append({"item_name": matched_name, "quantity": qty})
            return cleaned_items

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
            "Bu fotosuratda tugagan taomlar ko'rsatilgan. "
            "Barcha taom nomlarini aniqlang va FAQAT quyidagi JSON formatida qaytaring:\n"
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
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        if isinstance(data, dict) and "dishes" in data:
            return [str(x) for x in data["dishes"]]
        elif isinstance(data, list):
            return [str(x) for x in data]
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