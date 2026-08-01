import json
import pandas as pd


# Load JSON
with open("articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)


print(len(articles))
print(articles[0])


# Convert to dataframe
df = pd.DataFrame(articles)


print(df.head())
print(df.columns)

import re


# Combine title + paragraph
df["text"] = (
    df["title"] 
    + ". " 
    + df["first_paragraph"]
)


print(df["text"].head())

def clean_text(text):

    # lowercase
    text = text.lower()

    # remove URL
    text = re.sub(r"http\S+", "", text)

    # remove special characters
    text = re.sub(r"[^a-zA-Z\s]", "", text)

    # remove extra spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


df["clean_text"] = df["text"].apply(clean_text)


print(df[["title","clean_text"]].head())


processed = df[
    [
        "source",
        "title",
        "url",
        "published_date_new_york",
        "clean_text"
    ]
]


processed.to_json(
    "processed_articles.json",
    orient="records",
    indent=4,
    force_ascii=False
)


print("Preprocessing Complete!")