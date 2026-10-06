import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()


def get_client():
    url = os.getenv("CLICKHOUSE_URL")
    if url:
        import re

        match = re.match(r"https?://([^:]+):([^@]+)@([^:]+):(\d+)", url)
        if match:
            return clickhouse_connect.get_client(
                host=match.group(3),
                port=int(match.group(4)),
                username=match.group(1),
                password=match.group(2),
                secure=url.startswith("https"),
            )
    return clickhouse_connect.get_client(host="localhost")


client = get_client()

count = client.command("SELECT count() FROM programs WHERE length(embedding) = 0")
print(f"Programs missing embeddings: {count}")

if count > 0:
    print("Sample IDs:")
    res = client.query("SELECT id FROM programs WHERE length(embedding) = 0 LIMIT 5")
    for row in res.result_rows:
        print(row[0])
