

"""Fetch Housho's displayed 37-grade metal rates.

Use only where automated access is permitted.

Preserve the existing rates.json format.

"""

import datetime as dt

import json

import pathlib

import re

import urllib.parse

import urllib.request

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent

OUT = ROOT / "rates.json"

URL = "https://www.housho-diamond.co.jp/"

JST = dt.timezone(dt.timedelta(hours=9))

KEYS = [

    "金インゴット",

    "K24", "K22", "K21.6", "K20",

    "K18", "K14", "K10", "K9", "K18WG",

    "Pt1000インゴット",

    "Pt1000", "Pt950", "Pt900",

    "Pt900（ダイヤ付き）",

    "Pt850", "Pt850（ダイヤ付き）",

    "SV1000", "SV925",

]

KEYS += [

    f"K18/Pt{pt}（{n}:{10-n}）"

    for pt in (900, 850)

    for n in range(9, 0, -1)

]

assert len(KEYS) == 37

def normalize(label):

    return (

        re.sub(r"\s+", "", label)

        .upper()

        .replace("ＰＴ", "PT")

        .replace("ＳＶ", "SV")

        .replace("ＷＧ", "WG")

        .replace("／", "/")

        .replace("：", ":")

        .replace("(", "（")

        .replace(")", "）")

    )

def grade(label):

    x = normalize(label)

    if "金インゴット" in label:

        return "金インゴット"

    if "インゴット" in label and "PT1000" in x:

        return "Pt1000インゴット"

    if x in ("WGK18", "K18WG"):

        return "K18WG"

    if x.startswith("K18") and "PT" in x:

        m = re.search(

            r"PT(900|850).*?（([1-9]):([1-9])）",

            x

        )

        if m and int(m[2]) + int(m[3]) == 10:

            return (

                f"K18/Pt{m[1]}"

                f"（{m[2]}:{m[3]}）"

            )

    if x.startswith("PT"):

        m = re.match(

            r"PT(1000|950|900|850)", x

        )

        if m:

            suffix = (

                "（ダイヤ付き）"

                if "ダイヤモンド付き" in label

                else ""

            )

            return "Pt" + m[1] + suffix

    if x.startswith("SV"):

        m = re.fullmatch(

            r"SV(1000|925)(?:（純銀）)?",

            x

        )

        if m:

            return "SV" + m[1]

    if re.fullmatch(

        r"K(?:24|22|21\.6|20|18|14|10|9)",

        x

    ):

        return x

    return None

def publication(text):

    pattern = (

        r"(20\d{2})/(\d{1,2})/(\d{1,2})"

        r"\s*(?:\([^)]*\))?\s*"

        r"(\d{1,2}):(\d{2})"

    )

    m = re.search(pattern, text)

    if not m:

        raise ValueError(

            "Publication timestamp not found"

        )

    parts = [int(v) for v in m.groups()]

    value = dt.datetime(*parts, tzinfo=JST)

    if value > dt.datetime.now(JST) + dt.timedelta(

        minutes=5

    ):

        raise ValueError(

            "Publication timestamp is in the future"

        )

    return value, m.group()

def fetch_html():

    now = dt.datetime.now(JST)

    query = urllib.parse.urlencode({

        "_rate_check": now.strftime(

            "%Y%m%d%H%M%S%f"

        )

    })

    url = URL + "?" + query

    req = urllib.request.Request(

        url,

        headers={

            "User-Agent": (

                "Mozilla/5.0 "

                "(compatible; PersonalPriceChecker/1.0)"

            ),

            "Cache-Control": (

                "no-cache, no-store, max-age=0"

            ),

            "Pragma": "no-cache",

            "Accept": "text/html",

            "Accept-Language": "ja-JP,ja;q=0.9",

        }

    )

    with urllib.request.urlopen(

        req, timeout=30

    ) as response:

        print(

            "HTTP status:",

            response.status,

            flush=True

        )

        print(

            "Final URL:",

            response.geturl(),

            flush=True

        )

        print(

            "Response Date:",

            response.headers.get("Date"),

            flush=True

        )

        print(

            "Response Age:",

            response.headers.get("Age"),

            flush=True

        )

        print(

            "Cache Status:",

            response.headers.get("X-Cache"),

            flush=True

        )

        return response.read(3_000_000)

def parse_html(html):

    soup = BeautifulSoup(

        html, "html.parser"

    )

    for tag in soup([

        "script", "style", "noscript"

    ]):

        tag.decompose()

    content = soup.get_text(

        "\n", strip=True

    )

    start = content.find(

        "本日の地金買取価格"

    )

    end = content.find(

        "ご利用上の注意点",

        start

    )

    if start < 0 or end < 0:

        raise ValueError(

            "Price table boundaries missing"

        )

    section = content[start:end]

    published_dt, published_text = publication(

        section

    )

    rows = [

        line.strip()

        for line in section.splitlines()

        if line.strip()

    ]

    prices = {}

    for label, next_line in zip(

        rows, rows[1:]

    ):

        key = grade(label)

        if key not in KEYS:

            continue

        match = re.fullmatch(

            r"([\d,]+)円",

            next_line

        )

        if not match:

            continue

        value = int(

            match[1].replace(",", "")

        )

        if not 1 <= value <= 100000:

            raise ValueError(

                f"Invalid price: {key}"

            )

        if key in prices:

            raise ValueError(

                f"Duplicate grade: {key}"

            )

        prices[key] = value

    missing = set(KEYS) - set(prices)

    if missing:

        raise ValueError(

            "Incomplete table. Missing: "

            + ", ".join(sorted(missing))

        )

    return published_dt, published_text, prices

def main():

    now = dt.datetime.now(JST)

    print(

        "Checking Housho official rates",

        flush=True

    )

    print(

        "Checked at:",

        now.isoformat(timespec="seconds"),

        flush=True

    )

    html = fetch_html()

    published_dt, published_text, prices = (

        parse_html(html)

    )

    print(

        "Official publication:",

        published_text,

        flush=True

    )

    print(

        "K18:",

        prices["K18"],

        flush=True

    )

    print(

        "Pt900:",

        prices["Pt900"],

        flush=True

    )

    print(

        "Validated grades:",

        len(prices),

        flush=True

    )

    previous = {}

    if OUT.exists():

        previous = json.loads(

            OUT.read_text(encoding="utf-8")

        )

    old_published = previous.get(

        "published_at", ""

    )

    old_rates = previous.get(

        "rates", {}

    )

    same_date = (

        old_published == published_text

    )

    same_prices = (

        old_rates == prices

    )

    if same_date and same_prices:

        print(

            "No changes in displayed rates.",

            flush=True

        )

        print(

            "Existing rates.json retained.",

            flush=True

        )

        return

    if same_prices:

        print(

            "Prices unchanged; "

            "publication timestamp changed.",

            flush=True

        )

    else:

        print(

            "Displayed prices changed.",

            flush=True

        )

    payload = {

        "source": URL,

        "published_at": published_text,

        "checked_at": now.isoformat(

            timespec="seconds"

        ),

        "rates": {

            key: prices[key]

            for key in KEYS

        }

    }

    OUT.write_text(

        json.dumps(

            payload,

            ensure_ascii=False,

            indent=2

        ) + "\n",

        encoding="utf-8"

    )

    print(

        "Saved 37 grades.",

        flush=True

    )

    print(

        "Published:",

        published_text,

        flush=True

    )

    print(

        "K18:",

        prices["K18"],

        "Pt900:",

        prices["Pt900"],

        flush=True

    )

if __name__ == "__main__":

    main()
