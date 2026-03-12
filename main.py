import asyncio
import os
import json
from telethon import TelegramClient, events
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionCustomEmoji, ReactionEmoji
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import UpdateProfileRequest
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
import sqlite3
import re

# ============================================
# ⚙️  НАСТРОЙКИ БОТА
# ============================================

BOT_TOKEN = '8570375501:AAFabraVld-YR47Q4w-lUq9ziUWX-VzEcCE'
API_ID = 36590443
API_HASH = '401ed4b74b5d1d57feb7aa72c918e361'
DEFAULT_CHAT_ID = -1002559865477
DEFAULT_REACTION_ID = 5229159576649093081

# ============================================
# 🚀  ИНИЦИАЛИЗАЦИЯ
# ============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Хранилище данных пользователей
user_sessions = {}
user_states = {}
user_settings = {}
user_reactions = {}
active_bots = {}
user_devices = {}

# ============================================
# 📁  РАБОТА С ФАЙЛАМИ
# ============================================

def load_user_data(user_id):
    """Загрузка данных пользователя"""
    try:
        if os.path.exists(f'user_{user_id}.json'):
            with open(f'user_{user_id}.json', 'r') as f:
                return json.load(f)
    except:
        pass
    return {
        'sessions': [],
        'settings': {
            'chat_id': DEFAULT_CHAT_ID,
            'reaction_id': DEFAULT_REACTION_ID,
            'ignore_bots': True,
            'reply_only': False,
            'media_only': False,
            'keywords': [],
            'delay': 0,
            'history_hours': 1,
            'device_model': 'Telegram Bot',
            'session_name': 'default_session',
            'auto_start': True
        },
        'reactions': [],
        'active_bots': []
    }

def save_user_data(user_id, data):
    """Сохранение данных пользователя"""
    with open(f'user_{user_id}.json', 'w') as f:
        json.dump(data, f, indent=4)

def cleanup_session_files(session_name):
    """Очистка файлов сессии"""
    files_to_remove = [
        f'{session_name}.session',
        f'{session_name}.session-journal'
    ]
    for file in files_to_remove:
        if os.path.exists(file):
            try:
                os.remove(file)
            except:
                pass

# ============================================
# 🔐  КЛАВИАТУРЫ
# ============================================

def get_main_keyboard():
    """Главная клавиатура"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("🔐 Авторизация"),
        KeyboardButton("⚙️ Настройки"),
        KeyboardButton("🎭 Реакции"),
        KeyboardButton("📊 Статус"),
        KeyboardButton("📁 Сессии"),
        KeyboardButton("🔄 Запустить реакции"),
        KeyboardButton("⏹️ Остановить"),
        KeyboardButton("📱 Устройство"),
        KeyboardButton("❓ Помощь")
    )
    return keyboard

def get_code_keyboard():
    """Клавиатура для ввода кода (красные кнопки)"""
    keyboard = InlineKeyboardMarkup(row_width=5)
    
    # Создаем красные кнопки с цифрами
    buttons = []
    for i in range(10):
        buttons.append(
            InlineKeyboardButton(
                text=f"🔴 {i}",
                callback_data=f"code_{i}"
            )
        )
    
    # Добавляем кнопки по 5 в ряд
    keyboard.add(*buttons[:5])
    keyboard.add(*buttons[5:])
    
    # Кнопки управления
    keyboard.row(
        InlineKeyboardButton("⌫ Стереть", callback_data="code_backspace"),
        InlineKeyboardButton("✅ Готово", callback_data="code_done"),
        InlineKeyboardButton("🔄 Новый код", callback_data="code_resend")
    )
    
    return keyboard

def get_settings_keyboard(settings):
    """Клавиатура настроек"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # Статусы настроек
    bot_status = "✅" if settings.get('ignore_bots', True) else "❌"
    reply_status = "✅" if settings.get('reply_only', False) else "❌"
    media_status = "✅" if settings.get('media_only', False) else "❌"
    auto_status = "✅" if settings.get('auto_start', True) else "❌"
    
    keyboard.add(
        InlineKeyboardButton(f"{bot_status} Игнор ботов", callback_data="toggle_bots"),
        InlineKeyboardButton(f"{reply_status} Только ответы", callback_data="toggle_reply"),
        InlineKeyboardButton(f"{media_status} Только медиа", callback_data="toggle_media"),
        InlineKeyboardButton(f"{auto_status} Автостарт", callback_data="toggle_auto"),
        InlineKeyboardButton("⏱️ Задержка", callback_data="set_delay"),
        InlineKeyboardButton("📜 Часы истории", callback_data="set_history"),
        InlineKeyboardButton("🔑 Ключевые слова", callback_data="set_keywords"),
        InlineKeyboardButton("📱 Устройство", callback_data="set_device"),
        InlineKeyboardButton("📁 Имя сессии", callback_data="set_session_name"),
        InlineKeyboardButton("🆔 ID чата", callback_data="set_chat_id"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    return keyboard

def get_reaction_keyboard(current_reaction=None):
    """Клавиатура для выбора реакции"""
    keyboard = InlineKeyboardMarkup(row_width=3)
    
    # Обычные реакции
    keyboard.add(
        InlineKeyboardButton("❤️", callback_data="react_heart"),
        InlineKeyboardButton("🔥", callback_data="react_fire"),
        InlineKeyboardButton("👍", callback_data="react_like"),
        InlineKeyboardButton("👎", callback_data="react_dislike"),
        InlineKeyboardButton("😁", callback_data="react_smile"),
        InlineKeyboardButton("🎉", callback_data="react_confetti")
    )
    
    # Премиум реакции
    keyboard.row(
        InlineKeyboardButton("⭐️ Премиум (по умолчанию)", callback_data="react_premium_default"),
        InlineKeyboardButton("🎭 Свой ID", callback_data="react_custom")
    )
    
    if current_reaction:
        keyboard.row(InlineKeyboardButton(f"✅ Текущая: {current_reaction}", callback_data="noop"))
    
    keyboard.row(InlineKeyboardButton("🔙 Назад", callback_data="back_to_settings"))
    
    return keyboard

def get_device_keyboard():
    """Клавиатура выбора устройства"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📱 iPhone 15", callback_data="device_iphone15"),
        InlineKeyboardButton("📱 Samsung S24", callback_data="device_samsung"),
        InlineKeyboardButton("💻 MacBook", callback_data="device_mac"),
        InlineKeyboardButton("🖥️ Windows PC", callback_data="device_windows"),
        InlineKeyboardButton("🤖 Telegram Bot", callback_data="device_bot"),
        InlineKeyboardButton("🎮 Свой вариант", callback_data="device_custom"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_settings")
    )
    return keyboard

# ============================================
# 🎨  ФУНКЦИИ ДЛЯ КНОПОК
# ============================================

async def update_code_button(message: types.Message, code: str):
    """Обновляет кнопки с кодом (красные/зеленые)"""
    keyboard = InlineKeyboardMarkup(row_width=5)
    
    # Создаем кнопки с цветом в зависимости от того, нажата ли цифра
    buttons = []
    for i in range(10):
        if str(i) in code:
            # Зеленая если цифра уже введена
            buttons.append(
                InlineKeyboardButton(
                    text=f"🟢 {i}",
                    callback_data=f"code_{i}"
                )
            )
        else:
            # Красная если не введена
            buttons.append(
                InlineKeyboardButton(
                    text=f"🔴 {i}",
                    callback_data=f"code_{i}"
                )
            )
    
    keyboard.add(*buttons[:5])
    keyboard.add(*buttons[5:])
    
    # Показываем текущий введенный код
    display_code = code if code else "⚪️ Пусто"
    keyboard.row(InlineKeyboardButton(f"📝 Код: {display_code}", callback_data="noop"))
    
    # Кнопки управления
    keyboard.row(
        InlineKeyboardButton("⌫ Стереть", callback_data="code_backspace"),
        InlineKeyboardButton("✅ Готово", callback_data="code_done"),
        InlineKeyboardButton("🔄 Новый код", callback_data="code_resend")
    )
    
    try:
        await message.edit_reply_markup(reply_markup=keyboard)
    except:
        pass

# ============================================
# 🤖  ФУНКЦИИ TELEGRAM
# ============================================

async def create_telegram_session(user_id, phone, session_name=None, device_model=None):
    """Создание сессии Telegram"""
    try:
        user_data = load_user_data(user_id)
        settings = user_data['settings']
        
        if not session_name:
            session_name = settings.get('session_name', f'user_{user_id}')
        
        if not device_model:
            device_model = settings.get('device_model', 'Telegram Bot')
        
        # Очищаем старые файлы
        cleanup_session_files(session_name)
        
        # Создаем клиента с настройками
        client = TelegramClient(
            session_name,
            API_ID,
            API_HASH,
            device_model=device_model,
            app_version="1.0.0",
            system_version="4.16.30-vxCUSTOM"
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            # Отправляем код
            await client.send_code_request(phone)
            return {"status": "code_sent", "client": client, "phone": phone, "session_name": session_name}
        else:
            # Уже авторизован
            me = await client.get_me()
            return {"status": "already", "client": client, "user": me}
            
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def start_reaction_bot(user_id):
    """Запуск бота реакций"""
    try:
        user_data = load_user_data(user_id)
        settings = user_data['settings']
        
        session_name = settings.get('session_name', f'user_{user_id}')
        chat_id = settings.get('chat_id', DEFAULT_CHAT_ID)
        reaction_id = settings.get('reaction_id', DEFAULT_REACTION_ID)
        
        # Проверяем существует ли сессия
        if not os.path.exists(f'{session_name}.session'):
            return {"status": "error", "error": "Сессия не найдена. Сначала авторизуйтесь."}
        
        # Останавливаем старый бот если есть
        if user_id in active_bots:
            try:
                await active_bots[user_id].disconnect()
            except:
                pass
        
        # Создаем нового клиента
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.start()
        
        # Получаем информацию
        me = await client.get_me()
        
        # Создаем обработчик
        @client.on(events.NewMessage(chats=int(chat_id)))
        async def reaction_handler(event):
            try:
                # Проверяем настройки
                if settings.get('ignore_bots', True) and event.message.sender and event.message.sender.bot:
                    return
                
                if settings.get('reply_only', False) and not event.message.reply_to:
                    return
                
                if settings.get('media_only', False) and not event.message.media:
                    return
                
                if settings.get('keywords', []):
                    text = event.message.text or ""
                    if not any(k.lower() in text.lower() for k in settings['keywords']):
                        return
                
                # Задержка
                if settings.get('delay', 0) > 0:
                    await asyncio.sleep(settings['delay'])
                
                # Ставим реакцию
                if reaction_id == DEFAULT_REACTION_ID or str(reaction_id).isdigit():
                    # Премиум реакция
                    reaction = [ReactionCustomEmoji(document_id=int(reaction_id))]
                else:
                    # Обычные реакции
                    emoji_map = {
                        'heart': '❤️',
                        'fire': '🔥',
                        'like': '👍',
                        'dislike': '👎',
                        'smile': '😁',
                        'confetti': '🎉'
                    }
                    reaction = [ReactionEmoji(emoticon=emoji_map.get(reaction_id, '❤️'))]
                
                await client(SendReactionRequest(
                    peer=await client.get_input_entity(int(chat_id)),
                    msg_id=event.message.id,
                    reaction=reaction
                ))
                
                # Логируем (каждое 10-е сообщение)
                if event.message.id % 10 == 0:
                    await bot.send_message(
                        user_id,
                        f"✅ Реакция на [{event.message.id}] в чате {chat_id}"
                    )
                
            except Exception as e:
                print(f"Ошибка реакции: {e}")
        
        # Запускаем
        asyncio.create_task(client.run_until_disconnected())
        
        # Сохраняем активный бот
        active_bots[user_id] = client
        
        # Обновляем данные
        if 'active_bots' not in user_data:
            user_data['active_bots'] = []
        
        # Удаляем старые записи
        user_data['active_bots'] = [b for b in user_data['active_bots'] if b.get('chat_id') != str(chat_id)]
        
        user_data['active_bots'].append({
            'chat_id': str(chat_id),
            'reaction': str(reaction_id),
            'started': datetime.now().isoformat(),
            'session': session_name
        })
        save_user_data(user_id, user_data)
        
        return {
            "status": "success",
            "client": client,
            "me": me,
            "chat_id": chat_id,
            "reaction_id": reaction_id
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ============================================
# 🤖  ОБРАБОТЧИКИ КОМАНД
# ============================================

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
    # Загружаем настройки
    user_data = load_user_data(user_id)
    
    await message.answer(
        "👋 **Добро пожаловать в Telegram Reaction Bot!**\n\n"
        "Я помогу вам автоматически ставить реакции на сообщения.\n"
        "По умолчанию настроен на чат с премиум-реакцией.\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    
    # Автоматический запуск если включено
    if user_data['settings'].get('auto_start', True) and os.path.exists(f"user_{user_id}.session"):
        await message.answer("🔄 Автоматический запуск реакций...")
        result = await start_reaction_bot(user_id)
        if result['status'] == 'success':
            await message.answer(
                f"✅ **Бот реакций запущен!**\n\n"
                f"👤 Аккаунт: {result['me'].first_name}\n"
                f"💬 Чат: {result['chat_id']}\n"
                f"🎭 Реакция: {result['reaction_id']}",
                parse_mode="Markdown"
            )

@dp.message_handler(lambda message: message.text == "🔐 Авторизация")
async def auth_start(message: types.Message):
    """Начало авторизации"""
    user_id = message.from_user.id
    
    user_states[user_id] = {'action': 'waiting_phone'}
    
    await message.answer(
        "📱 **Авторизация в Telegram**\n\n"
        "Введите номер телефона в международном формате:\n"
        "Например: `+79001234567` или `+18255909247`\n\n"
        "⚠️ Номер должен быть от аккаунта с Telegram Premium!",
        parse_mode="Markdown"
    )

@dp.message_handler(lambda message: user_states.get(message.from_user.id, {}).get('action') == 'waiting_phone')
async def process_phone(message: types.Message):
    """Обработка ввода номера"""
    user_id = message.from_user.id
    phone = message.text.strip()
    
    # Валидация
    if not re.match(r'^\+\d{10,15}$', phone):
        await message.answer(
            "❌ **Неверный формат номера!**\n"
            "Используйте формат: +79001234567",
            parse_mode="Markdown"
        )
        return
    
    waiting_msg = await message.answer("🔄 Подключение к Telegram...")
    
    # Загружаем настройки
    user_data = load_user_data(user_id)
    session_name = user_data['settings'].get('session_name', f'user_{user_id}')
    device_model = user_data['settings'].get('device_model', 'Telegram Bot')
    
    # Создаем сессию
    result = await create_telegram_session(
        user_id,
        phone,
        session_name=session_name,
        device_model=device_model
    )
    
    if result['status'] == 'code_sent':
        user_states[user_id] = {
            'action': 'waiting_code',
            'phone': phone,
            'client': result['client'],
            'code': '',
            'message_id': waiting_msg.message_id,
            'session_name': result['session_name']
        }
        
        # Отправляем клавиатуру для ввода кода
        await waiting_msg.edit_text(
            "📲 **Код отправлен!**\n\n"
            "Введите код из Telegram с помощью кнопок ниже:",
            parse_mode="Markdown",
            reply_markup=get_code_keyboard()
        )
        
    elif result['status'] == 'already':
        await waiting_msg.edit_text(
            "✅ **Вы уже авторизованы!**\n"
            "Сессия готова к использованию.",
            parse_mode="Markdown"
        )
        user_states.pop(user_id, None)
        
        # Автоматически запускаем реакции
        if user_data['settings'].get('auto_start', True):
            await message.answer("🔄 Автоматический запуск реакций...")
            start_result = await start_reaction_bot(user_id)
            if start_result['status'] == 'success':
                await message.answer(
                    f"✅ **Бот реакций запущен!**\n\n"
                    f"👤 Аккаунт: {start_result['me'].first_name}\n"
                    f"💬 Чат: {start_result['chat_id']}",
                    parse_mode="Markdown"
                )
        
    else:
        await waiting_msg.edit_text(
            f"❌ **Ошибка:** {result.get('error', 'Неизвестная ошибка')}",
            parse_mode="Markdown"
        )
        user_states.pop(user_id, None)

@dp.callback_query_handler(lambda c: c.data.startswith('code_'))
async def process_code(callback_query: types.CallbackQuery):
    """Обработка нажатий на кнопки кода"""
    user_id = callback_query.from_user.id
    action = callback_query.data
    
    if user_id not in user_states or user_states[user_id].get('action') != 'waiting_code':
        await callback_query.answer("❌ Сессия истекла")
        return
    
    state = user_states[user_id]
    current_code = state.get('code', '')
    
    if action == 'code_backspace':
        # Удаляем последнюю цифру
        if current_code:
            current_code = current_code[:-1]
        await callback_query.answer("⌫ Удалено")
            
    elif action == 'code_done':
        # Завершаем ввод
        if len(current_code) == 5:
            await callback_query.answer("✅ Проверяем код...")
            
            # Пробуем войти
            try:
                await state['client'].sign_in(state['phone'], current_code)
                
                # Успех
                me = await state['client'].get_me()
                
                # Сохраняем данные
                user_data = load_user_data(user_id)
                user_data['sessions'].append({
                    'name': state['session_name'],
                    'phone': state['phone'],
                    'user_id': me.id,
                    'username': me.username,
                    'first_name': me.first_name,
                    'premium': True  # Помечаем как премиум
                })
                save_user_data(user_id, user_data)
                
                await callback_query.message.edit_text(
                    f"✅ **Авторизация успешна!**\n\n"
                    f"👤 Имя: {me.first_name}\n"
                    f"🆔 ID: {me.id}\n"
                    f"🔗 Username: @{me.username if me.username else 'нет'}\n"
                    f"⭐️ Premium: {'Да' if me.premium else 'Нет'}\n\n"
                    f"Сессия сохранена: {state['session_name']}.session",
                    parse_mode="Markdown"
                )
                
                user_states.pop(user_id, None)
                
                # Автоматически запускаем реакции
                if user_data['settings'].get('auto_start', True):
                    await bot.send_message(user_id, "🔄 Автоматический запуск реакций...")
                    start_result = await start_reaction_bot(user_id)
                    if start_result['status'] == 'success':
                        await bot.send_message(
                            user_id,
                            f"✅ **Бот реакций запущен!**\n\n"
                            f"👤 Аккаунт: {start_result['me'].first_name}\n"
                            f"💬 Чат: {start_result['chat_id']}",
                            parse_mode="Markdown"
                        )
                
            except SessionPasswordNeededError:
                # Нужен пароль 2FA
                user_states[user_id]['action'] = 'waiting_2fa'
                user_states[user_id]['code'] = current_code
                
                await callback_query.message.edit_text(
                    "🔐 **Требуется двухфакторная аутентификация**\n\n"
                    "Введите ваш пароль:",
                    parse_mode="Markdown"
                )
                
            except Exception as e:
                error_text = str(e)
                if "CODE_INVALID" in error_text:
                    await callback_query.message.edit_text(
                        "❌ **Неверный код!**\n\n"
                        "Попробуйте снова или запросите новый код.",
                        parse_mode="Markdown",
                        reply_markup=get_code_keyboard()
                    )
                else:
                    await callback_query.message.edit_text(
                        f"❌ **Ошибка:** {error_text}",
                        parse_mode="Markdown"
                    )
            
            return
        else:
            await callback_query.answer("❌ Нужно ввести 5 цифр!")
            return
            
    elif action == 'code_resend':
        # Запрашиваем новый код
        await callback_query.answer("🔄 Запрашиваем новый код...")
        try:
            await state['client'].send_code_request(state['phone'])
            current_code = ''
            await callback_query.answer("✅ Новый код отправлен!")
        except Exception as e:
            await callback_query.answer(f"❌ Ошибка: {e}")
            
    elif action.startswith('code_') and len(action) == 6:  # code_0 .. code_9
        digit = action[5]
        if len(current_code) < 5:
            current_code += digit
            await callback_query.answer(f"✅ {digit}")
        else:
            await callback_query.answer("❌ Максимум 5 цифр")
    
    # Обновляем состояние
    user_states[user_id]['code'] = current_code
    
    # Обновляем кнопки
    await update_code_button(callback_query.message, current_code)

@dp.message_handler(lambda message: user_states.get(message.from_user.id, {}).get('action') == 'waiting_2fa')
async def process_2fa(message: types.Message):
    """Обработка ввода пароля 2FA"""
    user_id = message.from_user.id
    password = message.text.strip()
    
    state = user_states[user_id]
    
    try:
        await state['client'].sign_in(password=password)
        
        me = await state['client'].get_me()
        
        # Сохраняем данные
        user_data = load_user_data(user_id)
        user_data['sessions'].append({
            'name': state['session_name'],
            'phone': state['phone'],
            'user_id': me.id,
            'username': me.username,
            'first_name': me.first_name,
            'premium': getattr(me, 'premium', False)
        })
        save_user_data(user_id, user_data)
        
        await message.answer(
            f"✅ **Авторизация успешна!**\n\n"
            f"👤 Имя: {me.first_name}\n"
            f"🆔 ID: {me.id}\n"
            f"🔗 Username: @{me.username if me.username else 'нет'}\n"
            f"⭐️ Premium: {'Да' if me.premium else 'Нет'}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        
        user_states.pop(user_id, None)
        
        # Автоматически запускаем реакции
        if user_data['settings'].get('auto_start', True):
            await message.answer("🔄 Автоматический запуск реакций...")
            start_result = await start_reaction_bot(user_id)
            if start_result['status'] == 'success':
                await message.answer(
                    f"✅ **Бот реакций запущен!**\n\n"
                    f"👤 Аккаунт: {start_result['me'].first_name}\n"
                    f"💬 Чат: {start_result['chat_id']}",
                    parse_mode="Markdown"
                )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message_handler(lambda message: message.text == "⚙️ Настройки")
async def settings_menu(message: types.Message):
    """Меню настроек"""
    user_id = message.from_user.id
    user_data = load_user_data(user_id)
    settings = user_data['settings']
    
    await message.answer(
        "⚙️ **Настройки бота**\n\n"
        "Выберите параметр для настройки:",
        parse_mode="Markdown",
        reply_markup=get_settings_keyboard(settings)
    )

@dp.callback_query_handler(lambda c: c.data.startswith('toggle_') or c.data in ['set_delay', 'set_history', 'set_keywords', 'set_device', 'set_session_name', 'set_chat_id', 'back_to_settings', 'back_to_main'])
async def process_settings(callback_query: types.CallbackQuery):
    """Обработка настроек"""
    user_id = callback_query.from_user.id
    action = callback_query.data
    
    user_data = load_user_data(user_id)
    settings = user_data['settings']
    
    if action == 'toggle_bots':
        settings['ignore_bots'] = not settings.get('ignore_bots', True)
        await callback_query.answer(f"Игнор ботов: {settings['ignore_bots']}")
        
    elif action == 'toggle_reply':
        settings['reply_only'] = not settings.get('reply_only', False)
        await callback_query.answer(f"Только ответы: {settings['reply_only']}")
        
    elif action == 'toggle_media':
        settings['media_only'] = not settings.get('media_only', False)
        await callback_query.answer(f"Только медиа: {settings['media_only']}")
        
    elif action == 'toggle_auto':
        settings['auto_start'] = not settings.get('auto_start', True)
        await callback_query.answer(f"Автостарт: {settings['auto_start']}")
        
    elif action == 'set_delay':
        user_states[user_id] = {'action': 'waiting_delay'}
        await callback_query.message.edit_text(
            "⏱️ **Введите задержку в секундах** (0-60):\n"
            "Например: `1.5`",
            parse_mode="Markdown"
        )
        return
        
    elif action == 'set_history':
        user_states[user_id] = {'action': 'waiting_history'}
        await callback_query.message.edit_text(
            "📜 **Сколько часов истории обрабатывать?** (0-24):\n"
            "Например: `2`",
            parse_mode="Markdown"
        )
        return
        
    elif action == 'set_keywords':
        user_states[user_id] = {'action': 'waiting_keywords'}
        await callback_query.message.edit_text(
            "🔑 **Введите ключевые слова через запятую**\n"
            "Например: `привет, как дела, важное`\n\n"
            "Или отправьте `-` чтобы очистить",
            parse_mode="Markdown"
        )
        return
        
    elif action == 'set_device':
        await callback_query.message.edit_text(
            "📱 **Выберите модель устройства:**",
            reply_markup=get_device_keyboard()
        )
        return
        
    elif action == 'set_session_name':
        user_states[user_id] = {'action': 'waiting_session_name'}
        await callback_query.message.edit_text(
            "📁 **Введите имя файла сессии**\n"
            "Например: `my_premium_session`\n\n"
            "Будет создан файл: my_premium_session.session",
            parse_mode="Markdown"
        )
        return
        
    elif action == 'set_chat_id':
        user_states[user_id] = {'action': 'waiting_chat_id'}
        await callback_query.message.edit_text(
            "🆔 **Введите ID чата**\n"
            f"Текущий: `{settings.get('chat_id', DEFAULT_CHAT_ID)}`\n\n"
            "Например: `-1002559865477`",
            parse_mode="Markdown"
        )
        return
        
    elif action == 'back_to_settings':
        await callback_query.message.edit_text(
            "⚙️ **Настройки бота**",
            reply_markup=get_settings_keyboard(settings)
        )
        return
        
    elif action == 'back_to_main':
        await callback_query.message.delete()
        await bot.send_message(
            user_id,
            "👋 Главное меню:",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Сохраняем изменения
    save_user_data(user_id, user_data)
    
    # Обновляем сообщение
    await callback_query.message.edit_reply_markup(
        reply_markup=get_settings_keyboard(settings)
    )

@dp.callback_query_handler(lambda c: c.data.startswith('device_'))
async def process_device(callback_query: types.CallbackQuery):
    """Выбор устройства"""
    user_id = callback_query.from_user.id
    device = callback_query.data.replace('device_', '')
    
    user_data = load_user_data(user_id)
    
    device_names = {
        'iphone15': 'iPhone 15 Pro Max',
        'samsung': 'Samsung Galaxy S24 Ultra',
        'mac': 'MacBook Pro 16"',
        'windows': 'Windows 11 PC',
        'bot': 'Telegram Bot',
        'custom': 'Пользовательское'
    }
    
    if device == 'custom':
        user_states[user_id] = {'action': 'waiting_custom_device'}
        await callback_query.message.edit_text(
            "📱 **Введите название устройства:**\n"
            "Например: `Google Pixel 8 Pro`",
            parse_mode="Markdown"
        )
        return
    
    user_data['settings']['device_model'] = device_names.get(device, device)
    save_user_data(user_id, user_data)
    
    await callback_query.message.edit_text(
        f"✅ **Устройство установлено:** {user_data['settings']['device_model']}",
        reply_markup=get_settings_keyboard(user_data['settings'])
    )

@dp.message_handler(lambda message: user_states.get(message.from_user.id, {}).get('action') in ['waiting_delay', 'waiting_history', 'waiting_keywords', 'waiting_session_name', 'waiting_chat_id', 'waiting_custom_device', 'waiting_reaction_id'])
async def process_input(message: types.Message):
    """Обработка ввода данных"""
    user_id = message.from_user.id
    action = user_states[user_id]['action']
    value = message.text.strip()
    
    user_data = load_user_data(user_id)
    
    if action == 'waiting_delay':
        try:
            delay = float(value)
            if 0 <= delay <= 60:
                user_data['settings']['delay'] = delay
                await message.answer(f"✅ Задержка установлена: {delay} сек")
            else:
                await message.answer("❌ Введите число от 0 до 60")
                return
        except:
            await message.answer("❌ Введите число")
            return
            
    elif action == 'waiting_history':
        try:
            hours = float(value)
            if 0 <= hours <= 24:
                user_data['settings']['history_hours'] = hours
                await message.answer(f"✅ Часов истории: {hours}")
            else:
                await message.answer("❌ Введите число от 0 до 24")
                return
        except:
            await message.answer("❌ Введите число")
            return
            
    elif action == 'waiting_keywords':
        if value == '-':
            user_data['settings']['keywords'] = []
            await message.answer("✅ Ключевые слова очищены")
        else:
            keywords = [k.strip() for k in value.split(',') if k.strip()]
            user_data['settings']['keywords'] = keywords
            await message.answer(f"✅ Ключевые слова: {', '.join(keywords)}")
            
    elif action == 'waiting_session_name':
        # Проверяем на допустимые символы
        if re.match(r'^[a-zA-Z0-9_]+$', value):
            user_data['settings']['session_name'] = value
            await message.answer(f"✅ Имя сессии: {value}.session")
        else:
            await message.answer("❌ Только буквы, цифры и _")
            return
            
    elif action == 'waiting_chat_id':
        try:
            chat_id = int(value)
            user_data['settings']['chat_id'] = chat_id
            await message.answer(f"✅ ID чата: {chat_id}")
        except:
            await message.answer("❌ Введите число")
            return
            
    elif action == 'waiting_custom_device':
        user_data['settings']['device_model'] = value
        await message.answer(f"✅ Устройство: {value}")
        
    elif action == 'waiting_reaction_id':
        try:
            reaction_id = int(value)
            user_data['settings']['reaction_id'] = reaction_id
            await message.answer(f"✅ Премиум реакция ID: {reaction_id}")
        except:
            await message.answer("❌ Введите число (ID реакции)")
            return
    
    # Сохраняем
    save_user_data(user_id, user_data)
    user_states.pop(user_id, None)
    
    # Возвращаем в меню настроек
    await message.answer(
        "⚙️ Настройки обновлены",
        reply_markup=get_settings_keyboard(user_data['settings'])
    )

@dp.message_handler(lambda message: message.text == "🎭 Реакции")
async def reactions_menu(message: types.Message):
    """Меню выбора реакций"""
    user_id = message.from_user.id
    user_data = load_user_data(user_id)
    current = user_data['settings'].get('reaction_id', DEFAULT_REACTION_ID)
    
    await message.answer(
        "🎭 **Выберите реакцию**\n\n"
        f"Текущая: `{current}`",
        parse_mode="Markdown",
        reply_markup=get_reaction_keyboard(current)
    )

@dp.callback_query_handler(lambda c: c.data.startswith('react_'))
async def process_reaction(callback_query: types.CallbackQuery):
    """Выбор реакции"""
    user_id = callback_query.from_user.id
    reaction = callback_query.data.replace('react_', '')
    
    user_data = load_user_data(user_id)
    
    if reaction == 'premium_default':
        user_data['settings']['reaction_id'] = DEFAULT_REACTION_ID
        await callback_query.answer("✅ Установлена премиум реакция по умолчанию")
        
    elif reaction == 'custom':
        user_states[user_id] = {'action': 'waiting_reaction_id'}
        await callback_query.message.edit_text(
            "🎭 **Введите ID премиум реакции**\n\n"
            "Например: `5229159576649093081`",
            parse_mode="Markdown"
        )
        return
        
    elif reaction in ['heart', 'fire', 'like', 'dislike', 'smile', 'confetti']:
        # Обычные реакции
        emoji_map = {
            'heart': '❤️',
            'fire': '🔥',
            'like': '👍',
            'dislike': '👎',
            'smile': '😁',
            'confetti': '🎉'
        }
        user_data['settings']['reaction_id'] = reaction
        await callback_query.answer(f"✅ Реакция: {emoji_map[reaction]}")
    
    # Сохраняем
    save_user_data(user_id, user_data)
    
    # Обновляем сообщение
    await callback_query.message.edit_text(
        "🎭 **Реакция обновлена!**",
        reply_markup=get_reaction_keyboard(user_data['settings']['reaction_id'])
    )

@dp.message_handler(lambda message: message.text == "📊 Статус")
async def show_status(message: types.Message):
    """Показать статус"""
    user_id = message.from_user.id
    user_data = load_user_data(user_id)
    
    active = user_data.get('active_bots', [])
    
    status_text = "📊 **Текущий статус**\n\n"
    
    # Активные боты
    if active:
        status_text += "✅ **Активные боты:**\n"
        for bot_info in active:
            status_text += f"• Чат: `{bot_info.get('chat_id')}`\n"
            status_text += f"  Реакция: `{bot_info.get('reaction')}`\n"
            status_text += f"  Запущен: {bot_info.get('started', '')[:16]}\n"
    else:
        status_text += "❌ Нет активных ботов\n\n"
    
    # Сессии
    sessions = user_data.get('sessions', [])
    status_text += f"\n📁 **Сессий:** {len(sessions)}\n"
    if sessions:
        last_session = sessions[-1]
        status_text += f"• Последняя: {last_session.get('first_name')} (@{last_session.get('username', 'нет')})\n"
        status_text += f"  Premium: {'✅' if last_session.get('premium') else '❌'}\n"
    
    # Настройки
    settings = user_data['settings']
    status_text += f"\n⚙️ **Настройки:**\n"
    status_text += f"• Чат: `{settings.get('chat_id')}`\n"
    status_text += f"• Реакция: `{settings.get('reaction_id')}`\n"
    status_text += f"• Устройство: {settings.get('device_model')}\n"
    status_text += f"• Задержка: {settings.get('delay', 0)}с\n"
    status_text += f"• Ключевых слов: {len(settings.get('keywords', []))}\n"
    
    await message.answer(status_text, parse_mode="Markdown")

@dp.message_handler(lambda message: message.text == "📁 Сессии")
async def list_sessions(message: types.Message):
    """Список сессий"""
    user_id = message.from_user.id
    user_data = load_user_data(user_id)
    
    sessions = user_data.get('sessions', [])
    
    if not sessions:
        await message.answer(
            "❌ **У вас нет сохраненных сессий**\n"
            "Используйте 🔐 Авторизация",
            parse_mode="Markdown"
        )
        return
    
    text = "📁 **Ваши сессии:**\n\n"
    for i, session in enumerate(reversed(sessions[-5:]), 1):  # Показываем последние 5
        premium = "⭐️" if session.get('premium') else "🔹"
        text += f"{i}. {premium} {session.get('first_name')}\n"
        text += f"   🆔 ID: `{session.get('user_id')}`\n"
        text += f"   📱 {session.get('phone')}\n"
        text += f"   📁 {session.get('name')}.session\n\n"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message_handler(lambda message: message.text == "🔄 Запустить реакции")
async def start_reactions(message: types.Message):
    """Запуск реакций"""
    user_id = message.from_user.id
    user_data = load_user_data(user_id)
    
    # Проверяем наличие сессии
    if not user_data.get('sessions'):
        await message.answer(
            "❌ **Сначала авторизуйтесь!**\n"
            "Используйте 🔐 Авторизация",
            parse_mode="Markdown"
        )
        return
    
    waiting_msg = await message.answer("🔄 Запуск бота реакций...")
    
    result = await start_reaction_bot(user_id)
    
    if result['status'] == 'success':
        await waiting_msg.edit_text(
            f"✅ **Бот реакций успешно запущен!**\n\n"
            f"👤 Аккаунт: {result['me'].first_name}\n"
            f"💬 Чат: `{result['chat_id']}`\n"
            f"🎭 Реакция: `{result['reaction_id']}`\n\n"
            f"📊 Статус: Активен",
            parse_mode="Markdown"
        )
    else:
        await waiting_msg.edit_text(
            f"❌ **Ошибка запуска:**\n{result.get('error', 'Неизвестная ошибка')}",
            parse_mode="Markdown"
        )

@dp.message_handler(lambda message: message.text == "⏹️ Остановить")
async def stop_reactions(message: types.Message):
    """Остановка реакций"""
    user_id = message.from_user.id
    
    if user_id in active_bots:
        try:
            await active_bots[user_id].disconnect()
            del active_bots[user_id]
            
            # Обновляем данные
            user_data = load_user_data(user_id)
            user_data['active_bots'] = []
            save_user_data(user_id, user_data)
            
            await message.answer("✅ **Бот реакций остановлен**", parse_mode="Markdown")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
    else:
        await message.answer("❌ Нет активных ботов")

@dp.message_handler(lambda message: message.text == "📱 Устройство")
async def device_menu(message: types.Message):
    """Меню выбора устройства"""
    await message.answer(
        "📱 **Выберите модель устройства:**\n\n"
        "Это влияет на то, как вас видят в Telegram",
        parse_mode="Markdown",
        reply_markup=get_device_keyboard()
    )

@dp.message_handler(lambda message: message.text == "❓ Помощь")
async def help_message(message: types.Message):
    """Справка"""
    help_text = """
❓ **Помощь по боту**

🔐 **Авторизация**
• Введите номер телефона
• Введите код из Telegram (кнопки)
• При необходимости пароль 2FA

⚙️ **Настройки**
• Игнор ботов - не реагировать на ботов
• Только ответы - только на сообщения-ответы
• Только медиа - только на фото/видео
• Ключевые слова - реагировать только на определенные слова
• Задержка - пауза перед реакцией

🎭 **Реакции**
• Обычные эмодзи
• Премиум реакции (по ID)
• По умолчанию: премиум 5229159576649093081

📱 **Устройство**
• Изменяет модель устройства в сессии
• Можно выбрать готовое или ввести свое

🔄 **Автозапуск**
• При включении бот запускается автоматически после авторизации

💬 **Чат по умолчанию:** `-1002559865477`
"""
    await message.answer(help_text, parse_mode="Markdown")

@dp.message_handler()
async def echo(message: types.Message):
    """Обработка неизвестных команд"""
    await message.answer(
        "❓ Неизвестная команда. Используйте кнопки меню.",
        reply_markup=get_main_keyboard()
    )

# ============================================
# 🚀  ЗАПУСК БОТА
# ============================================

if __name__ == '__main__':
    print("🤖 Telegram Reaction Bot запущен...")
    print(f"Бот: @{BOT_TOKEN.split(':')[0]}")
    print("По умолчанию настроен на чат: -1002559865477")
    print("Премиум реакция ID: 5229159576649093081")
    executor.start_polling(dp, skip_updates=True)