from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from datetime import datetime
from dateutil import parser
import pytz
import time


# -------------------------------
# NEW YORK TIMEZONE
# -------------------------------

NY_TIMEZONE = pytz.timezone(
    "America/New_York"
)



# -------------------------------
# DATE CONVERTER
# -------------------------------

def convert_to_newyork(date_text):

    try:

        date_obj = parser.parse(
            date_text
        )


        if date_obj.tzinfo is None:

            date_obj = pytz.utc.localize(
                date_obj
            )


        ny_date = date_obj.astimezone(
            NY_TIMEZONE
        )


        return ny_date.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


    except:

        return ""



# -------------------------------
# EXTRACT ARTICLE DATA
# -------------------------------

def extract_article(url, source):


    data = {

        "source": source,
        "title": "",
        "url": url,
        "published_date_new_york": "",
        "first_paragraph": ""

    }



    with sync_playwright() as p:


        browser = p.chromium.launch(
            headless=True
        )


        page = browser.new_page()



        try:


            page.goto(
                url,
                timeout=60000,
                wait_until="domcontentloaded"
            )


            time.sleep(2)


            html = page.content()



            soup = BeautifulSoup(
                html,
                "html.parser"
            )



            # -------------------
            # TITLE
            # -------------------

            title = soup.find(
                "h1"
            )


            if title:

                data["title"] = title.get_text(
                    " ",
                    strip=True
                )


            else:

                meta = soup.find(
                    "meta",
                    property="og:title"
                )


                if meta:

                    data["title"] = meta.get(
                        "content",
                        ""
                    )



            # -------------------
            # DATE
            # -------------------

            date = ""


            possible_dates = [

                soup.find(
                    "time"
                ),

                soup.find(
                    "meta",
                    property="article:published_time"
                ),

                soup.find(
                    "meta",
                    attrs={
                    "name":"date"
                    }
                )

            ]



            for item in possible_dates:


                if item:


                    date = (
                        item.get("datetime")
                        or
                        item.get("content")
                        or
                        item.get_text()
                    )

                    break



            if date:

                data["published_date_new_york"] = (
                    convert_to_newyork(date)
                )



            # -------------------
            # FIRST PARAGRAPH
            # -------------------

            paragraphs = soup.find_all(
                "p"
            )


            for p_tag in paragraphs:


                text = p_tag.get_text(
                    " ",
                    strip=True
                )


                if len(text) > 50:


                    data["first_paragraph"] = text

                    break



        except Exception as e:


            print(
                "ARTICLE ERROR:",
                url
            )

            print(e)



        browser.close()



    return data