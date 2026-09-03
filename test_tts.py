import asyncio
import tempfile
import os

print("=== ДИАГНОСТИКА TTS ===\n")

# Тест 1: edge-tts
print("1. Тест edge-tts (нужен интернет)...")
try:
    import edge_tts
    test_file = tempfile.mktemp(suffix=".mp3")
    
    async def test():
        communicate = edge_tts.Communicate("Привет, это тест голоса", "ru-RU-DmitryNeural")
        await communicate.save(test_file)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test())
    loop.close()
    
    if os.path.exists(test_file) and os.path.getsize(test_file) > 0:
        size = os.path.getsize(test_file)
        print(f"   ✓ edge-tts работает! Файл создан: {size} байт")
        print(f"   Файл сохранён: {test_file}")
        print("   → Попробуйте открыть его вручную (двойной клик)")
    else:
        print("   ✗ edge-tts создал пустой файл")
except Exception as e:
    print(f"   ✗ edge-tts ошибка: {e}")

print()

# Тест 2: pygame
print("2. Тест pygame...")
try:
    import pygame
    pygame.mixer.init()
    print(f"   ✓ pygame mixer инициализирован: {pygame.mixer.get_init()}")
    
    if 'test_file' in locals() and os.path.exists(test_file):
        print("   → Пробую воспроизвести файл...")
        pygame.mixer.music.load(test_file)
        pygame.mixer.music.play()
        print("   ✓ Воспроизведение запущено (должны услышать голос)")
        import time
        time.sleep(3)
        pygame.mixer.quit()
except Exception as e:
    print(f"   ✗ pygame ошибка: {e}")

print()

# Тест 3: pyttsx3
print("3. Тест pyttsx3 (оффлайн)...")
try:
    import pyttsx3
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    print(f"   ✓ pyttsx3 работает! Найдено голосов: {len(voices)}")
    
    russian_found = False
    for voice in voices:
        if any(lang in voice.id.lower() for lang in ['russian', 'ru-ru', 'ru_ru']):
            print(f"   ✓ Найден русский голос: {voice.name}")
            russian_found = True
            break
    
    if not russian_found:
        print("   ⚠ Русский голос не найден, но pyttsx3 работает")
    
    print("   → Пробую озвучить...")
    engine.say("Привет, это тест pyttsx3")
    engine.runAndWait()
    engine.stop()
    print("   ✓ pyttsx3 отработал (должны услышать голос)")
except Exception as e:
    print(f"   ✗ pyttsx3 ошибка: {e}")

print("\n=== ДИАГНОСТИКА ЗАВЕРШЕНА ===")