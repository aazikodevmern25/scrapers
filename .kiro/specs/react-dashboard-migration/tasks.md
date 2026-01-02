# Implementation Plan: React Dashboard Migration

## Overview

This implementation plan breaks down the React dashboard migration into discrete, manageable tasks. Each task builds incrementally on previous work, with property-based tests integrated throughout to catch issues early.

---

- [x] 1. Project Setup and Infrastructure
  - Set up Next.js project structure within the existing frontend folder
  - Configure TypeScript, Tailwind CSS, and RizzUI integration
  - Set up API client with base configuration and error handling
  - Configure environment variables for API endpoints
  - Set up testing infrastructure (Jest, React Testing Library, fast-check)
  - _Requirements: 12.1, 12.2, 12.3, 13.4, 13.5, 21.1, 21.3, 21.4_

- [x] 1.1 Initialize Next.js configuration
  - Verify Next.js 14 with App Router is properly configured
  - Ensure TypeScript configuration is set up correctly
  - Verify Tailwind CSS and RizzUI are working
  - _Requirements: 21.1, 21.3, 21.4_

- [x] 1.2 Create API client base structure
  - Implement base API client class with GET, POST, DELETE methods
  - Add error handling and response transformation
  - Add request/response interceptors
  - Configure base URL from environment variables
  - _Requirements: 13.5_

- [x] 1.3 Set up testing framework
  - Configure Jest for unit testing
  - Configure React Testing Library for component testing
  - Configure fast-check for property-based testing
  - Set up MSW for API mocking
  - _Requirements: 13.4_

- [x] 1.4 Write property test for API client error handling
  - **Property 7: Error Message Display**
  - **Validates: Requirements 5.5, 15.1, 15.2, 15.4**

---

- [x] 2. Core Layout and Navigation
  - Create dashboard layout using HydrogenLayout
  - Add "Scraper Dashboard" section to sidebar menu
  - Add all 8 dashboard menu items with Phosphor Icons
  - Configure route definitions in routes.ts
  - Implement active menu highlighting
  - _Requirements: 21.2, 22.1, 22.2, 22.3, 22.5, 22.6, 22.8_

- [x] 2.1 Create dashboard layout wrapper
  - Create (dashboard) route group with layout.tsx
  - Integrate HydrogenLayout for all dashboard pages
  - _Requirements: 21.2_

- [x] 2.2 Update sidebar menu configuration
  - Add "Scraper Dashboard" section to menu-items.tsx
  - Add menu items: Home, Task Management, Workers, System Health, Logs, Payloads, Task Queue, Data Sources
  - Use appropriate Phosphor Icons (Duotone style)
  - _Requirements: 22.1, 22.2, 22.3, 22.8_

- [x] 2.3 Configure dashboard routes
  - Add route definitions to src/config/routes.ts
  - Create placeholder pages for all 8 dashboard routes
  - _Requirements: 22.5_

- [x] 2.4 Write property test for layout consistency
  - **Property 16: Layout Consistency**
  - **Validates: Requirements 21.2**

- [x] 2.5 Write property test for active menu highlighting
  - **Property 17: Active Menu Highlighting**
  - **Validates: Requirements 22.6**

- [x] 2.6 Write property test for menu link validity
  - **Property 18: Menu Link Validity**
  - **Validates: Requirements 22.10**

- [x] 2.7 Write property test for icon consistency
  - **Property 19: Icon Style Consistency**
  - **Validates: Requirements 22.8**

- [x] 2.8 Write property test for menu structure preservation
  - **Property 20: Menu Structure Preservation**
  - **Validates: Requirements 22.7**

---

- [x] 3. TypeScript Types and Data Models
  - Define TypeScript interfaces for all data models
  - Create types for Scraper, Task, Worker, SystemHealth, DashboardStats
  - Create types for API requests and responses
  - Create types for form data and validation
  - _Requirements: 12.3_

- [x] 3.1 Create core type definitions
  - Define Scraper, Task, Worker interfaces in src/types/
  - Define SystemHealth, DashboardStats interfaces
  - Define API request/response types
  - _Requirements: 12.3_

---

- [x] 4. API Integration Layer
  - Implement API client methods for all endpoints
  - Create scraperAPI, taskAPI, workerAPI, healthAPI, payloadAPI modules
  - Add request/response type safety
  - Implement error handling for all API calls
  - _Requirements: 1.2, 1.5, 11.2_

- [x] 4.1 Implement scraper API methods
  - Create src/lib/api/scrapers.ts
  - Implement getStatus, start, stop, setLimit, setConcurrency methods
  - _Requirements: 1.2, 1.5_

- [x] 4.2 Implement task API methods
  - Create src/lib/api/tasks.ts
  - Implement getAll, getActive, cancel, getStatus, getLogs methods
  - _Requirements: 1.2, 1.5_

- [x] 4.3 Implement worker API methods
  - Create src/lib/api/workers.ts
  - Implement getStatus, start, shutdown, restart methods
  - _Requirements: 1.2, 1.5_

- [x] 4.4 Implement health API methods
  - Create src/lib/api/health.ts
  - Implement getStats, getSystemHealth methods
  - _Requirements: 1.2, 1.5_

- [x] 4.5 Implement payload API methods
  - Create src/lib/api/payloads.ts
  - Implement generate, getStats, getCreators methods
  - _Requirements: 1.2, 1.5_

- [x] 4.6 Write property test for API contract stability
  - **Property 1: API Contract Stability**
  - **Validates: Requirements 1.2, 1.5**

- [x] 4.7 Write property test for authentication token inclusionStill
  - **Property 10: Authentication Token Inclusion**
  - **Validates: Requirements 11.2**

---

- [x] 5. Real-time Data Hooks
  - Create useSSE hook for Server-Sent Events
  - Create useDashboardStats hook
  - Create useTaskManager hook
  - Add connection status tracking
  - Add automatic reconnection logic
  - _Requirements: 3.1, 3.2, 3.5_

- [x] 5.1 Implement useSSE hook
  - Create src/lib/hooks/use-sse.ts
  - Handle EventSource connection lifecycle
  - Parse incoming SSE messages
  - Track connection status
  - Implement reconnection logic
  - _Requirements: 3.1, 3.5_

- [x] 5.2 Create dashboard-specific hooks
  - Create useDashboardStats hook for /api/v1/dashboard/stream
  - Create useTaskManager hook for /api/task-manager/stream
  - _Requirements: 3.1, 3.2_

- [x] 5.3 Write property test for real-time update frequency
  - **Property 2: Real-time Update Frequency**
  - **Validates: Requirements 3.1**

---

- [x] 6. Shared UI Components
  - Create reusable dashboard components
  - Implement StatsCard, ScraperCard, TaskTable, WorkerCard components
  - Implement HealthMetrics, LogViewer, PayloadForm components
  - Add loading states and error boundaries
  - Ensure responsive design for all components
  - _Requirements: 4.1, 4.2, 4.3, 12.1_

- [x] 6.1 Create StatsCard component
  - Create src/components/dashboard/stats-card.tsx
  - Display title, value, icon, and optional trend
  - Add loading state
  - _Requirements: 4.3, 12.1_

- [x] 6.2 Create ScraperCard component
  - Create src/components/dashboard/scraper-card.tsx
  - Display scraper status, metrics, and controls
  - Add start/stop/adjust limit actions
  - _Requirements: 4.3, 12.1_

- [x] 6.3 Create TaskTable component
  - Create src/components/dashboard/task-table.tsx
  - Implement sorting, filtering, pagination
  - Add cancel/retry/view details actions
  - _Requirements: 4.2, 12.1_

- [x] 6.4 Write property test for table feature completeness
  - **Property 4: Table Feature Completeness**
  - **Validates: Requirements 4.2**

- [x] 6.5 Create WorkerCard component
  - Create src/components/dashboard/worker-card.tsx
  - Display worker status, queues, and metrics
  - Add start/stop/restart actions
  - _Requirements: 4.3, 12.1_

- [x] 6.6 Create HealthMetrics component
  - Create src/components/dashboard/health-metrics.tsx
  - Display CPU, memory, disk usage with charts
  - Add service status indicators
  - _Requirements: 12.1_

- [x] 6.7 Create LogViewer component
  - Create src/components/dashboard/log-viewer.tsx
  - Implement real-time log streaming
  - Add filtering and search capabilities
  - _Requirements: 12.1_

- [x] 6.8 Create PayloadForm component
  - Create src/components/dashboard/payload-form.tsx
  - Implement dynamic form rendering based on payload type
  - Add validation for all fields
  - _Requirements: 12.1_

- [x] 6.9 Write property test for responsive layout
  - **Property 3: Responsive Layout Adaptation**
  - **Validates: Requirements 4.1**

- [x] 6.10 Write property test for action feedback
  - **Property 5: Action Feedback Consistency**
  - **Validates: Requirements 4.3, 5.5**

- [x] 6.11 Write property test for form validation
  - **Property 8: Form Validation Consistency**
  - **Validates: Requirements 6.2, 6.4, 15.3**

---

- [x] 7. Home Dashboard Page
  - Implement dashboard home page with real-time statistics
  - Display all scraper cards with status and controls
  - Show system-wide metrics (total tasks, active workers, etc.)
  - Integrate real-time updates via SSE
  - _Requirements: 2.1, 3.1, 3.2_

- [x] 7.1 Create home dashboard page
  - Create src/app/(dashboard)/page.tsx
  - Fetch and display dashboard statistics
  - Render scraper cards for all scrapers
  - Display system-wide metrics
  - _Requirements: 2.1_

- [x] 7.2 Integrate real-time updates
  - Use useDashboardStats hook for live data
  - Update UI every 5 seconds
  - Handle connection errors gracefully
  - _Requirements: 3.1, 3.2_

---

- [x] 8. Task Management Page
  - Implement task management page
  - Display task creators with start/stop controls
  - Show task limits and allow adjustments
  - Display worker status and concurrency settings
  - _Requirements: 2.2, 5.1, 5.2, 5.3_

- [x] 8.1 Create task management page
  - Create src/app/(dashboard)/tasks/page.tsx
  - Fetch and display task creator status
  - Render controls for each task creator
  - _Requirements: 2.2_

- [x] 8.2 Implement task creator controls
  - Add start/stop buttons for each creator
  - Add task limit adjustment controls
  - Add worker concurrency controls
  - Show real-time status updates
  - _Requirements: 5.1, 5.2, 5.3_

---

- [x] 9. Workers Management Page
  - Implement workers management page
  - Display all Celery workers with status
  - Show worker queues, concurrency, and active tasks
  - Add worker control actions (start, stop, restart)
  - _Requirements: 2.3, 8.1, 8.2, 8.3, 8.5_

- [x] 9.1 Create workers page
  - Create src/app/(dashboard)/workers/page.tsx
  - Fetch and display worker status
  - Render worker cards with metrics
  - _Requirements: 2.3, 8.1_

- [x] 9.2 Implement worker controls
  - Add start/stop/restart buttons
  - Add worker configuration form
  - Show real-time worker statistics
  - _Requirements: 8.2, 8.3, 8.5_

---

- [x] 10. System Health Page
  - Implement system health monitoring page
  - Display CPU, memory, disk usage metrics
  - Show service status (Redis, Celery, database)
  - Add historical charts for resource usage
  - Highlight warnings when thresholds exceeded
  - _Requirements: 2.4, 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 10.1 Create health monitoring page
  - Create src/app/(dashboard)/health/page.tsx
  - Fetch and display system health metrics
  - Render health metrics component
  - _Requirements: 2.4, 9.1_

- [x] 10.2 Implement service status display
  - Show Redis, Celery, database connectivity status
  - Add visual indicators for healthy/unhealthy services
  - _Requirements: 9.2, 9.5_

- [x] 10.3 Add resource usage charts
  - Implement charts for CPU, memory, disk over time
  - Add threshold warning indicators
  - _Requirements: 9.3, 9.4_

---

- [x] 11. Logs Viewer Page
  - Implement real-time logs viewer page
  - Stream logs from all scrapers via SSE
  - Add filtering by scraper type, log level, time range
  - Add search with text highlighting
  - Add log export functionality
  - _Requirements: 2.5, 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 11.1 Create logs viewer page
  - Create src/app/(dashboard)/logs/page.tsx
  - Implement real-time log streaming
  - Render log entries with timestamps
  - _Requirements: 2.5, 10.1_

- [x] 11.2 Implement log filtering
  - Add filters for scraper type, log level, time range
  - Add search functionality with highlighting
  - _Requirements: 10.2, 10.3_

- [x] 11.3 Add log export
  - Implement download logs to text file
  - Apply current filters to export
  - _Requirements: 10.5_

---

- [x] 12. Payloads Generator Page
  - Implement payload generator page
  - Create forms for all 10 payload types
  - Add dynamic form rendering based on selected type
  - Implement validation for HS codes, countries, dates
  - Add autocomplete for country selection
  - Display task creation confirmation
  - _Requirements: 2.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 12.1 Create payloads page
  - Create src/app/(dashboard)/payloads/page.tsx
  - Add payload type selector
  - Implement dynamic form rendering
  - _Requirements: 2.6, 6.1_

- [x] 12.2 Implement payload forms
  - Create forms for all 10 payload types
  - Add field validation (HS codes, countries, dates)
  - Add country autocomplete
  - _Requirements: 6.2, 6.3, 6.4, 6.6_

- [x] 12.3 Write property test for payload form rendering
  - **Property 9: Payload Form Rendering**
  - **Validates: Requirements 6.1**

- [x] 12.4 Implement payload submission
  - Handle form submission for all payload types
  - Display success message with task count
  - Handle validation errors
  - _Requirements: 6.5_

---

- [x] 13. Task Queue Page
  - Implement task queue viewer page
  - Display tasks grouped by status
  - Add filtering by scraper type, status, date range
  - Show task details on selection
  - Add cancel and retry actions
  - _Requirements: 2.7, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 13.1 Create task queue page
  - Create src/app/(dashboard)/queue/page.tsx
  - Fetch and display all tasks
  - Group tasks by status (pending, running, success, failed)
  - _Requirements: 2.7, 7.1_

- [x] 13.2 Implement task filtering
  - Add filters for scraper type, status, date range
  - Update task list based on filters
  - _Requirements: 7.2_

- [x] 13.3 Implement task details view
  - Show detailed task information on selection
  - Display task parameters and logs
  - _Requirements: 7.3_

- [x] 13.4 Add task actions
  - Implement cancel task functionalitywe
  - Implement retry task functionality
  - _Requirements: 7.4, 7.5_

---

- [x] 14. Data Sources Page
  - Implement data sources page
  - Display all configured scrapers
  - Show database information for each scraper
  - Display scraper statistics
  - _Requirements: 2.8_

- [x] 14.1 Create data sources page
  - Create src/app/(dashboard)/sources/page.tsx
  - Fetch and display scraper configurations
  - Show database paths and statistics
  - _Requirements: 2.8_

---

- [x] 15. State Management
  - Set up Zustand store for global dashboard state
  - Implement dashboard store with stats, scrapers, selection
  - Add actions for updating state
  - Integrate store with components
  - _Requirements: 12.5_

- [x] 15.1 Create dashboard store
  - Create src/lib/stores/dashboard-store.ts
  - Define state shape and actions
  - Implement state update logic
  - _Requirements: 12.5_

- [x] 15.2 Integrate store with components
  - Connect components to dashboard store
  - Use store for shared state across pages
  - _Requirements: 12.5_

---

- [x] 16. Client-side Navigation and Routing
  - Verify client-side routing works without page reloads
  - Implement route transitions
  - Add loading states during navigation
  - _Requirements: 4.4_

- [x] 16.1 Verify SPA navigation
  - Test navigation between all dashboard pages
  - Ensure no full page reloads occur
  - _Requirements: 4.4_

- [x] 16.2 Write property test for client-side navigation
  - **Property 6: Client-side Navigation**
  - **Validates: Requirements 4.4**

---

- [x] 17. Performance Optimization
  - Implement code splitting for routes
  - Add data caching with React Query
  - Implement virtualization for large lists
  - Add optimistic updates for mutations
  - Optimize bundle size
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [x] 17.1 Set up React Query
  - Install and configure TanStack Query
  - Wrap app with QueryClientProvider
  - Configure cache settings
  - _Requirements: 14.4_

- [x] 17.2 Implement data caching
  - Use React Query for all API calls
  - Configure cache TTL for different endpoints
  - Implement background refetching
  - _Requirements: 14.4_

- [x] 17.3 Write property test for data caching
  - **Property 13: Data Caching Behavior**
  - **Validates: Requirements 14.4**

- [x] 17.4 Implement code splitting
  - Use Next.js dynamic imports for heavy components
  - Verify route-based code splitting
  - _Requirements: 14.2_

- [x] 17.5 Write property test for code splitting
  - **Property 12: Code Splitting Effectiveness**
  - **Validates: Requirements 14.2**

- [x] 17.6 Add virtualization for large lists
  - Implement react-window for task queue
  - Implement react-window for log viewer
  - _Requirements: 14.3_

- [x] 17.7 Implement optimistic updates
  - Add optimistic updates for scraper start/stop
  - Add optimistic updates for task cancel/retry
  - _Requirements: 14.5_

- [x] 17.8 Write property test for optimistic updates
  - **Property 14: Optimistic Update Pattern**
  - **Validates: Requirements 14.5**

- [x] 17.9 Optimize page load performance
  - Analyze and optimize bundle size
  - Implement lazy loading for images
  - Optimize font loading
  - _Requirements: 14.1_

- [x] 17.10 Write property test for page load performance
  - **Property 11: Page Load Performance**
  - **Validates: Requirements 14.1**

---

- [x] 18. Error Handling and Recovery
  - Implement global error boundary
  - Add error handling for all API calls
  - Implement retry logic for failed requests
  - Add error recovery mechanisms
  - Display user-friendly error messages
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [x] 18.1 Create error boundary component
  - Implement React error boundary
  - Add error fallback UI
  - Log errors to console/monitoring service
  - _Requirements: 15.4_

- [x] 18.2 Implement API error handling
  - Add error handling to all API client methods
  - Transform API errors to user-friendly messages
  - _Requirements: 15.1, 15.4_

- [x] 18.3 Add retry logic
  - Implement retry for network errors
  - Add retry buttons to error messages
  - Configure React Query retry settings
  - _Requirements: 15.2_

- [x] 18.4 Implement error recovery
  - Add state restoration after errors
  - Implement error recovery actions
  - _Requirements: 15.5_

- [x] 18.5 Write property test for error recovery
  - **Property 15: Error State Recovery**
  - **Validates: Requirements 15.5**

---

- [x] 19. Authentication Integration (Optional)
  - Implement authentication flow (if enabled)
  - Add login/logout functionality
  - Store and manage auth tokens
  - Add session expiration handling
  - Implement protected routes
  - _Requirements: 11.1, 11.2, 11.3_

- [x] 19.1 Create authentication context
  - Implement auth context provider
  - Add login/logout methods
  - Store auth token in localStorage/cookies
  - _Requirements: 11.1, 11.2_

- [x] 19.2 Implement session management
  - Add session expiration detection
  - Redirect to login on expiration
  - Preserve intended destination
  - _Requirements: 11.3_

- [x] 19.3 Add protected routes
  - Wrap dashboard routes with auth check
  - Redirect unauthenticated users to login
  - _Requirements: 11.1_

---

- [x] 20. Security Hardening
  - Implement CORS configuration
  - Add HTTPS enforcement in production
  - Implement input sanitization
  - Add Content Security Policy headers
  - _Requirements: 11.4, 11.5_

- [x] 20.1 Configure CORS
  - Verify CORS settings in FastAPI
  - Test cross-origin requests
  - _Requirements: 11.4_

- [ ] 20.2 Enforce HTTPS in production
  - Add HTTPS redirect in production
  - Update API URLs to use HTTPS
  - _Requirements: 11.5_

---

- [x] 21. Build and Deployment Configuration
  - Configure production build settings
  - Set up environment-specific configurations
  - Optimize build output
  - Configure FastAPI to serve React app
  - _Requirements: 13.1, 13.2, 13.3, 13.5_

- [x] 21.1 Configure production build
  - Set up Next.js production build configuration
  - Enable minification and optimization
  - Configure output directory
  - _Requirements: 13.1_

- [x] 21.2 Set up environment configurations
  - Create .env files for dev, staging, production
  - Configure API URLs for each environment
  - _Requirements: 13.5_

- [x] 21.3 Integrate with FastAPI
  - Update main.py to serve React static files
  - Configure static file mounting
  - Test API endpoints still work
  - _Requirements: 13.2_

- [x] 21.4 Test deployment
  - Build React app
  - Deploy to FastAPI
  - Test all functionality in production mode
  - _Requirements: 13.3_

---

- [ ] 22. Testing and Quality Assurance
  - Run all unit tests
  - Run all property-based tests
  - Run integration tests
  - Perform manual testing of all features
  - Fix any discovered bugs
  - _Requirements: 13.4, 17.1, 17.2, 17.3_

- [ ] 22.1 Run unit test suite
  - Execute all unit tests
  - Verify 80% code coverage
  - Fix failing tests
  - _Requirements: 17.1_

- [ ] 22.2 Run property-based test suite
  - Execute all 20 property tests
  - Verify all properties pass with 100 iterations
  - Fix any property violations
  - _Requirements: 17.3, 17.8_

- [ ] 22.3 Run integration tests
  - Execute all integration tests
  - Test API integration with mock server
  - Fix any integration issues
  - _Requirements: 17.2_

- [ ] 22.4 Perform manual testing
  - Test all user workflows manually
  - Test on different browsers and devices
  - Test real-time updates
  - Test error scenarios
  - _Requirements: 13.4_

---

- [ ] 23. Documentation
  - Write component documentation
  - Document API integration
  - Create deployment guide
  - Write user guide for new dashboard
  - _Requirements: 12.4_

- [ ] 23.1 Document components
  - Add JSDoc comments to all components
  - Document props and usage examples
  - _Requirements: 12.4_

- [ ] 23.2 Document API integration
  - Document API client usage
  - Document available endpoints
  - _Requirements: 12.4_

- [ ] 23.3 Create deployment guide
  - Write step-by-step deployment instructions
  - Document environment configuration
  - _Requirements: 12.4_

---

- [ ] 24. Final Checkpoint - Ensure all tests pass, ask the user if questions arise.

---

## Summary

This implementation plan provides a structured approach to migrating the dashboard from Jinja2 templates to React. The plan:

1. Starts with infrastructure setup and core layout
2. Builds API integration and data models
3. Implements pages incrementally (Home → Tasks → Workers → Health → Logs → Payloads → Queue → Sources)
4. Adds performance optimizations and error handling
5. Integrates property-based tests throughout to validate correctness
6. Concludes with testing, documentation, and deployment

Each task is designed to be independently testable and builds on previous work. Property-based tests are integrated as optional sub-tasks to validate correctness properties without blocking core development.
