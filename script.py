import requests
from bs4 import BeautifulSoup

# 1. ඉලක්කගත වෙබ් ලිපිනය සහ User-Agent header එක
URL = "https://quotes.toscrape.com/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 2. වෙබ් පිටුවට Request එකක් යවා HTML අන්තර්ගතය ලබා ගැනීම
response = requests.get(URL, headers=HEADERS)

if response.status_code == 200:
    # 3. HTML කේතය Parse කිරීම
    soup = BeautifulSoup(response.text, "html.parser")

    # 4. එක පිටුවක ඇති සියලුම quote blocks සොයා ගැනීම
    # <div class="quote">...</div> tags සියල්ලම list එකක් ලෙස ගනී
    quotes = soup.find_all("div", class_="quote")

    print(f"හමුවූ ප්‍රකාශන ගණන: {len(quotes)}\n" + "-" * 50)

    # 5. එක් එක් block එක තුළින් අවශ්‍ය දත්ත වෙන් කර ගැනීම
    for item in quotes:
        text = item.find("span", class_="text").get_text(strip=True)
        author = item.find("small", class_="author").get_text(strip=True)
        
        # Tags කිහිපයක් ඇති බැවින් ඒවා list එකක් ලෙස extract කිරීම
        tag_elements = item.find_all("a", class_="tag")
        tags = [tag.get_text(strip=True) for tag in tag_elements]

        # ප්‍රතිඵලය Console එකේ පෙන්වීම
        print(f"💬 ප්‍රකාශය: {text}")
        print(f"👤 කතුවරයා: {author}")
        print(f"🏷️ Tags: {', '.join(tags)}")
        print("-" * 50)
else:
    print(f"වෙබ් පිටුව ලබා ගැනීමට නොහැකි විය. Status code: {response.status_code}")