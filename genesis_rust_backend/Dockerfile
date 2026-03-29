FROM rust:1.83-bookworm AS builder

WORKDIR /app

# Cache dependencies by building a dummy project first
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && cargo build --release && rm -rf src

# Build real application
COPY src ./src
RUN touch src/main.rs && cargo build --release

FROM gcr.io/distroless/cc-debian12

COPY --from=builder /app/target/release/genesis_rust_backend /genesis_rust_backend

ENV PORT=8080
EXPOSE 8080

ENTRYPOINT ["/genesis_rust_backend"]
