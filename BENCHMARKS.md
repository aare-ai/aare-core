# aare-core Benchmarks

Performance benchmarks for aare-core verification engine.

## Latest Results

**Date**: 2025-12-05
**Hardware**: Apple M4 (10 cores: 4 performance + 6 efficiency)
**aare-core version**: latest

### HIPAA Ontology (76 constraints)

| Metric | Value |
|--------|-------|
| **Throughput** | 31.2 req/s |
| **p50 Latency** | 31.92 ms |
| **p95 Latency** | 32.70 ms |
| **p99 Latency** | 32.89 ms |
| **Min Latency** | 31.44 ms |
| **Max Latency** | 36.22 ms |
| **Memory Peak** | 0.4 MB |

### Single-Threaded (Small Ontology)

| Metric | Value |
|--------|-------|
| **Throughput** | 312.9 req/s |
| **p50 Latency** | 3.70 ms |
| **p95 Latency** | 3.95 ms |
| **p99 Latency** | 6.91 ms |
| **Min Latency** | 1.72 ms |
| **Max Latency** | 6.91 ms |
| **Memory Peak** | 0.1 MB |

## Full Test Output

```
$ python3 tests/stress_test.py --skip-multiprocess --requests 100 --hipaa-requests 500

============================================================
       aare-core STRESS TEST
============================================================
Configuration:
  Requests:         100
  Workers:          4
  HIPAA Requests:   500

============================================================
SINGLE-THREADED TEST: 100 requests
============================================================
Warming up...

--- Single-Threaded Results ---
Total Requests:     100
Completed:          100
Errors:             0
Total Time:         0.32s
Throughput:         312.9 req/sec

Latency (ms):
  Average:          3.19
  p50 (median):     3.70
  p95:              3.95
  p99:              6.91
  Min:              1.72
  Max:              6.91

Memory Peak:        0.1 MB

============================================================
HIPAA ONTOLOGY TEST: 500 requests (76 constraints)
============================================================
  Completed 100/500...
  Completed 200/500...
  Completed 300/500...
  Completed 400/500...
  Completed 500/500...

--- HIPAA (76 constraints) Results ---
Total Requests:     500
Completed:          500
Errors:             0
Total Time:         16.03s
Throughput:         31.2 req/sec

Latency (ms):
  Average:          32.05
  p50 (median):     31.92
  p95:              32.70
  p99:              32.89
  Min:              31.44
  Max:              36.22

Memory Peak:        0.4 MB

============================================================
                    SUMMARY
============================================================
Test                           Throughput           p99 Latency
------------------------------------------------------------
Single-threaded                     312.9 req/s        6.91 ms
HIPAA (76 constraints)               31.2 req/s       32.89 ms
============================================================
```

## Key Takeaways

- **HIPAA p99 latency: 32.89ms** - well under 50ms target for real-time verification
- **76 constraints** verified per request with consistent latency
- **0 errors** across 500 HIPAA verifications
- **0.4 MB memory** peak usage - lightweight footprint

## Running Benchmarks

Run the stress test yourself:

```bash
# Install aare-core
pip install aare-core

# Clone the repo for tests
git clone https://github.com/aare-ai/aare-core.git
cd aare-core

# Run basic benchmark
python tests/stress_test.py --requests 100

# Run HIPAA benchmark
python tests/stress_test.py --skip-multiprocess --hipaa-requests 500

# Full benchmark suite with multi-process
python tests/stress_test.py --requests 5000 --workers 4 --hipaa-requests 500
```

## Scaling Notes

- Z3 SMT solver is not thread-safe, so multi-process scaling is used for concurrent workloads
- Multi-process mode achieves near-linear scaling (4 workers ≈ 4x throughput)
- Memory usage scales linearly with constraint count
- Constraint complexity (nesting depth) has minimal impact on latency
