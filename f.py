import os
import json
import asyncio
import datetime
from typing import Dict, List, Any, Optional
import feedparser
from bs4 import BeautifulSoup
import httpx
from playwright.async_api import async_playwright


try:
    from playwright_stealth import stealth_async
except ImportError:
    stealth_async = None


class AINewsScraperPipeline:
    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)


        self.settings = self.config["scraping_settings"]
        self.filters = self.config["filters"]
        self.sources = self.config["rss_sources"]
        self.output_dir = self.settings.get("data_directory", "data/")
        os.makedirs(self.output_dir, exist_ok=True)


        self.user_agent = self.settings.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        )
        self.headers = {"User-Agent": self.user_agent}


        # 3-phase strategy config
        self.three_phase = self.settings.get("three_phase_strategy", {})
        self.three_phase_enabled = self.three_phase.get("enabled", True)


        # Browser settings
        self.browser_settings = self.settings.get("browser_settings", {})
        self.navigation_timeout_ms = self.browser_settings.get("navigation_timeout_ms", 15000)
        self.page_wait_ms = self.browser_settings.get("page_wait_ms", 2000)


        # Stats
        self.stats = {
            "sources_attempted": 0,
            "sources_successful": 0,
            "sources_failed": 0,
            "articles_collected": 0,
            "articles_skipped_by_filter": 0,
            "errors_and_retries": 0,
        }


    # =========================
    # Helpers: URL & Filters
    # =========================


    def is_valid_url(self, url: str) -> bool:
        if not url or not isinstance(url, str):
            return False
        from urllib.parse import urlparse


        try:
            r = urlparse(url)
            return all([r.scheme, r.netloc, "http" in r.scheme])
        except Exception:
            return False


    def should_exclude_by_pattern(self, url: str) -> bool:
        patterns = self.filters.get("exclude_patterns", [])
        url_lower = url.lower()
        return any(p.lower() in url_lower for p in patterns)


    def passes_filters(self, title: str, text: str) -> bool:
        min_title_len = self.filters.get("min_title_length", 10)
        min_para_len = self.filters.get("min_first_paragraph_length", 20)


        if len(title) < min_title_len:
            return False
        if len(text) < min_para_len:
            return False
        return True


    # =========================
    # Dynamic Date Chunk Generation
    # =========================


    def generate_date_chunks(self, start_date: str, end_date: str, num_chunks: int = 2) -> List[Dict[str, str]]:
        """
        Generate date chunks dynamically for a given date range.
        Splits the range into equal parts to maximize article retrieval.
        """
        from datetime import timedelta


        start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end - start).days


        chunk_days = total_days // num_chunks
        chunks = []


        for i in range(num_chunks):
            chunk_start = start + timedelta(days=i * chunk_days)
            if i == num_chunks - 1:
                # Last chunk goes to the end
                chunk_end = end
            else:
                chunk_end = chunk_start + timedelta(days=chunk_days)


            chunks.append({
                "label": f"chunk_{i + 1}",
                "from": chunk_start.strftime("%Y-%m-%d"),
                "to": chunk_end.strftime("%Y-%m-%d"),
            })


        return chunks


    def build_google_news_url(self, base_query: str, chunk: Dict[str, str]) -> str:
        """
        Build Google News RSS URL with date range.
        Example: https://news.google.com/rss/search?q=AI+after:2025-07-28+before:2026-01-28&hl=en-US&gl=US&ceid=US:en
        """
        from urllib.parse import quote


        # Format: query after:YYYY-MM-DD before:YYYY-MM-DD
        date_query = f"{base_query} after:{chunk['from']} before:{chunk['to']}"
        encoded_query = quote(date_query)


        return (
            f"https://news.google.com/rss/search?"
            f"q={encoded_query}"
            f"&hl=en-US&gl=US&ceid=US:en"
        )


    def extract_base_query_from_url(self, rss_url: str) -> str:
        """
        Extract the base query from an existing Google News RSS URL.
        Example: 
        Input: https://news.google.com/rss/search?q=site:bloomberg.com+artificial+intelligence+OR+AI&hl=en-US&gl=US&ceid=US:en
        Output: site:bloomberg.com artificial intelligence OR AI
        """
        from urllib.parse import urlparse, parse_qs, unquote


        parsed = urlparse(rss_url)
        query_params = parse_qs(parsed.query)
        
        if "q" in query_params:
            encoded_q = query_params["q"][0]
            decoded_q = unquote(encoded_q)
            
            # Remove date filters if present
            import re
            cleaned_q = re.sub(r"\s+after:\d{4}-\d{2}-\d{2}", "", decoded_q)
            cleaned_q = re.sub(r"\s+before:\d{4}-\d{2}-\d{2}", "", cleaned_q)
            
            return cleaned_q.strip()
        
        return ""


    # =========================
    # RSS Fetching with Date Chunks
    # =========================


    async def fetch_rss_entries(self, client: httpx.AsyncClient, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries = []
        target_count = self.settings.get("articles_per_source", 150)


        # Check if source uses date chunks (default: True for all Google News sources)
        use_date_chunks = source.get("use_date_chunks", True)


        if use_date_chunks:
            # Generate 2 chunks dynamically for 1-year range
            # Default: 2025-07-28 to 2026-07-28
            start_date = "2025-07-28"
            end_date = "2026-07-28"
            num_chunks = 2


            # Extract base query from RSS URL
            base_query = self.extract_base_query_from_url(source["rss_url"])
            
            if not base_query:
                # Fallback: use original URL without chunks
                print(f"    [!] Could not extract base query, using original URL")
                urls_to_fetch = [source["rss_url"]]
            else:
                # Generate date chunks
                chunks = self.generate_date_chunks(start_date, end_date, num_chunks)
                print(f"    [i] Using {len(chunks)} date chunks: {chunks}")
                
                # Build URLs for each chunk
                urls_to_fetch = [self.build_google_news_url(base_query, chunk) for chunk in chunks]
        else:
            urls_to_fetch = [source["rss_url"]]


        # Fetch all URLs
        for rss_url in urls_to_fetch:
            try:
                resp = await client.get(rss_url, follow_redirects=True, timeout=10.0)
                if resp.status_code == 200:
                    parsed = feedparser.parse(resp.text)
                    for entry in parsed.entries:
                        title = entry.get("title", "").strip()


                        # Robust link extraction
                        link = entry.get("link", "")
                        if not link:
                            if entry.get("id"):
                                link = entry["id"]
                            elif entry.get("guid"):
                                link = entry["guid"]
                            elif hasattr(entry, "links") and entry.links:
                                link = entry.links[0].get("href", "")


                        pub = entry.get("published", entry.get("updated", ""))
                        if not pub:
                            pub = datetime.datetime.now().isoformat()


                        entries.append({
                            "title": title,
                            "url": link,
                            "pub_date": pub,
                            "raw_description": entry.get("description", ""),
                        })
            except Exception as e:
                self.stats["errors_and_retries"] += 1
                print(f"    [!] RSS Fetch Warning: {e}")


            # Stop if we have enough articles
            if len(entries) >= target_count * 2:
                break


        # Deduplicate + validate
        seen = set()
        unique = []
        for item in entries:
            if not self.is_valid_url(item["url"]):
                continue
            if self.should_exclude_by_pattern(item["url"]):
                continue
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            unique.append(item)


        return unique


    # =========================
    # Content extraction
    # =========================


    def extract_content_from_html(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")


        # Priority 1: article / main container paragraphs
        container = soup.find("article") or soup.find("main") or soup.body
        if container:
            paragraphs = container.find_all("p")
            chunks = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 20:
                    low = text.lower()
                    if low.startswith(
                        (
                            "for ",
                            "to ",
                            "click ",
                            "sign up",
                            "advertisement",
                            "subscribe",
                            "our standards",
                            "reporting by",
                            "editing by",
                            "see more",
                            "read more",
                            "continue reading",
                        )
                    ):
                        continue
                    chunks.append(text)
                    if len(chunks) >= 2:
                        break
            if chunks:
                return " ".join(chunks)


        # Priority 2: meta description / og:description
        meta_og = soup.find("meta", property="og:description")
        if not meta_og:
            meta_og = soup.find("meta", attrs={"name": "description"})
        if meta_og and meta_og.get("content"):
            return meta_og["content"].strip()


        return ""


    def clean_rss_description(self, raw: str) -> str:
        if not raw:
            return ""
        soup = BeautifulSoup(raw, "html.parser")
        text = soup.get_text(" ", strip=True)
        return text


    # =========================
    # 3-phase article fetching (Engine-based)
    # =========================


    async def fetch_article_requests(self, client: httpx.AsyncClient, item: Dict[str, Any]) -> Optional[str]:
        """Phase 1: Simple HTTP request"""
        try:
            resp = await client.get(item["url"], follow_redirects=True, timeout=8.0)
            if resp.status_code == 200:
                text = self.extract_content_from_html(resp.text)
                if text and len(text) >= self.filters.get("min_first_paragraph_length", 20):
                    return text
        except Exception:
            self.stats["errors_and_retries"] += 1
        return None


    async def fetch_article_playwright_basic(self, page, item: Dict[str, Any]) -> Optional[str]:
        """Phase 2: Playwright without stealth"""
        try:
            await page.goto(item["url"], wait_until="domcontentloaded", timeout=self.navigation_timeout_ms)
            await page.wait_for_timeout(self.page_wait_ms)
            html = await page.content()
            text = self.extract_content_from_html(html)
            if text and len(text) >= self.filters.get("min_first_paragraph_length", 20):
                return text
        except Exception:
            self.stats["errors_and_retries"] += 1
        return None


    async def fetch_article_playwright_stealth(self, page, item: Dict[str, Any]) -> Optional[str]:
        """Phase 3: Playwright with high stealth"""
        try:
            if stealth_async:
                await stealth_async(page)


            await page.set_extra_http_headers(
                {
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            )


            await page.goto(item["url"], wait_until="networkidle", timeout=self.navigation_timeout_ms + 5000)
            await page.wait_for_timeout(self.page_wait_ms + 500)
            html = await page.content()
            text = self.extract_content_from_html(html)
            if text and len(text) >= self.filters.get("min_first_paragraph_length", 20):
                return text
        except Exception:
            self.stats["errors_and_retries"] += 1
        return None


    async def fetch_article_with_engine(
        self,
        httpx_client: httpx.AsyncClient,
        page_basic,
        page_stealth,
        item: Dict[str, Any],
        engine: str,
    ) -> Optional[str]:
        """
        Fetch article based on engine type:
        - 'requests': Phase 1 only
        - 'playwright': Phase 1 → Phase 2 (basic)
        - 'playwright_stealth': Phase 1 → Phase 2 → Phase 3 (stealth)
        """
        # Phase 1: Always try requests first
        text = await self.fetch_article_requests(httpx_client, item)
        if text:
            return text


        # Engine-specific phases
        if engine == "requests":
            return None


        elif engine == "playwright":
            # Phase 2: Basic Playwright
            text = await self.fetch_article_playwright_basic(page_basic, item)
            return text


        elif engine in ("playwright_stealth",):
            # Phase 2: Basic Playwright
            text = await self.fetch_article_playwright_basic(page_basic, item)
            if text:
                return text
            
            # Phase 3: Stealth Playwright
            text = await self.fetch_article_playwright_stealth(page_stealth, item)
            return text


        return None


    # =========================
    # Source processing
    # =========================


    async def process_source(
        self,
        source: Dict[str, Any],
        httpx_client: httpx.AsyncClient,
        page_basic,
        page_stealth,
    ) -> List[Dict[str, Any]]:
        if not source.get("enabled", True):
            return []


        self.stats["sources_attempted"] += 1
        engine = source.get("engine", "requests")
        print(f"\n[+] Processing: {source['name']} (Engine: {engine})")


        entries = await self.fetch_rss_entries(httpx_client, source)
        print(f"    - Discovered {len(entries)} RSS links.")


        target_count = self.settings.get("articles_per_source", 150)
        successful = []
        seen_urls = set()


        for idx, entry in enumerate(entries):
            if len(successful) >= target_count:
                break


            title = entry["title"]
            url = entry["url"]
            pub = entry["pub_date"]
            raw_desc = entry.get("raw_description", "")


            if url in seen_urls:
                continue


            # Try to fetch article content based on engine
            first_para = await self.fetch_article_with_engine(
                httpx_client, page_basic, page_stealth, entry, engine
            )


            # Fallback to RSS description
            if not first_para and raw_desc:
                cleaned = self.clean_rss_description(raw_desc)
                if cleaned and len(cleaned) >= self.filters.get("min_first_paragraph_length", 20):
                    first_para = cleaned


            if not first_para:
                self.stats["articles_skipped_by_filter"] += 1
                continue


            if not self.passes_filters(title, first_para):
                self.stats["articles_skipped_by_filter"] += 1
                continue


            article = {
                "title": title,
                "first_paragraph": first_para,
                "url": url,
                "published_time": pub,
                "category": source.get("category", "ai"),
                "source": {
                    "name": source["name"],
                    "url": source.get("rss_url", "").split("?")[0],
                },
            }


            successful.append(article)
            seen_urls.add(url)
            print(f"    [{len(successful)}/{target_count}] ✓ {title[:50]}...")


            delay = self.settings.get("request_delay_seconds", 1.0)
            if delay > 0:
                await asyncio.sleep(delay)


        if successful:
            self.stats["sources_successful"] += 1
            self.stats["articles_collected"] += len(successful)
        else:
            self.stats["sources_failed"] += 1


        # Save individual file
        output_filename = source.get("output_file", f"source_{source['id']}.json")
        output_path = os.path.join(self.output_dir, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(successful, f, indent=2, ensure_ascii=False)


        print(f"[✔ Completed {source['name']}] Saved {len(successful)} articles to {output_filename}")
        return successful


    # =========================
    # Pipeline runner
    # =========================


    async def run(self):
        print("Starting AI News Aggregator ...")
        print("=" * 60)
        print(f"Total sources: {len(self.sources)}")
        print(f"Expected articles per source: {self.settings.get('articles_per_source', 150)}")
        print(f"Date range: 2025-07-28 to 2026-07-28 (1 year)")
        print(f"Date chunks per source: 2 (for maximum coverage)")
        print("=" * 60)
        
        all_articles = []


        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=10.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        ) as httpx_client:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = await browser.new_context(
                    viewport={
                        "width": self.browser_settings.get("viewport", {}).get("width", 1920),
                        "height": self.browser_settings.get("viewport", {}).get("height", 1080),
                    }
                )


                page_basic = await context.new_page()
                page_stealth = await context.new_page()


                for source in self.sources:
                    articles = await self.process_source(source, httpx_client, page_basic, page_stealth)
                    all_articles.extend(articles)


                await browser.close()


        # Save combined file
        combined_filename = self.config.get("output_settings", {}).get(
            "combined_file", "combined_news.json"
        )
        combined_path = os.path.join(self.output_dir, combined_filename)


        combined_data = {
            "project_metadata": {
                "total_sources": self.stats["sources_successful"],
                "articles_per_source": self.settings.get("articles_per_source", 150),
                "total_articles": len(all_articles),
                "scraping_completed": datetime.datetime.now().isoformat(),
                "category": "ai",
                "date_range": "2025-07-28 to 2026-07-28",
                "date_chunks_per_source": 2,
            },
            "statistics": {
                "sources_attempted": self.stats["sources_attempted"],
                "sources_successful": self.stats["sources_successful"],
                "sources_failed": self.stats["sources_failed"],
                "total_articles_collected": self.stats["articles_collected"],
                "articles_skipped_by_filter": self.stats["articles_skipped_by_filter"],
                "errors_and_retries": self.stats["errors_and_retries"],
            },
            "news_articles": all_articles,
        }


        with open(combined_path, "w", encoding="utf-8") as f:
            json.dump(combined_data, f, indent=2, ensure_ascii=False)


        print("\n" + "=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)
        print(f"Sources attempted: {self.stats['sources_attempted']}")
        print(f"Sources successful: {self.stats['sources_successful']}")
        print(f"Sources failed: {self.stats['sources_failed']}")
        print(f"Total articles: {self.stats['articles_collected']}")
        print(f"Articles skipped by filters: {self.stats['articles_skipped_by_filter']}")
        print(f"Errors and retries: {self.stats['errors_and_retries']}")
        print(f"Combined output: {combined_path}")
        print("=" * 60)


if __name__ == "__main__":
    pipeline = AINewsScraperPipeline("config.json")
    asyncio.run(pipeline.run())