import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def search_web(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """
    Perform a web search using DuckDuckGo HTML interface (no API key required).
    """
    logger.info(f"Searching web for: {query}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    url = "https://html.duckduckgo.com/html/"
    data = {"q": query}

    try:
        response = requests.post(url, data=data, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []

        for result in soup.find_all("div", class_="result", limit=num_results):
            title_tag = result.find("a", class_="result__a")
            snippet_tag = result.find("a", class_="result__snippet")

            if title_tag and snippet_tag:
                results.append(
                    {
                        "title": title_tag.get_text(strip=True),
                        "link": title_tag["href"],
                        "snippet": snippet_tag.get_text(strip=True),
                    }
                )

        return results
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return [{"error": f"Search failed: {str(e)}"}]
