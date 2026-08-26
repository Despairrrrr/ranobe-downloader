import base64
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

FB2_NS = "http://www.gribuser.ru/xml/fictionbook/2.0"
XLINK_NS = "http://www.w3.org/1999/xlink"
NS = f"{{{FB2_NS}}}"


def parse_filename(filepath):
    basename = os.path.basename(filepath)
    match = re.match(r"том(\d+)_глава(.+)\.fb2$", basename, re.IGNORECASE)
    if not match:
        return None, None
    volume = int(match.group(1))
    chapter_str = match.group(2).replace("_", ".")
    try:
        chapter_num = float(chapter_str)
    except ValueError:
        return None, None
    return volume, chapter_num


def extract_chapter_info(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()

    title_el = root.find(f".//{NS}body/{NS}section/{NS}title")
    if title_el is None:
        return ""
    p = title_el.find(f"{NS}p")
    if p is None or not p.text:
        return ""
    full_title = p.text.strip()

    match = re.match(r"Том\s+\d+,\s*Глава\s+[\d.]+(?:\s*—\s*(.+))?$", full_title)
    if match and match.group(1):
        return match.group(1).strip()
    return ""


def extract_book_title(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    bt = root.find(f".//{NS}description/{NS}title-info/{NS}book-title")
    if bt is not None and bt.text:
        title = bt.text.strip()
        sep = " — "
        if sep in title:
            return title[:title.index(sep)]
        return title
    return ""


def extract_section_content(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    section = root.find(f".//{NS}body/{NS}section")
    if section is None:
        return []
    return list(section)


def extract_binaries(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = re.compile(r'<binary\s+id="([^"]+)"\s+content-type="([^"]+)">([^<]+)</binary>')
    return [(m.group(1), m.group(2), m.group(3)) for m in pattern.finditer(content)]


def find_cover(cwd):
    for name in os.listdir(cwd):
        if name.lower().endswith(".jpg") and name.lower().startswith("том"):
            path = os.path.join(cwd, name)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("ascii")
                return data
    return None


def indent_xml(text, level=0):
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            result.append("  " * level + stripped)
        else:
            result.append("")
    return "\n".join(result)


def build_merged_fb2(volume, chapter_files, cover_b64):
    book_title = extract_book_title(chapter_files[0])
    if not book_title:
        book_title = f"Том {volume}"

    toc_entries = []
    all_sections = []
    all_binaries = []
    img_counter = 0

    for filepath in chapter_files:
        chapter_num = parse_filename(filepath)[1]
        chapter_name = extract_chapter_info(filepath)

        num_str = str(int(chapter_num)) if chapter_num == int(chapter_num) else str(chapter_num)
        toc_label = f"{num_str} — {chapter_name}" if chapter_name else num_str
        toc_entries.append(toc_label)

        section_elements = extract_section_content(filepath)

        local_remap = {}
        for child in section_elements:
            if child.tag == f"{NS}image":
                old_href = child.get(f"{{{XLINK_NS}}}href", child.get("href", ""))
                if old_href.startswith("#"):
                    old_id = old_href[1:]
                    if old_id not in local_remap:
                        local_remap[old_id] = f"img{img_counter}"
                        img_counter += 1

        new_section_children = []
        for child in section_elements:
            tag = child.tag
            if tag == f"{NS}title":
                new_section_children.append(child)
            elif tag == f"{NS}image":
                old_href = child.get(f"{{{XLINK_NS}}}href", child.get("href", ""))
                if old_href.startswith("#"):
                    old_id = old_href[1:]
                    new_href = f"#{local_remap[old_id]}"
                    new_el = ET.SubElement(ET.Element("dummy"), f"{NS}image")
                    new_el.set(f"{{{XLINK_NS}}}href", new_href)
                    new_section_children.append(new_el)
            else:
                new_section_children.append(child)

        all_sections.append(new_section_children)

        binaries = extract_binaries(filepath)
        for bid, ctype, bdata in binaries:
            new_id = local_remap.get(bid, f"img{img_counter}")
            if bid not in local_remap:
                img_counter += 1
            all_binaries.append((new_id, ctype, bdata))

    toc_section_lines = []
    toc_section_lines.append("    <section>")
    toc_section_lines.append('      <title><p>Содержание</p></title>')
    for entry in toc_entries:
        escaped = entry.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        toc_section_lines.append(f"      <p>{escaped}</p>")
    toc_section_lines.append("    </section>")

    body_sections = []
    for section_children in all_sections:
        sec_lines = ["    <section>"]
        for child in section_children:
            if child.tag == f"{NS}title":
                p = child.find(f"{NS}p")
                if p is not None and p.text:
                    text = p.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    sec_lines.append(f"      <title><p>{text}</p></title>")
            elif child.tag == f"{NS}image":
                href = child.get(f"{{{XLINK_NS}}}href", child.get("href", ""))
                sec_lines.append(f'      <image l:href="{href}"/>')
            elif child.tag == f"{NS}p":
                texts = list(child.itertext())
                text = "".join(texts).strip()
                if text:
                    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    sec_lines.append(f"      <p>{escaped}</p>")
        sec_lines.append("    </section>")
        body_sections.append("\n".join(sec_lines))

    cover_ref = ""
    cover_binary = ""
    if cover_b64:
        cover_ref = '    <coverpage><image l:href="#cover"/></coverpage>\n'
        cover_binary = f'  <binary id="cover" content-type="image/jpeg">{cover_b64}</binary>\n'

    binaries_lines = []
    if cover_binary:
        binaries_lines.append(cover_binary)
    for bid, ctype, bdata in all_binaries:
        binaries_lines.append(f'  <binary id="{bid}" content-type="{ctype}">{bdata}</binary>')

    fb2_parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<FictionBook xmlns="{FB2_NS}" xmlns:l="http://www.w3.org/1999/xlink">',
        '  <description>',
        '    <title-info>',
        '      <genre>non-fiction</genre>',
        f'      <book-title>{book_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")} — Том {volume}</book-title>',
        f'{cover_ref.rstrip()}' if cover_ref else '',
        '      <lang>ru</lang>',
        '    </title-info>',
        '    <document-info>',
        '      <program-used>ranobe_downloader merge</program-used>',
        '      <date value="2026-01-01"/>',
        '      <version>1.0</version>',
        '    </document-info>',
        '  </description>',
        '  <body>',
        "\n".join(toc_section_lines),
        "\n\n".join(body_sections),
        '  </body>',
    ]

    if binaries_lines:
        fb2_parts.extend(binaries_lines)
    fb2_parts.append("</FictionBook>")

    return "\n".join(fb2_parts)


def main():
    if len(sys.argv) < 2:
        print("Использование: python merge_fb2.py <номер_тома>")
        sys.exit(1)

    try:
        volume = int(sys.argv[1])
    except ValueError:
        print("Номер тома должен быть целым числом")
        sys.exit(1)

    cwd = os.getcwd()
    fb2_files = glob.glob(os.path.join(cwd, "том*_глава*.fb2"))

    volume_files = []
    for fp in fb2_files:
        v, c = parse_filename(fp)
        if v == volume:
            volume_files.append(fp)

    if not volume_files:
        print(f"Файлы для тома {volume} не найдены")
        sys.exit(1)

    def chapter_sort_key(filepath):
        _, c = parse_filename(filepath)
        return c

    volume_files.sort(key=chapter_sort_key)

    print(f"Найдено {len(volume_files)} файлов для тома {volume}:")
    for fp in volume_files:
        print(f"  {os.path.basename(fp)}")

    cover_b64 = find_cover(cwd)
    if cover_b64:
        print("Найдена обложка")
    else:
        print("Обложка не найдена")

    merged = build_merged_fb2(volume, volume_files, cover_b64)

    output_path = os.path.join(cwd, f"том{volume}.fb2")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(merged)

    print(f"Сохранено: {output_path}")


if __name__ == "__main__":
    main()
