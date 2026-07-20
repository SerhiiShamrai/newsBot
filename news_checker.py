import feedparser
import json
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer
from bs4 import BeautifulSoup

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
        self.model = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2"
        )

        self.etalon_embeddings = self._compute_embeddings(
            ETALON_SENTENCES
        )

        self.published: List[str] = []
        self._load_published()

    def _compute_embeddings(self, texts: List[str]):
        """Обчислення нормалізованих embeddings."""
        return self.model.encode(texts, normalize_embeddings=True)

    def _load_published(self):
        """Завантаження історії опублікованих новин."""
        try:
            with open(
                "published.json",
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)
                self.published = data.get("urls", [])

        except FileNotFoundError:
            self._save_published()

    def _save_published(self):
        """Збереження історії опублікованих новин."""
        with open(
            "published.json",
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "urls": self.published
                },
                f,
                ensure_ascii=False,
                indent=2
            )

    def mark_as_published(self, url: str):
        """Позначення URL як опублікованого."""
        if url not in self.published:
            self.published.append(url)
            self._save_published()

    def is_already_published(
        self,
        url: str
    ) -> bool:
        """Перевірка, чи була новина опублікована."""
        return url in self.published

    def fetch_rss_feeds(
        self
    ) -> List[Dict]:
        """Отримання новин з усіх RSS-джерел."""

        feeds = []

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64)"
            )
        }

        for source in RSS_SOURCES:

            try:
                feed = feedparser.parse(
                    source["url"],
                    request_headers=headers
                )

                if not feed.entries:
                    print(
                        f"⚠️ Джерело "
                        f"{source['name']} "
                        f"не повернуло новин."
                    )

                    continue

                for entry in feed.entries:

                    entry_data = {
                        "title": getattr(
                            entry,
                            "title",
                            "Без назви"
                        ),

                        "description": getattr(entry, 'summary', '') or getattr(entry, 'description', ''),

                        "link": getattr(
                            entry,
                            "link",
                            ""
                        ),

                        "source_name": source["name"]
                    }

                    feeds.append(entry_data)

            except Exception as e:

                print(
                    f"❌ Помилка при читанні RSS "
                    f"{source['name']}: "
                    f"{type(e).__name__}: {e}"
                )

        print(
            f"📡 Всього отримано RSS-новин: "
            f"{len(feeds)}"
        )

        return feeds

    def extract_news_text(self, entry) -> str:
        """Витягування тексту з новини."""

        title = entry.get("title", "")
        description = entry.get("description", "") or ""

        soup = BeautifulSoup(
            description,
            "html.parser"
        )

        description = soup.get_text(
            " ",
            strip=True
        )

        return f"{title}\n\n{description}".strip()

    def compute_news_embedding(self, news_text: str) -> List[float]:
        """Обчислення embeddings для тексту новини."""
        return self.model.encode(news_text,normalize_embeddings=True)
				

    def compute_cosine_similarity(
        self,
        emb1,
        emb2
    ) -> float:
        """Обчислення косинусної схожості."""

        similarity = sum(
            a * b
            for a, b in zip(
                emb1,
                emb2
            )
        )

        return similarity

    def find_max_similarity(
        self,
        news_embedding
    ) -> Tuple[float, int]:
        """Пошук максимальної схожості."""

        max_similarity = -float(
            "inf"
        )

        best_index = -1

        for i, etalon_emb in enumerate(
            self.etalon_embeddings
        ):

            similarity = (
                self.compute_cosine_similarity(
                    news_embedding,
                    etalon_emb
                )
            )

            if similarity > max_similarity:

                max_similarity = similarity
                best_index = i

        return (
            max_similarity,
            best_index
        )

    def filter_news(
        self,
        feeds: List[Dict]
    ) -> List[Dict]:
        """Фільтрація новин за схожістю."""

        relevant_news = []

        for entry in feeds:

            if len(
                relevant_news
            ) >= MAX_NEWS_PER_RUN:

                break

            news_text = entry.get("title", "")

            if not news_text.strip():

                continue

            news_embedding = (
                self.compute_news_embedding(
                    news_text
                )
            )

            max_similarity, best_index = (
                self.find_max_similarity(
                    news_embedding
                )
            )

            print(
                f"📰 {entry.get('title', '')[:80]}"
            )

            print(
                f"   Схожість: "
                f"{max_similarity:.3f}"
            )

            if (
                max_similarity
                < SIMILARITY_THRESHOLD
            ):

                continue

            url = (
                entry.get(
                    "link",
                    ""
                )
                or
                entry.get(
                    "href",
                    ""
                )
            )

            if not url:

                continue

            if self.is_already_published(
                url
            ):

                continue

            source_name = entry.get(
                "source_name",
                "Невідоме джерело"
            )

            relevant_news.append(
                {
                    "title": entry.get(
                        "title",
                        ""
                    ),

                    "description": news_text,

                    "link": url,

                    "source": source_name,

                    "similarity": max_similarity,
                }
            )

        print(
            f"✅ Знайдено релевантних новин: "
            f"{len(relevant_news)}"
        )

        return relevant_news

    def get_formatted_post(
        self,
        news: Dict
    ) -> str:
        """Формування тексту посту для Telegram."""

        title = news["title"]

        link = news["link"]

        source = news["source"]

        post_text = (
            f"📰 {source}\n\n"
            f"{title}\n\n"
            f"🔗 {link}"
        )

        return post_text

    def get_stats(
        self
    ) -> Dict:
        """Отримання статистики."""

        return {
            "etalon_sentences_count": len(
                ETALON_SENTENCES
            ),

            "similarity_threshold": (
                SIMILARITY_THRESHOLD
            ),

            "rss_sources_count": len(
                RSS_SOURCES
            ),

            "published_count": len(
                self.published
            ),
        }