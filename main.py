import asyncio
from telethon import TelegramClient, events
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionCustomEmoji

# Ваши данные
api_id = 36590443
api_hash = '401ed4b74b5d1d57feb7aa72c918e361'
chat_id = -1002559865477
reaction_id = 5229159576649093081

# Создаем клиента
client = TelegramClient('session_name', api_id, api_hash)

@client.on(events.NewMessage(chats=chat_id))
async def handler(event):
    try:
        # Устанавливаем реакцию на сообщение
        await client(SendReactionRequest(
            peer=await client.get_input_entity(chat_id),
            msg_id=event.message.id,
            reaction=[ReactionCustomEmoji(document_id=reaction_id)]
        ))
        print(f"✅ Реакция установлена на сообщение {event.message.id}")
    except Exception as e:
        print(f"❌ Ошибка при установке реакции: {e}")

async def main():
    # Запускаем клиента
    await client.start()
    print("🟢 Бот запущен и слушает сообщения...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
