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
    'https://news.google.com/rss/search?q=сельское+хозяйство+Россия+АПК&hl=ru&gl=RU&ceid=RU:ru',
]

MIN_NEWS_FOR_POST = 1
MAX_NEWS_FOR_POST = 7
MAX_AGE_DAYS = 5

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
    '#апк', '#агропром', '#сзр', '#защитарастений',
    '#пестициды', '#поле', '#гербициды', '#фунгициды',
]

# === ФУНКЦИИ ===

def load_published():
    """Загружает список опубликованных URL"""
    try:
        repo = os.getenv('GITHUB_REPOSITORY')
        token = os.getenv('GITHUB_TOKEN')
        url = f'https://api.github.com/repos/{repo}/contents/published.json'
        
        headers = {'Authorization': f'token {token}'} if token else {}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
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
        with open(PUBLISHED_FILE, 'w', encoding='utf-8') as f:
            json.dump(published, f, ensure_ascii=False, indent=2)
        
        subprocess.run(['git', 'config', '--global', 'user.name', 'agro-bot'], 
                      check=True, capture_output=True)
        subprocess.run(['git', 'config', '--global', 'user.email', 'bot@agro.local'], 
                      check=True, capture_output=True)
        
        subprocess.run(['git', 'add', PUBLISHED_FILE], check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Update published news'], 
                      check=True, capture_output=True)
        
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
    
    if any(p['url'] == url for p in published):
        print(f"   ⚠️ Уже опубликовано: {url}")
        return
    
    published.append({
        'url': url,
        'title': title,
        'published_at': datetime.now().isoformat()
    })
    
    published = published[-1000:]
    save_to_repo(published)
    print(f"   ✅ Отмечено как опубликованное")

def _extract_source_from_google(link, title, description):
    """Извлекает оригинальный источник из новости Google News"""
    # Пробуем найти "via Название" в заголовке
    if ' via ' in title.lower():
        parts = title.split(' via ')
        if len(parts) > 1:
            return parts[-1].strip()
    
    # Пробуем найти источник в описании (формат: "› Источник •")
    source_match = re.search(r'›\s*([^\s•<]+(?:\s+[^\s•<]+)*)\s*[•<]', description)
    if source_match:
        return source_match.group(1).strip()
    
    # Пробуем извлечь из ссылки (ищем оригинальный домен в параметрах)
    # Google часто добавляет &url= или похожие параметры
    url_match = re.search(r'url=([^&]+)', link)
    if url_match:
        original_url = url_match.group(1)
        domain = urlparse(original_url).netloc.replace('www.', '')
        if domain and 'google' not in domain:
            return domain
    
    # Фоллбэк: возвращаем "Google News"
    return 'news.google.com'

def parse_all_rss():
    """Парсит все RSS ленты"""
    all_items = []
    
    for rss_url in RSS_URLS:
        print(f"\n📰 Парсинг: {rss_url[:50]}...")
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*'
            }
            
            response = requests.get(rss_url, headers=headers, timeout=15)
            feed = feedparser.parse(response.content)
            
            print(f"   Найдено: {len(feed.entries)}")
            
            for entry in feed.entries:
                title = entry.get('title', '').strip()
                link = entry.get('link', '').strip()
                description = entry.get('description', '')
                pub_date = entry.get('published', '')
                
                # Очищаем описание
                description = html.unescape(description)
                clean_desc = re.sub(r'<[^>]+>', '', description)[:300]
                
                # Определяем источник
                if 'news.google.com' in link:
                    source_name = _extract_source_from_google(link, title, description)
                else:
                    source_name = urlparse(link).netloc.replace('www.', '')
                
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
                    'source': source_name
                })
        
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            continue
    
    print(f"✅ RSS: {len(all_items)} новостей")
    return all_items

def parse_dairynews_kz():
    """Парсит новости dairynews.today/kz/ (HTML парсинг)"""
    url = 'https://dairynews.today/kz/'
    print(f"\n📰 Парсинг HTML: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'lxml')
        
        items = []
        news_blocks = soup.find_all('div', class_='row no-gutters')
        
        print(f"   Найдено блоков: {len(news_blocks)}")
        
        for block in news_blocks:
            link_tag = block.find('h3', class_='title')
            if not link_tag:
                link_tag = block.find('a', href=True)
            
            if not link_tag:
                continue
            
            title = link_tag.get_text(strip=True)
            link = link_tag.get('href')
            
            if link and link.startswith('/'):
                link = 'https://dairynews.today' + link
            elif not link or not link.startswith('http'):
                continue
            
            date_span = block.find('span', class_='data')
            date_text = date_span.get_text(strip=True) if date_span else ''
            
            pub_datetime = datetime.now()
            if date_text:
                try:
                    pub_datetime = datetime.strptime(date_text, '%d.%m.%Y')
                except:
                    pass
            
            desc_tag = block.find('div', class_='infotitle')
            description = desc_tag.get_text(strip=True)[:300] if desc_tag else ''
            
            if title and link:
                items.append({
                    'title': title,
                    'link': link,
                    'description': description,
                    'published_at': pub_datetime,
                    'source': 'dairynews.today'
                })
        
        print(f"   ✅ DairyNews: {len(items)} новостей")
        return items
        
    except Exception as e:
        print(f"   ❌ Ошибка парсинга DairyNews: {e}")
        return []

def _normalize_title(title):
    """Нормализует заголовок для сравнения (убирает спецсимволы, приводит к lower)"""
    return re.sub(r'[^\w\sа-яА-ЯёЁ]', '', title).lower().strip()

def filter_news(items, published_urls):
    """Фильтрует дубликаты по URL и по нормализованному заголовку"""
    seen_titles = set()
    new_items = []
    
    for item in items:
        # Пропускаем если URL уже опубликован
        if item['link'] in published_urls:
            continue
        
        # Пропускаем если заголовок уже встречался
        title_norm = _normalize_title(item['title'])
        if title_norm in seen_titles:
            print(f"   ⚠️ Дубль заголовка: {item['title'][:50]}...")
            continue
        
        seen_titles.add(title_norm)
        new_items.append(item)
    
    return new_items

def get_random_hashtags(count=4):
    """Возвращает случайные хештеги из пула"""
    return ' '.join(random.sample(HASHTAG_POOL, min(count, len(HASHTAG_POOL))))

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

def main():
    print("🚀 Запуск бота...")
    print(f"📋 Минимум новостей: {MIN_NEWS_FOR_POST}")
    print(f"📋 Максимум новостей: {MAX_NEWS_FOR_POST}")
    print(f"📋 Возраст новостей: до {MAX_AGE_DAYS} дней")
    
    # 1. Парсим ВСЕ источники
    print("\n📰 Парсинг всех источников...")
    rss_items = parse_all_rss()
    dairy_items = parse_dairynews_kz()
    all_items = rss_items + dairy_items
    
    print(f"\n✅ ВСЕГО новостей: {len(all_items)}")
    
    if not all_items:
        print("❌ Нет новостей")
        return
    
    # 2. Загружаем опубликованные
    print("\n📋 Загрузка опубликованных...")
    published = load_published()
    published_urls = [p['url'] for p in published]
    print(f"   Опубликовано: {len(published_urls)}")
    
    # 3. Фильтруем дубликаты
    print("\n🔍 Фильтрация дубликатов...")
    new_items = filter_news(all_items, published_urls)
    print(f"   Новых новостей: {len(new_items)}")
    
    # 4. ОГРАНИЧЕНИЕ GOOGLE NEWS (максимум 1 новость!)
    print("\n📊 Распределение источников...")
    google_items = [item for item in new_items if 'news.google.com' in item['link'].lower() or item['source'] == 'news.google.com']
    other_items = [item for item in new_items if item not in google_items]
    
    print(f"   Google News: {len(google_items)}")
    print(f"   Другие источники: {len(other_items)}")
    
    # Оставляем ТОЛЬКО 1 из Google (или 0 если мало других)
    if len(google_items) > 1:
        google_items = google_items[:1]
        print(f"   ⚠️ Google News ограничен до 1 новости")
    
    # Сначала не-Google, потом Google (если есть)
    filtered_items = other_items + google_items
    
    # 5. Проверяем минимум
    if len(filtered_items) < MIN_NEWS_FOR_POST:
        print(f"\n⏸️  Мало новостей ({len(filtered_items)} < {MIN_NEWS_FOR_POST})")
        print("   Ждём следующего запуска...")
        return
    
    # 6. Сортируем по дате (сначала новые)
    filtered_items.sort(key=lambda x: x['published_at'], reverse=True)
    
    # 7. Берем новости для дайджеста
    news_batch = filtered_items[:MAX_NEWS_FOR_POST]
    print(f"\n📋 Формируем дайджест из {len(news_batch)} новостей...")
    
    # 8. Формируем пост
    today = datetime.now().strftime("%d %B %Y").replace(' 0', ' ')
    message = f"📰 АГРО ДАЙДЖЕСТ | {today}\n\n"
    sources = set()
    
    for i, news in enumerate(news_batch, 1):
        # Заголовок
        message += f"🔹 {news['title']}\n"
        
        # Описание — ТОЛЬКО если оно отличается от заголовка!
        if news['description']:
            desc = news['description'][:150].strip()
            title_clean = _normalize_title(news['title'])
            desc_clean = _normalize_title(desc)
            
            # Добавляем описание только если оно НЕ дублирует заголовок
            if desc_clean and desc_clean != title_clean and title_clean not in desc_clean:
                if len(news['description']) > 150:
                    desc += "..."
                message += f"   {desc}\n"
        
        # Источник
        domain = news['source']
        sources.add(domain)
        message += f"   📎 {domain}\n"
        
        # Пустая строка между новостями
        message += "\n"
    
    # === Хештеги и CTA — ОДИН РАЗ В КОНЦЕ ===
    hashtags = get_random_hashtags(4)
    cta = "\n🔔 Подписывайтесь @yugagronews, чтобы не пропустить важные агро-новости!"
    sources_str = ', '.join(sources)
    
    message += f"📌 Источники: {sources_str}\n\n"
    message += f"{hashtags}\n"
    message += f"{cta}"
    
    print(f"\n💬 Сообщение ({len(message)} символов):")
    
    # 9. Публикуем в VK
    print("\n📤 Публикация в VK...")
    success = post_to_vk(message)
    
    if success:
        # 10. Отмечаем как опубликованные
        print("\n💾 Сохранение опубликованных...")
        for news in news_batch:
            mark_as_published(news['link'], news['title'])
        
        print("\n✅ Дайджест опубликован!")
        print(f"   Новостей: {len(news_batch)}")
        print(f"   Источников: {len(sources)}")
        print(f"   Источники: {', '.join(sources)}")
    else:
        print("\n❌ Ошибка публикации")

if __name__ == '__main__':
    main()
