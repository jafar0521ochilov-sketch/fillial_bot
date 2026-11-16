"""
gemini_ocr.py -> OpenAI GPT-4o OCR moduli
(Tartib raqamlari, qismlarga bo'lib kesish va miqdorlar xavfsizlik filtri bilan)
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

# 1 dan 134 gacha bo'lgan taomlar bazasi va ularning tartib raqamlari
MENU_ITEMS_WITH_INDEX = {
    1: "Гречка с капустой", 2: "Гарнир Пюре карт.", 3: "Гарнир Рис отв.", 
    4: "Драники картофельные с соус.Тар-тар", 5: "Картофель с грибами", 
    6: "Тыквенные оладьи с медом", 7: "Бефстроганов с рисом", 8: "Гуляш из говядины с гречкой", 
    9: "Долма", 10: "Домашние голубцы", 11: "Котлета говяжья с пюре", 12: "Макароны по-флотски", 
    13: "Манты с говядиной", 14: "Медальоны с овощами гриль", 15: "Мясо по-французски", 
    16: "Пельмени жареные", 17: "Плов из говядины", 18: "Рваная говядина в сливочно-перечном соусе с картофелем", 
    19: "Сардельки с пюре", 20: "Спагетти Болоньезе", 21: "Тефтели домашние", 22: "Тушенка с макаронами", 
    23: "Шавля с тыквой", 24: "Школьная котлета с пюре", 25: "Биточки из курицы с рисом и овощ.", 
    26: "Гречка по-домашнему с курицей", 27: "Грузинское оджахури с курицей и овощами", 
    28: "Жареный рис по-азиатски", 29: "Котлета куриная на пару с пюре", 30: "Котлета куриная по-киевски с пюре", 
    31: "Котлета куриная с пюре", 32: "Котлеты куриные на пару (2шт)", 33: "Котлеты куриные по-киевски (2шт)", 
    34: "Куриная грудка с овощами на пару", 35: "Куриная грудка с сыром и запеченной тыквой", 
    36: "Курица Гриль с овощами", 37: "Курица Карри с рисом", 38: "Курица по-азиатски с рисом", 
    39: "Курица по-мексикански", 40: "Курица Терияки с рисом", 41: "Люля куриные с гречкой", 
    42: "Оладьи куриные с пюре", 43: "Спагетти Карбонара", 44: "Утиная грудка с картофелем и розмарином", 
    45: "Фетучини Альфредо", 46: "Шницель в сырной панировке с пюре", 47: "Рыбная котлета с рисом и овощами", 
    48: "Судак на пару", 49: "Десерт Дубайский", 50: "Десерт Медовик", 51: "Десерт Черный лес", 
    52: "Рогалики с орехами", 53: "Блины с джемом", 54: "Блины с курицей", 55: "Блины с мясом", 
    56: "Блины с Нутеллой", 57: "Блины с творогом", 58: "Бургер", 59: "Каша Овсяная", 60: "Каша Рисовая", 
    61: "Кимбап Краб", 62: "Кимбап Курица", 63: "Кимбап Форель", 64: "Клаб сэндвич с Индейкой", 
    65: "Клаб сэндвич с Курицей", 66: "Клаб сэндвич с Салями", 67: "Клаб сэндвич с Тунцом", 
    68: "Клаб сэндвич с Форелью", 69: "Конвертики с грибами", 70: "Конвертики с запеченной курицей и сыром", 
    71: "Конвертики с мясом", 72: "Конвертики с творогом и вишней", 73: "Конвертики со шпинатом и сыром", 
    74: "Маффины ассорти (вишневый, шоколадный, цитрусовый)", 75: "Омлет ролл с курицей", 
    76: "Омлет ролл со шпинатом и сыром", 77: "ОНИГИРИ с тунцом", 78: "ОНИГИРИ Филадельфия", 
    79: "Панкейки с джемом", 80: "Пирожки с вишней", 81: "Пирожки с капустой", 82: "Пирожки с картошкой", 
    83: "Пирожки с мясом", 84: "Пирожки с рисом и яйцом", 85: "Пирожки с яблочным джемом", 
    86: "Роллы индейка с сыром", 87: "Роллы Цезарь", 88: "Сосиски в тесте", 89: "Сырники", 
    90: "Спринг-роллы с овощами и курицей", 91: "Сэндвич Чиабатта с курицей", 92: "Творожная запеканка", 
    93: "Шаурма куриная", 94: "Эчпочмаки", 95: "Смузи Витаминный микс", 96: "Смузи Тропический микс", 
    97: "Смузи Цитрусовый микс", 98: "Смузи Экзотический микс", 99: "Смузи Ягодный микс", 100: "Лимонад", 
    101: "Морс Клубника", 102: "Морс Клюква", 103: "Морс Смородина", 104: "Морс Шиповник", 105: "Напиток Айс-ти", 
    106: "Баклажаны по-корейски", 107: "Весенний", 108: "Винегрет", 109: "Винегрет с КАПУСТОЙ", 110: "Витаминка", 
    111: "Греческий", 112: "Домашняя Баклажанная Икра", 113: "Зеленый салат с заправкой", 114: "Королевский", 
    115: "Крабовый", 116: "Медовый с курицей", 117: "Мимоза", 118: "Морковча", 119: "Нежный с курицей", 
    120: "Огурцы по-корейски", 121: "Оливье с колбасой", 122: "Оливье с мясом", 123: "Сельдь под шубой", 
    124: "Цезарь с курицей", 125: "Борщ", 126: "Куриный бульон с лапшой", 127: "Мастава", 
    128: "Сливочный суп с рыбой и овощным миксом", 129: "Суп с фрикадельками", 130: "Сырный суп с овощами", 
    131: "Том Ям с креветками", 132: "Суп-пюре тыквенный", 133: "Чечевичный суп-пюре", 134: "Щи из щавеля"
}

def _parse_chunk(chunk_bytes: bytes, start_id: int, end_id: int) -> list[dict]:
    try:
        image = Image.open(io.BytesIO(chunk_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')

        sub_menu = {k: v for k, v in MENU_ITEMS_WITH_INDEX.items() if start_id <= k <= end_id}
        menu_str = "\n".join([f"{k}: {v}" for k, v in sub_menu.items()])

        prompt = (
            f"Это фрагмент накладной или чека (позиции с номерами от {start_id} по {end_id}).\n"
            "ЖЕСТКИЕ ПРАВИЛА:\n"
            "1. Количество (q) — это всегда небольшое число от 1 до 100.\n"
            "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО путать количество с ценой или суммами (например, 39000, 147000 — это деньги, их писать нельзя!).\n"
            "3. Для каждого порядкового номера (id) укажите точное индивидуальное количество из чека.\n\n"
            f"СПИСОК ДЛЯ ЭТОГО ФРАГМЕНТА:\n{menu_str}\n\n"
            "Верните ответ СТРОГО в формате JSON:\n"
            '{\n  "items": [\n    {"id": ' + str(start_id) + ', "q": число_от_1_до_100}\n  ]\n}'
        )
        
        response = client.chat.completions.create(
            model=MODEL_NAME,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Вы — точный бухгалтер. Считывайте строго индивидуальное количество (1-100) для каждого номера без путаницы с ценами."},
                {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}]}
            ],
            max_tokens=2000,
            temperature=0.0
        )

        raw_text = response.choices[0].message.content.strip()
        data = json.loads(raw_text.replace("```json", "").replace("```", "").strip())
        raw_items = data.get("items", []) if isinstance(data, dict) else data
        
        chunk_result = []
        for it in raw_items:
            item_id = it.get("id")
            try:
                qty = float(it.get("q", 1.0))
                # Xavfsizlik filtri: agar narxni o'qib yuborsa, 1 ga to'g'rilaymiz
                if qty > 100:
                    qty = 1.0
            except:
                qty = 1.0
                
            if item_id is not None:
                try:
                    int_id = int(item_id)
                    if int_id in MENU_ITEMS_WITH_INDEX:
                        chunk_result.append({"item_name": MENU_ITEMS_WITH_INDEX[int_id], "quantity": qty})
                except:
                    pass
        return chunk_result
    except Exception as e:
        print(f"❌ Chunk xatolik ({start_id}-{end_id}): {e}")
        return []

def parse_receipt_photo(image_bytes: bytes, branch_name: str = "", valid_menu_items: list[str] = None) -> list[dict]:
    """
    Chek rasmini 3 ta qismga bo'lib kesib, tartib raqamlari bo'yicha aniq o'qiydi.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
            
        width, height = image.size
        all_items = []

        # Uzun chek bo'lsa 3 ta bo'lakka kesamiz
        if height > width * 1.2:
            h_third = height / 3.0
            
            # 1-bo'lak (1 - 50)
            box1 = (0, 0, width, int(h_third * 1.1))
            buf1 = io.BytesIO()
            image.crop(box1).save(buf1, format="JPEG", quality=95)
            all_items.extend(_parse_chunk(buf1.getvalue(), 1, 50))
            
            # 2-bo'lak (51 - 100)
            box2 = (0, int(h_third * 0.9), width, int(h_third * 2.1))
            buf2 = io.BytesIO()
            image.crop(box2).save(buf2, format="JPEG", quality=95)
            all_items.extend(_parse_chunk(buf2.getvalue(), 51, 100))
            
            # 3-bo'lak (101 - 134)
            box3 = (0, int(h_third * 1.9), width, height)
            buf3 = io.BytesIO()
            image.crop(box3).save(buf3, format="JPEG", quality=95)
            all_items.extend(_parse_chunk(buf3.getvalue(), 101, 134))
        else:
            # Qisqa chek bo'lsa bittada o'qiymiz
            all_items.extend(_parse_chunk(image_bytes, 1, 134))

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