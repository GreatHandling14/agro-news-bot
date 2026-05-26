import os
import re
import json
import random
import requests
import feedparser
from datetime import datetime, timedelta
from urllib.parse import urlparse
import subprocess

# === КОНФИГУРАЦИЯ ===
RSS_URLS = [
    'https://www.agroinvestor.ru/feed/public-agronews.xml',
    'https://vesti365.ru/novosti-agro-rossii/',
    'https://agri-news.ru/feed/'
    # Можно добавить ещё источники
]

MIN_NEWS_FOR_POST = 5  # Минимум новостей для публикации
MAX_NEWS_FOR_POST = 7  # Максимум в дайджесте
MAX_AGE_DAYS = 2       # Брать новости не старше 2 дней

VK_ACCESS_TOKEN = os.getenv('VK_ACCESS_TOKEN')
VK_GROUP_ID = os.getenv('VK_GROUP_ID')
PUBLISHED_FILE = 'published.json'

# === ФУНКЦИИ ===

def load_published():
    """Загружает список опубликованных URL"""
    try:
        # Пробуем скачать из репозитория
        repo = os.getenv('GITHUB_REPOSITORY')
        url = f'https://raw.githubusercontent.com/{repo}/main/published.json'
        
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"   📥 Загружено {len(data)} опубликованных URL")
            return data
        else:
            print("   📭 Файл не найден (первый запуск)")
            return []
    except Exception as e:
        print(f"   ⚠️ Ошибка загрузки: {e}")
        return []

def save_to_repo(published):
    """Сохраняет published.json в репозиторий"""
    try:
        # Сохраняем локально
        with open(PUBLISHED_FILE, 'w', encoding='utf-8') as f:
            json.dump(published, f, ensure_ascii=False, indent=2)
        
        # Настраиваем git
        subprocess.run(['git', 'config', '--global', 'user.name', 'agro-bot'], 
                      check=True, capture_output=True)
        subprocess.run(['git', 'config', '--global', 'user.email', 'bot@agro.local'], 
                      check=True, capture_output=True)
        
        # Коммитим
        subprocess.run(['git', 'add', PUBLISHED_FILE], check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Update published news'], 
                      check=True, capture_output=True)
        
        # Пушим
        token = os.getenv('GITHUB_TOKEN')
        repo = os.getenv('GITHUB_REPOSITORY')
        remote_url = f'https://x-access-token:{token}@github.com/{repo}.git'
        
        subprocess.run(['git', 'remote', 'set-url', 'origin', remote_url], 
                      check=True, capture_output=True)
        subprocess.run(['git', 'push', 'origin', 'main'], 
                      check=True, capture_output=True)
        
        print("   ✅ Сохранено в репозиторий")
        
    except Exception as e:
        print(f"   ⚠️ Ошибка сохранения: {e}")

def mark_as_published(url, title):
    """Добавляет URL в список опубликованных"""
    published = load_published()
    
    # Проверяем не дубликат ли
    if any(p['url'] == url for p in published):
        print(f"   ⚠️ Уже опубликовано: {url}")
        return
    
    # Добавляем
    published.append({
        'url': url,
        'title': title,
        'published_at': datetime.now().isoformat()
    })
    
    # Оставляем последние 1000
    published = published[-1000:]
    
    # Сохраняем
    save_to_repo(published)
    print(f"   ✅ Отмечено как опубликованное")

def parse_all_rss():
    """Парсит все RSS ленты"""
    all_items = []
    
    for rss_url in RSS_URLS:
        print(f"\n📰 Парсинг: {rss_url[:50]}...")
        
        try:
            response = requests.get(rss_url, timeout=10)
            feed = feedparser.parse(response.content)
            
            print(f"   Найдено: {len(feed.entries)}")
            
            for entry in feed.entries:
                title = entry.get('title', '').strip()
                link = entry.get('link', '').strip()
                description = entry.get('description', '')
                pub_date = entry.get('published', '')
                
                # Парсим дату
                try:
                    if pub_date:
                        # Пробуем распарсить дату публикации
                        pub_datetime = datetime.strptime(
                            pub_date[:25], 
                            '%a, %d %b %Y %H:%M:%S'
                        )
                    else:
                        pub_datetime = datetime.now()
                except:
                    pub_datetime = datetime.now()
                
                # Проверяем возраст (не старше MAX_AGE_DAYS)
                age = datetime.now() - pub_datetime
                if age.days > MAX_AGE_DAYS:
                    continue
                
                # Очищаем описание
                clean_desc = re.sub(r'<[^>]+>', '', description)[:300]
                
                # Пропускаем пустые
                if not title or not link:
                    continue
                
                all_items.append({
                    'title': title,
                    'link': link,
                    'description': clean_desc,
                    'published_at': pub_datetime,
                    'source': urlparse(link).netloc.replace('www.', '')
                })
        
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            continue
    
    print(f"\n✅ Всего новостей из всех источников: {len(all_items)}")
    return all_items

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
    print(f"📋 Минимум новостей: {MIN_NEWS_FOR_POST}")
    print(f"📋 Максимум новостей: {MAX_NEWS_FOR_POST}")
    print(f"📋 Возраст новостей: до {MAX_AGE_DAYS} дней")
    
    # 1. Парсим ВСЕ RSS
    print("\n📰 Парсинг всех источников...")
    all_items = parse_all_rss()
    
    if not all_items:
        print("❌ Нет новостей в RSS")
        return
    
    # 2. Загружаем опубликованные
    print("\n📋 Загрузка опубликованных...")
    published = load_published()
    published_urls = [p['url'] for p in published]
    print(f"   Опубликовано: {len(published_urls)}")
    
    # 3. Фильтруем дубликаты
    print("\n🔍 Фильтрация дубликатов...")
    new_items = [
        item for item in all_items 
        if item['link'] not in published_urls
    ]
    print(f"   Новых новостей: {len(new_items)}")
    
    # 4. Проверяем минимум
    if len(new_items) < MIN_NEWS_FOR_POST:
        print(f"\n⏸️  Мало новостей ({len(new_items)} < {MIN_NEWS_FOR_POST})")
        print("   Ждём следующего запуска...")
        return
    
    # 5. Сортируем по дате (сначала новые)
    new_items.sort(key=lambda x: x['published_at'], reverse=True)
    
    # 6. Берем 5-7 новостей
    news_batch = new_items[:MAX_NEWS_FOR_POST]
    print(f"\n📋 Формируем дайджест из {len(news_batch)} новостей...")
    
    # 7. Формируем пост
    today = datetime.now().strftime("%d %B %Y").replace(' 0', ' ')
    
    message = f"📰 АГРО ДАЙДЖЕСТ | {today}\n\n"
    
    sources = set()
    
    for i, news in enumerate(news_batch, 1):
        # Заголовок
        message += f"🔹 {news['title']}\n"
        
        # Описание
        if news['description']:
            desc = news['description'][:150].strip()
            if len(news['description']) > 150:
                desc += "..."
            message += f"   {desc}\n"
        
        # Источник
        domain = news['source']
        sources.add(domain)
        message += f"   📎 {domain}\n"
        
        # Пустая строка
        message += "\n"
    
    # Хештеги и источники
    hashtags = "#агроюг #сельскоехозяйство #агробизнес #агродайджест"
    sources_str = ', '.join(sources)
    
    message += f"📌 Источники: {sources_str}\n\n"
    message += hashtags
    
    print(f"\n📝 Сообщение ({len(message)} символов):")
    print(message[:400] + "...\n")
    
    # 8. Публикуем в VK
    print("📤 Публикация в VK...")
    success = post_to_vk(message)
    
    if success:
        # 9. Отмечаем все как опубликованные
        print("\n💾 Сохранение опубликованных...")
        for news in news_batch:
            mark_as_published(news['link'], news['title'])
        
        print("\n✅ Дайджест опубликован!")
        print(f"   Новостей: {len(news_batch)}")
        print(f"   Источников: {len(sources)}")
    else:
        print("\n❌ Ошибка публикации")

def post_to_vk(message):
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
