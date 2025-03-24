import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from bs4 import BeautifulSoup
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from googlesearch import search
from urllib.parse import quote_plus

# Конфигурация
API_TOKEN = "YOUR_BOT_TOKEN"
MAX_RESULTS = 5
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
executor = ThreadPoolExecutor()

# Кэш для хранения результатов
cache = {}

async def yandex_search(query: str, num_results: int = 5):
    try:
        url = f"https://yandex.ru/search/?text={quote_plus(query)}&lr=213"
        headers = {"User -Agent": USER_AGENT}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=TIMEOUT) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                results = []
                for item in soup.select('.serp-item.organic')[:num_results]:
                    link = item.select_one('.organic__url')
                    if link:
                        url = link.get('href')
                        title = link.text.strip()
                        results.append({'url': url, 'title': title})
                return results
    except Exception as e:
        logging.error(f"Yandex search error: {e}")
        return []

async def google_search(query: str, num_results: int = 5):
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            executor,
            lambda: list(search(query, num_results=num_results, lang='ru'))
        )
        return [{'url': result, 'title': result} for result in results]
    except Exception as e:
        logging.error(f"Google search error: {e}")
        return []

async def perform_web_search(query: str):
    if query in cache:
        return cache[query]
    
    google_results = await google_search(query, MAX_RESULTS)
    yandex_results = await yandex_search(query, MAX_RESULTS)
    
    # Объединение и удаление дубликатов
    combined = {result['url']: result for result in google_results + yandex_results}
    cache[query] = list(combined.values())
    return cache[query][:MAX_RESULTS * 2]

async def fetch_page_content(url):
    try:
        headers = {"User -Agent": USER_AGENT}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=TIMEOUT) as response:
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Извлечение заголовка
                title = soup.find('title').get_text() if soup.title else url
                
                # Извлечение основного контента
                paragraphs = soup.find_all(['p', 'article', 'div.content'])
                description = ' '.join([p.get_text().strip() for p in paragraphs[:3]])
                description = description[:300] + '...' if len(description) > 300 else description
                
                return {
                    'title': title.strip(),
                    'description': description.strip(),
                    'url': url
                }
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        return None

@dp.message(Command("search"))
async def handle_search(message: types.Message):
    query = message.text.split(" ", 1)[1] if len(message.text.split()) > 1 else ""
    if not query:
        return await message.answer("✏️ Введите запрос после команды /search")
    
    await message.answer("🔍 Ищу информацию в Google и Yandex...")
    
    try:
        # Получаем список URL
        urls = await perform_web_search(query)
        if not urls:
            return await message.answer("😞 Ничего не найдено")
        
        # Парсим содержимое страниц
        tasks = [fetch_page_content(url['url']) for url in urls[:MAX_RESULTS * 2]]
        results = await asyncio.gather(*tasks)
        
        # Формируем ответ
        response = ["🔍 Результаты поиска:\ \n"]
        for i, result in enumerate(filter(None, results), 1):
            source = "🅰️ Яндекс" if "yandex" in result['url'] else "🌀 Google"
            response.append(
                f"{i}. {source}\n"
                f"<b><a href='{result['url']}'>{result['title']}</a></b>\n"
                f"{result['description']}\n"
            )
        
        await message.answer(
            '\n'.join(response),
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        
        # Добавление кнопок для пагинации
        await message.answer("📄 Показать больше результатов?", reply_markup=await create_pagination_keyboard(query))
        
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("⚠️ Произошла ошибка при обработке запроса")

async def create_pagination_keyboard(query):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Следующие результаты", callback_data=f"next_results:{query}"))
    return keyboard

@dp.callback_query_handler(lambda c: c.data.startswith("next_results:"))
async def process_next_results(callback_query: types.CallbackQuery):
    query = callback_query.data.split(":")[1]
    await callback_query.answer()
    
    # Получаем следующие результаты
    urls = await perform_web_search(query)
    if not urls:
        return await callback_query.message.answer("😞 Ничего не найдено")
    
    # Парсим содержимое страниц
    tasks = [fetch_page_content(url['url']) for url in urls[MAX_RESULTS:MAX_RESULTS * 2]]
    results = await asyncio.gather(*tasks)
    
    # Формируем ответ
    response = ["🔍 Дополнительные результаты:\n"]
    for i, result in enumerate(filter(None, results), 1):
        source = "🅰️ Яндекс" if "yandex" in result['url'] else "🌀 Google"
        response.append(
            f"{i}. {source}\n"
            f"<b><a href='{result['url']}'>{result['title']}</a></b>\n"
            f"{result['description']}\n"
        )
    
    await callback_query.message.answer(
        '\n'.join(response),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

# Функция для поиска изображений
async def image_search(query: str):
    # Реализация поиска изображений через Google или Yandex
    pass

@dp.message(Command("images"))
async def handle_image_search(message: types.Message):
    query = message.text.split(" ", 1)[1] if len(message.text.split()) > 1 else ""
    if not query:
        return await message.answer("✏️ Введите запрос после команды /images")
    
    await message.answer("🔍 Ищу изображения...")
    
    # Вызов функции поиска изображений
    await image_search(query)

# Интеграция нейросети Liama 3
async def liama_search(query: str):
    # Реализация поиска с использованием Liama 3
    pass

@dp.message(Command("liama"))
async def handle_liama_search(message: types.Message):
    query = message.text.split(" ", 1)[1] if len(message.text.split()) > 1 else ""
    if not query:
        return await message.answer("✏️ Введите запрос после команды /liama")
    
    await message.answer("🔍 Ищу с помощью Liama 3...")
    
    # Вызов функции поиска с Liama 3
    await liama_search(query)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
