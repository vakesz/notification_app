![Notification App](https://repository-images.githubusercontent.com/1005227614/0c6f83ac-3ce5-4ee8-bcad-344c166ad5fb)

# Notification App

[![Build Status](https://github.com/vakesz/notification_app/actions/workflows/ci.yml/badge.svg)](https://github.com/vakesz/notification_app/actions)
[![Docker Image](https://github.com/vakesz/notification_app/actions/workflows/release-docker.yml/badge.svg)](https://github.com/vakesz/notification_app/actions/workflows/release-docker.yml)
[![GitHub Pages](https://github.com/vakesz/notification_app/actions/workflows/static.yml/badge.svg)](https://vakesz.github.io/notification_app/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A real-time web application for monitoring blog posts with intelligent notifications, Azure AD authentication, and web push support.

## Description

This Flask-based application automatically monitors blog content and delivers personalized notifications to users. It features Microsoft Azure AD single sign-on authentication, customizable notification filters, and web push notifications for real-time updates.

### Key Features

- **Real-time Blog Monitoring**: Automatically polls blog APIs and parses new posts
- **Azure AD Authentication**: Secure single sign-on with Microsoft accounts
- **Intelligent Filtering**: Location-based and keyword-based notification filters
- **Web Push Notifications**: Cross-platform push notifications with VAPID support
- **User Dashboard**: Comprehensive interface for managing settings and viewing notifications
- **Multi-language Support**: English, Hungarian, and Swedish language options
- **Responsive Design**: Mobile-friendly web interface
- **Export Functionality**: Export posts and notifications to JSON format
- **Session Management**: Secure session handling with token validation

## Installation Instructions

### Prerequisites

- Python 3.10 or higher
- Azure AD application registration
- VAPID keys for web push notifications

### Local Development Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/vakesz/notification_app.git
   cd notification_app
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -e .
   ```

4. **Environment Configuration**

   Create a `.env` file in the project root:

   ```env
   # Flask Configuration
   SECRET_KEY=your-secret-key-here
   FLASK_ENV=development

   # Azure AD Configuration
   AAD_CLIENT_ID=your-azure-ad-client-id
   AAD_CLIENT_SECRET=your-azure-ad-client-secret
   AAD_TENANT_ID=your-azure-ad-tenant-id
   AAD_REDIRECT_URI=http://localhost:5000/auth/callback

   # Blog API Configuration
   BLOG_API_URL=https://your-blog-api-url.com
   BLOG_API_AUTH_METHOD=none

   # Optional Blog API Authentication (choose one if needed)
   # For OAuth2:
   # BLOG_API_OAUTH2_CLIENT_ID=your-oauth2-client-id
   # BLOG_API_OAUTH2_CLIENT_SECRET=your-oauth2-client-secret
   # BLOG_API_OAUTH2_TOKEN_URL=https://your-oauth2-token-url.com

   # For MSAL:
   # BLOG_API_MSAL_CLIENT_ID=your-msal-client-id
   # BLOG_API_MSAL_CLIENT_SECRET=your-msal-client-secret
   # BLOG_API_MSAL_TENANT_ID=your-msal-tenant-id
   # BLOG_API_MSAL_SCOPE=your-msal-scope

   # For NTLM:
   # BLOG_API_NTLM_USER=your-ntlm-user
   # BLOG_API_NTLM_PASSWORD=your-ntlm-password
   # BLOG_API_NTLM_DOMAIN=your-ntlm-domain

   # Web Push Configuration
   PUSH_VAPID_PUBLIC_KEY=your-vapid-public-key
   PUSH_VAPID_PRIVATE_KEY=your-vapid-private-key
   PUSH_CONTACT_EMAIL=your-contact-email@example.com

   # Application Settings
   APP_NAME=Blog Notifications Parser
   APP_DATABASE_PATH=db/posts.db
   POLLING_INTERVAL_MINUTES=15
   HTTP_TIMEOUT=30

   # Optional Advanced Settings
   # HTTP_MAX_RETRIES=3
   # HTTP_RETRY_BACKOFF=1
   # POLLING_BACKOFF_FACTOR=1.5
   # POLLING_MAX_BACKOFF=3600
   # AUTH_TOKEN_TTL_DAYS=30
   # PUSH_TTL=86400
   ```

5. **Database Setup**

   ```bash
   mkdir -p db
   # Database will be automatically initialized on first run
   ```

### Docker Deployment

#### Run with Docker

```bash
# Pull the latest image
docker pull ghcr.io/vakesz/notification_app:latest

# Run with environment variables
docker run -d \
  --name notification-app \
  -p 5000:5000 \
  -e SECRET_KEY=your-secret-key \
  -e AAD_CLIENT_ID=your-azure-ad-client-id \
  -e AAD_CLIENT_SECRET=your-azure-ad-client-secret \
  -e AAD_TENANT_ID=your-azure-ad-tenant-id \
  -e BLOG_API_URL=https://your-blog-api-url.com \
  -e PUSH_VAPID_PUBLIC_KEY=your-vapid-public-key \
  -e PUSH_VAPID_PRIVATE_KEY=your-vapid-private-key \
  -e PUSH_CONTACT_EMAIL=your-contact-email@example.com \
  -v notification-db:/app/db \
  ghcr.io/vakesz/notification_app:latest
```

#### Run with Docker Compose

   ```yaml
   version: '3.8'
   services:
     app:
       image: ghcr.io/vakesz/notification_app:latest
       ports:
         - "5000:5000"
       environment:
         - SECRET_KEY=your-secret-key
         - AAD_CLIENT_ID=your-client-id
         - AAD_CLIENT_SECRET=your-azure-ad-client-secret
         - AAD_TENANT_ID=your-tenant-id
         - AAD_REDIRECT_URI=http://localhost:5000/auth/callback
         - BLOG_API_URL=https://your-blog-api-url.com
         - PUSH_VAPID_PUBLIC_KEY=your-vapid-public-key
         - PUSH_VAPID_PRIVATE_KEY=your-vapid-private-key
         - PUSH_CONTACT_EMAIL=your-contact-email@example.com
       volumes:
         - notification-db:/app/db
   volumes:
     notification-db:
   ```

**Note:** The Docker image uses multi-architecture support (amd64/arm64) and runs with `gunicorn -w 4 -b 0.0.0.0:5000 "app.web.main:create_app()"` to properly initialize the Flask application factory.

## Usage Instructions

### Starting the Application

**Development Mode:**

```bash
export FLASK_APP=app.web.main
export FLASK_ENV=development
flask run
```

**Production Mode:**

```bash
gunicorn -w 4 -b 0.0.0.0:5000 "app.web.main:create_app()"
```

### Accessing the Application

1. Navigate to `http://localhost:5000`
2. Click "Login with Microsoft" to authenticate
3. Configure your notification preferences in the dashboard
4. Enable push notifications when prompted by your browser

### API Endpoints

The application provides several API endpoints:

- `POST /api/subscriptions` - Subscribe to push notifications
- `DELETE /api/subscriptions` - Unsubscribe from push notifications
- `GET /api/notifications/status` - Get notification summary
- `POST /api/notifications/mark-read` - Mark notifications as read
- `POST /api/notifications/settings` - Update notification settings
- `GET /api/session/validate` - Validate current session

### Configuration Options

**Notification Settings:**

Users can customize their notification preferences through the dashboard:

- **Language**: Choose from English, Hungarian, or Swedish
- **Location Filter**: Filter notifications by specific locations
- **Keyword Filter**: Filter notifications by custom keywords
- **Push Notifications**: Enable/disable web push notifications

**Blog API Authentication:**

The application supports multiple authentication methods:

- OAuth2 client credentials
- Microsoft MSAL authentication
- NTLM authentication
- No authentication (public APIs)

## Architecture Overview

```text
├── app/
│   ├── api/routes/          # Flask blueprints and routes
│   ├── core/               # Core configuration and security
│   ├── db/                 # Database models and management
│   ├── services/           # Business logic services
│   ├── utils/              # Utility functions
│   └── web/                # Web application entry point
├── static/                 # Frontend assets
├── templates/              # Jinja2 templates
└── db/                     # SQLite database files
```

### Key Components

- **AuthService**: Handles Azure AD authentication and token management
- **PollingService**: Monitors blog APIs for new content
- **NotificationService**: Manages user notifications and web push
- **DatabaseManager**: Handles all database operations
- **ContentParser**: Parses HTML content from blog APIs

## Development

### Development Dependencies

The project includes comprehensive development tools configured in `pyproject.toml`:

- **pytest**: Testing framework with coverage reporting
- **black**: Automatic code formatting
- **isort**: Import statement organization
- **flake8**: Code style and quality linting

All development dependencies are automatically installed with:

```bash
pip install -e .[dev]
```

### Running Tests and Quality Checks

```bash
# Install development dependencies
pip install -e .[dev]

# Run tests
pytest

# Run with coverage
pytest --cov=app --maxfail=1 --disable-warnings -q
```

### Code Quality

The project uses automated code quality tools that are also run in CI:

```bash
# Format code
black app/

# Check formatting
black --check .

# Sort imports
isort app/

# Check import sorting
isort --check-only .

# Lint code
flake8 app
```

### Continuous Integration

This project uses GitHub Actions for automated testing and code quality checks. The CI pipeline:

- **Multi-Python Testing**: Tests against Python 3.10, 3.11, and 3.12
- **Code Formatting**: Validates code formatting with Black
- **Import Sorting**: Ensures consistent import organization with isort
- **Linting**: Code quality checks with Flake8
- **Test Coverage**: Automated test execution with coverage reporting

The CI workflow runs on every push to main and on pull requests, ensuring code quality and compatibility across Python versions.

## 🤝 Contribution Guidelines

Contributions are welcome. Open an issue or create a pull request.

### Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes following the coding standards below
4. Write tests for new functionality
5. Submit a pull request with a clear description

### Coding Standards

- **Python Code**: Follow PEP 8 style guidelines
- **Type Hints**: Use type annotations for all functions
- **Documentation**: Include docstrings for all classes and functions
- **Logging**: Use the logging module instead of print statements
- **Error Handling**: Implement comprehensive error handling

### Reporting Issues

- Use the GitHub issue tracker
- Include detailed reproduction steps
- Provide environment information (Python version, OS, etc.)
- Include relevant log files when possible

## License Information

This project is licensed under the MIT License.

### Third-Party Dependencies

This project uses several open-source libraries:

- Flask (BSD-3-Clause)
- MSAL (MIT)
- pywebpush (MIT)
- APScheduler (MIT)
- Beautiful Soup (MIT)

See `pyproject.toml` for a complete list of dependencies.

### Support

- **Question**: Use [Discussions](https://github.com/vakesz/notification_app/discussions)
- **Bug Reports**: [GitHub Issues](https://github.com/vakesz/notification_app/issues)
- **Security Issues** (Confidential): Use the [Security Policy](https://github.com/vakesz/notification_app/blob/main/SECURITY.md)

Built with ❤️ for efficient company communication.
