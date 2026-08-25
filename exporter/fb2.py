import base64
import mimetypes
import os
import textwrap
from xml.sax.saxutils import escape

import requests

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"


def _escape(text: str) -> str:
    return escape(text)


def _download_image(url: str) -> tuple[str, str]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if not content_type or content_type.startswith("text/"):
        content_type, _ = mimetypes.guess_type(url)
    if not content_type:
        content_type = "image/jpeg"
    b64 = base64.b64encode(resp.content).decode("ascii")
    return b64, content_type


def save_fb2(
    volume: int,
    chapter_number: float,
    book_title: str,
    chapter_text: str,
    image_urls: list[str] | None = None,
    output_dir: str = ".",
) -> str:
    chapter_num_str = str(int(chapter_number)) if chapter_number == int(chapter_number) else str(chapter_number).replace(".", "_")
    filename = f"том{volume}_глава{chapter_num_str}.fb2"

    chapter_title_num = str(int(chapter_number)) if chapter_number == int(chapter_number) else str(chapter_number)

    body_elements = []
    binaries = []

    if image_urls:
        for i, url in enumerate(image_urls):
            try:
                b64, content_type = _download_image(url)
            except Exception:
                continue
            img_id = f"img{i}"
            body_elements.append(f'      <image l:href="#{img_id}"/>')
            b64_wrapped = textwrap.fill(b64, 76)
            binaries.append(f'  <binary id="{img_id}" content-type="{content_type}">{b64_wrapped}</binary>')

    if chapter_text.strip():
        paragraphs = chapter_text.split("\n")
        for p in paragraphs:
            p = p.strip()
            if p:
                body_elements.append(f"      <p>{_escape(p)}</p>")

    body_content = "\n".join(body_elements)
    binaries_content = "\n".join(binaries)

    chapter_title = f"Том {volume}, Глава {chapter_title_num}"
    fb2_parts = [
        f'<?xml version="1.0" encoding="utf-8"?>',
        f'<FictionBook xmlns="{FB2_NS}" xmlns:l="http://www.w3.org/1999/xlink">',
        f'  <description>',
        f'    <title-info>',
        f'      <genre>non-fiction</genre>',
        f'      <book-title>{_escape(book_title)} — {_escape(chapter_title)}</book-title>',
        f'      <lang>ru</lang>',
        f'    </title-info>',
        f'    <document-info>',
        f'      <program-used>ranobe_downloader</program-used>',
        f'      <date value="2026-01-01"/>',
        f'      <version>1.0</version>',
        f'    </document-info>',
        f'  </description>',
        f'  <body>',
        f'    <section>',
        f'      <title><p>{_escape(chapter_title)}</p></title>',
        body_content,
        f'    </section>',
        f'  </body>',
    ]
    if binaries_content:
        fb2_parts.append(binaries_content)
    fb2_parts.append("</FictionBook>")

    fb2_content = "\n".join(fb2_parts)

    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(fb2_content)
    return filepath
