import os
import time
import json
import numpy as np
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
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

print("Fetching programs with embeddings...")
query = "SELECT * FROM programs WHERE length(embedding) > 0"
res = client.query(query)

if not res.result_rows:
    print("No programs with embeddings found.")
    exit()

print(f"Found {len(res.result_rows)} programs.")

programs = []


# Simple dict wrapper to mimic Program object behavior for attributes
class Program:
    def __init__(self, data, cols):
        for k, v in zip(cols, data):
            setattr(self, k, v)
        # Initialize clustering fields
        self.embedding_pca_2d = []
        self.embedding_pca_3d = []
        self.embedding_cluster_id = -1


for row in res.result_rows:
    programs.append(Program(row, res.column_names))

if len(programs) < 3:
    print("Not enough programs for clustering.")
    exit()

embeddings = [p.embedding for p in programs]
X = np.array(embeddings)

print("Computing PCA...")
pca_2d = PCA(n_components=2)
X_2d = pca_2d.fit_transform(X)

pca_3d = PCA(n_components=3)
X_3d = pca_3d.fit_transform(X)

print("Computing KMeans...")
kmeans = KMeans(n_clusters=min(4, len(X)), n_init=10)
labels = kmeans.fit_predict(X)

print("Updating database...")
updated_rows = []
for i, program in enumerate(programs):
    program.embedding_pca_2d = X_2d[i].tolist()
    program.embedding_pca_3d = X_3d[i].tolist()
    program.embedding_cluster_id = int(labels[i])
    program.timestamp = time.time()

    # Use existing strings for JSON fields, don't re-serialize
    updated_rows.append(
        [
            program.id,
            program.code,
            program.language,
            program.parent_id,
            program.archive_inspiration_ids,
            program.top_k_inspiration_ids,
            program.generation,
            program.timestamp,
            program.code_diff,
            program.combined_score,
            program.public_metrics,
            program.private_metrics,
            program.text_feedback,
            program.complexity,
            program.embedding,
            json.dumps(program.embedding_pca_2d),
            json.dumps(program.embedding_pca_3d),
            program.embedding_cluster_id,
            1 if program.correct else 0,
            program.children_count,
            program.metadata,
            program.island_idx if program.island_idx is not None else -1,
            program.migration_history,
            1 if program.in_archive else 0,
        ]
    )

client.insert(
    "programs",
    updated_rows,
    column_names=[
        "id",
        "code",
        "language",
        "parent_id",
        "archive_inspiration_ids",
        "top_k_inspiration_ids",
        "generation",
        "timestamp",
        "code_diff",
        "combined_score",
        "public_metrics",
        "private_metrics",
        "text_feedback",
        "complexity",
        "embedding",
        "embedding_pca_2d",
        "embedding_pca_3d",
        "embedding_cluster_id",
        "correct",
        "children_count",
        "metadata",
        "island_idx",
        "migration_history",
        "in_archive",
    ],
)
print(f"Updated {len(programs)} programs.")
