# Requirements Document: React Dashboard Migration

## Introduction

This document outlines the requirements for migrating the existing Python/FastAPI-based dashboard to a modern React.js frontend application. The current system uses Jinja2 templates served by FastAPI for all dashboard functionality. The goal is to create a decoupled, modern React frontend that consumes the existing REST API while maintaining all current functionality and improving user experience.

## Glossary

- **Dashboard**: The web-based user interface for monitoring and controlling scraper operations
- **FastAPI Backend**: The Python-based REST API server that handles scraper operations and data management
- **React Frontend**: The new JavaScript-based single-page application (SPA) that will replace Jinja2 templates
- **Scraper**: An automated data collection service (e.g., MacMap Tariff, Eximpedia, IndiaMART)
- **Task Creator**: A background process that generates scraping tasks and queues them for execution
- **Celery Worker**: A distributed task queue worker that executes scraping tasks
- **WebSocket**: Real-time bidirectional communication protocol for live updates
- **SSE (Server-Sent Events)**: One-way real-time communication from server to client
- **Task Queue**: Redis-backed queue system for managing scraping tasks
- **Payload**: Configuration data for generating scraping tasks

## Requirements

### Requirement 1: API Backend Preservation

**User Story:** As a system architect, I want to preserve the existing FastAPI backend without modifications, so that the migration is low-risk and the API remains stable.

#### Acceptance Criteria

1. WHEN the React frontend is deployed, THE FastAPI backend SHALL continue to operate without code changes
2. WHEN API endpoints are called, THE system SHALL return the same response format as before migration
3. WHEN the backend serves the React app, THE system SHALL use FastAPI's static file serving capabilities
4. THE FastAPI backend SHALL remove Jinja2 template dependencies after migration is complete
5. THE system SHALL maintain all existing API endpoints at their current paths under `/api/v1/`

### Requirement 2: Dashboard Feature Parity

**User Story:** As a scraper operator, I want all current dashboard features available in the React version, so that I don't lose any functionality during migration.

#### Acceptance Criteria

1. WHEN accessing the home dashboard, THE system SHALL display real-time statistics for all scrapers
2. WHEN viewing task management, THE system SHALL show task creators with start/stop controls and task limits
3. WHEN monitoring workers, THE system SHALL display Celery worker status, queues, and assignments
4. WHEN checking system health, THE system SHALL show CPU, memory, disk usage, and service status
5. WHEN viewing logs, THE system SHALL stream real-time logs with filtering capabilities
6. WHEN managing payloads, THE system SHALL provide forms for all 10 payload types with validation
7. WHEN viewing task queues, THE system SHALL display pending, running, completed, and failed tasks
8. WHEN accessing data sources, THE system SHALL show all configured scrapers with their databases

### Requirement 3: Real-Time Data Updates

**User Story:** As a scraper operator, I want to see live updates without refreshing the page, so that I can monitor operations in real-time.

#### Acceptance Criteria

1. WHEN dashboard is open, THE system SHALL update statistics every 5 seconds via SSE or WebSocket
2. WHEN tasks are running, THE system SHALL stream progress updates to the dashboard
3. WHEN logs are generated, THE system SHALL push new log entries to the logs view in real-time
4. WHEN worker status changes, THE system SHALL immediately reflect the change in the UI
5. WHEN connection is lost, THE system SHALL display a reconnection indicator and attempt to reconnect

### Requirement 4: Modern UI/UX Design

**User Story:** As a user, I want a modern, responsive interface, so that I can efficiently manage scrapers from any device.

#### Acceptance Criteria

1. WHEN accessing from mobile devices, THE system SHALL display a responsive layout optimized for small screens
2. WHEN viewing data tables, THE system SHALL provide sorting, filtering, and pagination
3. WHEN performing actions, THE system SHALL show loading states and success/error feedback
4. WHEN navigating, THE system SHALL use client-side routing without full page reloads
5. THE system SHALL follow modern design principles with consistent spacing, typography, and color scheme

### Requirement 5: Scraper Control Interface

**User Story:** As a scraper operator, I want to control individual scrapers and task creators, so that I can manage data collection operations.

#### Acceptance Criteria

1. WHEN starting a task creator, THE system SHALL send a POST request and display confirmation
2. WHEN stopping a task creator, THE system SHALL pause all pending tasks and stop the process
3. WHEN adjusting task limits, THE system SHALL update the maximum concurrent tasks for that scraper
4. WHEN viewing scraper status, THE system SHALL show running/stopped state with process IDs
5. WHEN errors occur, THE system SHALL display detailed error messages with retry options

### Requirement 6: Payload Generation Interface

**User Story:** As a data analyst, I want to generate payloads for different scrapers, so that I can create scraping tasks with specific parameters.

#### Acceptance Criteria

1. WHEN selecting a payload type, THE system SHALL display the appropriate form fields for that type
2. WHEN entering HS codes, THE system SHALL validate the format (6 digits for most types)
3. WHEN entering countries, THE system SHALL provide autocomplete from the available country list
4. WHEN submitting a payload, THE system SHALL validate all required fields before submission
5. WHEN generation completes, THE system SHALL display the number of tasks created
6. THE system SHALL support all 10 payload types: MacMap Tariff, Trade Remedies, Regulatory, Compare Market, Competitors, Products, Full Tariff, Indian Trade Portal, TradeMap, Eximpedia

### Requirement 7: Task Queue Management

**User Story:** As a scraper operator, I want to view and manage the task queue, so that I can monitor progress and handle failures.

#### Acceptance Criteria

1. WHEN viewing the task queue, THE system SHALL display tasks grouped by status (pending, running, success, failed)
2. WHEN filtering tasks, THE system SHALL allow filtering by scraper type, status, and date range
3. WHEN selecting a task, THE system SHALL display detailed information including parameters and logs
4. WHEN canceling a task, THE system SHALL revoke the Celery task and update the database
5. WHEN retrying a failed task, THE system SHALL requeue the task with the same parameters

### Requirement 8: Worker Management Interface

**User Story:** As a system administrator, I want to manage Celery workers, so that I can optimize resource allocation.

#### Acceptance Criteria

1. WHEN viewing workers, THE system SHALL display all active workers with their queues and concurrency
2. WHEN starting a worker, THE system SHALL launch a new Celery worker process with specified configuration
3. WHEN stopping a worker, THE system SHALL gracefully terminate the worker process
4. WHEN assigning scrapers, THE system SHALL update queue routing to direct tasks to specific workers
5. WHEN viewing worker stats, THE system SHALL show tasks processed, success rate, and resource usage

### Requirement 9: System Health Monitoring

**User Story:** As a system administrator, I want to monitor system health, so that I can identify and resolve issues proactively.

#### Acceptance Criteria

1. WHEN viewing health dashboard, THE system SHALL display CPU, memory, and disk usage metrics
2. WHEN checking service status, THE system SHALL show Redis, Celery, and database connectivity
3. WHEN viewing historical data, THE system SHALL display charts for resource usage over time
4. WHEN thresholds are exceeded, THE system SHALL highlight warnings in the UI
5. WHEN services are down, THE system SHALL display clear error indicators

### Requirement 10: Log Viewing and Filtering

**User Story:** As a developer, I want to view and filter logs, so that I can debug issues and monitor scraper behavior.

#### Acceptance Criteria

1. WHEN viewing logs, THE system SHALL stream logs in real-time from all scrapers
2. WHEN filtering logs, THE system SHALL allow filtering by scraper type, log level, and time range
3. WHEN searching logs, THE system SHALL highlight matching text in the log entries
4. WHEN viewing task logs, THE system SHALL display logs specific to a single task ID
5. WHEN downloading logs, THE system SHALL export filtered logs to a text file

### Requirement 11: Authentication and Security

**User Story:** As a system administrator, I want to secure the dashboard, so that only authorized users can access scraper controls.

#### Acceptance Criteria

1. WHERE authentication is enabled, WHEN accessing the dashboard, THE system SHALL require authentication
2. WHEN making API calls, THE system SHALL include authentication tokens in requests
3. WHEN sessions expire, THE system SHALL redirect to login and preserve the intended destination
4. THE system SHALL implement CORS policies to prevent unauthorized access
5. THE system SHALL use HTTPS in production environments

### Requirement 12: Code Organization and Maintainability

**User Story:** As a developer, I want well-organized code, so that the application is easy to maintain and extend.

#### Acceptance Criteria

1. THE React application SHALL use a component-based architecture with reusable components
2. THE system SHALL separate concerns using containers, components, services, and utilities
3. THE system SHALL use TypeScript for type safety and better developer experience
4. THE system SHALL include comprehensive documentation for components and API integration
5. THE system SHALL follow React best practices including hooks, context, and proper state management

### Requirement 13: Build and Deployment

**User Story:** As a DevOps engineer, I want automated build and deployment, so that releases are consistent and reliable.

#### Acceptance Criteria

1. WHEN building for production, THE system SHALL create optimized, minified bundles
2. WHEN deploying, THE system SHALL serve the React app from FastAPI's static file handler
3. WHEN updating, THE system SHALL support zero-downtime deployments
4. THE build process SHALL include linting, type checking, and testing
5. THE system SHALL provide environment-specific configuration (development, staging, production)

### Requirement 14: Performance Optimization

**User Story:** As a user, I want fast page loads and smooth interactions, so that I can work efficiently.

#### Acceptance Criteria

1. WHEN loading the dashboard, THE initial page SHALL load in under 2 seconds
2. WHEN switching views, THE system SHALL use code splitting to load only required components
3. WHEN displaying large datasets, THE system SHALL use virtualization for tables and lists
4. WHEN making API calls, THE system SHALL implement caching for frequently accessed data
5. WHEN updating data, THE system SHALL use optimistic updates for better perceived performance

### Requirement 15: Error Handling and Recovery

**User Story:** As a user, I want clear error messages and recovery options, so that I can resolve issues without technical support.

#### Acceptance Criteria

1. WHEN API calls fail, THE system SHALL display user-friendly error messages
2. WHEN network errors occur, THE system SHALL provide retry options
3. WHEN validation fails, THE system SHALL highlight specific fields with error messages
4. WHEN unexpected errors occur, THE system SHALL log details and show a generic error message
5. WHEN recovering from errors, THE system SHALL restore the previous valid state

### Requirement 16: Python Backend Code Optimization

**User Story:** As a developer, I want optimized Python backend code, so that the system performs efficiently and is maintainable.

#### Acceptance Criteria

1. THE FastAPI application SHALL be split into modular route files (scrapers, tasks, workers, payloads, health) with each file under 500 lines
2. THE system SHALL implement database connection pooling to reduce connection overhead
3. THE system SHALL use async database operations for all SQLite queries to improve concurrency
4. THE system SHALL implement response caching for static endpoints (HS codes, countries) with 1-hour TTL
5. THE task creator scripts SHALL inherit from a common base class to eliminate 80% code duplication
6. THE system SHALL use centralized configuration management with environment variables
7. THE system SHALL implement consistent error handling decorators across all scraper functions
8. THE system SHALL use type hints throughout the codebase for better IDE support and error detection
9. THE system SHALL implement request/response validation using Pydantic models
10. THE system SHALL use dependency injection for database connections and services

### Requirement 17: Code Quality and Testing

**User Story:** As a developer, I want comprehensive tests and code quality tools, so that bugs are caught early and code is reliable.

#### Acceptance Criteria

1. THE system SHALL have unit tests covering at least 70% of business logic
2. THE system SHALL have integration tests for all API endpoints
3. THE system SHALL use pytest as the testing framework with fixtures for common test data
4. THE system SHALL implement pre-commit hooks for linting (flake8/ruff) and formatting (black)
5. THE system SHALL use mypy for static type checking with strict mode enabled
6. THE system SHALL have CI/CD pipeline that runs tests, linting, and type checking on every commit
7. THE system SHALL generate test coverage reports and fail builds below 70% coverage
8. THE system SHALL use property-based testing for data validation functions

### Requirement 18: Performance Monitoring and Optimization

**User Story:** As a system administrator, I want performance monitoring, so that I can identify and resolve bottlenecks.

#### Acceptance Criteria

1. THE system SHALL implement request timing middleware to track API endpoint performance
2. THE system SHALL log slow queries (>100ms) with query details for optimization
3. THE system SHALL implement rate limiting on API endpoints to prevent abuse
4. THE system SHALL use Redis for caching frequently accessed data (task statistics, worker status)
5. THE system SHALL implement database query optimization with proper indexes on frequently queried columns
6. THE system SHALL use connection pooling for Redis with minimum 5 and maximum 20 connections
7. THE system SHALL implement background task cleanup to remove old completed tasks (>30 days)
8. THE system SHALL use bulk insert operations for creating multiple tasks to reduce database overhead

### Requirement 19: Logging and Observability

**User Story:** As a developer, I want structured logging and observability, so that I can debug issues and monitor system behavior.

#### Acceptance Criteria

1. THE system SHALL use structured logging (JSON format) with consistent fields (timestamp, level, service, message, context)
2. THE system SHALL implement log rotation with maximum file size of 100MB and retention of 30 days
3. THE system SHALL log all API requests with method, path, status code, duration, and user context
4. THE system SHALL implement correlation IDs to track requests across services
5. THE system SHALL separate logs by service (api, scrapers, task_creators, workers) in different files
6. THE system SHALL implement log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL) with environment-based configuration
7. THE system SHALL send ERROR and CRITICAL logs to a centralized monitoring system (optional)
8. THE system SHALL implement health check endpoints that return detailed service status

### Requirement 20: Security Hardening

**User Story:** As a security engineer, I want secure code practices, so that the system is protected from common vulnerabilities.

#### Acceptance Criteria

1. THE system SHALL validate and sanitize all user inputs to prevent SQL injection
2. THE system SHALL implement CORS with specific allowed origins (not wildcard in production)
3. THE system SHALL use parameterized queries for all database operations
4. THE system SHALL implement rate limiting (100 requests per minute per IP) on all API endpoints
5. THE system SHALL not expose sensitive information (stack traces, internal paths) in error responses
6. THE system SHALL implement request size limits (10MB max) to prevent DoS attacks
7. THE system SHALL use secure headers (X-Content-Type-Options, X-Frame-Options, CSP)
8. THE system SHALL implement API key authentication for production deployments
9. THE system SHALL log all authentication attempts and failed access attempts
10. THE system SHALL use environment variables for all secrets (never hard-coded)

### Requirement 21: Frontend Structure and Styling Consistency

**User Story:** As a developer, I want the dashboard to follow the existing frontend folder structure and UI patterns, so that the codebase remains consistent and maintainable.

#### Acceptance Criteria

1. THE React Frontend SHALL follow the existing Next.js App Router structure in the `frontend` folder
2. THE React Frontend SHALL use the existing Hydrogen layout (`HydrogenLayout`) for all dashboard pages
3. THE React Frontend SHALL use Tailwind CSS with the existing theme configuration for styling
4. THE React Frontend SHALL use the RizzUI component library that is already configured in the project
5. THE React Frontend SHALL follow the existing folder structure: `src/app` for pages, `src/components` for reusable components, `src/layouts` for layout components
6. THE React Frontend SHALL use the existing TypeScript configuration and type safety patterns
7. THE React Frontend SHALL use the existing font configuration (Inter and Lexend Deca fonts)
8. THE React Frontend SHALL follow the existing color scheme and design tokens defined in `tailwind.config.ts`
9. THE React Frontend SHALL use the existing utility functions in `src/utils` for common operations
10. THE React Frontend SHALL maintain consistency with existing component patterns (modal, drawer, theme provider)

### Requirement 22: Sidebar Navigation Integration

**User Story:** As a user, I want to access all dashboard features from the sidebar menu, so that I can easily navigate between different sections.

#### Acceptance Criteria

1. THE system SHALL add a new "Scraper Dashboard" section to the sidebar menu in `menu-items.tsx`
2. WHEN viewing the sidebar, THE system SHALL display dashboard menu items with appropriate icons from Phosphor Icons
3. THE system SHALL add the following menu items under "Scraper Dashboard": Home, Task Management, Workers, System Health, Logs, Payloads, Task Queue, Data Sources
4. THE system SHALL use dropdown navigation for related pages (e.g., grouping payload types under Payloads)
5. THE system SHALL add route definitions for all dashboard pages in `src/config/routes.ts`
6. THE system SHALL highlight the active menu item based on the current route
7. THE system SHALL maintain the existing menu structure and not remove or modify existing menu items
8. THE system SHALL use consistent icon styling with other menu items (Duotone style from Phosphor Icons)
9. THE system SHALL organize dashboard menu items logically with appropriate grouping and labels
10. THE system SHALL ensure all menu items link to valid routes that correspond to implemented pages
