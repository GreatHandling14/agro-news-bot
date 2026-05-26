import os
import re
import json
import random
import hashlib
import requests
import feedparser
from datetime import datetime

# === КОНФИГУРАЦИЯ ===
RSS_URL = os.getenv('RSS_URL', 'https://newsnovosti.ru/agro-rossii-novosti/feed/')
VK_ACCESS_TOKEN = os.getenv('VK_ACCESS_TOKEN')
VK_GROUP_ID = os.getenv('VK_GROUP_ID')

# Файл для хранения опубликованных URL
PUBLISHED_FILE = 'published.json'

# === ФУНКЦИИ ===

def load_published():
    """Загружает список опубликованных URL"""
    try:
        # Пробуем скачать с GitHub (если есть)
        response = requests.get(
            'https://raw.githubusercontent.com/' + os.getenv('GITHUB_REPOSITORY') + '/main/published.json'
        )
        if response.status_code == 200:
            return response.json()
    except:
        pass
    
    # Или читаем локальный файл
    if os.path.exists(PUBLISHED_FILE):
        with open(PUBLISHED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_published(url, title):
    """Сохраняет URL в список опубликованных"""
    published = load_published()
    published.append({
        'url': url,
        'title': title,
        'published_at': datetime.now().isoformat()
    })
    
    # Сохраняем последние 1000 записей
    published = published[-1000:]
    
    with open(PUBLISHED_FILE, 'w', encoding='utf-8') as f:
        json.dump(published, f, ensure_ascii=False, indent=2)
    
    return published

def parse_rss(rss_url):
    """Парсит RSS ленту"""
    print(f"   RSS URL: {rss_url}")
    
    try:
        response = requests.get(rss_url, timeout=10)
        print(f"   Status code: {response.status_code}")
        
        feed = feedparser.parse(response.content)
        
        print(f"   Feed title: {feed.feed.get('title', 'Unknown')}")
        print(f"   Number of entries: {len(feed.entries)}")
        
        items = []
        for i, entry in enumerate(feed.entries):
            # CDATA автоматически парсится в feedparser
            title = entry.get('title', '').strip()
            link = entry.get('link', '').strip()
            description = entry.get('description', '')
            
            # Очищаем description от HTML тегов
            # Очищаем от HTML но оставляем до 1000 символов
            clean_desc = re.sub(r'<[^>]+>', '', description)[:1000]
            
            # Пропускаем заголовок канала
            if not title or not link:
                continue
            
            print(f"   Entry {i+1}: {title[:50]}...")
            
            items.append({
                'title': title,
                'link': link,
                'description': clean_desc
            })
        
        print(f"   ✅ Всего новостей: {len(items)}")
        return items
        
    except Exception as e:
        print(f"   ❌ Ошибка парсинга: {e}")
        import traceback
        traceback.print_exc()
        return []

def filter_news(items, published_urls):
    """Фильтрует уже опубликованные новости"""
    new_items = [
        item for item in items 
        if item['link'] not in published_urls
    ]
    return new_items

def generate_hashtags(title, description):
    """Генерирует хештеги на основе текста"""
    # Простые агро-хештеги
    hashtags = ['#агроюг', '#сельскоехозяйство', '#агробизнес']
    
    # Добавляем тематические
    text = (title + ' ' + description).lower()
    
    if any(word in text for word in ['кукуруз', 'урожай', 'растени']):
        hashtags.append('#кукуруза')
        hashtags.append('#урожай')
    
    if any(word in text for word in ['технолог', 'инновац', 'современн']):
        hashtags.append('#агротехнологии')
    
    if 'краснодар' in text or 'кубан' in text:
        hashtags.append('#краснодарскийкрай')
    
    if 'ростов' in text:
        hashtags.append('#ростовскаяобласть')
    
    return ' '.join(hashtags[:7])  # Максимум 7 хештегов

def post_to_vk(message, link=None):
    """Публикует пост в VK"""
    url = 'https://api.vk.com/method/wall.post'
    
    # Добавляем ссылку в конец сообщения (если есть)
    if link and link not in message:
        message = message + f'\n\n🔗 {link}'
    
    params = {
        'owner_id': f'-{VK_GROUP_ID}',  # Минус для группы
        'message': message,
        'access_token': VK_ACCESS_TOKEN,
        'v': '5.199'
    }
    
    # УБРАЛИ attachments - VK сам создаст preview из ссылки в тексте
    response = requests.post(url, data=params)
    result = response.json()
    
    if 'response' in result:
        print(f"✅ Пост опубликован! ID: {result['response']['post_id']}")
        return True
    else:
        print(f"❌ Ошибка: {result}")
        return False

def main():
    print("🚀 Запуск бота...")
    
    # 1. Парсим RSS
    print("📰 Парсинг RSS...")
    items = parse_rss(RSS_URL)
    print(f"   Найдено новостей: {len(items)}")
    
    if not items:
        print("❌ Нет новостей в RSS")
        return
    
    # 2. Загружаем опубликованные
    print("📋 Загрузка опубликованных...")
    published_urls = [item['url'] for item in load_published()]
    print(f"   Опубликовано: {len(published_urls)}")
    
    # 3. Фильтруем
    print("🔍 Фильтрация...")
    new_items = filter_news(items, published_urls)
    print(f"   Новых новостей: {len(new_items)}")
    
    if not new_items:
        print("✅ Нет новых новостей для публикации")
        return
    
    # 4. Выбираем 6-7 последних новостей
    news_batch = new_items[:7]  # Берем максимум 7
    print(f"\n📋 Формируем дайджест из {len(news_batch)} новостей...")
    
    # 5. Формируем пост
    today = datetime.now().strftime("%d %B %Y").replace(' 0', ' ')
    
    message = f"📰 АГРО ДАЙДЖЕСТ | {today}\n\n"
    
    for i, news in enumerate(news_batch, 1):
        # Заголовок с номером
        message += f"🔹 {news['title']}\n"
        
        # Описание (если есть)
        if news['description']:
            # Обрезаем до 150 символов
            desc = news['description'][:150].strip()
            if len(news['description']) > 150:
                desc += "..."
            message += f"   {desc}\n"
        
        # Ссылка (короткая)
        from urllib.parse import urlparse
        domain = urlparse(news['link']).netloc.replace('www.', '')
        message += f"   📎 {domain}\n"
        
        # Пустая строка между новостями
        message += "\n"
    
    # Хештеги
    hashtags = "#агроюг #сельскоехозяйство #агробизнес #агродайджест"
    message += f"📌 Источники: {domain}\n\n"
    message += hashtags
    
    print(f"\n📝 Сообщение ({len(message)} символов):")
    print(message[:300] + "...\n")
    
    # 6. Публикуем в VK
    print("📤 Публикация в VK...")
    success = post_to_vk(message)
    
    if success:
        # 7. Сохраняем все опубликованные URL
        for news in news_batch:
            save_published(news['link'], news['title'])
        print("✅ Дайджест опубликован!")
    else:
        print("❌ Ошибка публикации")

def post_to_vk(message, link=None):
    """Публикует пост в VK"""
    url = 'https://api.vk.com/method/wall.post'
    
    params = {
        'owner_id': f'-{VK_GROUP_ID}',
        'message': message,
        'access_token': VK_ACCESS_TOKEN,
        'v': '5.199'
    }
    
    response = requests.post(url, data=params)
    result = response.json()
    
    if 'response' in result:
        print(f"✅ Пост опубликован! ID: {result['response']['post_id']}")
        return True
    else:
        print(f"❌ Ошибка VK API: {result}")
        return False

if __name__ == '__main__':
    main()
