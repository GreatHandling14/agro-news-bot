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
    feed = feedparser.parse(rss_url)
    items = []
    
    for entry in feed.entries:
        title = entry.get('title', '')
        link = entry.get('link', '')
        description = entry.get('description', '')
        
        # Очищаем description от HTML тегов
        clean_desc = re.sub(r'<[^>]+>', '', description)[:300]
        
        # Пропускаем заголовок канала
        if 'Агро XXI' in title or 'Комментарии' in title:
            continue
        
        items.append({
            'title': title,
            'link': link,
            'description': clean_desc
        })
    
    return items

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
    
    params = {
        'owner_id': f'-{VK_GROUP_ID}',  # Минус для группы
        'message': message,
        'access_token': VK_ACCESS_TOKEN,
        'v': '5.199'
    }
    
    if link:
        params['attachments'] = link
    
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
    
    # 4. Выбираем случайную из первых 3
    selected = random.choice(new_items[:min(3, len(new_items))])
    print(f"\n📰 Выбрана новость: {selected['title'][:50]}...")
    
    # 5. Формируем сообщение
    hashtags = generate_hashtags(selected['title'], selected['description'])
    
    message = f"""🌾 {selected['title']}

{selected['description']}

🔗 {selected['link']}

{hashtags}"""
    
    print(f"\n📝 Сообщение:\n{message[:200]}...")
    
    # 6. Публикуем в VK
    print("\n📤 Публикация в VK...")
    success = post_to_vk(message, selected['link'])
    
    if success:
        # 7. Сохраняем в опубликованные
        save_published(selected['link'], selected['title'])
        print("✅ Готово!")
    else:
        print("❌ Ошибка публикации")

if __name__ == '__main__':
    main()
