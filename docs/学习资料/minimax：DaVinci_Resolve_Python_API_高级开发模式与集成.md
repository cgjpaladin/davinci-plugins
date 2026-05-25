# DaVinci Resolve Python API — Advanced Development Patterns & Integration

This report builds upon foundational knowledge of the DaVinci Resolve Scripting API to address five critical areas of advanced plugin development: async architecture patterns, external API integration, Apple Silicon optimization, packaging for non-technical users, and testing strategies. The research prioritizes confirmed, working patterns sourced from active open-source projects and community documentation.

---

## 1. Real-World Plugin Architecture Patterns

### 1.1 Async API Call Patterns

Commercial Resolve plugins that interact with cloud APIs for operations like watermark removal, lip sync, voice cloning, or super-resolution face a fundamental architectural challenge: these operations take 5–10 minutes or longer, but blocking Resolve's UI during this time renders the plugin unusable. The most robust pattern identified in production code is the **lazy connection with background executor** approach, as implemented in the `davinci-resolve-mcp` server.

The lazy connection pattern separates concerns between the MCP server startup and Resolve connectivity. Rather than blocking during initialization to verify Resolve is running, the server starts immediately and establishes the Resolve connection only when the first API call arrives. This same principle extends to long-running cloud operations: the plugin should spawn a background task that communicates with the cloud service while the main thread returns control to Resolve immediately.

```python
import threading
import queue
from typing import Callable, Any, Optional

class CloudAPIClient:
    """Manages async cloud API calls without blocking Resolve UI."""
    
    def __init__(self, api_endpoint: str, api_key: str):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self._worker_thread: Optional[threading.Thread] = None
        self._task_queue: queue.Queue = queue.Queue()
        self._results: dict = {}
        self._running = False
    
    def submit_task(self, task_id: str, operation: Callable[[], Any]) -> str:
        """Submit a task for async execution. Returns immediately."""
        self._task_queue.put((task_id, operation))
        
        if not self._running or not self._worker_thread.is_alive():
            self._running = True
            self._worker_thread = threading.Thread(
                target=self._process_queue,
                daemon=True,
                name="CloudAPI-Worker"
            )
            self._worker_thread.start()
        
        return task_id
    
    def get_result(self, task_id: str, timeout: float = 0.1) -> Optional[Any]:
        """Non-blocking result check. Returns None if not ready."""
        return self._results.get(task_id, queue.Empty)
    
    def _process_queue(self):
        """Background worker that processes queued operations."""
        while self._running:
            try:
                task_id, operation = self._task_queue.get(timeout=1.0)
                try:
                    result = operation()
                    self._results[task_id] = {'status': 'complete', 'data': result}
                except Exception as e:
                    self._results[task_id] = {'status': 'error', 'error': str(e)}
                finally:
                    self._task_queue.task_done()
            except queue.Empty:
                continue
    
    def shutdown(self):
        """Graceful shutdown of worker thread."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
```

### 1.2 Threading Constraints in Resolve's Python Environment

Resolve's embedded Python environment has specific threading constraints:

- **GIL**: Python's GIL means CPU-bound operations cannot achieve true parallelism through threading. For I/O-bound cloud API calls, threading remains effective because the GIL is released during network waits.
- **Thread Safety**: All Resolve API calls should happen from a single dedicated thread. The recommended architecture is a **producer-consumer model** with a dispatch thread.

```python
class ResolveCloudBridge:
    """Bridge between Resolve API and cloud services."""
    
    def __init__(self):
        self._command_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue()
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop,
            daemon=True,
            name="Resolve-Dispatch"
        )
        self._running = False
    
    def submit(self, resolve_operation: Callable, cloud_operation: Callable, task_id: str):
        self._command_queue.put((task_id, resolve_operation, cloud_operation))
    
    def get_result(self, task_id: str, timeout: float = 0.1) -> dict:
        try:
            return self._result_queue.get_nowait()
        except queue.Empty:
            return None
    
    def _dispatch_loop(self):
        while self._running:
            try:
                task_id, resolve_op, cloud_op = self._command_queue.get(timeout=0.5)
                frame_data = resolve_op()
                cloud_result = cloud_op(frame_data)
                self._result_queue.put({
                    'task_id': task_id,
                    'status': 'complete',
                    'data': cloud_result
                })
            except Exception as e:
                self._result_queue.put({
                    'task_id': task_id,
                    'status': 'error',
                    'error': str(e)
                })
            except queue.Empty:
                continue
```

### 1.3 State Persistence Patterns

Three primary approaches:

1. **JSON files**: Simple config and session state. Recommended for plugin settings.
2. **SQLite**: Structured storage for complex relational data (processing jobs, results).
3. **PathMap-based storage**: Reactor's virtual path approach.

Hybrid approach recommended: JSON for config, SQLite for tracking processing jobs.

### 1.4 Key Open-Source Architecture References

- **davinci-resolve-mcp**: Most comprehensive. Lazy connection, helper function reduction, null guard discipline, stateless Fusion design.
- **Reactor package manager**: Package distribution and installation patterns.
- **pybmd**: Version compatibility layer, wrapping Resolve API for cross-version stability.

---

## 2. External API Integration: File Upload and Download Patterns

### 2.1 Streaming Upload from Resolve

No direct media pool → cloud piping without intermediate storage. Optimization strategies:

- **Render cache utilization**: Use cached render files instead of re-exporting. [UNVERIFIED]
- **Chunked upload with resume capability**: Prevents total retransmission on failure.

```python
class ChunkedUploader:
    def __init__(self, api_endpoint: str, chunk_size: int = 5 * 1024 * 1024):
        self.api_endpoint = api_endpoint
        self.chunk_size = chunk_size
    
    def upload_file(self, file_path: str, progress_callback=None) -> dict:
        self.initiate_upload(file_path)
        file_size = os.path.getsize(file_path)
        total_parts = (file_size + self.chunk_size - 1) // self.chunk_size
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            for part_num in range(total_parts):
                future = executor.submit(self.upload_chunk, file_path, part_num)
                futures.append((part_num, future))
            
            for part_num, future in futures:
                result = future.result()
                self._completed_parts.append(result)
                if progress_callback:
                    progress_callback(part_num + 1, total_parts)
        
        return self.complete_upload()
```

### 2.2 Progress Reporting

Three approaches:
1. **Console output with carriage return** (`\r`) — works in Resolve Script Console
2. **External logging file** — survives Script Console closure
3. **Fusion Text+ nodes** — visible in composition

### 2.3 Background Processing After Script Console Closes

**Critical limitation**: Python scripts terminate when Console closes. Workaround: **standalone wrapper process** that reads from a shared queue file.

```python
# Standalone processor (runs outside Resolve)
class BackgroundProcessor:
    def __init__(self, task_queue_file: str):
        self.queue_file = Path(task_queue_file)
    
    def watch_queue(self):
        while self.processing:
            if self.queue_file.exists():
                # Read tasks, process pending ones, update status
                tasks = json.loads(open(self.queue_file).read())
                # ... process and update ...
            time.sleep(5)
```

---

## 3. Apple Silicon (M4) Specific Optimization

### 3.1 Python Threading on M4

- **GIL bound** for CPU work, but I/O-bound cloud API calls benefit from threading
- **P-cores beneficial** for background network threads
- **Unified memory** eliminates CPU-GPU data copy penalty

### 3.2 Metal/MPS Acceleration

```python
import torch

def get_mps_device():
    if torch.backends.mps.is_available():
        return torch.device('mps')
    elif torch.cuda.is_available():
        return torch.device('cuda')
    return torch.device('cpu')
```

### 3.3 Memory Management on 16GB

- Resolve itself uses 6-10GB → plugin has 4-6GB available
- Implement **adaptive batch size** based on memory pressure
- Force `gc.collect()` between batches when memory > 75%

```python
def adaptive_batch_size(base_batch_size: int) -> int:
    status = get_memory_status()
    if status['percent_used'] > 85:
        return max(1, base_batch_size // 4)
    elif status['percent_used'] > 75:
        return base_batch_size // 2
    elif status['percent_used'] > 65:
        return int(base_batch_size * 0.75)
    return base_batch_size
```

### 3.4 Performance Benchmarks

- M1: 3x improvement over Intel Macs for Resolve native ops
- M1 Max: 5x faster 8K editing
- M4 Pro: Varying results vs M1 Max
- [UNVERIFIED] No published Resolve Python script benchmarks for M-series.

---

## 4. Packaging and Distribution for Non-Developer Users

### 4.1 One-Click Installation

**Reactor Package Manager** is the gold standard:
- User downloads `Reactor-Installer.lua` → drags into Fusion Console
- Browse and install packages with one click
- Create Reactor-compatible **Atom** packages for distribution

### 4.2 Dependency Management

Resolve's embedded Python has no `pip`. Solution: **vendoring** — bundle all dependencies in `lib/` directory:

```
YourPlugin/
└── lib/
    ├── requests/
    ├── urllib3/
    └── certifi/
```

```python
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
_lib_dir = os.path.join(_plugin_dir, 'lib')
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)
import requests  # Now works
```

**Alternative**: Use stdlib `urllib.request` to eliminate dependency complexity entirely.

### 4.3 Auto-Update

- **Startup version check**: Plugin checks for updates when Resolve launches
- **Reactor integration**: Built-in update mechanism for Reactor-distributed packages
- **External update service**: For commercial plugins with license management

### 4.4 Licensing

Patterns for commercial plugins:
- **Online activation**: License key validated against server
- **Offline activation**: Challenge-response with activation file
- **Subscription validation**: Periodic re-validation required

---

## 5. Unit Testing and CI for Resolve Scripts

### 5.1 Mocking Patterns

No standardized mock library exists. Use **interface-based design with dependency injection**:

```python
# production_code.py
def process_timeline(resolve_api, timeline, api_client):
    """Process a timeline with injected dependencies for testing."""
    project = resolve_api.GetProjectManager().GetCurrentProject()
    timeline_items = timeline.GetItemsInRange(0, timeline.GetDuration())
    # ...

# test_code.py
class TestProcessTimeline(unittest.TestCase):
    def setUp(self):
        self.mock_resolve = MagicMock()
        self.mock_project = MagicMock()
        self.mock_resolve.GetProjectManager.return_value.GetCurrentProject.return_value = self.mock_project
```

Create **test fixtures** that provide fully configured mock Resolve objects.

### 5.2 CI Strategies

- **GitHub Actions with self-hosted runner** (macOS + Resolve installed) for live API testing
- **Code quality CI**: flake8 + black + mypy for linting (runs anywhere)
- **Unit tests with mocks**: run on standard CI runners without Resolve

```yaml
# .github/workflows/quality.yml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install flake8 black mypy
      - run: flake8 src/ && black --check src/ && mypy src/
  
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pytest pytest-mock
      - run: pytest tests/unit/ -v
```

### 5.3 Integration Testing

- Linux Docker/Podman configurations exist but no true headless Resolve testing
- **Manual checklist**: Environment setup, script loading, API coverage, error paths, platform consistency
- **Sample project files (.drp)**: Pre-configured projects for testing different scenarios

### 5.4 Logging and Debugging

```python
def setup_logger(name: str, log_file: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    # File handler + console handler
    # Default log location: ~/Library/Application Support/Blackmagic Design/logs/
    return logger
```

---

## Summary of Key Gaps

| Gap | Severity |
|-----|----------|
| No documented async cloud API architecture for 5-10 min operations | 🔴 Critical |
| No subprocess persistence after Script Console closes | 🔴 Critical |
| No M4-specific Python script benchmarks | 🟡 Moderate |
| No headless Resolve CI testing infrastructure | 🟡 Moderate |
| No standardized mock library for Resolve API | 🟡 Moderate |

## Recommendations

1. **Architecture First**: Invest in standalone wrapper process architecture for background cloud processing
2. **Testing**: Build comprehensive mock fixtures + unit tests for CI; live Resolve testing for integration
3. **Memory**: Implement adaptive batch processing and memory monitoring from day one
4. **Dependencies**: Prefer stdlib `urllib` over vendored `requests` when possible
5. **Distribution**: Leverage Reactor ecosystem for installation, updates, and package management
