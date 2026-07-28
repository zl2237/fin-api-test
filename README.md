# Fin API Test

> A powerful financial API automation testing framework built with Python and pytest.

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![pytest](https://img.shields.io/badge/pytest-9.0-green.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

A comprehensive API testing framework designed for financial systems, featuring multi-environment support, database verification, YAML-based test data management, and beautiful HTML reports.

---

## Features

- **Multi-Environment Support** - Seamlessly switch between test/pre-production environments
- **Auto Token Refresh** - Automatic re-authentication on 401 responses
- **Database Verification** - Direct MySQL queries to validate API results
- **YAML Test Data** - Environment-specific test data management
- **Page Object Pattern** - Clean layered architecture (API → Step → Test)
- **30+ Custom Assertions** - Flexible validation methods
- **Beautiful Reports** - Self-contained pytest-html reports
- **Enterprise Notifications** - WeChat Work webhook alerts

---

## Quick Start

### Requirements

- Python 3.8+
- MySQL 5.7+
- pip

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd fin-api-test

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp config/env_demo.yaml config/env_test.yaml
# Edit config/env_test.yaml with your settings
```

### Run Tests

```bash
# Run all tests with HTML report
python run.py

# Or use pytest directly
pytest --html=reports/report.html --self-contained-html

# Run specific test markers
pytest -m create
pytest -m submit
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Test Cases                            │
│                    (testcases/order/*.py)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Business Steps                           │
│                     (steps/order/*.py)                       │
│           create_order() → distribute() → stash()            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                              │
│                     (api/order/*.py)                         │
│              orderAdd_api.py, file_api.py                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     HTTP Client                               │
│                   (utils/http_client.py)                      │
│            Auto token refresh · Retry logic                   │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────────┐
│       External API      │     │        MySQL Database       │
│    (Financial System)   │     │     (Result Verification)   │
└─────────────────────────┘     └─────────────────────────────┘
```

### Layer Responsibilities

| Layer | Path | Purpose |
|-------|------|---------|
| **Test** | `testcases/` | Test execution, assertions, pytest markers |
| **Step** | `steps/` | Business workflow orchestration |
| **API** | `api/` | HTTP request封装，接口调用 |
| **DB** | `db/` | Database operations, data verification |
| **Utils** | `utils/` | Shared utilities (logging, assertions, generators) |

---

## Project Structure

```
fin-api-test/
├── api/                          # API layer
│   ├── base_api.py              # Base class for all APIs
│   ├── auth_api.py              # Authentication (login/logout)
│   ├── file_api.py              # File upload/download
│   └── order/
│       └── orderAdd_api.py      # Order operations
├── db/                           # Database layer
│   ├── base_db.py               # Base class for DB operations
│   ├── db_client.py             # MySQL client (connection pool)
│   └── biz/
│       └── order_db.py          # Order data queries
├── utils/                        # Utilities
│   ├── http_client.py           # HTTP client with retry
│   ├── api_factory.py           # API lazy loading factory
│   ├── db_factory.py            # DB lazy loading factory
│   ├── yaml_util.py             # YAML read/write
│   ├── log_util.py              # Logging (file + console)
│   ├── assert_util.py           # 30+ assertion methods
│   ├── generator_util.py        # Test data generators
│   ├── common_util.py          # Path helpers
│   └── wecom_util.py            # WeChat Work notifications
├── steps/                        # Business workflows
│   ├── file_step.py             # File upload workflow
│   └── order/
│       └── orderAdd_step.py     # Order workflow steps
├── testcases/                   # Test cases
│   └── order/
│       └── test_orderAdd.py     # Order API tests
├── data/                         # Test data (YAML)
│   └── test/                    # Environment-specific
│       ├── auth/auth_data.yaml  # Login credentials
│       └── order/               # Order test data
├── config/                       # Configuration
│   └── env_*.yaml              # Environment configs
├── conftest.py                  # Pytest fixtures
├── run.py                        # Entry point
└── pytest.ini                   # Pytest configuration
```

---

## Usage

### 1. Environment Configuration

Create `config/env_test.yaml`:

```yaml
env: test
base_url: "https://api.test.example.com"
mysql:
  host: "localhost"
  port: 3306
  user: "test_user"
  password: "your_password"
  database: "fin_db"
wecom:
  webhook_url: "https://qyapi.weixin.qq.com/..."
```

### 2. Test Data (YAML)

```yaml
# data/test/order/create.yaml
order_no: "AUTO_{timestamp}"
amount: 10000
currency: "CNY"
products:
  - name: "Product A"
    quantity: 1
    price: 5000
```

### 3. Write Test Cases

```python
import pytest
from steps.order.orderAdd_step import OrderAddStep

class TestOrderAdd:
    """Order API Test Suite"""

    @pytest.mark.create
    def test_create_order(self, order_step):
        """Create a new order"""
        result = order_step.create_order(
            amount=10000,
            currency="CNY"
        )
        assert result.code == 200
        assert result.data.order_no is not None

    @pytest.mark.submit
    def test_submit_order(self, order_step, order_data):
        """Submit an existing order"""
        order_step.create_order()
        order_step.distribute()
        order_step.stash()
        result = order_step.submit()
        assert result.code == 200
```

### 4. Run Specific Tests

```bash
# By marker
pytest -m create          # Only create tests
pytest -m "create and not submit"  # Create but not submit

# By file
pytest testcases/order/test_orderAdd.py

# With report
pytest --html=reports.html --self-contained-html -v
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TEST_ENV` | Environment name | `test` |
| `RETRY_COUNT` | HTTP retry attempts | `3` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Pytest Markers

| Marker | Description |
|--------|-------------|
| `@pytest.mark.create` | Order creation tests |
| `@pytest.mark.distribute` | Order distribution tests |
| `@pytest.mark.stash` | Order stash tests |
| `@pytest.mark.submit` | Order submission tests |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Test Framework | [pytest](https://pytest.org/) 9.0.3 |
| HTTP Client | [requests](https://docs.python-requests.org/) 2.33.0 |
| Database | [PyMySQL](https://pymysql.readthedocs.io/) 1.1.1 |
| Data Format | [PyYAML](https://pyyaml.org/) 6.0.1 |
| Reports | [pytest-html](https://pytest-html.readthedocs.io/) 4.0.2 |

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
