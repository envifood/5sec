#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_films.py — обновляет базу фильмов (const FILMS) в index.html
данными из Google Таблицы фестиваля «Ща5сек».

КАК ПОЛЬЗОВАТЬСЯ
-----------------
1. Убедитесь, что таблица доступна по ссылке на чтение:
   Файл → Настройки доступа → «Все, у кого есть ссылка» → Читатель.
   Без этого скрипт не сможет скачать данные.

2. Положите этот файл (update_films.py) в ту же папку, где лежит index.html.

3. Запустите:
       python3 update_films.py

   Скрипт скачает таблицу, соберёт из неё список фильмов в формате,
   который понимает сайт, и подставит его в index.html вместо старого
   массива `const FILMS = [ ... ];`. Всё остальное в файле не трогается.

4. Таблицу можно редактировать когда угодно — просто запускайте скрипт
   заново, и сайт обновится под текущее содержимое таблицы.

СТРУКТУРА ТАБЛИЦЫ
------------------
Первая строка — заголовки столбцов. Порядок столбцов не важен: скрипт
ищет их по названию, а не по букве колонки. Обязательные названия
заголовков (регистр важен, ровно как в сайте):

    id, title, author

Необязательные:

    city, videoId, authorUrl, adult

Столбец "№" (или любой другой лишний столбец) просто игнорируется.
Столбец "show" в таблице больше не нужен — на сайте показ определяется
автоматически по id вида "<слаг-показа>-<номер>", например "2019-bfm-1"
(скрипт при этом всё равно проверяет, что слаг из id совпадает с одним
из известных показов, и предупреждает, если нет).

Про поле adult: значения "yes", "true", "1", "да" (без учёта регистра)
считаются истиной — у фильма появится значок 18+. Любое другое значение
(включая пустое) — фильм обычный.

Если в таблице несколько листов (вкладок) — впишите их gid в список
GIDS ниже. gid листа виден в адресной строке браузера после того, как
открыть нужную вкладку — это число после "#gid=". Первый лист обычно
имеет gid "0".
"""

import csv
import io
import os
import re
import ssl
import sys
import urllib.request
import urllib.error

# На macOS Python из python.org иногда не видит системные корневые сертификаты,
# из-за чего HTTPS-запросы падают с CERTIFICATE_VERIFY_FAILED. Если установлен
# пакет certifi — используем его сертификаты явно, это чинит проблему без
# необходимости лезть в системные настройки.
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

# ============================== НАСТРОЙКИ ===================================

# ID таблицы — это часть ссылки между /d/ и /edit
SHEET_ID = "15_FGf8ISv9c6fFPcsr-mZrFjfIa4VaK_gXmUVGkaRA8"

# gid листов (вкладок), которые нужно собрать в базу. Если данные лежат
# на одном листе — оставьте только "0". Если добавите вкладки на разные
# показы — впишите сюда все их gid через запятую: GIDS = ["0", "123456789"]
GIDS = ["1170556722"]

# Путь к файлу сайта. По умолчанию скрипт ищет index.html РЯДОМ С СОБОЙ —
# то есть в той же папке, где лежит update_films.py, а не в той папке,
# откуда его запустили (это разные вещи: можно запускать скрипт из любого
# места, указав к нему полный путь, и он всё равно найдёт index.html рядом с собой).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML_PATH = os.path.join(SCRIPT_DIR, "index.html")

# Слаги показов, которые сайт умеет отображать (см. SHOW_SLUGS в index.html).
# Показ вычисляется на сайте из id вида "<слаг>-<номер>" — скрипт здесь просто
# сверяет слаг из id с этим списком и предупреждает, если он не найден
# (скорее всего, опечатка в id или новый показ, которого ещё нет на сайте).
KNOWN_SLUGS = {
    "2019-bfm", "2020-suzdal", "2020-online", "2020-bfm",
    "2021-suzdal", "2021-insmn", "2021-bfm",
    "2024-suzdal", "2024-insmn", "2024-bfm",
    "2025-suzdal", "2025-insmn", "2025-bfm",
    "2026-suzdal", "2026-insmn",
}

# id вида "<слаг>-<номер>", например "2019-bfm-142" → слаг "2019-bfm"
ID_SLUG_RE = re.compile(r"^(.+)-\d+$")

REQUIRED_FIELDS = ["id", "title", "author"]
TRUE_VALUES = {"yes", "true", "1", "да", "истина"}

# ==============================================================================


def csv_url(gid):
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"


def fetch_rows(gid):
    url = csv_url(gid)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
            raw = resp.read().decode("utf-8-sig")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            raise SystemExit(
                f"Лист с gid={gid} не найден (HTTP 400) — скорее всего, неверный gid.\n"
                "Как узнать правильный: откройте таблицу в браузере, кликните на нужную "
                "вкладку внизу и посмотрите на конец адресной строки — там будет "
                "«#gid=ЧИСЛО». Впишите это число в список GIDS в начале скрипта."
            )
        raise SystemExit(
            f"Не удалось скачать лист gid={gid} (HTTP {e.code}).\n"
            "Проверьте, что таблица открыта для чтения по ссылке "
            "(Файл → Настройки доступа) и что gid указан верно."
        )
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e.reason):
            raise SystemExit(
                "Ошибка проверки SSL-сертификата (типично для Python с python.org на macOS).\n"
                "Исправьте одним из способов:\n"
                "  1) pip3 install certifi   — и запустите скрипт заново;\n"
                "  2) откройте папку /Applications/Python 3.x/ и запустите файл "
                "«Install Certificates.command» двойным кликом."
            )
        raise SystemExit(f"Нет соединения с Google Таблицами: {e.reason}")

    reader = csv.DictReader(io.StringIO(raw))
    return list(reader)


def js_string(value):
    """Экранирует строку для подстановки в двойные кавычки JS."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .strip()
    )


def build_film_line(row, location):
    film_id = (row.get("id") or "").strip()
    title = (row.get("title") or "").strip()
    author = (row.get("author") or "").strip()

    # полностью пустые строки (иногда встречаются в таблицах как разделители) —
    # пропускаем молча, без предупреждения
    if not any((row.get(k) or "").strip() for k in row):
        return None, None

    missing = [f for f in REQUIRED_FIELDS if not (row.get(f) or "").strip()]
    if missing:
        print(f"  [пропущено] {location}: нет обязательных полей {missing}")
        return None, None

    m = ID_SLUG_RE.match(film_id)
    slug = m.group(1) if m else None
    if slug not in KNOWN_SLUGS:
        print(f"  [внимание] {location}: не удалось определить показ по id «{film_id}» "
              f"— проверьте формат id (ожидается «слаг-показа-номер», например «2019-bfm-1») "
              f"или добавьте слаг в KNOWN_SLUGS/SHOW_SLUGS")

    parts = [
        f'id:"{js_string(film_id)}"',
        f'title:"{js_string(title)}"',
        f'author:"{js_string(author)}"',
    ]

    city = (row.get("city") or "").strip()
    if city:
        parts.append(f'city:"{js_string(city)}"')

    video_id = (row.get("videoId") or "").strip()
    if video_id:
        parts.append(f'videoId:"{js_string(video_id)}"')

    author_url = (row.get("authorUrl") or "").strip()
    if author_url:
        parts.append(f'authorUrl:"{js_string(author_url)}"')

    adult_raw = (row.get("adult") or "").strip().lower()
    if adult_raw in TRUE_VALUES:
        parts.append("adult:true")

    return film_id, "  { " + ", ".join(parts) + " }"


def build_films_block(all_rows):
    lines = []
    seen_ids = set()

    for gid, rows in all_rows:
        for i, row in enumerate(rows, start=2):  # +2: строка 1 — заголовки
            location = f"лист gid={gid}, строка {i}"
            film_id, line = build_film_line(row, location)
            if line is None:
                continue
            if film_id in seen_ids:
                print(f"  [внимание] {location}: повторяющийся id «{film_id}» "
                      f"— фильм всё равно добавлен, но проверьте таблицу")
            seen_ids.add(film_id)
            lines.append(line)

    if not lines:
        raise SystemExit(
            "Не найдено ни одной валидной строки. Проверьте, что в таблице "
            "заполнены столбцы id, title, author."
        )

    return "const FILMS = [\n" + ",\n\n".join(lines) + "\n];", len(lines)


def replace_films_block(html, new_block):
    start_marker = "const FILMS = ["
    start = html.find(start_marker)
    if start == -1:
        raise SystemExit(f"В {INDEX_HTML_PATH} не найдено 'const FILMS = ['.")
    end = html.find("\n];", start)
    if end == -1:
        raise SystemExit(f"В {INDEX_HTML_PATH} не найден конец массива FILMS ('];').")
    end += len("\n];")
    return html[:start] + new_block + html[end:]


def main():
    all_rows = []
    for gid in GIDS:
        print(f"Загружаю лист gid={gid}…")
        rows = fetch_rows(gid)
        print(f"  получено строк: {len(rows)}")
        all_rows.append((gid, rows))

    print("Собираю базу фильмов…")
    films_block, count = build_films_block(all_rows)
    print(f"Успешно собрано фильмов: {count}")

    try:
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        raise SystemExit(
            f"Не найден файл {INDEX_HTML_PATH}. Положите update_films.py в ту же папку, "
            "где лежит index.html (или поправьте INDEX_HTML_PATH в начале скрипта)."
        )

    new_html = replace_films_block(html, films_block)

    with open(INDEX_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"Готово! {INDEX_HTML_PATH} обновлён — {count} фильмов из таблицы.")


if __name__ == "__main__":
    main()
