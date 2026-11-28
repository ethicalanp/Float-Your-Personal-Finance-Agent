import time
import tracemalloc

import pytest


@pytest.mark.real_embedder
@pytest.mark.slow
@pytest.mark.timeout(180)
def test_real_embedder_load_and_memory_benchmark() -> None:
    """Measure real multilingual-e5-base cold-load, query/passage latency, and peak memory."""
    from app.ai.rag.embedder.local import LocalEmbedder

    tracemalloc.start()
    t_init0 = time.perf_counter()
    embedder = LocalEmbedder()
    # Trigger lazy model load
    t_first0 = time.perf_counter()
    vec_q = embedder.embed_query("What is money and how do I report UPI fraud 1930?")
    t_first_ms = (time.perf_counter() - t_first0) * 1000.0
    t_init_ms = (time.perf_counter() - t_init0) * 1000.0

    assert len(vec_q) == 768

    warm_latencies_ms: list[float] = []
    queries = [
        "How do I file a complaint on cybercrime.gov.in?",
        "എന്റെ അക്കൗണ്ടിൽ നിന്ന് പണം നഷ്ടപ്പെട്ടു 1930 വിളിക്കണോ?",
        "UPI scam aayi 5000 poyi entha cheyyendathu?",
        "What is an emergency fund?",
        "How does EMI calculation work for a personal loan?",
    ]
    for q in queries:
        t0 = time.perf_counter()
        v = embedder.embed_query(q)
        warm_latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        assert len(v) == 768

    t_batch0 = time.perf_counter()
    passages = embedder.embed_passages([f"Passage {i}: RBI guidelines on UPI safety." for i in range(16)])
    t_batch_ms = (time.perf_counter() - t_batch0) * 1000.0
    assert len(passages) == 16

    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mb = peak_bytes / (1024 * 1024)
    warm_sorted = sorted(warm_latencies_ms)
    p50_ms = warm_sorted[len(warm_sorted) // 2]
    p95_ms = warm_sorted[-1]

    print(
        f"\n[REAL_EMBEDDER_BENCHMARK] init_plus_first_ms={t_init_ms:.1f} "
        f"first_query_ms={t_first_ms:.1f} warm_p50_ms={p50_ms:.1f} "
        f"warm_p95_ms={p95_ms:.1f} batch16_ms={t_batch_ms:.1f} peak_tracemalloc_mb={peak_mb:.2f}"
    )
    assert t_init_ms < 60_000.0
    assert p95_ms < 5_000.0
