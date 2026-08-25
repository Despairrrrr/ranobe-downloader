import re
from urllib.parse import urlparse, urlencode

import requests
from lxml import html

API_BASE = "https://api.cdnlibs.org/api/manga"


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


def extract_slug(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    slug = path.split("/")[-1]
    slug = re.sub(r"^\d+--", "", slug)
    if not slug:
        raise ApiError("Неверный формат ссылки. Укажите ссылку вида: https://ranobelib.me/ru/book/...")
    return slug


def _api_get(endpoint: str, params: dict | None = None) -> dict:
    url = f"{API_BASE}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=15)
    except requests.ConnectionError:
        raise ApiError("Сервер недоступен. Проверьте подключение к интернету")
    except requests.Timeout:
        raise ApiError("Превышено время ожидания ответа от сервера")

    if resp.status_code != 200:
        raise ApiError(
            f"Ошибка сервера (код: {resp.status_code})",
            status_code=resp.status_code,
        )
    return resp.json()


def get_book_title(slug: str) -> str:
    try:
        data = _api_get(slug, params={"fields[]": ["rus_name"]})
        return data.get("data", {}).get("rus_name", "")
    except ApiError:
        return slug.replace("-", " ").title()


def get_chapters(slug: str) -> list[dict]:
    data = _api_get(f"{slug}/chapters")
    return data.get("data", [])


def find_chapters_by_number(chapters: list[dict], target: int, volume: int) -> list[dict]:
    vol_str = str(volume)
    exact = [
        ch for ch in chapters
        if ch["volume"] == vol_str and float(ch["number"]) == target
    ]
    if not exact:
        return []

    sub = [
        ch for ch in chapters
        if ch["volume"] == vol_str
        and int(float(ch["number"])) == target
        and float(ch["number"]) != target
    ]

    result = exact + sub
    result.sort(key=lambda ch: float(ch["number"]))
    return result


def _pick_branch(chapter: dict) -> int:
    branches = chapter.get("branches", [])
    if not branches:
        return 0
    counts: dict[int, int] = {}
    for b in branches:
        bid = b.get("branch_id", 0)
        counts[bid] = counts.get(bid, 0) + 1
    return max(counts, key=counts.get)


def _extract_text_from_paragraphs(data) -> list[str]:
    result = []
    if isinstance(data, dict):
        if data.get("type") == "paragraph":
            content = data.get("content", [])
            texts = [item["text"] for item in content if isinstance(item, dict) and "text" in item]
            if texts:
                result.append(" ".join(texts))
        else:
            for value in data.values():
                result.extend(_extract_text_from_paragraphs(value))
    elif isinstance(data, list):
        for item in data:
            result.extend(_extract_text_from_paragraphs(item))
    return result


def _parse_html_content(html_str: str) -> list[str]:
    tree = html.fromstring(html_str)
    paragraphs = tree.xpath("//p//text()")
    return [p.strip() for p in paragraphs if p.strip()]


def _extract_image_urls(html_str: str) -> list[str]:
    return re.findall(r'<img[^>]+src="([^"]+)"', html_str)


def get_chapter_content(slug: str, chapter: dict) -> tuple[str, list[str]]:
    branch_id = _pick_branch(chapter)
    volume = chapter["volume"]
    number = chapter["number"]

    params = {"volume": volume, "number": number, "branch_id": branch_id}
    data = _api_get(f"{slug}/chapter", params=params)

    content = data.get("data", {}).get("content", "")

    if isinstance(content, dict):
        if "content" in content:
            paragraphs = _extract_text_from_paragraphs(content)
            return "\n".join(paragraphs), []
        return "", []

    if isinstance(content, str) and content.strip():
        paragraphs = _parse_html_content(content)
        image_urls = _extract_image_urls(content)
        return "\n".join(paragraphs), image_urls

    return "", []


def download_chapter(slug: str, chapters: list[dict], target: int, volume: int) -> tuple[str, str, list[str]]:
    matched = find_chapters_by_number(chapters, target, volume)
    if not matched:
        raise ApiError(f"Глава {target} тома {volume} не найдена в списке глав")

    book_title = get_book_title(slug)
    parts = []
    all_image_urls = []
    for ch in matched:
        text, images = get_chapter_content(slug, ch)
        if text:
            parts.append(text)
        all_image_urls.extend(images)

    combined = "\n\n".join(parts)
    if not combined.strip() and not all_image_urls:
        raise ApiError(f"Не удалось извлечь текст главы {target}")

    return book_title, combined, all_image_urls
