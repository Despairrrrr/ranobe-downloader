from urllib.parse import urlparse

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
    slug = slug.split("--", 1)[-1]
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


def _extract_ordered_elements_from_dict(data) -> list[dict]:
    result = []
    if isinstance(data, dict):
        if data.get("type") == "paragraph":
            content = data.get("content", [])
            texts = [item["text"] for item in content if isinstance(item, dict) and "text" in item]
            if texts:
                result.append({"type": "paragraph", "text": " ".join(texts)})
        elif data.get("type") == "image":
            url = data.get("src", "")
            if url:
                result.append({"type": "image", "url": url})
        else:
            for value in data.values():
                result.extend(_extract_ordered_elements_from_dict(value))
    elif isinstance(data, list):
        for item in data:
            result.extend(_extract_ordered_elements_from_dict(item))
    return result


def _parse_html_ordered(html_str: str) -> list[dict]:
    tree = html.fromstring(html_str)
    result = []
    for elem in tree.iter():
        if elem.tag == "p":
            text = "".join(elem.itertext()).strip()
            if text:
                result.append({"type": "paragraph", "text": text})
        elif elem.tag == "img":
            src = elem.get("src", "")
            if src:
                result.append({"type": "image", "url": src})
    return result


def get_chapter_content(slug: str, chapter: dict) -> list[dict]:
    branch_id = _pick_branch(chapter)
    volume = chapter["volume"]
    number = chapter["number"]

    params = {"volume": volume, "number": number, "branch_id": branch_id}
    data = _api_get(f"{slug}/chapter", params=params)

    content = data.get("data", {}).get("content", "")

    if isinstance(content, dict):
        if "content" in content:
            return _extract_ordered_elements_from_dict(content)
        return []

    if isinstance(content, str) and content.strip():
        return _parse_html_ordered(content)

    return []


def download_chapter(slug: str, chapters: list[dict], target: int, volume: int) -> tuple[str, list[dict]]:
    matched = find_chapters_by_number(chapters, target, volume)
    if not matched:
        raise ApiError(f"Глава {target} тома {volume} не найдена в списке глав")

    book_title = get_book_title(slug)
    all_elements = []
    for ch in matched:
        elements = get_chapter_content(slug, ch)
        all_elements.extend(elements)
        all_elements.append({"type": "paragraph", "text": ""})

    if all_elements:
        all_elements.pop()

    if not all_elements:
        raise ApiError(f"Не удалось извлечь текст главы {target}")

    return book_title, all_elements
