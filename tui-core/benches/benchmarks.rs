//! Standalone Performance Benchmark Harness
//! Can be executed via: cargo bench OR cargo run --bench benchmarks

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tui_core::benchmarks::run_full_benchmark_suite().await?;
    Ok(())
}
