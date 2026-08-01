import feedparser


# --------------------------------
# CLEAN ARTICLES
# --------------------------------

def clean_articles(entries, source):

    articles = []

    seen = set()


    for item in entries:

        url = item.get("link", "")

        title = item.get("title", "")

        published = item.get(
            "published",
            ""
        )


        if not url:
            continue


        if url in seen:
            continue


        seen.add(url)


        articles.append({

            "source": source,

            "title": title,

            "url": url,

            "rss_date": published

        })


    return articles



# --------------------------------
# GET RSS ARTICLES
# --------------------------------

def get_rss_articles(
        source,
        rss_urls,
        limit=150
):


    print(
        "\nReading RSS:",
        source
    )


    all_entries = []


    try:


        # multiple RSS feeds

        for rss_url in rss_urls:


            print(
                "Feed:",
                rss_url
            )


            feed = feedparser.parse(
                rss_url
            )


            all_entries.extend(
                feed.entries
            )



        articles = clean_articles(
            all_entries,
            source
        )



        articles = articles[:limit]



        print(
            source,
            "Found:",
            len(articles)
        )



        return articles



    except Exception as e:


        print(
            "RSS ERROR:",
            source,
            e
        )


        return []