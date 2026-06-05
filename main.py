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
from itertools import zip_longest

# === КОНФИГУРАЦИЯ ===
RSS_URLS = [
    'https://www.agroinvestor.ru/feed/public-agronews.xml',
    'https://news.google.com/rss/search?q=сельское+хозяйство+Россия+АПК&hl=ru&gl=RU&ceid=RU:ru',
]

MIN_NEWS_FOR_POST = 1
MAX_NEWS_FOR_POST = 7
MAX_AGE_DAYS = 14       # 2 недели

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

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def _clean_title(title):
    """Убирает лишний мусор из заголовка (но даты теперь разделены в HTML)"""
    # 1. Убираем переносы строк
    title = title.replace('\n', ' ').replace('\r', ' ')
    
    # 2. Убираем "via ..." (от Google)
    title = re.sub(r'\s*via\s+\S+', '', title, flags=re.IGNORECASE)
    
    # 3. Убираем лишние пробелы
    title = ' '.join(title.split())
    
    # 4. Убираем точку в конце
    if title.endswith('.'):
        title = title[:-1]
    
    if len(title) < 10:
        return ''
    
    return title.strip()

def _extract_source_from_google(entry):
    """Извлекает оригинальный источник из Google News"""
    if hasattr(entry, 'source') and entry.source:
        if hasattr(entry.source, 'title'):
            return entry.source.title.strip()
    
    link = entry.get('link', '')
    if 'news.google.com' in link:
        return 'news.google.com'
    
    return urlparse(link).netloc.replace('www.', '')

def _mix_sources(items, max_count):
    """Чередует новости из разных источников (до 3 источников)"""
    if not items:
        return []
    
    # Группируем по источникам
    by_source = {}
    for item in items:
        src = item['source']
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(item)
    
    print(f"   📊 Источников: {len(by_source)}")
    for src, src_items in by_source.items():
        print(f"      {src}: {len(src_items)}")
    
    # Чередуем источники
    mixed = []
    source_names = list(by_source.keys())
    
    for i in range(max_count):
        for src in source_names:
            if len(mixed) >= max_count:
                break
            if i < len(by_source[src]):
                mixed.append(by_source[src][i])
        
        if len(mixed) >= max_count:
            break
    
    sources_in_mix = set(item['source'] for item in mixed)
    print(f"   ✅ В дайджесте: {len(mixed)} новостей из {len(sources_in_mix)} источников")
    for src in sources_in_mix:
        count = sum(1 for item in mixed if item['source'] == src)
        print(f"      {src}: {count}")
    
    return mixed

# === ОСНОВНЫЕ ФУНКЦИИ ===

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
    """Парсит все RSS ленты (Agroinvestor + Google News)"""
    all_items = []
    
    for rss_url in RSS_URLS:
        print(f"\n📰 Парсинг: {rss_url[:60]}...")
        
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
                title = _clean_title(title)
                
                if not title:
                    continue
                
                link = entry.get('link', '').strip()
                description = entry.get('description', '')
                pub_date = entry.get('published', '')
                
                description = html.unescape(description)
                clean_desc = re.sub(r'<[^>]+>', '', description)[:300]
                
                if 'news.google.com' in link:
                    source_name = _extract_source_from_google(entry)
                else:
                    source_name = urlparse(link).netloc.replace('www.', '')
                
                pub_datetime = datetime.now()
                if pub_date:
                    try:
                        pub_datetime = datetime.strptime(pub_date[:25], '%a, %d %b %Y %H:%M:%S')
                    except:
                        pass
                
                age = datetime.now() - pub_datetime
                if age.days > MAX_AGE_DAYS:
                    continue
                
                if not link:
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
    """Парсит новости dairynews.today/kz/ (ИСПОЛЬЗУЕТ .main-news-item)"""
    url = 'https://dairynews.today/kz/'
    print(f"\n📰 Парсинг HTML: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'lxml')
        
        items = []
        news_blocks = soup.find_all('div', class_='main-news-item')
        
        print(f"   Найдено блоков: {len(news_blocks)}")
        
        for block in news_blocks:
            # 1. Заголовок
            title_tag = block.find('h3', class_='title')
            if not title_tag:
                continue
            
            title = title_tag.get_text(strip=True)
            title = _clean_title(title)
            
            if not title or len(title) < 10:
                continue
            
            # 2. ССЫЛКА
            link_tag = block.find('a', class_='title-link')
            if not link_tag:
                continue
            
            link = link_tag.get('href')
            
            # Если ссылка относительная — делаем абсолютной
            if link:
                if link.startswith('/kz/'):
                    link = 'https://dairynews.today' + link
                elif link.startswith('/'):
                    link = 'https://dairynews.today/kz' + link
                # Если уже полная ссылка — оставляем как есть
            
            # 3. Дата
            date_span = block.find('span', class_='data')
            date_text = date_span.get_text(strip=True) if date_span else ''
            
            pub_datetime = datetime.now()
            if date_text:
                try:
                    pub_datetime = datetime.strptime(date_text, '%d.%m.%Y')
                except:
                    pass
            
            # 4. Описание — ИСПРАВЛЕНО (не обрезаем на полуслове)
            desc_tag = block.find('div', class_='text')
            if desc_tag:
                full_desc = desc_tag.get_text(strip=True)
                # Обрезаем на границе предложения или слова
                if len(full_desc) > 200:
                    # Ищем последнюю точку или пробел
                    cut_desc = full_desc[:200]
                    last_period = cut_desc.rfind('.')
                    last_space = cut_desc.rfind(' ')
                    
                    if last_period > 150:
                        description = cut_desc[:last_period+1]
                    elif last_space > 150:
                        description = cut_desc[:last_space] + "..."
                    else:
                        description = full_desc[:200] + "..."
                else:
                    description = full_desc
            else:
                description = ''
            
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

def filter_news(items, published_urls):
    """Фильтрует дубликаты по URL"""
    new_items = []
    seen_urls = set()
    
    for item in items:
        if item['link'] in published_urls or item['link'] in seen_urls:
            continue
        
        seen_urls.add(item['link'])
        new_items.append(item)
    
    return new_items

def get_random_hashtags(count=4):
    """Возвращает случайные хештеги из пула"""
    return ' '.join(random.sample(HASHTAG_POOL, min(count, len(HASHTAG_POOL))))

def get_random_image_url():
    """Возвращает URL случайной картинки с хостинга"""
    # 19 картинок в формате PNG
    image_number = random.randint(1, 19)
    image_url = f'https://agrokom.su/agro_news/{image_number}.png'
    print(f"   🖼️ Выбрана картинка: {image_url}")
    return image_url

def download_image(image_url):
    """Скачивает картинку по URL и возвращает путь к временному файлу"""
    import tempfile
    
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        
        # Сохраняем во временный файл
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        temp_file.write(response.content)
        temp_file.close()
        
        print(f"   ✅ Картинка скачана: {temp_file.name}")
        return temp_file.name
        
    except Exception as e:
        print(f"   ❌ Ошибка скачивания картинки: {e}")
        return None

def upload_image_to_vk(image_path):
    """Загружает картинку в VK и возвращает attachment строку"""
    if not image_path:
        return None
    
    try:
        # 1. Получаем URL для загрузки через правильный метод
        upload_url_req = requests.get(
            'https://api.vk.com/method/photos.getWallUploadURL',
            params={
                'group_id': VK_GROUP_ID,
                'access_token': VK_ACCESS_TOKEN,
                'v': '5.199'
            }
        )
        
        print(f"   📤 Запрос URL: {upload_url_req.status_code}")
        upload_url_data = upload_url_req.json()
        
        if 'response' not in upload_url_data:
            print(f"   ❌ Ошибка получения URL загрузки: {upload_url_data}")
            return None
        
        upload_url = upload_url_data['response']['upload_url']
        print(f"   📥 URL получен: {upload_url[:50]}...")
        
        # 2. Загружаем фото на полученный URL
        with open(image_path, 'rb') as f:
            files = {'photo': f}
            upload_response = requests.post(upload_url, files=files)
            upload_result = upload_response.json()
        
        print(f"   📤 Загрузка фото: {upload_result.get('photo', 'NO PHOTO')[:50] if upload_result.get('photo') else 'EMPTY'}...")
        
        if not upload_result.get('photo'):
            print(f"   ❌ Ошибка загрузки фото: {upload_result}")
            return None
        
        # 3. Сохраняем фото
        save_req = requests.post(
            'https://api.vk.com/method/photos.saveWallPhoto',
            data={
                'photo': upload_result['photo'],
                'server': upload_result.get('server', ''),
                'hash': upload_result.get('hash', ''),
                'group_id': VK_GROUP_ID,
                'access_token': VK_ACCESS_TOKEN,
                'v': '5.199'
            }
        )
        save_result = save_req.json()
        
        print(f"   💾 Сохранение фото: {save_result}")
        
        if 'response' in save_result:
            photo_id = save_result['response'][0]['id']
            owner_id = save_result['response'][0]['owner_id']
            access_key = save_result['response'][0].get('access_key', '')
            
            attachment = f'photo{owner_id}_{photo_id}'
            if access_key:
                attachment += f'_{access_key}'
            
            print(f"   ✅ Картинка загружена в VK! {attachment}")
            return attachment
        else:
            print(f"   ❌ Ошибка сохранения фото: {save_result}")
            return None
            
    except Exception as e:
        print(f"   ❌ Ошибка загрузки картинки: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        # Удаляем временный файл
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
                print(f"   🗑️ Временный файл удалён")
            except:
                pass

def post_to_vk(message, attachment=None):
    """Публикует пост в VK (с картинкой или без)"""
    url = 'https://api.vk.com/method/wall.post'
    
    params = {
        'owner_id': f'-{VK_GROUP_ID}',
        'message': message,
        'access_token': VK_ACCESS_TOKEN,
        'v': '5.199'
    }
    
    # Если есть картинка — добавляем
    if attachment:
        params['attachment'] = attachment
    
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
    print(f" Возраст новостей: до {MAX_AGE_DAYS} дней")
    
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
    
    # 6. ЧЕРЕДУЕМ 3 ИСТОЧНИКА
    news_batch = _mix_sources(new_items, MAX_NEWS_FOR_POST)
    print(f"\n📋 Формируем дайджест из {len(news_batch)} новостей...")
    
    # 7. Формируем пост
    today = datetime.now().strftime("%d %B %Y").replace(' 0', ' ')
    message = f"📰 АГРО ДАЙДЖЕСТ | {today}\n\n"
    sources = set()
    
    for i, news in enumerate(news_batch, 1):
        # Заголовок (теперь точно без даты)
        message += f"🔹 {news['title']}\n"
        
        # Описание — умная обрезка (не на полуслове)
        if news['description']:
            full_desc = news['description'].strip()
            
            # Обрезаем только если описание длинное
            if len(full_desc) > 200:
                # Ищем последнюю точку в пределах 200 символов
                cut_desc = full_desc[:200]
                last_period = cut_desc.rfind('.')
                last_space = cut_desc.rfind(' ')
                
                # Режем на границе предложения или слова
                if last_period > 150:
                    desc = cut_desc[:last_period+1]
                elif last_space > 150:
                    desc = cut_desc[:last_space] + "..."
                else:
                    desc = full_desc[:200] + "..."
            else:
                desc = full_desc
            
            # Проверяем что описание отличается от заголовка
            title_lower = news['title'].lower().strip()
            desc_lower = desc.lower().strip()
            
            should_skip = False
            
            if not desc_lower:
                should_skip = True
            elif title_lower == desc_lower:
                should_skip = True
            elif title_lower in desc_lower or desc_lower in title_lower:
                should_skip = True
            elif len(title_lower) > 20 and len(desc_lower) > 20:
                if title_lower[:50] == desc_lower[:50]:
                    should_skip = True
            
            if not should_skip:
                message += f"{desc}\n"
        
        # ССЫЛКА НА СТАТЬЮ — ДОБАВЛЕНО
        if news['link']:
            message += f"🔗 {news['link']}\n"
        
        # Источник
        domain = news['source']
        sources.add(domain)
        
        
        # Пустая строка
        message += "\n"
    
    # === Хештеги и CTA - ОДИН РАЗ В КОНЦЕ ===
    hashtags = get_random_hashtags(4)
    cta = "🔔 Подписывайтесь @yugagronews, чтобы не пропустить важные агро-новости!"
    sources_str = ', '.join(sources)
    
    message += f"📌 Источники: {sources_str}\n\n"
    message += f"{hashtags}\n\n"
    message += cta
    
    print(f"\n💬 Сообщение ({len(message)} символов):")
    
        # 8. Выбираем случайную картинку
    print("\n🎨 Подготовка картинки...")
    image_url = get_random_image_url()
    temp_image_path = download_image(image_url)
    vk_attachment = None
    
    if temp_image_path:
        vk_attachment = upload_image_to_vk(temp_image_path)
    
    # 9. Публикуем в VK
    print("\n📤 Публикация в VK...")
    success_vk = post_to_vk(message, attachment=vk_attachment)
    
    if success_vk:
        # 10. Отмечаем как опубликованные
        print("\n💾 Сохранение опубликованных...")
        for news in news_batch:
            mark_as_published(news['link'], news['title'])
        
        print("\n✅ Дайджест опубликован!")
        print(f"   Новостей: {len(news_batch)}")
        print(f"   Источников: {len(sources)}")
        print(f"   Источники: {', '.join(sources)}")
    else:
        print("\n Ошибка публикации")

if __name__ == '__main__':
    main()
