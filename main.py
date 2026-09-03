import os
import platform
import logging
import time
import json
import numpy as np
from pathlib import Path
import threading
import queue
import wave
import asyncio
import tempfile
import requests
from datetime import datetime
import re
import webbrowser
import subprocess
import random
import math

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
logging.getLogger('tensorflow').setLevel(logging.ERROR)

import cv2
from PIL import ImageFont, ImageDraw, Image
from deepface import DeepFace

import sounddevice as sd
from resemblyzer import VoiceEncoder, preprocess_wav
import edge_tts
import pygame

# --- Проверка доступности модулей ---
try:
    from ddgs import DDGS

    SEARCH_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS

        SEARCH_AVAILABLE = True
    except ImportError:
        SEARCH_AVAILABLE = False

try:
    import g4f

    G4F_AVAILABLE = True
except ImportError:
    G4F_AVAILABLE = False

try:
    from vosk import Model, KaldiRecognizer

    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

# --- Настройки ---
KNOWN_FACES_FOLDER = 'known_faces'
CACHE_FILE = 'known_faces_cache.json'
KNOWN_VOICES_FOLDER = 'known_voices'
VOSK_MODEL_PATH = 'vosk-model-ru-0.42'

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff', '.tif'}
SAMPLE_RATE = 16000
VOICE_CONFIDENCE_THRESHOLD = 75.0

audio_queue = queue.Queue()
tts_queue = queue.Queue()
vosk_queue = queue.Queue()
chat_queue = queue.Queue()

current_speaker = "Неизвестно"
current_speaker_conf = 0.0
current_dominant_emotion = "neutral"
identity_folder = "Неизвестно"
face_status = "Неизвестно"
is_speaking = False
greeted_users = {}
GREETING_COOLDOWN = 120.0
last_ai_response_text = ""
best_raw_sim = 0.0
current_partial_text = ""

# === НАСТРОЙКИ ПОМОЩНИКА ===
WAKE_WORDS = ["джарвис", "алиса", "компьютер", "ассистент", "помощник", "jarvis", "джабер", "джавас", "джар вис"]
WAKE_WORD_ENABLED = False
CONVERSATION_HISTORY = []
MAX_HISTORY_LENGTH = 10
NOTES_FILE = "voice_notes.txt"
INITIAL_GREETING_DONE = False  # Флаг: было ли уже начальное приветствие


# ==================== УТИЛИТЫ ====================
def get_font(font_size):
    try:
        if platform.system() == 'Windows':
            return ImageFont.truetype("arial.ttf", font_size)
        else:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except IOError:
        return ImageFont.load_default()


def put_text_right(img, text, y, font_size=16, color_bgr=(0, 0, 100), margin=15):
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = get_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = img.shape[1] - text_width - margin
    color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
    draw.text((x, y), font=font, fill=color_rgb, text=text)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


# ==================== РАСШИРЕННАЯ СИСТЕМА КОМАНД ====================
def execute_command(command_type, params=None):
    try:
        # === ОТКРЫТИЕ ПРИЛОЖЕНИЙ WINDOWS ===
        if command_type == "open_browser":
            webbrowser.open("https://www.google.com")
            return "Открыл браузер"
        elif command_type == "open_youtube":
            webbrowser.open("https://www.youtube.com")
            return "Открыл YouTube"
        elif command_type == "open_calculator":
            if platform.system() == "Windows":
                subprocess.Popen("calc.exe")
            else:
                subprocess.Popen(["gnome-calculator"])
            return "Открыл калькулятор"
        elif command_type == "open_notepad":
            if platform.system() == "Windows":
                subprocess.Popen("notepad.exe")
            else:
                subprocess.Popen(["gedit"])
            return "Открыл блокнот"
        elif command_type == "open_explorer":
            if platform.system() == "Windows":
                subprocess.Popen("explorer.exe")
            return "Открыл проводник"
        elif command_type == "open_paint":
            if platform.system() == "Windows":
                subprocess.Popen("mspaint.exe")
            return "Открыл Paint"
        elif command_type == "open_snipping":
            if platform.system() == "Windows":
                subprocess.Popen("snippingtool.exe")
            return "Открыл ножницы"
        elif command_type == "open_word":
            if platform.system() == "Windows":
                subprocess.Popen("winword.exe")
            return "Открыл Word"
        elif command_type == "open_excel":
            if platform.system() == "Windows":
                subprocess.Popen("excel.exe")
            return "Открыл Excel"
        elif command_type == "open_powerpoint":
            if platform.system() == "Windows":
                subprocess.Popen("powerpnt.exe")
            return "Открыл PowerPoint"
        elif command_type == "open_settings":
            if platform.system() == "Windows":
                subprocess.Popen("ms-settings:")
            return "Открыл настройки"
        elif command_type == "open_control_panel":
            if platform.system() == "Windows":
                subprocess.Popen("control")
            return "Открыл панель управления"
        elif command_type == "open_task_manager":
            if platform.system() == "Windows":
                subprocess.Popen("taskmgr.exe")
            return "Открыл диспетчер задач"
        elif command_type == "open_cmd":
            if platform.system() == "Windows":
                subprocess.Popen("cmd.exe")
            return "Открыл командную строку"
        elif command_type == "open_camera":
            if platform.system() == "Windows":
                subprocess.Popen("start microsoft.windows.camera:")
            return "Открыл камеру"
        elif command_type == "open_recycle_bin":
            if platform.system() == "Windows":
                subprocess.Popen("explorer.exe shell:RecycleBinFolder")
            return "Открыл корзину"
        elif command_type == "open_clock":
            if platform.system() == "Windows":
                subprocess.Popen("start ms-clock:")
            return "Открыл часы"
        elif command_type == "open_store":
            if platform.system() == "Windows":
                subprocess.Popen("start ms-windows-store:")
            return "Открыл Microsoft Store"

        # === ВЕБ-СЕРВИСЫ ===
        elif command_type == "open_google":
            webbrowser.open("https://www.google.com")
            return "Открыл Google"
        elif command_type == "open_wikipedia":
            if params and "query" in params:
                query = params["query"].replace(" ", "_")
                webbrowser.open(f"https://ru.wikipedia.org/wiki/{query}")
                return f"Открыл Википедию: {params['query']}"
            webbrowser.open("https://ru.wikipedia.org")
            return "Открыл Википедию"
        elif command_type == "open_github":
            webbrowser.open("https://github.com")
            return "Открыл GitHub"
        elif command_type == "open_translate":
            if params and "text" in params:
                text = params["text"].replace(" ", "+")
                webbrowser.open(f"https://translate.google.com/?sl=auto&tl=en&text={text}")
                return f"Открыл переводчик для: {params['text']}"
            webbrowser.open("https://translate.google.com")
            return "Открыл переводчик"
        elif command_type == "search_google":
            if params and "query" in params:
                query = params["query"].replace(" ", "+")
                webbrowser.open(f"https://www.google.com/search?q={query}")
                return f"Ищу в Google: {params['query']}"
        elif command_type == "search_youtube":
            if params and "query" in params:
                query = params["query"].replace(" ", "+")
                webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
                return f"Ищу на YouTube: {params['query']}"
        elif command_type == "open_maps":
            if params and "location" in params:
                location = params["location"].replace(" ", "+")
                webbrowser.open(f"https://www.google.com/maps/search/{location}")
                return f"Открыл карту: {params['location']}"
            webbrowser.open("https://maps.google.com")
            return "Открыл Google Карты"

        # === ЗАМЕТКИ ===
        elif command_type == "save_note":
            if params and "text" in params:
                with open(NOTES_FILE, "a", encoding="utf-8") as f:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp}] {params['text']}\n")
                return f"Сохранил заметку: {params['text'][:50]}"
        elif command_type == "read_notes":
            if os.path.exists(NOTES_FILE):
                with open(NOTES_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last_notes = lines[-3:]
                        return "Последние заметки: " + "; ".join([l.strip() for l in last_notes])
            return "Заметок пока нет"

        # === РАЗВЛЕЧЕНИЯ ===
        elif command_type == "tell_joke":
            jokes = [
                "Почему программисты путают Хэллоуин и Рождество? Потому что Oct 31 = Dec 25!",
                "Что сказал JavaScript Java? Ты не в теме, бро!",
                "Как называется боязнь интернета? Веб-фобия!",
                "Почему программист ушел с работы? Потому что он не получил массивов удовольствия!",
                "В мире есть 10 типов людей: те, кто понимают двоичную систему, и те, кто не понимают."
            ]
            return random.choice(jokes)
        elif command_type == "flip_coin":
            result = random.choice(["орёл", "решка"])
            return f"Подбросил монетку: выпал {result}"
        elif command_type == "roll_dice":
            result = random.randint(1, 6)
            return f"Бросил кубик: выпало {result}"
        elif command_type == "random_number":
            if params and "max" in params:
                result = random.randint(1, int(params["max"]))
                return f"Случайное число от 1 до {params['max']}: {result}"
            return f"Случайное число: {random.randint(1, 100)}"
        elif command_type == "tell_fact":
            facts = [
                "Осьминоги имеют три сердца и голубую кровь.",
                "Мёд никогда не портится. Археологи находили мёд в египетских гробницах, которому более 3000 лет.",
                "Бананы на 50% совпадают по ДНК с человеком.",
                "Свет от Солнца до Земли идёт 8 минут 20 секунд.",
                "У человека около 100 тысяч волос на голове."
            ]
            return random.choice(facts)

        # === МАТЕМАТИКА ===
        elif command_type == "calculate":
            if params and "expression" in params:
                try:
                    expr = params["expression"]
                    # Безопасная замена слов на операторы
                    expr = expr.replace("плюс", "+").replace("минус", "-").replace("умножить на", "*").replace(
                        "разделить на", "/")
                    expr = expr.replace("x", "*").replace("х", "*")
                    # Разрешенные символы
                    allowed = set("0123456789+-*/.() ")
                    if all(c in allowed for c in expr):
                        result = eval(expr)
                        return f"Результат: {result}"
                    else:
                        return "Не удалось вычислить выражение"
                except Exception:
                    return "Ошибка вычисления"

        # === ИНФОРМАЦИЯ ===
        elif command_type == "weather":
            return "Рекомендую проверить Яндекс.Погоду или Gismeteo для точного прогноза"
        elif command_type == "news":
            webbrowser.open("https://news.google.com")
            return "Открыл Google Новости"
        elif command_type == "system_info":
            info = f"Система: {platform.system()} {platform.release()}. "
            info += f"Процессор: {platform.processor() or 'неизвестно'}. "
            info += f"Имя компьютера: {platform.node()}"
            return info
        elif command_type == "tell_time":
            now = datetime.now()
            return f"Сейчас {now.strftime('%H часов %M минут')}"
        elif command_type == "tell_date":
            now = datetime.now()
            months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                      "июля", "августа", "сентября", "октября", "ноября", "декабря"]
            month = months[now.month - 1]
            return f"Сегодня {now.day} {month} {now.year} года"
        elif command_type == "tell_day":
            days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
            today = datetime.now().weekday()
            return f"Сегодня {days[today]}"

        # === УПРАВЛЕНИЕ СИСТЕМОЙ ===
        elif command_type == "lock_screen":
            if platform.system() == "Windows":
                subprocess.Popen("rundll32.exe user32.dll,LockWorkStation")
            return "Блокирую экран"
        elif command_type == "shutdown":
            if platform.system() == "Windows":
                subprocess.Popen("shutdown /s /t 60")
            return "Компьютер выключится через минуту. Скажите 'отмена' чтобы отменить."
        elif command_type == "cancel_shutdown":
            if platform.system() == "Windows":
                subprocess.Popen("shutdown /a")
            return "Выключение отменено"
        elif command_type == "restart":
            if platform.system() == "Windows":
                subprocess.Popen("shutdown /r /t 60")
            return "Перезагрузка через минуту"
        elif command_type == "volume_up":
            return "Для изменения громкости используйте клавиши на клавиатуре"
        elif command_type == "volume_down":
            return "Для изменения громкости используйте клавиши на клавиатуре"
        elif command_type == "mute":
            return "Для отключения звука используйте клавиши на клавиатуре"

        # === ВЫХОД ===
        elif command_type == "exit":
            return "EXIT_PROGRAM"

    except Exception as e:
        return f"Не удалось выполнить команду: {e}"
    return None


def detect_command(text):
    text_lower = text.lower()

    # === ПРИЛОЖЕНИЯ ===
    if any(w in text_lower for w in
           ["открой браузер", "запусти браузер", "открой интернет", "открой хром"]): return "open_browser", None
    if any(w in text_lower for w in ["открой youtube", "ютуб", "youtube"]): return "open_youtube", None
    if any(w in text_lower for w in ["калькулятор", "посчитай"]): return "open_calculator", None
    if any(w in text_lower for w in ["блокнот", "notepad"]): return "open_notepad", None
    if any(w in text_lower for w in ["проводник", "папки", "файлы"]): return "open_explorer", None
    if any(w in text_lower for w in ["paint", "пейнт", "рисовалка"]): return "open_paint", None
    if any(w in text_lower for w in ["ножницы", "скриншот", "снимок экрана"]): return "open_snipping", None
    if any(w in text_lower for w in ["word", "ворд"]): return "open_word", None
    if any(w in text_lower for w in ["excel", "эксель", "таблицы"]): return "open_excel", None
    if any(w in text_lower for w in ["powerpoint", "презентация"]): return "open_powerpoint", None
    if any(w in text_lower for w in ["настройки", "параметры"]): return "open_settings", None
    if any(w in text_lower for w in ["панель управления"]): return "open_control_panel", None
    if any(w in text_lower for w in ["диспетчер задач"]): return "open_task_manager", None
    if any(w in text_lower for w in ["командная строка", "cmd", "терминал"]): return "open_cmd", None
    if any(w in text_lower for w in ["камера", "вебка"]): return "open_camera", None
    if any(w in text_lower for w in ["корзина"]): return "open_recycle_bin", None
    if any(w in text_lower for w in ["часы", "будильник"]): return "open_clock", None
    if any(w in text_lower for w in ["магазин приложений", "microsoft store"]): return "open_store", None

    # === ВЕБ-СЕРВИСЫ ===
    if any(w in text_lower for w in ["открой google", "гугл"]): return "open_google", None
    if any(w in text_lower for w in ["википедия", "wikipedia"]):
        query = text_lower.replace("википедия", "").replace("wikipedia", "").replace("найди в википедии", "").replace(
            "открой", "").strip()
        if query: return "open_wikipedia", {"query": query}
        return "open_wikipedia", None
    if any(w in text_lower for w in ["github", "гитхаб"]): return "open_github", None
    if "переведи" in text_lower or "перевод" in text_lower:
        text_to_translate = text_lower.replace("переведи", "").replace("перевод", "").strip()
        if text_to_translate: return "open_translate", {"text": text_to_translate}
        return "open_translate", None
    if "погугли" in text_lower or "найди в google" in text_lower:
        query = text_lower.replace("погугли", "").replace("найди в google", "").strip()
        if query: return "search_google", {"query": query}
    if any(w in text_lower for w in ["найди на ютубе", "посмотри на ютубе"]):
        query = text_lower.replace("найди на ютубе", "").replace("посмотри на ютубе", "").strip()
        if query: return "search_youtube", {"query": query}
    if any(w in text_lower for w in ["покажи на карте", "где находится", "открой карту"]):
        location = text_lower.replace("покажи на карте", "").replace("где находится", "").replace("открой карту",
                                                                                                  "").strip()
        if location: return "open_maps", {"location": location}
        return "open_maps", None

    # === ЗАМЕТКИ ===
    if any(w in text_lower for w in ["запиши", "сохрани заметку", "запомни"]):
        note_text = text_lower.replace("запиши", "").replace("сохрани заметку", "").replace("запомни", "").strip()
        if note_text: return "save_note", {"text": note_text}
    if any(w in text_lower for w in ["прочитай заметки", "покажи заметки", "что я записал"]): return "read_notes", None

    # === РАЗВЛЕЧЕНИЯ ===
    if any(w in text_lower for w in ["расскажи шутку", "анекдот", "пошути"]): return "tell_joke", None
    if any(w in text_lower for w in ["подбрось монетку", "монетка", "орёл или решка"]): return "flip_coin", None
    if any(w in text_lower for w in ["брось кубик", "кубик"]): return "roll_dice", None
    if any(w in text_lower for w in ["случайное число", "рандомное число"]):
        match = re.search(r'от\s*(\d+)\s*до\s*(\d+)', text_lower)
        if match:
            return "random_number", {"max": match.group(2)}
        return "random_number", {"max": "100"}
    if any(w in text_lower for w in ["расскажи факт", "интересный факт", "удиви меня"]): return "tell_fact", None

    # === МАТЕМАТИКА ===
    if any(w in text_lower for w in ["посчитай", "сколько будет", "вычисли"]):
        expr = text_lower.replace("посчитай", "").replace("сколько будет", "").replace("вычисли", "").strip()
        if expr: return "calculate", {"expression": expr}

    # === ИНФОРМАЦИЯ ===
    if any(w in text_lower for w in ["погода", "прогноз"]): return "weather", None
    if any(w in text_lower for w in ["новости", "что в мире"]): return "news", None
    if any(w in text_lower for w in
           ["информация о системе", "характеристики", "что за компьютер"]): return "system_info", None
    if any(w in text_lower for w in ["который час", "сколько времени", "время"]): return "tell_time", None
    if any(w in text_lower for w in ["какое число", "какая дата", "сегодня"]): return "tell_date", None
    if any(w in text_lower for w in ["какой день недели", "день недели"]): return "tell_day", None

    # === УПРАВЛЕНИЕ ===
    if any(w in text_lower for w in ["заблокируй экран", "заблокируй компьютер"]): return "lock_screen", None
    if any(w in text_lower for w in ["выключи компьютер", "заверши работу"]): return "shutdown", None
    if any(w in text_lower for w in ["отмена выключения", "отмени выключение"]): return "cancel_shutdown", None
    if any(w in text_lower for w in ["перезагрузи", "перезагрузка"]): return "restart", None
    if any(w in text_lower for w in ["громче", "увеличь громкость"]): return "volume_up", None
    if any(w in text_lower for w in ["тише", "уменьши громкость"]): return "volume_down", None
    if any(w in text_lower for w in ["без звука", "выключи звук", "mute"]): return "mute", None

    # === ВЫХОД ===
    if any(w in text_lower for w in ["выход", "выключи программу", "закрой программу"]): return "exit", None

    return None, None


# ==================== УМНЫЙ ПОИСК ====================
def extract_keywords(text):
    text = text.lower()
    keywords = []
    if any(w in text for w in ["погод", "градус", "температур", "дождь", "снег"]): keywords.append("погода")
    if "воронеж" in text: keywords.append("воронеж")
    if "москв" in text: keywords.append("москва")
    if "илон" in text or "маск" in text: keywords.append("илон маск")
    if "вратар" in text: keywords.append("лучший вратарь")

    if not keywords:
        stop_words = {"один", "формат", "алу", "а", "и", "в", "на", "по", "с", "что", "это", "как", "то", "же", "но",
                      "или", "сурман", "фадин"}
        words = text.split()
        unique_words = [w for w in words if w not in stop_words and len(w) > 2]
        seen = set()
        result = [w for w in unique_words if not (w in seen or seen.add(w))]
        return " ".join(result) if result else text
    return " ".join(keywords)


def is_valid_russian_result(text):
    if not text: return False
    if not re.search('[а-яА-ЯёЁ]', text): return False
    spam_words = ["forex", "casino", "buy now", "click here", "trading", "broker", "купить сейчас", "скачать бесплатно"]
    if any(word in text.lower() for word in spam_words): return False
    return True


def search_internet(query, max_results=3):
    if not SEARCH_AVAILABLE: return None
    try:
        clean_query = extract_keywords(query)
        print(f"  🔍 Ищу: '{clean_query}'")
        with DDGS() as ddgs:
            results = list(ddgs.text(clean_query, max_results=max_results))
            if results:
                valid_results = []
                for r in results:
                    combined = f"{r.get('title', '')}: {r.get('body', '')}"
                    if is_valid_russian_result(combined):
                        valid_results.append(combined)
                if valid_results:
                    return "\n".join(valid_results)
    except Exception as e:
        print(f"  ✗ Ошибка поиска: {e}")
    return None


# ==================== ОБРАБОТКА ЗАПРОСОВ ====================
def add_to_history(role, message):
    global CONVERSATION_HISTORY
    CONVERSATION_HISTORY.append({"role": role, "message": message})
    if len(CONVERSATION_HISTORY) > MAX_HISTORY_LENGTH:
        CONVERSATION_HISTORY = CONVERSATION_HISTORY[-MAX_HISTORY_LENGTH:]


def get_ai_response(user_text, emotion, face_name):
    global last_ai_response_text

    original_text = user_text
    user_text = user_text.lower().strip()

    print(f"🎯 [DEBUG] Исходный текст от Vosk: '{original_text}'")

    if not user_text or len(user_text) < 2:
        return None

    if last_ai_response_text:
        common_words = set(user_text.split()) & set(last_ai_response_text.lower().split())
        if len(common_words) >= 3:
            print("  [ИИ] Игнорирую: эхо.")
            return None

    words = user_text.split()
    if len(words) > 3 and (len(set(words)) < len(words) * 0.6):
        print("  [ИИ] Игнорирую: заикание/шум.")
        return None

    if len(words) <= 2 and any(wake in user_text for wake in WAKE_WORDS):
        print("  [ИИ] Обнаружен только вызов по имени. Отвечаю: 'Слушаю вас'")
        return "Слушаю вас. Чем могу помочь?"

    for wake in WAKE_WORDS:
        if wake in user_text:
            user_text = user_text.replace(wake, "").strip()
            print(f"  [Wake] Имя '{wake}' удалено из команды. Осталось: '{user_text}'")
            break

    if len(user_text) < 3:
        return None

    add_to_history("user", user_text)
    name_str = f", {face_name}" if face_name and face_name != "Неизвестно" else ""

    command_type, params = detect_command(user_text)
    if command_type:
        result = execute_command(command_type, params)
        if result:
            if result == "EXIT_PROGRAM":
                speak("Завершаю работу")
                time.sleep(1)
                os._exit(0)
            add_to_history("assistant", result)
            return result

    search_triggers = ["погод", "кто такой", "что такое", "расскажи о", "новости", "курс", "цена", "воронеж", "москв",
                       "илон", "маск", "вратар", "лучш", "футбол", "хоккей", "игрок", "найди", "информация", "история",
                       "биография", "как зовут", "сколько лет", "объясни", "определи"]
    needs_search = any(trigger in user_text for trigger in search_triggers)

    if any(trigger in user_text for trigger in ["как дела", "кто ты", "спасибо", "пока", "привет", "шутк", "анекдот"]):
        needs_search = False

    response = None

    if needs_search and SEARCH_AVAILABLE:
        search_results = search_internet(user_text, max_results=3)
        if search_results:
            if G4F_AVAILABLE:
                try:
                    history_context = "\n".join([f"{m['role']}: {m['message']}" for m in CONVERSATION_HISTORY[-5:]])
                    res = g4f.ChatCompletion.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system",
                             "content": "Ты полезный ассистент. Отвечай ОЧЕНЬ КРАТКО (1-2 предложения)."},
                            {"role": "user",
                             "content": f"История:\n{history_context}\n\nВопрос: '{user_text}'\n\nКонтекст:\n{search_results}"}
                        ],
                        timeout=8
                    )
                    if res and len(str(res)) > 10:
                        response = str(res).strip()
                except Exception as e:
                    print(f"  ✗ Ошибка g4f: {e}")

            if not response:
                first_valid = search_results.split('\n')[0]
                clean_text = first_valid.split(':', 1)[-1].strip() if ':' in first_valid else first_valid
                if len(clean_text) > 20 and is_valid_russian_result(clean_text):
                    response = f"Нашла в интернете: {clean_text[:150]}"

    if not response:
        emotion_lower = emotion.lower()
        if any(w in user_text for w in ["привет", "здравствуй", "добрый"]):
            responses = [f"Здравствуйте{name_str}! Рад вас видеть.", f"Приветствую{name_str}! Чем могу помочь?"]
            response = random.choice(responses) if emotion_lower not in ['angry',
                                                                         'sad'] else f"Здравствуйте{name_str}. Вижу, вы расстроены."
        elif any(w in user_text for w in ["как дела", "как ты"]):
            response = "Мои модули работают стабильно. А как ваше?"
        elif any(w in user_text for w in ["кто ты", "умеешь", "можешь"]):
            response = "Я нейросетевая система. Распознаю лица, эмоции, выполняю команды и ищу информацию."
        elif any(w in user_text for w in ["время", "час", "который час"]):
            response = f"Прямо сейчас {datetime.now().strftime('%H часов %M минут')}."
        elif any(w in user_text for w in ["дата", "какое число", "сегодня"]):
            response = f"Сегодня {datetime.now().strftime('%d %B %Y года')}."
        elif any(w in user_text for w in ["спасибо", "благодарю"]):
            response = random.choice(["Всегда пожалуйста!", "Рад помочь!", "Обращайтесь!"])
        elif any(w in user_text for w in ["пока", "до свидания"]):
            response = random.choice(["До свидания!", "Всего доброго!", "Хорошего дня!"])
        elif any(w in user_text for w in ["шутк", "анекдот", "рассмеши"]):
            response = execute_command("tell_joke")
        elif "вратар" in user_text:
            response = "Лучшими вратарями в истории часто называют Льва Яшина, Буффона и Нойера. В хоккее — Третьяка."
        elif "погод" in user_text:
            response = "Для точного прогноза погоды рекомендую использовать Яндекс.Погоду или Gismeteo."
        elif "илон" in user_text or "маск" in user_text:
            response = "Илон Маск — предприниматель, основатель Tesla и SpaceX."
        elif any(w in user_text for w in ["помощь", "помоги", "что умеешь"]):
            response = "Я могу: открывать приложения, искать информацию, рассказывать шутки, сохранять заметки, считать, управлять системой и многое другое."
        else:
            response = "Я вас услышала, но не смогла найти точный ответ. Попробуйте перефразировать или дайте команду."

    last_ai_response_text = response
    add_to_history("assistant", response)
    return response


# ==================== ПРИВЕТСТВИЕ С УЧЕТОМ ЭМОЦИИ ====================
def generate_initial_greeting(face_name, emotion):
    """Генерирует персонализированное приветствие в начале сеанса"""
    emotion_lower = emotion.lower()
    name_str = f", {face_name}" if face_name and face_name != "Неизвестно" else ""

    # Приветствие в зависимости от эмоции
    if emotion_lower in ['happy']:
        greetings = [
            f"Добрый день{name_str}! Вижу, у вас отличное настроение. Чем могу помочь?",
            f"Здравствуйте{name_str}! Рад видеть вас в хорошем настроении!",
            f"Приветствую{name_str}! Ваше настроение заразительно!"
        ]
    elif emotion_lower in ['sad']:
        greetings = [
            f"Здравствуйте{name_str}. Вижу, что-то вас расстроило. Я здесь, если нужна помощь.",
            f"Добрый день{name_str}. Надеюсь, я смогу поднять вам настроение.",
            f"Приветствую{name_str}. Чем могу помочь в этот непростой момент?"
        ]
    elif emotion_lower in ['angry']:
        greetings = [
            f"Здравствуйте{name_str}. Вижу, вы чем-то недовольны. Постараюсь помочь.",
            f"Добрый день{name_str}. Чем могу быть полезен?",
            f"Приветствую{name_str}. Готов выслушать и помочь."
        ]
    elif emotion_lower in ['fear', 'surprise']:
        greetings = [
            f"Здравствуйте{name_str}. Не волнуйтесь, я здесь чтобы помочь.",
            f"Добрый день{name_str}. Чем могу помочь?",
            f"Приветствую{name_str}. Я к вашим услугам."
        ]
    else:  # neutral или другие
        greetings = [
            f"Добрый день{name_str}! Система активирована и готова к работе.",
            f"Здравствуйте{name_str}! Рад вас видеть. Чем могу помочь?",
            f"Приветствую{name_str}! Я вас слушаю."
        ]

    # Добавляем информацию о времени
    hour = datetime.now().hour
    if 5 <= hour < 12:
        time_greeting = "Доброе утро! "
    elif 12 <= hour < 17:
        time_greeting = "Добрый день! "
    elif 17 <= hour < 22:
        time_greeting = "Добрый вечер! "
    else:
        time_greeting = "Доброй ночи! "

    return time_greeting + random.choice(greetings)


# ==================== TTS С ИСПРАВЛЕНИЯМИ ====================
def tts_worker():
    global is_speaking
    print("✓ TTS поток запущен")
    while True:
        try:
            while tts_queue.qsize() > 3:
                try:
                    old_msg = tts_queue.get_nowait()
                    print(f"  [TTS] Пропускаю старое сообщение: '{old_msg[:30]}...'")
                except queue.Empty:
                    break

            message = tts_queue.get(timeout=1)
            if message is None:
                break

            if not chat_queue.empty():
                print("  [TTS] Прервано: новое сообщение в очереди")
                continue

            print(f"\n🔊 [TTS] Озвучка: '{message}'")
            tmp_path = tempfile.mktemp(suffix=".mp3")
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                communicate = edge_tts.Communicate(message, "ru-RU-DmitryNeural")
                loop.run_until_complete(communicate.save(tmp_path))
                loop.close()
            except Exception as e:
                print(f"  ✗ Ошибка edge-tts: {e}")
                continue

            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 500:
                continue

            is_speaking = True
            sound_played = False
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=2048)
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                clock = pygame.time.Clock()

                while pygame.mixer.music.get_busy():
                    if not chat_queue.empty():
                        pygame.mixer.music.stop()
                        print("  [TTS] Воспроизведение прервано")
                        break
                    clock.tick(10)
                else:
                    sound_played = True
            except Exception:
                pass

            if not sound_played:
                try:
                    os.startfile(tmp_path)
                    time.sleep(len(message) * 0.15 + 1.5)
                    sound_played = True
                except Exception:
                    pass

            is_speaking = False
            time.sleep(0.5)
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        except queue.Empty:
            continue
        except Exception as e:
            is_speaking = False


def speak(text):
    if text and text.strip():
        tts_queue.put(text)


# ==================== VOSK ====================
def vosk_worker():
    global is_speaking, current_partial_text
    if not VOSK_AVAILABLE or not os.path.exists(VOSK_MODEL_PATH):
        print(f"⚠ Vosk недоступна или модель не найдена: {VOSK_MODEL_PATH}")
        return
    try:
        model = Model(VOSK_MODEL_PATH)
        recognizer = KaldiRecognizer(model, SAMPLE_RATE)
        print(f"✓ Vosk загружена (модель: {VOSK_MODEL_PATH})")

        last_partial_time = 0
        last_voice_time = time.time()
        SILENCE_TIMEOUT = 1.5
        ENERGY_THRESHOLD = 300

        while True:
            try:
                chunk = vosk_queue.get(timeout=1)

                if is_speaking:
                    recognizer.Reset()
                    current_partial_text = ""
                    last_voice_time = time.time()
                    continue

                energy = np.abs(chunk).mean()
                has_voice = energy > ENERGY_THRESHOLD

                if has_voice:
                    last_voice_time = time.time()

                if has_voice or (time.time() - last_voice_time) < 0.8:
                    if recognizer.AcceptWaveform(chunk.tobytes()):
                        result = json.loads(recognizer.Result())
                        text = result.get('text', '').strip().lower()
                        current_partial_text = ""
                        if text and len(text) > 2:
                            print(f"🎤 Распознано: '{text}'")
                            chat_queue.put(text)

                current_time = time.time()
                if current_time - last_partial_time >= 0.4:
                    last_partial_time = current_time
                    try:
                        partial = json.loads(recognizer.PartialResult())
                        partial_text = partial.get('partial', '').strip()
                        if partial_text:
                            current_partial_text = partial_text
                            print(f"  ...слушаю: {partial_text}          ", end='\r')
                    except Exception:
                        pass

                if current_time - last_voice_time > SILENCE_TIMEOUT:
                    try:
                        final = json.loads(recognizer.FinalResult())
                        text = final.get('text', '').strip().lower()
                        current_partial_text = ""
                        if text and len(text) > 2:
                            print(f"🎤 Распознано (final): '{text}'")
                            chat_queue.put(text)
                    except Exception:
                        pass
                    recognizer.Reset()
                    last_voice_time = time.time()

            except queue.Empty:
                continue
    except Exception as e:
        print(f"✗ Ошибка Vosk: {e}")


def chat_worker():
    last_reply_time = 0
    while True:
        try:
            text = chat_queue.get(timeout=1)
            if time.time() - last_reply_time < 2.0:
                continue

            wait_count = 0
            while is_speaking and wait_count < 10:
                time.sleep(0.5)
                wait_count += 1

            if is_speaking:
                print("  [Пропуск] Ответ пропущен: TTS занят")
                continue

            response = get_ai_response(text, current_dominant_emotion, identity_folder)
            if response:
                print(f"💬 Ответ: {response}")
                speak(response)
                last_reply_time = time.time()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"✗ Ошибка чата: {e}")


# ==================== РАСПОЗНАВАНИЕ ЛИЦ ====================
def safe_represent(img_path, model_name='Facenet'):
    try:
        return DeepFace.represent(img_path=img_path, model_name=model_name, enforce_detection=False, silent=True)
    except TypeError:
        pass
    try:
        return DeepFace.represent(img_path=img_path, model_name=model_name, enforce_detection=False, verbose=False)
    except TypeError:
        pass
    return DeepFace.represent(img_path=img_path, model_name=model_name, enforce_detection=False)


def safe_analyze(img_path):
    try:
        return DeepFace.analyze(img_path=img_path, actions=['emotion'], enforce_detection=False, silent=True)
    except TypeError:
        pass
    try:
        return DeepFace.analyze(img_path=img_path, actions=['emotion'], enforce_detection=False, verbose=False)
    except TypeError:
        pass
    return DeepFace.analyze(img_path=img_path, actions=['emotion'], enforce_detection=False)


def find_image_files(folder_path):
    folder = Path(folder_path)
    if not folder.exists(): return []
    return [f for f in folder.rglob('*') if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]


def load_known_faces(folder_path=KNOWN_FACES_FOLDER, cache_file=CACHE_FILE, ask_cache=True):
    print(f"\n=== Загрузка лиц ===")
    if os.path.exists(cache_file) and ask_cache:
        use_cache = input("Использовать кэш лиц? (y/n): ").strip().lower()
        if use_cache != 'n':
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data and len(data) > 0:
                    print(f"✓ Загружено {len(data)} лиц из кэша.")
                    return data
            except Exception:
                pass
        else:
            try:
                os.remove(cache_file)
            except Exception:
                pass

    folder = Path(folder_path)
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        return None

    image_files = find_image_files(folder_path)
    if not image_files: return None

    print(f"✓ Найдено изображений: {len(image_files)}")
    known_faces = []
    for img_path in image_files:
        try:
            embedding_objs = safe_represent(str(img_path), model_name='Facenet')
            if embedding_objs:
                for idx, emb_obj in enumerate(embedding_objs):
                    known_faces.append({'source': img_path.name, 'folder_name': img_path.parent.name,
                                        'embedding': emb_obj['embedding']})
                    print(f"  ✓ {img_path.name}")
        except Exception:
            pass

    if known_faces:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(known_faces, f, ensure_ascii=False)
    return known_faces if known_faces else None


def identify_face_with_deepface(test_embedding, known_faces):
    global best_raw_sim
    test_vec = np.array(test_embedding)
    best_similarity, best_match = -1, None
    for known_face in known_faces:
        known_vec = np.array(known_face['embedding'])
        cosine_sim = np.dot(test_vec, known_vec) / (np.linalg.norm(test_vec) * np.linalg.norm(known_vec))
        if cosine_sim > best_similarity:
            best_similarity = cosine_sim
            best_match = known_face

    similarity_percent = ((best_similarity + 1) / 2) * 100
    best_raw_sim = best_similarity

    if similarity_percent >= 85.0:
        return {'status': 'Свой', 'percent': similarity_percent, 'folder_name': best_match['folder_name']}
    return {'status': 'Чужой', 'percent': 100 - similarity_percent, 'folder_name': None}


def load_known_voices(folder_path=KNOWN_VOICES_FOLDER):
    folder = Path(folder_path)
    if not folder.exists():
        folder.mkdir(parents=True, exist_ok=True)
        return None
    wav_files = list(folder.rglob('*.wav'))
    if not wav_files: return None
    encoder = VoiceEncoder()
    known_voices = []
    for wav_path in wav_files:
        try:
            wav = preprocess_wav(wav_path)
            embedding = encoder.embed_utterance(wav)
            known_voices.append({'name': wav_path.parent.name, 'embedding': embedding})
        except Exception:
            pass
    return known_voices if known_voices else None


def audio_callback(indata, frames, time_info, status):
    audio_queue.put(indata[:, 0].copy())
    if VOSK_AVAILABLE:
        float_data = indata[:, 0]
        float_data = np.clip(float_data, -1.0, 1.0)
        int16_data = (float_data * 32767).astype(np.int16)
        vosk_queue.put(int16_data)


def audio_worker(known_voices, encoder):
    global current_speaker, current_speaker_conf, is_speaking
    buffer = []
    process_interval = 2.0
    last_process_time = time.time()
    while True:
        try:
            chunk = audio_queue.get(timeout=1)
            if is_speaking:
                buffer.clear()
                continue
            buffer.extend(chunk)
            current_time = time.time()
            if current_time - last_process_time >= process_interval and len(buffer) >= SAMPLE_RATE * 1:
                last_process_time = current_time
                audio_np = np.array(buffer, dtype=np.float32)
                if known_voices and encoder:
                    try:
                        wav = preprocess_wav(audio_np, source_sr=SAMPLE_RATE)
                        if len(wav) > 0:
                            embedding = encoder.embed_utterance(wav)
                            best_sim, best_name = -1, "Неизвестно"
                            for known in known_voices:
                                sim = np.dot(embedding, known['embedding']) / (
                                        np.linalg.norm(embedding) * np.linalg.norm(known['embedding']))
                                if sim > best_sim:
                                    best_sim = sim
                                    best_name = known['name']
                            conf = ((best_sim + 1) / 2) * 100
                            current_speaker_conf = conf
                            current_speaker = best_name if conf >= VOICE_CONFIDENCE_THRESHOLD else "Неизвестно"
                    except Exception:
                        pass
                buffer = buffer[-int(SAMPLE_RATE * 0.5):]
        except queue.Empty:
            continue


# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================
def main():
    global current_dominant_emotion, identity_folder, face_status, greeted_users, best_raw_sim, current_partial_text, INITIAL_GREETING_DONE

    print(f"\n{'=' * 45}")
    print(f" СТАТУС МОДУЛЕЙ")
    print(f"{'=' * 45}")
    print(f"🔍 Поиск (ddgs): {'✅' if SEARCH_AVAILABLE else '❌ pip install ddgs'}")
    print(f"🤖 G4F:   {'✅' if G4F_AVAILABLE else '❌'}")
    print(f"🎤 Vosk:  {'✅' if VOSK_AVAILABLE else '❌'}")
    print(f"📁 Модель: {VOSK_MODEL_PATH} ({'✅ найдена' if os.path.exists(VOSK_MODEL_PATH) else '❌ НЕ НАЙДЕНА'})")
    print(f"🔊 Озвучка: ✅ ВКЛЮЧЕНА")
    print(f"{'=' * 45}\n")

    known_faces = load_known_faces(ask_cache=True)
    if known_faces is None:
        print("\n⚠ Нет базы лиц.")
        input("Нажмите Enter...")
        return

    print("\n=== Инициализация ===")
    known_voices = load_known_voices()
    voice_encoder = VoiceEncoder() if known_voices else None

    threading.Thread(target=tts_worker, daemon=True).start()
    threading.Thread(target=audio_worker, args=(known_voices, voice_encoder), daemon=True).start()
    if VOSK_AVAILABLE: threading.Thread(target=vosk_worker, daemon=True).start()
    threading.Thread(target=chat_worker, daemon=True).start()

    audio_stream = None
    try:
        audio_stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=audio_callback,
                                      blocksize=int(SAMPLE_RATE * 0.1))
        audio_stream.start()
        print("✓ Микрофон активирован.")
    except Exception as e:
        print(f"✗ Ошибка микрофона: {e}")

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("⚠ DirectShow не сработал, пробую стандартный бэкенд...")
        cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Ошибка: Не удалось открыть веб-камеру.")
        print("💡 Подсказка: Закрой другие приложения, использующие камеру.")
        input("Нажми Enter для выхода...")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    print("\n=== Запуск ===")
    print("Клавиши: q - выход | r - кэш | c - очистить | v - голос")
    print("\n📋 ДОСТУПНЫЕ КОМАНДЫ:")
    print("  • Приложения: блокнот, калькулятор, проводник, paint, word, excel, powerpoint")
    print("  • Настройки, панель управления, диспетчер задач, командная строка")
    print("  • Веб: google, youtube, wikipedia, github, переводчик, карты")
    print("  • Развлечения: шутка, монетка, кубик, случайное число, факт")
    print("  • Информация: время, дата, день недели, погода, новости")
    print("  • Система: заблокировать экран, выключить, перезагрузить")
    print("  • Заметки: запиши, покажи заметки")
    print("  • Математика: посчитай [выражение]")

    emotion_translation = {'happy': 'Радость', 'fear': 'Испуг', 'surprise': 'Удивление', 'sad': 'Грусть',
                           'angry': 'Злость', 'neutral': 'Спокойствие', 'disgust': 'Отвращение'}
    last_analysis_time = 0
    analysis_interval = 1.5
    current_emotions = {}

    identity_info = "Неизвестно"
    identity_folder = "Неизвестно"
    face_status = "Неизвестно"
    current_dominant_emotion = "neutral"

    DEBUG_COLOR = (0, 0, 0)

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("⚠ Не удалось получить кадр с камеры")
                time.sleep(0.1)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))
            y_offset = 15

            if len(faces) > 0:
                for (x, y, w, h) in faces:
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    face_roi = frame[y:y + h, x:x + w]

                    current_time = time.time()
                    if current_time - last_analysis_time > analysis_interval:
                        last_analysis_time = current_time

                        try:
                            analysis = safe_analyze(face_roi)
                            if analysis and len(analysis) > 0:
                                raw_emotions = analysis[0].get('emotion', {})
                                current_emotions = {k: v for k, v in raw_emotions.items() if k in emotion_translation}
                                current_dominant_emotion = max(current_emotions,
                                                               key=current_emotions.get) if current_emotions else 'neutral'

                                # === ПРИВЕТСТВИЕ ТОЛЬКО ОДИН РАЗ В НАЧАЛЕ СЕАНСА ===
                                if not INITIAL_GREETING_DONE:
                                    INITIAL_GREETING_DONE = True
                                    # Определяем имя
                                    try:
                                        embedding_objs = safe_represent(face_roi, model_name='Facenet')
                                        if embedding_objs and len(embedding_objs) > 0:
                                            result = identify_face_with_deepface(embedding_objs[0]['embedding'],
                                                                                 known_faces)
                                            if result['status'] == 'Свой':
                                                identity_folder = result['folder_name']
                                    except Exception:
                                        pass

                                    # Генерируем и говорим приветствие
                                    greeting = generate_initial_greeting(identity_folder, current_dominant_emotion)
                                    print(f"\n👋 ПРИВЕТСТВИЕ: {greeting}")
                                    speak(greeting)
                        except Exception:
                            current_emotions = {}
                            current_dominant_emotion = 'neutral'

                        try:
                            embedding_objs = safe_represent(face_roi, model_name='Facenet')
                            if embedding_objs and len(embedding_objs) > 0:
                                result = identify_face_with_deepface(embedding_objs[0]['embedding'], known_faces)
                                face_status = result['status']
                                identity_folder = result['folder_name'] if face_status == 'Свой' else "Неизвестно"
                                identity_info = f"Свой: {result['percent']:.1f}%" if face_status == 'Свой' else f"Чужой: {result['percent']:.1f}%"
                            else:
                                identity_info = "Лицо не распознано"
                                face_status = "Неизвестно"
                                identity_folder = "Неизвестно"
                                best_raw_sim = 0.0
                        except Exception:
                            identity_info = "Ошибка анализа"
                            best_raw_sim = 0.0

                    status_color = (0, 255, 0) if 'Свой' in identity_info else (0, 0, 255)
                    frame = put_text_right(frame, identity_info, y_offset, font_size=18, color_bgr=status_color)
                    y_offset += 25

                    if identity_folder and identity_folder != "Неизвестно":
                        frame = put_text_right(frame, f"Пользователь: {identity_folder}", y_offset, font_size=14,
                                               color_bgr=(255, 0, 0))
                        y_offset += 22

                    if current_emotions:
                        sorted_emotions = sorted(current_emotions.items(), key=lambda item: item[1], reverse=True)
                        for i, (key, percentage) in enumerate(sorted_emotions[:3]):
                            color = (0, 0, 100) if i == 0 else (255, 255, 255)
                            frame = put_text_right(frame, f"{emotion_translation.get(key, key)}: {percentage:.1f}%",
                                                   y_offset, font_size=16, color_bgr=color)
                            y_offset += 22
                    y_offset += 10
            else:
                frame = put_text_right(frame, "Лицо не обнаружено", y_offset, font_size=16, color_bgr=(128, 128, 128))
                y_offset += 30
                face_status = "Нет_лица"
                current_dominant_emotion = "neutral"
                identity_info = "Неизвестно"
                identity_folder = "Неизвестно"
                current_emotions = {}
                best_raw_sim = 0.0

            voice_color = (0, 255, 255) if current_speaker != "Неизвестно" else (0, 0, 255)
            voice_text = f"Голос: {current_speaker} ({current_speaker_conf:.1f}%)"
            frame = put_text_right(frame, voice_text, y_offset, font_size=18, color_bgr=voice_color)

            if is_speaking:
                status_text = "Govoryu..."
                status_color = (0, 165, 255)
            elif VOSK_AVAILABLE and os.path.exists(VOSK_MODEL_PATH):
                status_text = "Slushayu..."
                status_color = (0, 255, 0)
            else:
                status_text = "Vosk ne zagrujena"
                status_color = (0, 0, 255)

            overlay = frame.copy()
            cv2.rectangle(overlay, (10, 10), (230, 50), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)
            cv2.putText(frame, status_text, (20, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

            debug_y = frame.shape[0] - 15
            line_h = 18
            margin = 15

            debug_lines = []
            if face_status != "Неизвестно" and face_status != "Нет_лица":
                calc_pct = ((best_raw_sim + 1) / 2) * 100
                debug_lines.append(f"Cosine Similarity: {best_raw_sim:.4f}")
                debug_lines.append(f"Formula: (({best_raw_sim:.4f} + 1) / 2) * 100 = {calc_pct:.1f}%")
                debug_lines.append(f"Threshold: 85.0% | Result: {face_status.upper()}")
                debug_lines.append("")

            if current_emotions:
                debug_lines.append("--- Emotion Softmax ---")
                sorted_emo = sorted(current_emotions.items(), key=lambda item: item[1], reverse=True)[:2]
                for key, pct in sorted_emo:
                    emo_name = emotion_translation.get(key, key)
                    debug_lines.append(f"{emo_name}: {pct:.1f}% (Raw Output)")

            if debug_lines:
                font = get_font(12)
                max_width = 0
                for line in debug_lines:
                    bbox = font.getbbox(line)
                    w = bbox[2] - bbox[0]
                    if w > max_width:
                        max_width = w

                padding = 8
                x1 = frame.shape[1] - max_width - margin - padding
                y1 = debug_y - (len(debug_lines) * line_h) - padding
                x2 = frame.shape[1] - margin + padding
                y2 = debug_y + line_h

                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(frame.shape[1], x2)
                y2 = min(frame.shape[0], y2)

                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 255, 255), -1)
                alpha = 0.6
                cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

                for line in debug_lines:
                    if line:
                        frame = put_text_right(frame, line, debug_y, font_size=12, color_bgr=DEBUG_COLOR)
                    debug_y -= line_h

            cv2.imshow('Super Neural Assistant (with Math)', frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                known_faces = load_known_faces(ask_cache=True)
                if known_faces: speak("Кэш обновлен")
            elif key == ord('c'):
                if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
                known_faces = load_known_faces(ask_cache=False)
                if known_faces: speak("База пересоздана")
            elif key == ord('v'):
                print("\n=== Запись голоса (3 сек) ===")
                speak("Говорите")
                time.sleep(1)
                try:
                    recording = sd.rec(int(3 * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
                    sd.wait()
                    name = input("Имя (ИмяПапки/Файл): ").strip()
                    if name:
                        if not name.lower().endswith('.wav'): name += '.wav'
                        filepath = Path(KNOWN_VOICES_FOLDER) / name
                        filepath.parent.mkdir(parents=True, exist_ok=True)
                        with wave.open(str(filepath), 'wb') as wf:
                            wf.setnchannels(1)
                            wf.setsampwidth(2)
                            wf.setframerate(SAMPLE_RATE)
                            wf.writeframes(recording.tobytes())
                        print(f"✓ Сохранено: {filepath}")
                        known_voices = load_known_voices()
                except Exception as e:
                    print(f"✗ Ошибка: {e}")

    finally:
        tts_queue.put(None)
        if audio_stream:
            audio_stream.stop()
            audio_stream.close()
        cap.release()
        cv2.destroyAllWindows()
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        print("\nПрограмма завершена.")


if __name__ == "__main__":
    main()
