# news_checker.py — Логіка отримання RSS, обчислення embeddings і фільтрації новин

import feedparser
import json
import os
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer

from config import (
    ETALON_SENTENCES,
    SIMILARITY_THRESHOLD,
    RSS_SOURCES,
    MAX_NEWS_PER_RUN,
)


class NewsChecker:
    """Клас для перевірки новин за допомогою семантичного пошуку."""

    def __init__(self):
        """Ініціалізація класу."""
        # Завантаження моделі embeddings (робиться один раз при першому запуску)
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        
        # Обчислення embeddings для еталонних речень (також робиться один раз)
        self.etalon_embeddings = self._compute_embeddings(ETALON_SENTENCES)
        
        # Завантаження історії опублікованих новин
        self.published: List[str] = []
        self._load_published()

    def _compute_embeddings(self, texts: List[str]) -> List[float]:
        """Обчислення embeddings для списку текстів."""
        return self.model.encode(texts)

    def _load_published(self):
        """Завантаження історії опублікованих новин з published.json."""
        try:
            with open("published.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                self.published = data.get("urls", [])
        except FileNotFoundError:
            # Файл ще не існує — створюємо порожній
            self._save_published()

    def _save_published(self):
        """Збереження історії опублікованих новин у published.json."""
        with open("published.json", "w", encoding="utf-8") as f:
            json.dump({"urls": self.published}, f, ensure_ascii=False, indent=2)

    def mark_as_published(self, url: str):
        """Позначення URL як опублікованого."""
        if url not in self.published:
            self.published.append(url)
            self._save_published()

    def is_already_published(self, url: str) -> bool:
        """Перевірка, чи вже була опублікована ця новина."""
        return url in self.published

    def fetch_rss_feeds(self) -> List[Dict]:
        """Отримання RSS-стрічок з усіх джерел з надійною обробкою."""
        feeds = []
        # Додаємо User-Agent, щоб сайти думали, що це звичайний браузер
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        for source in RSS_SOURCES:
            try:
                # Парсимо з заголовками
                feed = feedparser.parse(source["url"], request_headers=headers)
                
                # Перевіряємо, чи є взагалі записи, щоб уникнути помилок
                if not hasattr(feed, 'entries') or not feed.entries:
                    print(f"⚠️ Джерело {source['name']} не повернуло новин.")
                    continue
                
                for entry in feed.entries:
                    # Використовуємо getattr з безпечними дефолтними значеннями
                    entry_data = {
                        "title": getattr(entry, 'title', 'Без назви'),
                        "description": getattr(entry, 'description', '') or getattr(entry, 'summary', ''),
                        "link": getattr(entry, 'link', 'немає посилання'),
                        "source_name": source["name"]
                    }
                    feeds.append(entry_data)
                    
            except Exception as e:
                # Виводимо тип помилки замість спроби обчислити її довжину
                print(f"❌ Помилка при читанні RSS {source['name']}: {type(e).__name__}")
        
        return feeds

    def extract_news_text(self, entry) -> str:
        """Витягування тексту з новини (заголовок + опис)."""
        title = getattr(entry, 'title', '')
        description = getattr(entry, 'description', '') or ''
        content = getattr(entry, 'content', {})
        
        # Спроба витягнути body з content (деякі сайти використовують цей формат)
        if content and isinstance(content, dict):
            for key in ['body', 'value']:
                if key in content:
                    description += content[key]
                    break
        
        return f"{title}\n\n{description}".strip()

    def compute_news_embedding(self, news_text: str) -> List[float]:
        """Обчислення embeddings для тексту новини."""
        return self.model.encode(news_text)

    def compute_cosine_similarity(self, emb1: List[float], emb2: List[float]) -> float:
        """Обчислення косинусної схожості між двома embeddings."""
        # Модель sentence-transformers повертає нормалізовані вектори,
        # тому можна просто взяти скалярний добуток (це і є косинусна схожість)
        similarity = sum(a * b for a, b in zip(emb1, emb2))
        return similarity

    def find_max_similarity(self, news_embedding: List[float]) -> Tuple[float, int]:
        """Пошук максимальної схожості з еталонами та індексу найкращого еталону."""
        max_similarity = -float('inf')
        best_index = -1
        
        for i, etalon_emb in enumerate(self.etalon_embeddings):
            similarity = self.compute_cosine_similarity(news_embedding, etalon_emb)
            if similarity > max_similarity:
                max_similarity = similarity
                best_index = i
        
        return max_similarity, best_index

    def filter_news(self, feeds: List[feedparser.FeedParserDict]) -> List[Dict]:
        """Фільтрація новин за семантичною схожістю (безпечна версія)."""
        relevant_news = []
        
        for entry in feeds:
            if len(relevant_news) >= MAX_NEWS_PER_RUN:
                break
                
            news_text = self.extract_news_text(entry)
            
            # Пропускаємо, якщо немає тексту
            if not news_text.strip():
                continue
            
            # Обчислення embeddings для новини
            news_embedding = self.compute_news_embedding(news_text)
            
            # Знаходження максимальної схожості з еталонами
            max_similarity, best_index = self.find_max_similarity(news_embedding)
            
            # Перевірка порогу схожості
            if max_similarity >= SIMILARITY_THRESHOLD:
                url = getattr(entry, 'link', '') or getattr(entry, 'href', '') or ''
                
                # Пропускаємо, якщо вже була опублікована
                if self.is_already_published(url):
                    continue
                
                # --- ОСЬ ТУТ БУЛА ПОМИЛКА, ВИПРАВЛЯЄМО ---
                # Перевіряємо, чи існує індекс в списку RSS_SOURCES
                if 0 <= best_index < len(RSS_SOURCES):
                    source_name = RSS_SOURCES[best_index]["name"]
                else:
                    source_name = "Невідоме джерело"
                # ----------------------------------------
                
                relevant_news.append({
                    "title": getattr(entry, 'title', ''),
                    "description": news_text,
                    "link": url,
                    "source": source_name,
                    "similarity": max_similarity,
                })
        
        return relevant_news

    def get_formatted_post(self, news: Dict) -> str:
        """Формування тексту посту для Telegram."""
        title = news["title"]
        description = news["description"][:300] + "..." if len(news["description"]) > 300 else news["description"]
        link = news["link"]
        source = news["source"]
        
        post_text = f"📰 {source}\n\n{title}\n\n{description}\n\n🔗 {link}"
        return post_text

    def get_stats(self) -> Dict:
        """Отримання статистики роботи бота."""
        return {
            "etalon_sentences_count": len(ETALON_SENTENCES),
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "rss_sources_count": len(RSS_SOURCES),
            "published_count": len(self.published),
        }