import asyncio
import logging
from telethon import TelegramClient, events, Button
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionCustomEmoji, User, Chat, Channel
from telethon.errors import SessionPasswordNeededError
from datetime import datetime, timedelta
import json
import os
from collections import defaultdict

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = '8508349706:AAEGMIyk1SeOZqa2msNi8ocAHvfH5j7aLVQ'
API_ID = 36590443
API_HASH = '401ed4b74b5d1d57feb7aa72c918e361'
DEFAULT_REACTION_ID = 5229159576649093081

# Файлы для хранения данных
USER_SESSIONS_FILE = 'user_sessions.json'
CHAT_SETTINGS_FILE = 'chat_settings.json'
REACTION_STATS_FILE = 'reaction_stats.json'

class ReactionBot:
    def __init__(self):
        self.bot = TelegramClient('bot_session', API_ID, API_HASH)
        self.user_clients = {}  # user_id -> TelegramClient
        self.user_auth_states = {}  # user_id -> {'phone': str, 'phone_code_hash': str, 'stage': str}
        self.chat_settings = self.load_data(CHAT_SETTINGS_FILE, {})  # user_id -> [chat_ids]
        self.reaction_stats = self.load_data(REACTION_STATS_FILE, {})  # user_id -> {chat_id: {msg_id: timestamp}}
        self.user_sessions = self.load_data(USER_SESSIONS_FILE, {})  # user_id -> session_string
        
    def load_data(self, filename, default):
        """Загружает данные из JSON файла"""
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return default
        return default
    
    def save_data(self, filename, data):
        """Сохраняет данные в JSON файл"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def start(self):
        """Запускает бота"""
        await self.bot.start(bot_token=BOT_TOKEN)
        logger.info("Бот запущен")
        
        # Регистрируем обработчики
        self.register_handlers()
        
        # Запускаем фоновые задачи
        asyncio.create_task(self.cleanup_old_stats())
        
        await self.bot.run_until_disconnected()
    
    def register_handlers(self):
        """Регистрирует все обработчики команд и сообщений"""
        
        @self.bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.respond(
                "👋 **Добро пожаловать в бота автореакций!**\n\n"
                "Этот бот позволяет автоматически ставить реакции на новые сообщения в выбранных чатах.\n\n"
                "**Основные команды:**\n"
                "🔑 /login - Войти в аккаунт Telegram\n"
                "📋 /chats - Управление чатами для автореакций\n"
                "📊 /stats - Статистика реакций\n"
                "🚪 /logout - Выйти из аккаунта\n\n"
                "Для начала работы используйте /login",
                parse_mode='markdown'
            )
        
        @self.bot.on(events.NewMessage(pattern='/login'))
        async def login_handler(event):
            user_id = str(event.sender_id)
            
            # Проверяем, есть ли уже сохраненная сессия
            if user_id in self.user_sessions:
                await event.respond("✅ Вы уже вошли в аккаунт. Используйте /logout чтобы выйти.")
                return
            
            await event.respond(
                "📱 **Вход в аккаунт Telegram**\n\n"
                "Пожалуйста, введите ваш номер телефона в международном формате:\n"
                "Например: +79001234567",
                parse_mode='markdown'
            )
            self.user_auth_states[user_id] = {'stage': 'waiting_phone'}
        
        @self.bot.on(events.NewMessage(pattern='/chats'))
        async def chats_handler(event):
            user_id = str(event.sender_id)
            
            # Проверяем, авторизован ли пользователь
            if user_id not in self.user_clients and user_id not in self.user_sessions:
                await event.respond("❌ Сначала войдите в аккаунт через /login")
                return
            
            # Загружаем или создаем клиента
            client = await self.get_user_client(user_id)
            if not client:
                await event.respond("❌ Ошибка подключения к аккаунту")
                return
            
            await event.respond("🔄 Загружаю список чатов...")
            
            try:
                # Получаем все диалоги пользователя
                dialogs = await client.get_dialogs()
                
                # Фильтруем только группы и каналы
                chats = []
                for dialog in dialogs:
                    if isinstance(dialog.entity, (Chat, Channel)):
                        chats.append((dialog.id, dialog.name))
                
                # Сохраняем список чатов для отображения
                self.user_chats_list[user_id] = chats
                
                # Создаем кнопки для каждого чата (по 2 в ряд)
                buttons = []
                row = []
                for i, (chat_id, chat_name) in enumerate(chats[:20]):  # Ограничиваем 20 чатами
                    # Обрезаем длинные названия
                    display_name = chat_name[:20] + "..." if len(chat_name) > 20 else chat_name
                    
                    # Проверяем, выбран ли чат
                    is_selected = user_id in self.chat_settings and chat_id in self.chat_settings[user_id]
                    prefix = "✅ " if is_selected else ""
                    
                    button = Button.inline(f"{prefix}{display_name}", data=f"chat_{chat_id}")
                    row.append(button)
                    
                    if len(row) == 2:
                        buttons.append(row)
                        row = []
                
                if row:
                    buttons.append(row)
                
                # Добавляем кнопку "Готово"
                buttons.append([Button.inline("✅ Готово", data="done")])
                
                await event.respond(
                    "📋 **Выберите чаты для автореакций:**\n"
                    "Нажимайте на чаты чтобы выбрать/отменить выбор.\n"
                    "✅ - чат выбран",
                    buttons=buttons,
                    parse_mode='markdown'
                )
            except Exception as e:
                logger.error(f"Ошибка при получении чатов: {e}")
                await event.respond("❌ Ошибка при загрузке чатов")
        
        @self.bot.on(events.CallbackQuery)
        async def callback_handler(event):
            user_id = str(event.sender_id)
            data = event.data.decode()
            
            if data.startswith("chat_"):
                chat_id = int(data[5:])
                
                # Инициализируем настройки если их нет
                if user_id not in self.chat_settings:
                    self.chat_settings[user_id] = []
                
                # Переключаем выбор чата
                if chat_id in self.chat_settings[user_id]:
                    self.chat_settings[user_id].remove(chat_id)
                else:
                    self.chat_settings[user_id].append(chat_id)
                
                # Сохраняем настройки
                self.save_data(CHAT_SETTINGS_FILE, self.chat_settings)
                
                # Обновляем клавиатуру
                await self.update_chats_keyboard(event, user_id)
            
            elif data == "done":
                await event.respond(
                    f"✅ Настройки сохранены!\n"
                    f"Выбрано чатов: {len(self.chat_settings.get(user_id, []))}"
                )
                await event.delete()
        
        @self.bot.on(events.NewMessage(pattern='/stats'))
        async def stats_handler(event):
            user_id = str(event.sender_id)
            
            if user_id not in self.reaction_stats or not self.reaction_stats[user_id]:
                await event.respond("📊 Статистика пока пуста")
                return
            
            stats = self.reaction_stats[user_id]
            total_reactions = sum(len(messages) for messages in stats.values())
            
            # Получаем клиента для получения названий чатов
            client = await self.get_user_client(user_id)
            
            response = f"📊 **Статистика реакций**\n\n"
            response += f"Всего реакций: {total_reactions}\n\n"
            response += "**По чатам:**\n"
            
            for chat_id, messages in list(stats.items())[:10]:  # Показываем топ-10 чатов
                try:
                    if client:
                        entity = await client.get_entity(int(chat_id))
                        chat_name = entity.title
                    else:
                        chat_name = f"Чат {chat_id}"
                except:
                    chat_name = f"Чат {chat_id}"
                
                response += f"• {chat_name}: {len(messages)} реакций\n"
            
            await event.respond(response, parse_mode='markdown')
        
        @self.bot.on(events.NewMessage(pattern='/logout'))
        async def logout_handler(event):
            user_id = str(event.sender_id)
            
            if user_id in self.user_clients:
                await self.user_clients[user_id].disconnect()
                del self.user_clients[user_id]
            
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
                self.save_data(USER_SESSIONS_FILE, self.user_sessions)
            
            if user_id in self.chat_settings:
                del self.chat_settings[user_id]
                self.save_data(CHAT_SETTINGS_FILE, self.chat_settings)
            
            if user_id in self.reaction_stats:
                del self.reaction_stats[user_id]
                self.save_data(REACTION_STATS_FILE, self.reaction_stats)
            
            await event.respond("👋 Вы вышли из аккаунта")
        
        @self.bot.on(events.NewMessage)
        async def message_handler(event):
            # Обработка ввода номера телефона и кода
            user_id = str(event.sender_id)
            
            if user_id in self.user_auth_states:
                await self.handle_auth_input(event, user_id)
    
    async def handle_auth_input(self, event, user_id):
        """Обрабатывает ввод данных для авторизации"""
        state = self.user_auth_states[user_id]
        text = event.message.text.strip()
        
        if state['stage'] == 'waiting_phone':
            # Создаем клиента для пользователя
            client = TelegramClient(f'user_{user_id}', API_ID, API_HASH)
            await client.connect()
            
            try:
                # Отправляем запрос на код
                send_code_result = await client.send_code_request(text)
                
                state['phone'] = text
                state['phone_code_hash'] = send_code_result.phone_code_hash
                state['stage'] = 'waiting_code'
                state['client'] = client
                
                await event.respond("📱 Код подтверждения отправлен. Пожалуйста, введите его:")
            except Exception as e:
                logger.error(f"Ошибка при отправке кода: {e}")
                await event.respond("❌ Ошибка при отправке кода. Проверьте номер и попробуйте снова.")
                del self.user_auth_states[user_id]
        
        elif state['stage'] == 'waiting_code':
            try:
                # Пытаемся войти с кодом
                user = await state['client'].sign_in(
                    phone=state['phone'],
                    code=text,
                    phone_code_hash=state['phone_code_hash']
                )
                
                # Успешный вход
                self.user_clients[user_id] = state['client']
                
                # Сохраняем сессию
                session_string = state['client'].session.save()
                self.user_sessions[user_id] = session_string
                self.save_data(USER_SESSIONS_FILE, self.user_sessions)
                
                # Удаляем состояние авторизации
                del self.user_auth_states[user_id]
                
                # Запускаем слушатель сообщений для этого пользователя
                asyncio.create_task(self.start_user_listener(user_id))
                
                await event.respond(
                    "✅ **Успешный вход!**\n\n"
                    "Теперь вы можете использовать команду /chats для настройки автореакций.",
                    parse_mode='markdown'
                )
                
            except SessionPasswordNeededError:
                # Требуется 2FA
                state['stage'] = 'waiting_2fa'
                await event.respond("🔐 Требуется двухфакторная аутентификация. Введите ваш пароль:")
            except Exception as e:
                logger.error(f"Ошибка при входе: {e}")
                await event.respond("❌ Ошибка при входе. Проверьте код и попробуйте снова.")
                del self.user_auth_states[user_id]
        
        elif state['stage'] == 'waiting_2fa':
            try:
                # Вход с 2FA паролем
                user = await state['client'].sign_in(password=text)
                
                # Успешный вход
                self.user_clients[user_id] = state['client']
                
                # Сохраняем сессию
                session_string = state['client'].session.save()
                self.user_sessions[user_id] = session_string
                self.save_data(USER_SESSIONS_FILE, self.user_sessions)
                
                # Удаляем состояние авторизации
                del self.user_auth_states[user_id]
                
                # Запускаем слушатель сообщений для этого пользователя
                asyncio.create_task(self.start_user_listener(user_id))
                
                await event.respond(
                    "✅ **Успешный вход!**\n\n"
                    "Теперь вы можете использовать команду /chats для настройки автореакций.",
                    parse_mode='markdown'
                )
                
            except Exception as e:
                logger.error(f"Ошибка при входе с 2FA: {e}")
                await event.respond("❌ Ошибка при входе. Проверьте пароль и попробуйте снова.")
                del self.user_auth_states[user_id]
    
    async def get_user_client(self, user_id):
        """Получает или создает клиента для пользователя"""
        if user_id in self.user_clients:
            return self.user_clients[user_id]
        
        if user_id in self.user_sessions:
            try:
                client = TelegramClient(f'user_{user_id}', API_ID, API_HASH)
                client.session.load(self.user_sessions[user_id])
                await client.connect()
                
                if await client.is_user_authorized():
                    self.user_clients[user_id] = client
                    asyncio.create_task(self.start_user_listener(user_id))
                    return client
                else:
                    return None
            except:
                return None
        
        return None
    
    async def start_user_listener(self, user_id):
        """Запускает слушатель сообщений для пользователя"""
        client = self.user_clients.get(user_id)
        if not client:
            return
        
        @client.on(events.NewMessage)
        async def user_message_handler(event):
            chat_id = event.chat_id
            
            # Проверяем, включен ли этот чат для автореакций
            if (user_id in self.chat_settings and 
                chat_id in self.chat_settings[user_id]):
                
                try:
                    # Ставим реакцию
                    await client(SendReactionRequest(
                        peer=await client.get_input_entity(chat_id),
                        msg_id=event.message.id,
                        reaction=[ReactionCustomEmoji(document_id=DEFAULT_REACTION_ID)]
                    ))
                    
                    # Сохраняем в статистику
                    chat_id_str = str(chat_id)
                    if user_id not in self.reaction_stats:
                        self.reaction_stats[user_id] = {}
                    if chat_id_str not in self.reaction_stats[user_id]:
                        self.reaction_stats[user_id][chat_id_str] = []
                    
                    self.reaction_stats[user_id][chat_id_str].append({
                        'msg_id': event.message.id,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Ограничиваем историю последними 100 сообщениями на чат
                    if len(self.reaction_stats[user_id][chat_id_str]) > 100:
                        self.reaction_stats[user_id][chat_id_str] = self.reaction_stats[user_id][chat_id_str][-100:]
                    
                    self.save_data(REACTION_STATS_FILE, self.reaction_stats)
                    
                    logger.info(f"Реакция установлена пользователем {user_id} в чате {chat_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка при установке реакции для пользователя {user_id}: {e}")
        
        # Запускаем клиента
        await client.run_until_disconnected()
    
    async def update_chats_keyboard(self, event, user_id):
        """Обновляет клавиатуру с чатами"""
        # Получаем текущие выбранные чаты
        selected_chats = self.chat_settings.get(user_id, [])
        
        # Получаем список всех чатов
        chats = self.user_chats_list.get(user_id, [])
        
        # Создаем кнопки
        buttons = []
        row = []
        for i, (chat_id, chat_name) in enumerate(chats[:20]):
            display_name = chat_name[:20] + "..." if len(chat_name) > 20 else chat_name
            is_selected = chat_id in selected_chats
            prefix = "✅ " if is_selected else ""
            
            button = Button.inline(f"{prefix}{display_name}", data=f"chat_{chat_id}")
            row.append(button)
            
            if len(row) == 2:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        buttons.append([Button.inline("✅ Готово", data="done")])
        
        await event.edit(
            "📋 **Выберите чаты для автореакций:**\n"
            "Нажимайте на чаты чтобы выбрать/отменить выбор.\n"
            "✅ - чат выбран",
            buttons=buttons,
            parse_mode='markdown'
        )
    
    async def cleanup_old_stats(self):
        """Очищает старую статистику (каждые 24 часа)"""
        while True:
            await asyncio.sleep(24 * 3600)
            
            # Удаляем статистику старше 30 дней
            cutoff = datetime.now() - timedelta(days=30)
            
            for user_id in list(self.reaction_stats.keys()):
                for chat_id in list(self.reaction_stats[user_id].keys()):
                    messages = self.reaction_stats[user_id][chat_id]
                    self.reaction_stats[user_id][chat_id] = [
                        msg for msg in messages
                        if datetime.fromisoformat(msg['timestamp']) > cutoff
                    ]
                    
                    if not self.reaction_stats[user_id][chat_id]:
                        del self.reaction_stats[user_id][chat_id]
                
                if not self.reaction_stats[user_id]:
                    del self.reaction_stats[user_id]
            
            self.save_data(REACTION_STATS_FILE, self.reaction_stats)

async def main():
    bot = ReactionBot()
    await bot.start()

if __name__ == '__main__':
    asyncio.run(main())
