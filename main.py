import os
import re
import json
import random
import requests
import html
import feedparser
from datetime import datetime, timedelta
from urllib.parse import urlparse
import subprocess
from bs4 import BeautifulSoup

# === КОНФИГУРАЦИЯ ===
RSS_URLS = [
    'https://www.agroinvestor.ru/feed/public-agronews.xml',
    'https://newsnovosti.ru/novosti-selskoe-hozajstvo/'
    # Можно добавить ещё источники
]

MIN_NEWS_FOR_POST = 2  # Минимум новостей для публикации
MAX_NEWS_FOR_POST = 7  # Максимум в дайджесте
MAX_AGE_DAYS = 2       # Брать новости не старше 2 дней

VK_ACCESS_TOKEN = os.getenv('VK_ACCESS_TOKEN')
VK_GROUP_ID = os.getenv('VK_GROUP_ID')
PUBLISHED_FILE = 'published.json'

# === ПУЛ ХЕШТЕГОВ ===
HASHTAG_POOL = [
    '#агроюг', '#сельскоехозяйство', '#агробизнес', '#агродайджест',
    '#кукуруза', '#урожай', '#растениеводство', '#животноводство',
    '#агротехнологии', '#инновации', '#фермер', '#агропром',
    '#краснодарскийкрай', '#ростовскаяобласть', '#ставрополье',
    '#зерно', '#овощи', '#фрукты', '#техника', '#удобрения',
    '#ирригация', '#агрострахование', '#экспорт', '#импорт', '#агро2026',
    '#апк', '#агропром','#сзр','#защитарастений',
    '#пестициды', '#поле','#гербициды','#фунгициды',
]

# === ФУНКЦИИ ===

def load_published():
    """Загружает список опубликованных URL"""
    try:
        # Скачиваем published.json из репозитория
        repo = os.getenv('GITHUB_REPOSITORY')
        token = os.getenv('GITHUB_TOKEN')
        url = f'https://api.github.com/repos/{repo}/contents/published.json'
        
        headers = {'Authorization': f'token {token}'} if token else {}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # Декодируем base64
            import base64
            content = base64.b64decode(data['content']).decode('utf-8')
            published = json.loads(content)
            print(f"   📥 Загружено {len(published)} опубликованных URL")
            return published
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
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*'
            }
            
            response = requests.get(rss_url, headers=headers, timeout=15)
            feed = feedparser.parse(response.content)
            
            print(f"   Найдено: {len(feed.entries)}")
            
            # Показываем первые 5 новостей для отладки
            for i, entry in enumerate(feed.entries[:5]):
                title = entry.get('title', '')
                pub_date = entry.get('published', '')
                print(f"   📰 {title[:60]}... | Дата: {pub_date[:25] if pub_date else 'НЕТ'}")
            
            for entry in feed.entries:
                title = entry.get('title', '').strip()
                link = entry.get('link', '').strip()
                description = entry.get('description', '')
                pub_date = entry.get('published', '')
                
                # Декодируем HTML-сущности и убираем теги
                description = html.unescape(description)
                clean_desc = re.sub(r'<[^>]+>', '', description)[:300]
                
                # Парсим дату
                pub_datetime = datetime.now()
                if pub_date:
                    try:
                        pub_datetime = datetime.strptime(pub_date[:25], '%a, %d %b %Y %H:%M:%S')
                    except:
                        pass
                
                # Проверяем возраст
                age = datetime.now() - pub_datetime
                if age.days > MAX_AGE_DAYS:
                    continue
                
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
        # Парсим HTML сайты
    print("\n📰 Парсим HTML сайты...")
    html_items = parse_agroxxi_html()
    all_items.extend(html_items)
    
    
    print(f"\n✅ Всего новостей из всех источников: {len(all_items)}")
    return all_items

def parse_agroxxi_html():
    """Парсит новости с agroxxi.ru"""
    url = 'https://www.agroxxi.ru/novosti-selskogo-hozjaistva.html'
    print(f"\n📰 Парсинг HTML: {url[:50]}...")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'lxml')
        
        items = []
        news_blocks = soup.find_all('article', class_='slavecon')
        
        print(f"   Найдено блоков: {len(news_blocks)}")
        
        for block in news_blocks[:20]:  # Берём первые 20 новостей
            # Ссылка и заголовок
            link_tag = block.find('a', href=True)
            if not link_tag:
                continue
            
            title_tag = block.find('h2')
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
            
            link = link_tag.get('href')
            if link and not link.startswith('http'):
                link = 'https://www.agroxxi.ru' + link
            
            # Описание
            desc_tag = block.find('div', class_='slavecon-desc')
            description = desc_tag.get_text(strip=True)[:300] if desc_tag else ''
            
            # Дата (сегодня/вчера)
            date_tag = block.find('div', class_='slavecon-pubdate')
            date_text = date_tag.get_text(strip=True) if date_tag else ''
            
            # Парсим дату
            pub_datetime = datetime.now()
            try:
                if 'сегодня' in date_text.lower():
                    time_str = date_text.split('в')[1].strip() if 'в' in date_text else '00:00'
                    pub_datetime = datetime.now().replace(
                        hour=int(time_str.split(':')[0]),
                        minute=int(time_str.split(':')[1].strip())
                    )
                elif 'вчера' in date_text.lower():
                    time_str = date_text.split('в')[1].strip() if 'в' in date_text else '00:00'
                    pub_datetime = (datetime.now() - timedelta(days=1)).replace(
                        hour=int(time_str.split(':')[0]),
                        minute=int(time_str.split(':')[1].strip())
                    )
            except:
                pass
            
            items.append({
                'title': title,
                'link': link,
                'description': description,
                'published_at': pub_datetime,
                'source': 'agroxxi.ru'
            })
        
        print(f"   ✅ Спаршено новостей: {len(items)}")
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

def get_random_hashtags(count=4):
    """Возвращает случайные хештеги из пула"""
    return ' '.join(random.sample(HASHTAG_POOL, min(count, len(HASHTAG_POOL))))
    
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
    
    # Показываем первые 5 новостей для отладки
    if len(all_items) < 5:
        print(f"   📰 {title[:60]}...")
        print(f"      🔗 {link[:60]}...")
        print(f"      📅 {pub_date}")
    
    # ... остальной код ...


    
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
    
        # Случайные хештеги
        hashtags = get_random_hashtags(4)

        # Призыв подписаться
        cta = "\n\n🔔 Подписывайтесь на нашу группу, чтобы не пропустить важные агро-новости!"
        sources_str = ', '.join(sources)
        message += f"📌 Источники: {sources_str}"
        message += f"\n\n{hashtags}"
        message += f"\n{cta}"
    
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
