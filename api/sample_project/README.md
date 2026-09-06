# ShopFlow E-Commerce API (Sample Project)

A lightweight FastAPI backend demonstrating REST API architecture, JWT authentication, and SQLite persistence.

## Architecture

- **Web Framework**: FastAPI
- **Database**: SQLite with SQLAlchemy ORM
- **Authentication**: OAuth2 Password Bearer with JWT (`auth.py`)
- **Password Hashing**: SHA-256 with salted key
- **Endpoints**:
  - `POST /api/v1/users/register`: Register new user
  - `POST /api/v1/users/login`: Authenticate and receive JWT (raises 401 if invalid credentials)
  - `GET /api/v1/users/me`: Current user profile (requires Bearer token)
  - `POST /api/v1/orders/`: Create new order (requires Bearer token)
  - `GET /api/v1/orders/`: List user orders (requires Bearer token)
