# Root Dockerfile - builds the Rust backend
# For local Python development, use: uv pip install -e ".[dev]"

FROM rust:1.83-bookworm AS builder
WORKDIR /app
COPY lib/rust/genesis_rust_backend/Cargo.toml lib/rust/Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && cargo build --release && rm -rf src
COPY lib/rust/genesis_rust_backend/src ./src
RUN touch src/main.rs && cargo build --release

FROM gcr.io/distroless/cc-debian12
COPY --from=builder /app/target/release/genesis_rust_backend /genesis_rust_backend
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/genesis_rust_backend"]
