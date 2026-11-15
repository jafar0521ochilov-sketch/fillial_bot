"""
gemini_ocr.py -> OpenAI GPT-4o OCR moduli
(Kassa cheklari va ProFood nakladnoylarini rus tilida mukammal o'qish uchun)
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
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        image.thumbnail((2000, 8000))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid hisobot." if branch_name else ""

        # OpenAI ga rus tilida aniq yozilganidek o'qishni buyuramiz
        prompt = (
            f"{branch_hint}\n"
            "Это кассовый чек или накладная ProFood. Внимательно прочтите ВСЕ строки сверху вниз.\n"
            "Для каждого блюда или товара укажите точное название на русском языке (как написано на изображении) и его количество (цифру из столбца кол-во, остаток или ячеек).\n"
            "Запрещено ставить одинаковые цифры на все строки! У каждой строки свое реальное количество.\n"
            "Верните ответ СТРОГО в формате JSON, без лишнего текста, используя короткие ключи 'n' (название) и 'q' (количество):\n"
            '{\n  "items": [\n    {"n": "Гречка с капустой", "q": 4.0},\n    {"n": "Гарнир Пюре карт.", "q": 6.0}\n  ]\n}'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Вы — профессиональный бухгалтерский помощник, который точно и без ошибок считывает названия блюд на русском языке и их количества с документов."
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
            max_tokens=4096,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        print(f"\n================ 🤖 OPENAI OCR XOM JAVOBI ================")
        print(raw_text[:500] + "..." if len(raw_text) > 500 else raw_text)
        print(f"==========================================================\n")
        
        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
        
        items = []
        try:
            data = json.loads(clean_text)
            raw_items = []
            if isinstance(data, dict):
                raw_items = data.get("items", [])
                if not raw_items:
                    for val in data.values():
                        if isinstance(val, list):
                            raw_items = val
                            break
            elif isinstance(data, list):
                raw_items = data
                
            for it in raw_items:
                name = str(it.get("n") or it.get("item_name") or "").strip()
                try:
                    qty = float(it.get("q") or it.get("quantity") or 1.0)
                except:
                    qty = 1.0
                if name:
                    items.append({"item_name": name, "quantity": qty})
                    
        except Exception as e:
            print(f"⚠️ JSON xatoligi, regex ishga tushdi: {e}")
            matches = re.findall(r'["\'](?:n|item_name)["\']\s*:\s*["\'](.*?)["\']\s*,\s*["\'](?:q|quantity)["\']\s*:\s*([0-9.]+)', raw_text)
            for name, qty in matches:
                try:
                    items.append({"item_name": name.strip(), "quantity": float(qty)})
                except:
                    pass

        # Menyu nomlari bilan moslash
        if valid_menu_items and items:
            cleaned_items = []
            for it in items:
                name = it.get("item_name", "")
                qty = it.get("quantity", 1.0)
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

        prompt = '{"dishes": ["Блюдо 1", "Блюдо 2"]}'
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Определите закончившиеся блюда."},
                {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}]}
            ],
            max_tokens=2000,
            temperature=0.0
        )
        raw_text = response.choices[0].message.content.strip()
        data = json.loads(raw_text.replace("```json", "").replace("```", "").strip())
        if isinstance(data, dict) and "dishes" in data:
            return [str(x) for x in data["dishes"]]
    except:
        pass
    return []


def ask_gemini_agent(user_query: str, context_data: str = "") -> str:
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Помощник ресторана Mazzali."},
                {"role": "user", "content": f"Контекст:\n{context_data}\n\nВопрос: {user_query}"}
            ],
            max_tokens=800
        )
        return response.choices[0].message.content
    except:
        return "⚠️ Ошибка связи с ИИ."