"""
Text Preprocessing Script for articles.json
=============================================
Ye script news articles ke JSON file ko load kr ke unke 'title' aur
'first_paragraph' fields per standard NLP text preprocessing steps apply karti hai:

    1. Lowercasing
    2. URL removal
    3. HTML entities / special characters removal
    4. Punctuation removal
    5. Numbers removal (optional - flag se control hota hai)
    6. Tokenization
    7. Stopword removal
    8. Stemming (Porter Stemmer - pure python implementation, no external lib chahiye)
    9. Extra whitespace cleanup

Output:
    - preprocessed_articles.json  -> cleaned + tokenized data
    - preprocessed_articles.csv   -> flat table for easy viewing in Excel

No external NLP library (nltk/spacy) ki zaroorat nahi — sab kuch pure Python
standard library se hua hai, isliye ye kahin bhi bina internet ke chal jayega.
"""

import json
import os
import re
import csv
import string

# -------------------------------------------------------------------
# 1. STOPWORDS LIST (English) - manually curated, nltk jaisi list
# -------------------------------------------------------------------
STOPWORDS = set("""
a about above after again against all am an and any are aren't as at be
because been before being below between both but by can't cannot could
couldn't did didn't do does doesn't doing don't down during each few for
from further had hadn't has hasn't have haven't having he he'd he'll he's
her here here's hers herself him himself his how how's i i'd i'll i'm i've
if in into is isn't it it's its itself let's me more most mustn't my
myself no nor not of off on once only or other ought our ours ourselves
out over own same shan't she she'd she'll she's should shouldn't so some
such than that that's the their theirs them themselves then there there's
these they they'd they'll they're they've this those through to too under
until up very was wasn't we we'd we'll we're we've were weren't what
what's when when's where where's which while who who's whom why why's
with won't would wouldn't you you'd you'll you're you've your yours
yourself yourselves
""".split())


# -------------------------------------------------------------------
# 2. PURE-PYTHON PORTER STEMMER (lightweight, no dependency)
# -------------------------------------------------------------------
class PorterStemmer:
    """Minimal Porter Stemmer implementation (classic algorithm)."""

    def _is_consonant(self, word, i):
        ch = word[i]
        if ch in "aeiou":
            return False
        if ch == "y":
            return i == 0 or not self._is_consonant(word, i - 1)
        return True

    def _measure(self, word):
        n = 0
        i = 0
        length = len(word)
        while i < length and self._is_consonant(word, i):
            i += 1
        while i < length:
            while i < length and not self._is_consonant(word, i):
                i += 1
            if i >= length:
                break
            while i < length and self._is_consonant(word, i):
                i += 1
            n += 1
        return n

    def _contains_vowel(self, stem):
        return any(not self._is_consonant(stem, i) for i in range(len(stem)))

    def stem(self, word):
        word = word.lower()
        if len(word) <= 2:
            return word

        # Step 1a
        if word.endswith("sses"):
            word = word[:-2]
        elif word.endswith("ies"):
            word = word[:-2]
        elif word.endswith("ss"):
            pass
        elif word.endswith("s"):
            word = word[:-1]

        # Step 1b
        if word.endswith("eed"):
            if self._measure(word[:-3]) > 0:
                word = word[:-1]
        else:
            stripped = None
            if word.endswith("ed") and self._contains_vowel(word[:-2]):
                stripped = word[:-2]
            elif word.endswith("ing") and self._contains_vowel(word[:-3]):
                stripped = word[:-3]
            if stripped is not None:
                word = stripped
                if word.endswith(("at", "bl", "iz")):
                    word += "e"
                elif len(word) >= 2 and word[-1] == word[-2] and word[-1] not in "lsz":
                    word = word[:-1]
                elif self._measure(word) == 1 and word[-1] not in "aeiou" and \
                        not (len(word) >= 3 and word[-3] in "aeiou" and word[-2] not in "aeiouwxy" and word[-1] in "wxy"):
                    pass

        # Step 1c
        if word.endswith("y") and self._contains_vowel(word[:-1]):
            word = word[:-1] + "i"

        return word


stemmer = PorterStemmer()


# -------------------------------------------------------------------
# 3. CLEANING / PREPROCESSING FUNCTIONS
# -------------------------------------------------------------------
def remove_urls(text):
    return re.sub(r"http\S+|www\.\S+", "", text)


def remove_html_entities(text):
    return re.sub(r"&\w+;", "", text)


def remove_punctuation(text):
    return text.translate(str.maketrans("", "", string.punctuation))


def remove_numbers(text):
    return re.sub(r"\d+", "", text)


def remove_extra_whitespace(text):
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text):
    return text.split()


def remove_stopwords(tokens):
    return [t for t in tokens if t not in STOPWORDS]


def stem_tokens(tokens):
    return [stemmer.stem(t) for t in tokens]


def preprocess_text(text, remove_nums=True, do_stem=True):
    """Full preprocessing pipeline for a single string. Returns dict with
    the cleaned sentence and the final token list."""
    if not text:
        return {"clean_text": "", "tokens": []}

    text = text.lower()
    text = remove_urls(text)
    text = remove_html_entities(text)
    text = remove_punctuation(text)
    if remove_nums:
        text = remove_numbers(text)
    text = remove_extra_whitespace(text)

    tokens = tokenize(text)
    tokens = remove_stopwords(tokens)
    tokens = [t for t in tokens if t]  # drop empty strings

    if do_stem:
        tokens = stem_tokens(tokens)

    clean_text = " ".join(tokens)
    return {"clean_text": clean_text, "tokens": tokens}


# -------------------------------------------------------------------
# 4. MAIN PIPELINE
# -------------------------------------------------------------------
def main():
    # Script ke jis folder me ye file hai, usi folder me articles.json
    # dhoondega aur output bhi usi folder me save karega.
    # (Windows/Mac/Linux har jagah kaam karega)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    input_path = os.path.join(script_dir, "articles.json")
    output_json_path = os.path.join(script_dir, "preprocessed_articles.json")
    output_csv_path = os.path.join(script_dir, "preprocessed_articles.csv")

    if not os.path.exists(input_path):
        print(f"ERROR: '{input_path}' nahi mili.")
        print("articles.json ko isi folder me rakhein jahan ye script hai:")
        print(f"   {script_dir}")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"Total articles loaded: {len(articles)}")

    processed = []
    for art in articles:
        title_result = preprocess_text(art.get("title", ""))
        para_result = preprocess_text(art.get("first_paragraph", ""))

        processed.append({
            "source": art.get("source", ""),
            "url": art.get("url", ""),
            "published_date_new_york": art.get("published_date_new_york", ""),
            "original_title": art.get("title", ""),
            "clean_title": title_result["clean_text"],
            "title_tokens": title_result["tokens"],
            "original_first_paragraph": art.get("first_paragraph", ""),
            "clean_first_paragraph": para_result["clean_text"],
            "first_paragraph_tokens": para_result["tokens"],
        })

    # Save as JSON
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    # Save as CSV (tokens joined with '|' for readability in Excel)
    with open(output_csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "source", "url", "published_date_new_york",
            "original_title", "clean_title",
            "original_first_paragraph", "clean_first_paragraph"
        ])
        for row in processed:
            writer.writerow([
                row["source"],
                row["url"],
                row["published_date_new_york"],
                row["original_title"],
                row["clean_title"],
                row["original_first_paragraph"],
                row["clean_first_paragraph"],
            ])

    print(f"Preprocessing complete.")
    print(f"JSON saved to: {output_json_path}")
    print(f"CSV saved to:  {output_csv_path}")

    # Quick sample preview
    print("\n--- Sample (first article) ---")
    print("Original title:", processed[0]["original_title"])
    print("Clean title:   ", processed[0]["clean_title"])
    print("Original para: ", processed[0]["original_first_paragraph"])
    print("Clean para:    ", processed[0]["clean_first_paragraph"])


if __name__ == "__main__":
    main()