import asyncio
import os
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# ============================================
# ⚙️  НАСТРОЙКИ (меняйте здесь!)
# ============================================

# Ваши данные API (обязательно введите)
API_ID = 36590443          # Вставьте свой API ID
API_HASH = '401ed4b74b5d1d57feb7aa72c918e361'  # Вставьте свой API Hash
PHONE_NUMBER = '+18255909247'  # Номер для авторизации

# ⚠️  Режим работы:
# Поставьте 'netu' чтобы запросить новый код
# Или введите 5 цифр кода для авторизации
CODE_OR_NETU = 'netu'  # ← ИЗМЕНИТЕ ЭТО! 'netu' для кода или 5 цифр

# Пароль 2FA (если включена двухфакторка, иначе оставьте пустым)
TFA_PASSWORD = ''  # Введите пароль если есть

# ============================================
# 🚀  СКРИПТ (ниже ничего не трогать)
# ============================================

async def main():
    print("=" * 60)
    print("🤖 Telegram Session Creator".center(60))
    print("=" * 60)
    
    # Информация о настройках
    print(f"\n📱 Номер: {PHONE_NUMBER}")
    print(f"🔑 Режим: {'ЗАПРОС КОДА' if CODE_OR_NETU == 'netu' else 'ВВОД КОДА'}")
    print("-" * 60)
    
    # Удаляем старую сессию если есть
    session_file = 'telegram_session.session'
    if os.path.exists(session_file):
        os.remove(session_file)
        print("✅ Старая сессия удалена")
    
    # Создаем клиента
    client = TelegramClient('telegram_session', API_ID, API_HASH)
    
    try:
        # Подключаемся
        await client.connect()
        print("✅ Подключение к Telegram установлено")
        
        # Проверка авторизации
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Уже авторизован как: {me.first_name}")
            return
        
        # Обработка режима
        if CODE_OR_NETU.lower() == 'netu':
            # Запрашиваем код
            print(f"\n📤 Отправка кода на {PHONE_NUMBER}...")
            await client.send_code_request(PHONE_NUMBER)
            print("✅ Код отправлен!")
            print("\n⚠️  Теперь измените CODE_OR_NETU в скрипте на полученный код")
            print("   и запустите скрипт снова!")
            
        elif CODE_OR_NETU.isdigit() and len(CODE_OR_NETU) == 5:
            # Пробуем войти с кодом
            print(f"\n🔑 Попытка входа с кодом: {CODE_OR_NETU}")
            
            try:
                await client.sign_in(PHONE_NUMBER, CODE_OR_NETU)
                print("✅ Успешная авторизация!")
                
            except SessionPasswordNeededError:
                # Нужен пароль 2FA
                print("🔐 Требуется двухфакторная аутентификация")
                
                if TFA_PASSWORD:
                    try:
                        await client.sign_in(password=TFA_PASSWORD)
                        print("✅ Успешная авторизация с 2FA!")
                    except Exception as e:
                        print(f"❌ Ошибка 2FA: {e}")
                        print("⚠️  Проверьте пароль в TFA_PASSWORD")
                        return
                else:
                    print("❌ Нужен пароль 2FA, но TFA_PASSWORD не указан")
                    print("⚠️  Введите пароль в переменную TFA_PASSWORD")
                    return
                    
            except Exception as e:
                if "CODE_INVALID" in str(e):
                    print("❌ Неверный код!")
                    print("⚠️  Проверьте код и попробуйте снова")
                else:
                    print(f"❌ Ошибка: {e}")
                return
        else:
            print("❌ Неверный формат CODE_OR_NETU!")
            print("   Должно быть: 'netu' или 5 цифр")
            return
        
        # Если дошли сюда - авторизация успешна
        me = await client.get_me()
        print("\n" + "=" * 60)
        print("✅ СЕССИЯ УСПЕШНО СОЗДАНА!".center(60))
        print("=" * 60)
        print(f"👤 Имя: {me.first_name} {me.last_name or ''}")
        print(f"🆔 ID: {me.id}")
        print(f"📱 Телефон: {me.phone}")
        print(f"🔗 Username: @{me.username if me.username else 'нет'}")
        print(f"📁 Файл сессии: telegram_session.session")
        print("=" * 60)
        
        # Показываем как использовать сессию
        print("\n📌 Теперь можете использовать эту сессию в других скриптах:")
        print('   client = TelegramClient("telegram_session", API_ID, API_HASH)')
        print("\n✅ Готово!")
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        
    finally:
        await client.disconnect()
        print("\n👋 Отключено")

if __name__ == '__main__':
    asyncio.run(main())