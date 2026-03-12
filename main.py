import asyncio
import os
from telethon import TelegramClient, events
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionCustomEmoji
from datetime import datetime, timedelta
import logging

# ============================================
# ⚙️  НАСТРОЙКИ
# ============================================

# Данные Telegram API
API_ID = 36590443
API_HASH = '401ed4b74b5d1d57feb7aa72c918e361'

# Чат и реакция
CHAT_ID = -1002559865477  # ID чата
REACTION_ID = 5229159576649093081  # ID премиум реакции

# Настройки
SESSION_NAME = 'premium_session'  # Имя файла сессии
HISTORY_HOURS = 1  # Сколько часов истории обработать

# ============================================
# 🚀  ОСНОВНОЙ КОД
# ============================================

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Множество для отслеживания обработанных сообщений
processed_messages = set()
total_processed = 0

async def setup_client():
    """Настройка клиента"""
    # Удаляем поврежденную сессию если есть
    if os.path.exists(f'{SESSION_NAME}.session'):
        try:
            # Проверяем сессию
            test_client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
            await test_client.connect()
            if await test_client.is_user_authorized():
                await test_client.disconnect()
                logger.info("✅ Существующая сессия загружена")
            else:
                await test_client.disconnect()
                os.remove(f'{SESSION_NAME}.session')
                logger.info("🗑️ Удалена неавторизованная сессия")
        except:
            os.remove(f'{SESSION_NAME}.session')
            logger.info("🗑️ Удалена поврежденная сессия")
    
    # Создаем клиента
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    return client

async def process_history(client):
    """Обработка сообщений за последний час"""
    global total_processed
    
    logger.info(f"📜 Загрузка сообщений за последние {HISTORY_HOURS} час(а)...")
    
    try:
        # Получаем чат
        chat = await client.get_entity(CHAT_ID)
        
        # Вычисляем время
        time_limit = datetime.now() - timedelta(hours=HISTORY_HOURS)
        
        # Получаем все сообщения
        messages = []
        async for message in client.iter_messages(chat, limit=None):
            if message.date.replace(tzinfo=None) < time_limit:
                break
            messages.append(message)
        
        logger.info(f"📊 Найдено {len(messages)} сообщений")
        
        # Обрабатываем сообщения (от старых к новым)
        processed = 0
        for message in reversed(messages):
            if message.id not in processed_messages:
                try:
                    # Ставим реакцию
                    await client(SendReactionRequest(
                        peer=chat,
                        msg_id=message.id,
                        reaction=[ReactionCustomEmoji(document_id=REACTION_ID)]
                    ))
                    
                    processed_messages.add(message.id)
                    processed += 1
                    total_processed += 1
                    
                    # Логируем каждое 10-е сообщение
                    if processed % 10 == 0:
                        logger.info(f"📌 Обработано {processed}/{len(messages)} сообщений истории")
                    
                    # Небольшая задержка чтобы не флудить
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка на сообщении {message.id}: {e}")
        
        logger.info(f"✅ История обработана: +{processed} реакций")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке истории: {e}")

async def main():
    global total_processed, processed_messages
    
    print("\n" + "="*60)
    print("🚀 TELEGRAM REACTION BOT (ПРЕМИУМ)")
    print("="*60)
    print(f"📱 Чат: {CHAT_ID}")
    print(f"🎭 Реакция ID: {REACTION_ID}")
    print(f"📜 История: {HISTORY_HOURS} час(а)")
    print("="*60 + "\n")
    
    # Настраиваем клиента
    client = await setup_client()
    
    try:
        # Подключаемся
        await client.start()
        logger.info("✅ Клиент запущен")
        
        # Проверяем авторизацию
        me = await client.get_me()
        logger.info(f"👤 Аккаунт: {me.first_name} (ID: {me.id})")
        
        if not me.premium:
            logger.warning("⚠️ У аккаунта нет Telegram Premium! Премиум реакции могут не работать")
        
        # Получаем информацию о чате
        try:
            chat = await client.get_entity(CHAT_ID)
            chat_title = getattr(chat, 'title', 'Личный чат')
            logger.info(f"💬 Чат: {chat_title}")
        except Exception as e:
            logger.error(f"❌ Не удалось получить чат: {e}")
            return
        
        # ОБРАБАТЫВАЕМ ИСТОРИЮ
        logger.info("\n" + "="*60)
        logger.info("📜 НАЧАЛО ОБРАБОТКИ ИСТОРИИ")
        logger.info("="*60)
        await process_history(client)
        
        # РЕГИСТРИРУЕМ ОБРАБОТЧИК НОВЫХ СООБЩЕНИЙ
        logger.info("\n" + "="*60)
        logger.info("🟢 СЛУШАЕМ НОВЫЕ СООБЩЕНИЯ")
        logger.info("="*60)
        
        @client.on(events.NewMessage(chats=CHAT_ID))
        async def handler(event):
            global total_processed
            
            try:
                message = event.message
                
                # Проверяем не обрабатывали ли уже
                if message.id in processed_messages:
                    return
                
                # Ставим реакцию
                await client(SendReactionRequest(
                    peer=await client.get_input_entity(CHAT_ID),
                    msg_id=message.id,
                    reaction=[ReactionCustomEmoji(document_id=REACTION_ID)]
                ))
                
                processed_messages.add(message.id)
                total_processed += 1
                
                # Ограничиваем размер множества
                if len(processed_messages) > 10000:
                    processed_messages = set(list(processed_messages)[-5000:])
                
                logger.info(f"✅ Реакция на [{message.id}] | Всего: {total_processed}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
        
        # Ждем новые сообщения
        logger.info("🟢 Бот активен. Ожидание новых сообщений...")
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        logger.info("\n👋 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        if client:
            await client.disconnect()
        
        # Итоговая статистика
        print("\n" + "="*60)
        print("📊 ИТОГОВАЯ СТАТИСТИКА")
        print("="*60)
        print(f"✅ Всего обработано сообщений: {total_processed}")
        print("="*60)

if __name__ == '__main__':
    asyncio.run(main())