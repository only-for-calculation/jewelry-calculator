

"""Fetch and validate Housho's published 37-grade table.

Use only where automated access is permitted by the site operator.

Never overwrite valid saved rates with incomplete or older data.

"""

import datetime as dt

import json

import pathlib

import re

import time

import urllib.error

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

        m = re.match(r"PT(1000|950|900|850)", x)

        if m:

            suffix = (

                "（ダイヤ付き）"

                if "ダイヤモンド付き" in label

                else ""

            )

            return "Pt" + m[1] + suffix

    if x.startswith("SV"):

        m = re.fullmatch(

            r"SV(1000|925)(?:（純銀）)?", x

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

def make_urls():

    stamp = dt.datetime.now(JST).strftime(

        "%Y%m%d%H%M%S%f"

    )

    return [

        (

            "https://www.housho-diamond.co.jp/"

            f"?_rate_check={stamp}"

        ),

        (

            "https://housho-diamond.co.jp/"

            f"?_rate_check={stamp}1"

        ),

        (

            "https://www.housho-diamond.co.jp/"

            f"?_rate_check={stamp}2"

            "&_nocache=1"

        ),

    ]

def download(url):

    request = urllib.request.Request(

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

        },

    )

    with urllib.request.urlopen(

        request, timeout=30

    ) as response:

        html = response.read(3_000_000)

        print(

            "HTTP status:",

            response.status,

            "Final URL:",

            response.geturl(),

            flush=True,

        )

    return html

def parse_rates(html):

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup([

        "script", "style", "noscript"

    ]):

        tag.decompose()

    content = soup.get_text("\n", strip=True)

    start = content.find("本日の地金買取価格")

    if start < 0:

        raise ValueError(

            "Price table heading not found"

        )

    end = content.find(

        "ご利用上の注意点", start

    )

    if end < 0:

        raise ValueError(

            "Price table ending not found"

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

            r"([\d,]+)円", next_line

        )

        if not match:

            continue

        value = int(

            match[1].replace(",", "")

        )

        if not 1 <= value <= 100000:

            raise ValueError(

                f"Invalid price: {key}={value}"

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

    return {

        "published_dt": published_dt,

        "published_at": published_text,

        "rates": prices,

    }

def load_previous():

    if not OUT.exists():

        return None, None

    previous = json.loads(

        OUT.read_text(encoding="utf-8")

    )

    try:

        old_dt, _ = publication(

            previous.get("published_at", "")

        )

    except ValueError:

        old_dt = None

    return previous, old_dt

def check_freshness(published_dt):

    now = dt.datetime.now(JST)

    age = now - published_dt

    # During weekday business hours, flag a

    # publication older than 20 hours.

    # Public holidays may require manual review.

    if (

        now.weekday() < 5

        and now.hour >= 10

        and age > dt.timedelta(hours=20)

    ):

        raise ValueError(

            "Official rate publication appears stale: "

            f"{published_dt.isoformat()} "

            f"(age: {age})"

        )

def main():

    now = dt.datetime.now(JST)

    previous, old_dt = load_previous()

    print(

        "Rate check started:",

        now.isoformat(timespec="seconds"),

        flush=True,

    )

    candidates = []

    errors = []

    for index, url in enumerate(

        make_urls(), start=1

    ):

        print(

            f"Checking source {index}/3",

            flush=True,

        )

        try:

            html = download(url)

            result = parse_rates(html)

            print(

                "Publication:",

                result["published_at"],

                flush=True,

            )

            print(

                "K18:",

                result["rates"]["K18"],

                "Pt900:",

                result["rates"]["Pt900"],

                flush=True,

            )

            print(

                "Validated grades:",

                len(result["rates"]),

                flush=True,

            )

            candidates.append(result)

        except Exception as exc:

            message = (

                f"Source {index} failed: "

                f"{type(exc).__name__}: {exc}"

            )

            errors.append(message)

            print(message, flush=True)

        if index < 3:

            time.sleep(2)

    if not candidates:

        raise RuntimeError(

            "All official source checks failed.\n"

            + "\n".join(errors)

        )

    latest_dt = max(

        item["published_dt"]

        for item in candidates

    )

    latest = [

        item for item in candidates

        if item["published_dt"] == latest_dt

    ]

    # If equally dated sources disagree,

    # do not choose prices arbitrarily.

    first_rates = latest[0]["rates"]

    for item in latest[1:]:

        if item["rates"] != first_rates:

            raise ValueError(

                "Official sources disagree on prices "

                "for the same publication timestamp"

            )

    selected = latest[0]

    print(

        "Selected publication:",

        selected["published_at"],

        flush=True,

    )

    check_freshness(selected["published_dt"])

    if old_dt and selected["published_dt"] < old_dt:

        raise ValueError(

            "Stale upstream response: "

            f"{selected['published_at']} "

            f"< {previous['published_at']}"

        )

    if (

        old_dt

        and selected["published_dt"] == old_dt

    ):

        if previous.get("rates") != first_rates:

            raise ValueError(

                "Prices changed without a new "

                "publication timestamp. "

                "Manual review required."

            )

        print(

            "No new official publication:",

            selected["published_at"],

            flush=True,

        )

        return

    payload = {

        "source": URL,

        "published_at": selected["published_at"],

        "checked_at": now.isoformat(

            timespec="seconds"

        ),

        "rates": {

            key: first_rates[key]

            for key in KEYS

        },

    }

    OUT.write_text(

        json.dumps(

            payload,

            ensure_ascii=False,

            indent=2,

        ) + "\n",

        encoding="utf-8",

    )

    print(

        "Saved 37 grades.",

        "Published:",

        selected["published_at"],

        "K18:",

        first_rates["K18"],

        "Pt900:",

        first_rates["Pt900"],

        flush=True,

    )

if __name__ == "__main__":

    main()
