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
    # Google News УБРАН — только дублирует контент
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
                
                # Источник
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
        # ИСПРАВЛЕНО: правильный класс с ТРЕМЯ 's'
        news_blocks = soup.find_all('div', class_='row no-guttersss')
        
        print(f"   Найдено блоков: {len(news_blocks)}")
        
        for block in news_blocks:
            # Ищем заголовок и ссылку
            title_tag = block.find('h3', class_='title')
            link_tag = title_tag.find('a') if title_tag else None
            
            if not link_tag:
                link_tag = block.find('a', href=True)
            
            if not link_tag:
                continue
            
            title = link_tag.get_text(strip=True)
            link = link_tag.get('href')
            
            # Если ссылка относительная — делаем абсолютной
            if link and link.startswith('/'):
                link = 'https://dairynews.today' + link
            elif not link or not link.startswith('http'):
                continue
            
            # Дата (ищем в соседнем блоке)
            # Находим родительский блок с датой
            parent_div = block.find_parent('div', class_='col-12')
            date_span = None
            if parent_div:
                # Ищем дату в тексте (формат: "Казахстан 01.06.2026")
                import re
                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', parent_div.get_text())
                if date_match:
                    date_text = date_match.group(1)
                else:
                    date_text = ''
            else:
                date_text = ''
            
            # Парсим дату
            pub_datetime = datetime.now()
            if date_text:
                try:
                    pub_datetime = datetime.strptime(date_text, '%d.%m.%Y')
                except:
                    pass
            
            # Описание
            desc_div = block.find('div', class_='infotitle')
            description = desc_div.get_text(strip=True)[:300] if desc_div else ''
            
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
        import traceback
        traceback.print_exc()
        return []

def filter_news(items, published_urls):
    """Фильтрует дубликаты по URL"""
    new_items = []
    seen_urls = set()
    
    for item in items:
        # Пропускаем если URL уже опубликован
        if item['link'] in published_urls or item['link'] in seen_urls:
            continue
        
        seen_urls.add(item['link'])
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
    
    # 4. Проверяем минимум
    if len(new_items) < MIN_NEWS_FOR_POST:
        print(f"\n⏸️  Мало новостей ({len(new_items)} < {MIN_NEWS_FOR_POST})")
        print("   Ждём следующего запуска...")
        return
    
    # 5. Сортируем по дате (сначала новые)
    new_items.sort(key=lambda x: x['published_at'], reverse=True)
    
    # 6. Берем новости для дайджеста
    news_batch = new_items[:MAX_NEWS_FOR_POST]
    print(f"\n📋 Формируем дайджест из {len(news_batch)} новостей...")
    
    # 7. Формируем пост
    today = datetime.now().strftime("%d %B %Y").replace(' 0', ' ')
    message = f"📰 АГРО ДАЙДЖЕСТ | {today}\n\n"
    sources = set()
    
    for i, news in enumerate(news_batch, 1):
        # Заголовок
        message += f"🔹 {news['title']}\n"
        
        # Описание — ТОЛЬКО если оно НЕ пустое и отличается от заголовка
        if news['description']:
            desc = news['description'][:150].strip()
            title_lower = news['title'].lower().strip()
            desc_lower = desc.lower().strip()
            
            # Добавляем описание только если оно существенно отличается
            if desc_lower and title_lower not in desc_lower and desc_lower not in title_lower:
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
    
    # 8. Публикуем в VK
    print("\n📤 Публикация в VK...")
    success = post_to_vk(message)
    
    if success:
        # 9. Отмечаем как опубликованные
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
