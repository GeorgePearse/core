use sqlx::PgPool;
use testcontainers::runners::AsyncRunner;
use testcontainers::ContainerAsync;
use testcontainers::ImageExt;
use testcontainers_modules::postgres::Postgres;

pub struct TestDb {
    pub pool: PgPool,
    _container: ContainerAsync<Postgres>,
}

impl TestDb {
    pub async fn new() -> Self {
        let container = Postgres::default()
            .with_tag("15")
            .start()
            .await
            .expect("failed to start postgres container");

        let host_port = container
            .get_host_port_ipv4(5432)
            .await
            .expect("failed to get postgres port");

        let url = format!("postgresql://postgres:postgres@127.0.0.1:{host_port}/postgres");
        let pool = PgPool::connect(&url)
            .await
            .expect("failed to connect to test postgres");

        let ddl = std::fs::read_to_string(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../../migrations/full_ddl.sql"),
        )
        .expect("failed to read full_ddl.sql");

        sqlx::raw_sql(&ddl)
            .execute(&pool)
            .await
            .expect("failed to apply DDL");

        Self {
            pool,
            _container: container,
        }
    }
}
