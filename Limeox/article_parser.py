from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from dateutil import parser
import pytz
import time


# --------------------------------
# NEW YORK TIMEZONE
# --------------------------------

NY_ZONE = pytz.timezone(
    "America/New_York"
)



# --------------------------------
# DATE CONVERSION
# --------------------------------

def convert_to_newyork(date_text):

    try:

        date_obj = parser.parse(
            date_text
        )


        # agar timezone missing ho

        if date_obj.tzinfo is None:

            date_obj = pytz.utc.localize(
                date_obj
            )


        ny_time = date_obj.astimezone(
            NY_ZONE
        )


        return ny_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


    except:

        return ""



# --------------------------------
# EXTRACT ARTICLE DATA
# --------------------------------

def parse_article(article):


    url = article["url"]

    source = article["source"]


    result = {


        "source": source,

        "title": article.get(
            "title",
            ""
        ),

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

                timeout=30000,

                wait_until="domcontentloaded"

            )


            time.sleep(2)



            html = page.content()



            soup = BeautifulSoup(
                html,
                "html.parser"
            )



            # ----------------------
            # TITLE
            # ----------------------

            h1 = soup.find(
                "h1"
            )


            if h1:


                result["title"] = (
                    h1.get_text(
                        " ",
                        strip=True
                    )
                )



            # ----------------------
            # DATE
            # ----------------------

            date = ""



            time_tag = soup.find(
                "time"
            )


            if time_tag:


                date = (

                    time_tag.get(
                        "datetime"
                    )

                    or

                    time_tag.get_text(
                        strip=True
                    )

                )



            if not date:


                meta = soup.find(
                    "meta",
                    property="article:published_time"
                )


                if meta:


                    date = meta.get(
                        "content",
                        ""
                    )



            if date:


                result[
                    "published_date_new_york"
                ] = convert_to_newyork(
                    date
                )



            # ----------------------
            # FIRST PARAGRAPH
            # ----------------------

            paragraphs = soup.find_all(
                "p"
            )


            for p_tag in paragraphs:


                text = p_tag.get_text(
                    " ",
                    strip=True
                )


                if len(text) > 60:


                    result[
                        "first_paragraph"
                    ] = text


                    break



        except Exception as e:


            print(
                "ARTICLE ERROR:",
                url
            )


            print(e)



        finally:


            browser.close()



    return result