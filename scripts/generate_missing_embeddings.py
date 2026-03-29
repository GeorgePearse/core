import os
import time
import json
import logging
import clickhouse_connect
from dotenv import load_dotenv
from genesis.llm.embedding import EmbeddingClient

# Configure logging to see EmbeddingClient errors
logging.basicConfig(level=logging.INFO)

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

# Fetch programs missing embeddings
print("Fetching programs missing embeddings...")
# Exclude empty code
query = "SELECT id, code FROM programs WHERE length(embedding) = 0 AND length(code) > 0 LIMIT 1000"
res = client.query(query)

if not res.result_rows:
    print("No programs missing embeddings (with non-empty code).")
    exit()

print(f"Found {len(res.result_rows)} programs to process.")

# Initialize embedding client
# Use default model or from env
model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
print(f"Initializing EmbeddingClient with model: {model}")
embedder = EmbeddingClient(model_name=model)

# Process in batches
BATCH_SIZE = 20
total_updated = 0

rows = res.result_rows
for i in range(0, len(rows), BATCH_SIZE):
    batch = rows[i : i + BATCH_SIZE]
    ids = [row[0] for row in batch]
    codes = [row[1] for row in batch]

    print(f"Processing batch {i // BATCH_SIZE + 1} ({len(batch)} items)...")

    try:
        # Get embeddings
        embeddings, cost = embedder.get_embedding(codes)

        if not embeddings or len(embeddings) != len(ids):
            print(f"Error: Got {len(embeddings)} embeddings for {len(ids)} inputs.")
            continue

        # Update DB
        # Use ALTER TABLE UPDATE for each row (slow but safe)
        # or INSERT replacement.
        # Since we only want to update ONE column, ALTER TABLE is better here to avoid parsing full metadata again.
        # We can batch updates using a single query? No.

        # Actually, for 250 items, iterating ALTER TABLE is feasible.
        # But wait, clickhouse_connect allows parameterized execution?

        for pid, embed in zip(ids, embeddings):
            # ClickHouse Array(Float32) format: [1.0, 2.0, ...]
            # Python list is fine.

            client.command(
                "ALTER TABLE programs UPDATE embedding = {embed:Array(Float32)} WHERE id = {pid:String}",
                parameters={"embed": embed, "pid": pid},
            )

        total_updated += len(batch)
        print(f"Updated {len(batch)} programs. Total: {total_updated}")

        # Sleep slightly to avoid rate limits
        time.sleep(0.5)

    except Exception as e:
        print(f"Error processing batch: {e}")

print("Done. Now run compute_clusters.py to update visualizations.")
