
<p align="center">
  <img src="https://repository-images.githubusercontent.com/1005227614/0c6f83ac-3ce5-4ee8-bcad-344c166ad5fb" alt="Notification App" />
</p>

# Notification App

[![Build Status](https://github.com/vakesz/notification_app/actions/workflows/ci.yml/badge.svg)](https://github.com/vakesz/notification_app/actions)
[![Coverage Status](https://coveralls.io/repos/github/vakesz/notification_app/badge.svg?branch=main)](https://coveralls.io/github/vakesz/notification_app?branch=main)

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

- Python 3.8 or higher
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
   BLOG_API_BASE_URL=https://your-blog-api-url.com
   BLOG_API_AUTH_METHOD=none

   # Web Push Configuration
   PUSH_VAPID_PUBLIC_KEY=your-vapid-public-key
   PUSH_VAPID_PRIVATE_KEY=your-vapid-private-key
   PUSH_CONTACT_EMAIL=your-contact-email@example.com

   # Application Settings
   APP_NAME=Blog Notifications Parser
   APP_DATABASE_PATH=db/posts.db
   POLLING_INTERVAL_MIN=15
   HTTP_TIMEOUT=30
   ```

5. **Database Setup**

   ```bash
   mkdir -p db
   # Database will be automatically initialized on first run
   ```

### Docker Deployment

1. **Build the Docker image**

   ```bash
   docker build -t notification-app .
   ```

2. **Run with Docker Compose** (create docker-compose.yml)

   ```yaml
   version: '3.8'
   services:
     app:
       build: .
       ports:
         - "5000:5000"
       environment:
         - SECRET_KEY=your-secret-key
         - AAD_CLIENT_ID=your-client-id
         # ... other environment variables
       volumes:
         - ./db:/app/db
   ```

3. **Start the application**

   ```bash
   docker-compose up -d
   ```

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
gunicorn -w 4 -b 0.0.0.0:5000 app.web.main:create_app()
```

### Accessing the Application

1. Navigate to `http://localhost:5000`
2. Click "Login with Microsoft" to authenticate
3. Configure your notification preferences in the dashboard
4. Enable push notifications when prompted by your browser

### API Endpoints

The application provides several API endpoints:

- `POST /subscribe` - Subscribe to push notifications
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

- **Bug Reports**: [GitHub Issues](https://github.com/vakesz/notification_app/issues)

Built with ❤️ for efficient company communication.
