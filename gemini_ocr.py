"""
gemini_ocr.py -> OpenAI GPT-4o OCR moduli
(Kataklardagi raqamlarni bir xil yozib yuborish xatosini oldini oluvchi versiya)
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

VALID_MENU_ITEMS = [
    "Гречка с капустой", "Гарнир Пюре карт.", "Гарнир Рис отв.", 
    "Драники картофельные с соус.Тар-тар", "Картофель с грибами", 
    "Тыквенные оладьи с медом", "Бефстроганов с рисом", "Гуляш из говядины с гречкой", 
    "Долма", "Домашние голубцы", "Котлета говяжья с пюре", "Макароны по-флотски", 
    "Манты с говядиной", "Медальоны с овощами гриль", "Мясо по-французски", 
    "Пельмени жареные", "Плов из говядины", "Рваная говядина в сливочно-перечном соусе с картофелем", 
    "Сардельки с пюре", "Спагетти Болоньезе", "Тефтели домашние", "Тушенка с макаронами", 
    "Шавля с тыквой", "Школьная котлета с пюре", "Биточки из курицы с рисом и овощ.", 
    "Гречка по-домашнему с курицей", "Грузинское оджахури с курицей и овощами", 
    "Жареный рис по-азиатски", "Котлета куриная на пару с пюре", "Котлета куриная по-киевски с пюре", 
    "Котлета куриная с пюре", "Котлеты куриные на пару (2шт)", "Котлеты куриные по-киевски (2шт)", 
    "Куриная грудка с овощами на пару", "Куриная грудка с сыром и запеченной тыквой", 
    "Курица Гриль с овощами", "Курица Карри с рисом", "Курица по-азиатски с рисом", 
    "Курица по-мексикански", "Курица Терияки с рисом", "Люля куриные с гречкой", 
    "Оладьи куриные с пюре", "Спагетти Карбонара", "Утиная грудка с картофелем и розмарином", 
    "Фетучини Альфредо", "Шницель в сырной панировке с пюре", "Рыбная котлета с рисом и овощами", 
    "Судак на пару", "Десерт Дубайский", "Десерт Медовик", "Десерт Черный лес", 
    "Рогалики с орехами", "Блины с джемом", "Блины с курицей", "Блины с мясом", 
    "Блины с Нутеллой", "Блины с творогом", "Бургер", "Каша Овсяная", "Каша Рисовая", 
    "Кимбап Краб", "Кимбап Курица", "Кимбап Форель", "Клаб сэндвич с Индейкой", 
    "Клаб сэндвич с Курицей", "Клаб сэндвич с Салями", "Клаб сэндвич с Тунцом", 
    "Клаб сэндвич с Форелью", "Конвертики с грибами", "Конвертики с запеченной курицей и сыром", 
    "Конвертики с мясом", "Конвертики с творогом и вишней", "Конвертики со шпинатом и сыром", 
    "Маффины ассорти (вишневый, шоколадный, цитрусовый)", "Омлет ролл с курицей", 
    "Омлет ролл со шпинатом и сыром", "ОНИГИРИ с тунцом", "ОНИГИРИ Филадельфия", 
    "Панкейки с джемом", "Пирожки с вишней", "Пирожки с капустой", "Пирожки с картошкой", 
    "Пирожки с мясом", "Пирожки с рисом и яйцом", "Пирожки с яблочным джемом", 
    "Роллы индейка с сыром", "Роллы Цезарь", "Сосиски в тесте", "Сырники", 
    "Спринг-роллы с овощами и курицей", "Сэндвич Чиабатта с курицей", "Творожная запеканка", 
    "Шаурма куриная", "Эчпочмаки", "Смузи Витаминный микс", "Смузи Тропический микс", 
    "Смузи Цитрусовый микс", "Смузи Экзотический микс", "Смузи Ягодный микс", "Лимонад", 
    "Морс Клубника", "Морс Клюква", "Морс Смородина", "Морс Шиповник", "Напиток Айс-ти", 
    "Баклажаны по-корейски", "Весенний", "Винегрет", "Винегрет с КАПУСТОЙ", "Витаминка", 
    "Греческий", "Домашняя Баклажанная Икра", "Зеленый салат с заправкой", "Королевский", 
    "Крабовый", "Медовый с курицей", "Мимоза", "Морковча", "Нежный с курицей", 
    "Огурцы по-корейски", "Оливье с колбасой", "Оливье с мясом", "Сельдь под шубой", 
    "Цезарь с курицей", "Борщ", "Куриный бульон с лапшой", "Мастава", 
    "Сливочный суп с рыбой и овощным миксом", "Суп с фрикадельками", "Сырный суп с овощами", 
    "Том Ям с креветками", "Суп-пюре тыквенный", "Чечевичный суп-пюре", "Щи из щавеля"
]

def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    try:
        if not valid_menu_items:
            valid_menu_items = VALID_MENU_ITEMS

        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        image.thumbnail((2000, 8000))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        branch_hint = f"'{branch_name}' filialiga oid hisobot." if branch_name else ""
        menu_list_str = ", ".join([f'"{m}"' for m in valid_menu_items])

        # KRITIK O'ZGARISH: Har bir qator uchun alohida raqamni topishni qat'iy talab qiluvchi prompt
        prompt = (
            f"{branch_hint}\n"
            "Это накладная ProFood с таблицей. Внимательно прочтите КАЖДУЮ строку сверху вниз.\n"
            "КРИТИЧЕСКИ ВАЖНО: В таблице у каждого блюда в ячейке справа написана СВОЯ уникальная цифра (количество). "
            "Категорически запрещено ставить одинаковые цифры (например, всем 6.0 или всем 4.0)! Посмотрите внимательно на каждую строку и найдите точное число, указанное именно для этого блюда в ячейке.\n\n"
            f"ОФИЦИАЛЬНЫЙ СПИСОК МЕНЮ: [{menu_list_str}]\n\n"
            "Для каждого блюда из документа найдите точное название из списка выше и его реальное индивидуальное количество ('q').\n"
            "Верните ответ СТРОГО в формате JSON:\n"
            '{\n  "items": [\n    {"n": "Название из меню", "q": число_из_ячейки}\n  ]\n}'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Вы — внимательный бухгалтер. Вы никогда не путаете и не дублируете цифры из таблиц. Каждая строка имеет свое уникальное количество."
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
            matches = re.findall(r'["\'](?:n|item_name)["\']\s*:\s*["\'](.*?)["\']\s*,\s*["\'](?:q|quantity)["\']\s*:\s*([0-9.]+)', raw_text)
            for name, qty in matches:
                try:
                    items.append({"item_name": name.strip(), "quantity": float(qty)})
                except:
                    pass

        if valid_menu_items and items:
            cleaned_items = []
            for it in items:
                name = it.get("item_name", "").strip()
                qty = it.get("quantity", 1.0)
                
                matched_name = name
                for vm in valid_menu_items:
                    if name.lower() == vm.lower():
                        matched_name = vm
                        break
                    elif name.lower() in vm.lower() or vm.lower() in name.lower():
                        matched_name = vm
                        
                cleaned_items.append({"item_name": matched_name, "quantity": qty})
            return cleaned_items

        return items
            
    except Exception as e:
        print(f"❌ OpenAI OCR xatolik: {e}")

    return []


def parse_finished_dishes_photo(image_bytes: bytes, valid_menu_items: list[str] = None) -> list[str]:
    try:
        if not valid_menu_items:
            valid_menu_items = VALID_MENU_ITEMS

        image = Image.open(io.BytesIO(image_bytes))
        image.thumbnail((1024, 1024))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        prompt = '{"dishes": ["Блюдо 1"]}'
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Определите закончившиеся блюда на русском языке."},
                {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}]}
            ],
            max_tokens=2000,
            temperature=0.0
        )
        raw_text = response.choices[0].message.content.strip()
        data = json.loads(raw_text.replace("```json", "").replace("```", "").strip())
        if isinstance(data, dict) and "dishes" in data:
            dishes = [str(x) for x in data["dishes"]]
            if valid_menu_items:
                matched_dishes = []
                for d in dishes:
                    md = d
                    for vm in valid_menu_items:
                        if d.lower() == vm.lower() or d.lower() in vm.lower():
                            md = vm
                            break
                    matched_dishes.append(md)
                return matched_dishes
            return dishes
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