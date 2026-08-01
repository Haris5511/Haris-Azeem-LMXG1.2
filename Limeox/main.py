from config import (
    WEBSITES,
    ARTICLES_PER_SITE,
    OUTPUT_FILE
)

from rss_scraper import get_rss_articles
from article_parser import parse_article

import json
import time



all_articles = []

global_urls = set()



# -------------------------------
# SAVE JSON
# -------------------------------

def save_json():

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            all_articles,
            f,
            indent=4,
            ensure_ascii=False
        )


    print(
        "\nJSON SAVED:",
        OUTPUT_FILE
    )




# -------------------------------
# SCRAPER
# -------------------------------

def run_scraper():


    print(
        "\nNEWS SCRAPER VERSION 3 STARTED\n"
    )



    for source, rss_list in WEBSITES.items():


        print(
            "\n===================="
        )

        print(
            "SOURCE:",
            source
        )

        print(
            "===================="
        )



        articles = get_rss_articles(

            source,

            rss_list,

            ARTICLES_PER_SITE

        )



        count = 0



        for article in articles:



            if count >= ARTICLES_PER_SITE:

                break



            url = article["url"]



            if url in global_urls:

                continue



            global_urls.add(
                url
            )



            print(
                f"{source}: {count+1}/{ARTICLES_PER_SITE}"
            )



            data = parse_article(
                article
            )



            if (

                data["title"]

                and

                data["first_paragraph"]

            ):


                all_articles.append(
                    data
                )


                count += 1



            time.sleep(0.5)



        print(
            source,
            "DONE:",
            count
        )



    save_json()



    print(
        "\n===================="
    )

    print(
        "TOTAL ARTICLES:",
        len(all_articles)
    )

    print(
        "===================="
    )




if __name__ == "__main__":

    run_scraper()