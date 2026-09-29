import os
from dotenv import load_dotenv
load_dotenv()
import re
import sys
from tinyfish import TinyFish

client = TinyFish(api_key=os.getenv("TINYFISH_API_KEY", ""))

def fetch_url(url):

    try:
        result = client.fetch.get_contents(urls=[url])
        if result.results:
            print(result.results[0].title)
            print(result.results[0].text)
        else:
            print("No content found.")
    except Exception as e:
        print(f"Error: {e}")

if len(sys.argv) != 2:
    print("Usage: python scrape_site.py <url>")
else:
    fetch_url(sys.argv[1])