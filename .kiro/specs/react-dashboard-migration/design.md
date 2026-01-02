# Design Document: React Dashboard Migration

## Overview

This document outlines the technical design for migrating the existing Python/FastAPI-based dashboard with Jinja2 templates to a modern React.js frontend application. The migration will create a decoupled single-page application (SPA) that consumes the existing REST API while maintaining all current functionality and improving user experience.

### Key Design Principles

1. **Zero Backend Changes**: The FastAPI backend remains unchanged during migration
2. **Progressive Enhancement**: Build features incrementally with continuous testing
3. **Consistency**: Follow existing frontend patterns and styling
4. **Real-time Updates**: Leverage SSE/WebSocket for live data streaming
5. **Type Safety**: Use TypeScript throughout for better maintainability

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     React Frontend (SPA)                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │   Pages    │  │ Components │  │   Services/Hooks       │ │
│  │            │  │            │  │                        │ │
│  │ - Home     │  │ - Tables   │  │ - API Client          │ │
│  │ - Tasks    │  │ - Charts   │  │ - WebSocket Manager   │ │
│  │ - Workers  │  │ - Forms    │  │ - State Management    │ │
│  │ - Health   │  │ - Modals   │  │ - Real-time Hooks     │ │
│  │ - Logs     │  │ - Cards    │  │                        │ │
│  └────────────┘  └────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP/SSE/WebSocket
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Backend (Unchanged)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  REST API Endpoints (/api/v1/*)                        │ │
│  │  - Scraper control                                     │ │
│  │  - Task management                                     │ │
│  │  - Worker management                                   │ │
│  │  - System health                                       │ │
│  │  - Real-time streams (SSE)                            │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Static File Serving                                   │ │
│  │  - Serves built React app                             │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Celery + Redis + SQLite                         │
│  - Task queue management                                     │
│  - Worker processes                                          │
│  - Task storage                                              │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

**Frontend:**
- Next.js 14 (App Router)
- React 18
- TypeScript
- Tailwind CSS
- RizzUI Component Library
- TanStack Query (React Query) for data fetching
- Zustand for global state management
- Recharts for data visualization
- EventSource API for SSE

**Backend (Unchanged):**
- FastAPI
- Celery
- Redis
- SQLite
- Python 3.x

## Components and Interfaces

### Frontend Folder Structure

```
frontend/
├── src/
│   ├── app/
│   │   ├── (dashboard)/              # Dashboard route group
│   │   │   ├── layout.tsx            # Dashboard layout wrapper
│   │   │   ├── page.tsx              # Home dashboard
│   │   │   ├── tasks/
│   │   │   │   └── page.tsx          # Task management
│   │   │   ├── workers/
│   │   │   │   └── page.tsx          # Worker management
│   │   │   ├── health/
│   │   │   │   └── page.tsx          # System health
│   │   │   ├── logs/
│   │   │   │   └── page.tsx          # Log viewer
│   │   │   ├── payloads/
│   │   │   │   └── page.tsx          # Payload generator
│   │   │   ├── queue/
│   │   │   │   └── page.tsx          # Task queue
│   │   │   └── sources/
│   │   │       └── page.tsx          # Data sources
│   │   ├── layout.tsx                # Root layout
│   │   ├── page.tsx                  # Landing/redirect
│   │   └── globals.css
│   ├── components/
│   │   ├── dashboard/                # Dashboard-specific components
│   │   │   ├── stats-card.tsx
│   │   │   ├── scraper-card.tsx
│   │   │   ├── task-table.tsx
│   │   │   ├── worker-card.tsx
│   │   │   ├── health-metrics.tsx
│   │   │   ├── log-viewer.tsx
│   │   │   └── payload-form.tsx
│   │   ├── ui/                       # Shared UI components
│   │   └── charts/                   # Chart components
│   ├── lib/
│   │   ├── api/                      # API client
│   │   │   ├── client.ts             # Base API client
│   │   │   ├── scrapers.ts           # Scraper endpoints
│   │   │   ├── tasks.ts              # Task endpoints
│   │   │   ├── workers.ts            # Worker endpoints
│   │   │   └── health.ts             # Health endpoints
│   │   ├── hooks/                    # Custom hooks
│   │   │   ├── use-sse.ts            # SSE hook
│   │   │   ├── use-dashboard-stats.ts
│   │   │   ├── use-tasks.ts
│   │   │   └── use-workers.ts
│   │   ├── stores/                   # Zustand stores
│   │   │   └── dashboard-store.ts
│   │   └── utils/                    # Utility functions
│   ├── types/                        # TypeScript types
│   │   ├── api.ts
│   │   ├── scraper.ts
│   │   ├── task.ts
│   │   └── worker.ts
│   └── config/
│       ├── routes.ts                 # Route definitions
│       └── api-config.ts             # API configuration
```

### Key Components

#### 1. Dashboard Layout Component
```typescript
// Wraps all dashboard pages with sidebar navigation
interface DashboardLayoutProps {
  children: React.ReactNode;
}
```

#### 2. Stats Card Component
```typescript
interface StatsCardProps {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  loading?: boolean;
}
```

#### 3. Scraper Card Component
```typescript
interface ScraperCardProps {
  id: string;
  name: string;
  status: 'running' | 'stopped' | 'error';
  tasksQueued: number;
  tasksCompleted: number;
  tasksFailed: number;
  onStart: () => void;
  onStop: () => void;
  onAdjustLimit: (limit: number) => void;
}
```

#### 4. Task Table Component
```typescript
interface TaskTableProps {
  tasks: Task[];
  loading: boolean;
  onCancel: (taskId: string) => void;
  onRetry: (taskId: string) => void;
  onViewDetails: (taskId: string) => void;
}
```

#### 5. Real-time SSE Hook
```typescript
function useSSE<T>(url: string, options?: {
  onMessage?: (data: T) => void;
  onError?: (error: Error) => void;
  enabled?: boolean;
}): {
  data: T | null;
  error: Error | null;
  isConnected: boolean;
}
```

## Data Models

### TypeScript Interfaces

```typescript
// Scraper Types
interface Scraper {
  id: string;
  name: string;
  displayName: string;
  status: 'running' | 'stopped' | 'error';
  queue: string;
  tasksQueued: number;
  tasksRunning: number;
  tasksCompleted: number;
  tasksFailed: number;
  taskLimit: number;
  workerConcurrency: number;
  workerStatus: 'running' | 'stopped';
  workerPid?: number;
  lastStarted?: string;
  lastStopped?: string;
}

// Task Types
interface Task {
  id: string;
  taskId: string;
  source: string;
  sourceLabel: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILURE' | 'REVOKED';
  payload: Record<string, any>;
  result?: any;
  error?: string;
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  retryCount: number;
}

// Worker Types
interface Worker {
  name: string;
  status: 'online' | 'offline';
  queues: string[];
  concurrency: number;
  activeTasks: number;
  totalTasks: number;
  loadAverage: string;
  clock: string;
}

// System Health Types
interface SystemHealth {
  cpu: {
    percent: number;
    cores: number;
  };
  memory: {
    total: number;
    used: number;
    percent: number;
    available: number;
  };
  disk: {
    total: number;
    used: number;
    percent: number;
    free: number;
  };
  services: {
    redis: 'healthy' | 'unhealthy';
    celery: 'healthy' | 'unhealthy';
    database: 'healthy' | 'unhealthy';
  };
}

// Dashboard Stats Types
interface DashboardStats {
  totalScrapers: number;
  activeScrapers: number;
  totalTasks: number;
  pendingTasks: number;
  runningTasks: number;
  completedTasks: number;
  failedTasks: number;
  activeWorkers: number;
  systemHealth: SystemHealth;
}

// Payload Types
interface PayloadConfig {
  type: 'macmap_tariff' | 'trade_remedies' | 'regulatory' | 'compare_market' | 
        'competitors' | 'products' | 'full_tariff' | 'indian_trade_portal' | 
        'trademap' | 'eximpedia';
  config: Record<string, any>;
}

// Log Entry Types
interface LogEntry {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  source: string;
  message: string;
  taskId?: string;
}
```

## API Integration

### API Client Structure

```typescript
// Base API client with error handling and interceptors
class APIClient {
  private baseURL: string;
  
  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }
  
  async get<T>(endpoint: string): Promise<T> {
    // Implementation with error handling
  }
  
  async post<T>(endpoint: string, data: any): Promise<T> {
    // Implementation with error handling
  }
  
  async delete<T>(endpoint: string): Promise<T> {
    // Implementation with error handling
  }
}

// Scraper API
export const scraperAPI = {
  getStatus: () => client.get<{data: {creators: Record<string, Scraper>}}>('/api/task-manager/status'),
  start: (id: string) => client.post(`/api/task-manager/start/${id}`, {}),
  stop: (id: string) => client.post(`/api/task-manager/stop/${id}`, {}),
  setLimit: (id: string, limit: number) => client.post(`/api/task-manager/limit/${id}`, {limit}),
  setConcurrency: (id: string, concurrency: number) => 
    client.post(`/api/task-manager/concurrency/${id}`, {limit: concurrency}),
};

// Task API
export const taskAPI = {
  getAll: (params: {limit?: number; offset?: number; status?: string}) => 
    client.get<{tasks: Task[]}>('/api/v1/tasks/all', params),
  getActive: () => client.get('/api/v1/tasks/active'),
  cancel: (taskId: string) => client.delete(`/api/v1/task/${taskId}`),
  getStatus: (taskId: string) => client.get(`/api/v1/task/${taskId}`),
  getLogs: (taskId: string) => client.get(`/api/v1/task/${taskId}/logs`),
};

// Worker API
export const workerAPI = {
  getStatus: () => client.get<{data: Record<string, Worker>}>('/api/v1/workers/status'),
  start: (config: WorkerStartRequest) => client.post('/api/v1/workers/start', config),
  shutdown: (name: string) => client.post(`/api/v1/workers/${name}/shutdown`, {}),
  restart: (name: string) => client.post(`/api/v1/workers/${name}/restart`, {}),
};

// Health API
export const healthAPI = {
  getStats: () => client.get<DashboardStats>('/api/v1/dashboard/stats'),
  getSystemHealth: () => client.get<SystemHealth>('/api/v1/health'),
};

// Payload API
export const payloadAPI = {
  generate: (config: PayloadConfig) => client.post('/api/v1/payload/generate', config),
  getStats: () => client.get('/api/v1/payload/stats'),
  getCreators: () => client.get('/api/v1/payload/creators'),
};
```

### Real-time Data Streaming

```typescript
// SSE Hook for real-time updates
function useSSE<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  
  useEffect(() => {
    const eventSource = new EventSource(url);
    
    eventSource.onopen = () => setIsConnected(true);
    
    eventSource.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        setData(parsed);
      } catch (err) {
        setError(err as Error);
      }
    };
    
    eventSource.onerror = () => {
      setIsConnected(false);
      setError(new Error('SSE connection error'));
    };
    
    return () => eventSource.close();
  }, [url]);
  
  return { data, error, isConnected };
}

// Usage in components
function DashboardHome() {
  const { data: stats } = useSSE<DashboardStats>('/api/v1/dashboard/stream');
  const { data: taskManagerData } = useSSE('/api/task-manager/stream');
  
  // Render dashboard with real-time data
}
```

## State Management

### Zustand Store for Dashboard State

```typescript
interface DashboardStore {
  // State
  stats: DashboardStats | null;
  scrapers: Record<string, Scraper>;
  selectedScraper: string | null;
  
  // Actions
  setStats: (stats: DashboardStats) => void;
  setScrapers: (scrapers: Record<string, Scraper>) => void;
  selectScraper: (id: string | null) => void;
  updateScraperStatus: (id: string, status: Partial<Scraper>) => void;
}

const useDashboardStore = create<DashboardStore>((set) => ({
  stats: null,
  scrapers: {},
  selectedScraper: null,
  
  setStats: (stats) => set({ stats }),
  setScrapers: (scrapers) => set({ scrapers }),
  selectScraper: (id) => set({ selectedScraper: id }),
  updateScraperStatus: (id, status) => 
    set((state) => ({
      scrapers: {
        ...state.scrapers,
        [id]: { ...state.scrapers[id], ...status }
      }
    })),
}));
```

## Routing Configuration

### Route Definitions

```typescript
// src/config/routes.ts
export const routes = {
  dashboard: {
    home: '/dashboard',
    tasks: '/dashboard/tasks',
    workers: '/dashboard/workers',
    health: '/dashboard/health',
    logs: '/dashboard/logs',
    payloads: '/dashboard/payloads',
    queue: '/dashboard/queue',
    sources: '/dashboard/sources',
  },
};
```

### Sidebar Menu Configuration

```typescript
// Update frontend/src/layouts/hydrogen/menu-items.tsx
export const menuItems = [
  // ... existing items ...
  
  // Scraper Dashboard section
  {
    name: "Scraper Dashboard",
  },
  {
    name: "Home",
    href: routes.dashboard.home,
    icon: <PiHouseLineDuotone />,
  },
  {
    name: "Task Management",
    href: routes.dashboard.tasks,
    icon: <PiListNumbersDuotone />,
  },
  {
    name: "Workers",
    href: routes.dashboard.workers,
    icon: <PiUserGearDuotone />,
  },
  {
    name: "System Health",
    href: routes.dashboard.health,
    icon: <PiHeartbeatDuotone />,
  },
  {
    name: "Logs",
    href: routes.dashboard.logs,
    icon: <PiFileTextDuotone />,
  },
  {
    name: "Payloads",
    href: routes.dashboard.payloads,
    icon: <PiPackageDuotone />,
  },
  {
    name: "Task Queue",
    href: routes.dashboard.queue,
    icon: <PiQueueDuotone />,
  },
  {
    name: "Data Sources",
    href: routes.dashboard.sources,
    icon: <PiDatabaseDuotone />,
  },
];
```

## Error Handling

### Error Handling Strategy

```typescript
// Global error boundary
class ErrorBoundary extends React.Component<Props, State> {
  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error to monitoring service
    console.error('Error caught by boundary:', error, errorInfo);
  }
  
  render() {
    if (this.state.hasError) {
      return <ErrorFallback />;
    }
    return this.props.children;
  }
}

// API error handling
class APIError extends Error {
  constructor(
    public status: number,
    public message: string,
    public details?: any
  ) {
    super(message);
  }
}

async function handleAPIError(response: Response) {
  if (!response.ok) {
    const error = await response.json();
    throw new APIError(response.status, error.message || 'API Error', error);
  }
  return response.json();
}

// Component-level error handling
function TaskManagement() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: taskAPI.getAll,
    retry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
  
  if (error) {
    return <ErrorMessage error={error} onRetry={() => refetch()} />;
  }
  
  // Render component
}
```

## Testing Strategy

### Testing Approach

**Unit Tests:**
- Test individual components in isolation
- Test utility functions and hooks
- Test API client methods
- Test state management logic

**Integration Tests:**
- Test component interactions
- Test API integration with mock server
- Test real-time data flow with SSE
- Test form submissions and validations

**End-to-End Tests:**
- Test complete user workflows
- Test dashboard navigation
- Test scraper control operations
- Test task management operations

### Testing Tools

- **Jest**: Unit testing framework
- **React Testing Library**: Component testing
- **MSW (Mock Service Worker)**: API mocking
- **Playwright**: E2E testing

### Example Test Structure

```typescript
// Component test
describe('ScraperCard', () => {
  it('should display scraper status correctly', () => {
    render(<ScraperCard {...mockScraperProps} />);
    expect(screen.getByText('Running')).toBeInTheDocument();
  });
  
  it('should call onStart when start button is clicked', () => {
    const onStart = jest.fn();
    render(<ScraperCard {...mockScraperProps} onStart={onStart} />);
    fireEvent.click(screen.getByText('Start'));
    expect(onStart).toHaveBeenCalled();
  });
});

// API test
describe('scraperAPI', () => {
  it('should fetch scraper status', async () => {
    server.use(
      rest.get('/api/task-manager/status', (req, res, ctx) => {
        return res(ctx.json({ data: { creators: mockScrapers } }));
      })
    );
    
    const result = await scraperAPI.getStatus();
    expect(result.data.creators).toEqual(mockScrapers);
  });
});
```

## Performance Optimization

### Optimization Strategies

1. **Code Splitting**: Use Next.js dynamic imports for route-based code splitting
2. **Data Caching**: Use React Query for intelligent data caching and background refetching
3. **Virtualization**: Use react-window for large lists (task queue, logs)
4. **Debouncing**: Debounce search inputs and filter operations
5. **Memoization**: Use React.memo and useMemo for expensive computations
6. **Lazy Loading**: Lazy load charts and heavy components
7. **Image Optimization**: Use Next.js Image component for optimized images
8. **Bundle Analysis**: Regular bundle size analysis and optimization

### Performance Monitoring

```typescript
// Performance monitoring hook
function usePerformanceMonitor(componentName: string) {
  useEffect(() => {
    const startTime = performance.now();
    
    return () => {
      const endTime = performance.now();
      const renderTime = endTime - startTime;
      
      if (renderTime > 100) {
        console.warn(`${componentName} took ${renderTime}ms to render`);
      }
    };
  }, [componentName]);
}
```

## Deployment Strategy

### Build Process

```bash
# Frontend build
cd frontend
npm run build

# Output: frontend/out/ (static files)
```

### FastAPI Integration

```python
# main.py - Add static file serving
from fastapi.staticfiles import StaticFiles

# Serve React app
app.mount("/", StaticFiles(directory="frontend/out", html=True), name="static")

# API routes remain at /api/v1/*
```

### Environment Configuration

```typescript
// frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

// frontend/.env.production
NEXT_PUBLIC_API_URL=https://api.production.com
NEXT_PUBLIC_WS_URL=wss://api.production.com
```

### Deployment Steps

1. Build React application: `npm run build`
2. Copy build output to FastAPI static directory
3. Update FastAPI to serve static files
4. Remove Jinja2 template dependencies
5. Test all endpoints and functionality
6. Deploy to production

## Security Considerations

### Frontend Security

1. **XSS Prevention**: Sanitize user inputs, use React's built-in XSS protection
2. **CSRF Protection**: Include CSRF tokens in API requests
3. **Content Security Policy**: Configure CSP headers
4. **Secure Storage**: Use httpOnly cookies for sensitive data
5. **Input Validation**: Validate all user inputs on client and server
6. **Rate Limiting**: Implement client-side rate limiting for API calls

### API Security

1. **CORS Configuration**: Restrict allowed origins in production
2. **Authentication**: Implement JWT or session-based auth
3. **Authorization**: Role-based access control for sensitive operations
4. **HTTPS**: Enforce HTTPS in production
5. **API Rate Limiting**: Server-side rate limiting on all endpoints

## Migration Path

### Phase 1: Setup and Infrastructure
- Set up Next.js project structure
- Configure Tailwind CSS and RizzUI
- Create base layout and routing
- Set up API client and error handling

### Phase 2: Core Dashboard Features
- Implement home dashboard with stats
- Implement task management page
- Implement worker management page
- Add real-time updates with SSE

### Phase 3: Additional Features
- Implement system health monitoring
- Implement log viewer
- Implement payload generator
- Implement task queue viewer
- Implement data sources page

### Phase 4: Testing and Optimization
- Write unit and integration tests
- Perform performance optimization
- Conduct security audit
- User acceptance testing

### Phase 5: Deployment
- Build production bundle
- Integrate with FastAPI
- Deploy to production
- Monitor and fix issues

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property Reflection

After analyzing all acceptance criteria, I've identified several areas where properties can be consolidated:

**Redundancy Analysis:**
- Properties about "displaying" UI elements (2.1-2.8, 9.1-9.5, 10.1-10.5) are mostly examples of specific pages working, not universal properties
- Properties about error handling (5.5, 15.1-15.5) can be consolidated into comprehensive error handling properties
- Properties about form validation (6.2, 6.4, 15.3) can be consolidated into a single validation property
- Properties about API consistency (1.2, 1.5) can be consolidated
- Properties about navigation and routing (22.6, 22.10) can be consolidated

**Consolidated Properties:**
The following properties provide comprehensive coverage without redundancy:

1. **API Contract Stability** - Covers 1.2 and 1.5
2. **Real-time Update Frequency** - Covers 3.1
3. **Responsive Layout** - Covers 4.1
4. **Table Functionality** - Covers 4.2
5. **Action Feedback** - Covers 4.3
6. **Client-side Navigation** - Covers 4.4
7. **Error Display** - Covers 5.5, 15.1, 15.2, 15.4
8. **Form Validation** - Covers 6.2, 6.4, 15.3
9. **Payload Type Forms** - Covers 6.1
10. **Authentication Token Inclusion** - Covers 11.2
11. **Page Load Performance** - Covers 14.1
12. **Code Splitting** - Covers 14.2
13. **Data Caching** - Covers 14.4
14. **Optimistic Updates** - Covers 14.5
15. **Error Recovery** - Covers 15.5
16. **Layout Consistency** - Covers 21.2
17. **Active Menu Highlighting** - Covers 22.6
18. **Menu Link Validity** - Covers 22.10
19. **Icon Consistency** - Covers 22.8
20. **Menu Structure Preservation** - Covers 22.7

### Correctness Properties

Property 1: API Contract Stability
*For any* API endpoint that existed before migration, calling that endpoint after migration should return a response with the same schema and structure
**Validates: Requirements 1.2, 1.5**

Property 2: Real-time Update Frequency
*For any* dashboard page with real-time updates, the time between consecutive updates should be approximately 5 seconds (±1 second)
**Validates: Requirements 3.1**

Property 3: Responsive Layout Adaptation
*For any* viewport width, the dashboard should display a layout appropriate for that screen size without horizontal scrolling or content overflow
**Validates: Requirements 4.1**

Property 4: Table Feature Completeness
*For any* data table in the application, the table should provide sorting, filtering, and pagination capabilities
**Validates: Requirements 4.2**

Property 5: Action Feedback Consistency
*For any* user action (button click, form submission, API call), the UI should display a loading state during execution and success/error feedback upon completion
**Validates: Requirements 4.3, 5.5**

Property 6: Client-side Navigation
*For any* navigation between dashboard pages, the browser should not perform a full page reload (no network request for HTML document)
**Validates: Requirements 4.4**

Property 7: Error Message Display
*For any* API error or network failure, the system should display a user-friendly error message with actionable information (retry option, error details, or next steps)
**Validates: Requirements 5.5, 15.1, 15.2, 15.4**

Property 8: Form Validation Consistency
*For any* form with validation rules, submitting the form with invalid data should prevent submission, highlight invalid fields, and display specific error messages for each field
**Validates: Requirements 6.2, 6.4, 15.3**

Property 9: Payload Form Rendering
*For any* payload type selection, the system should render a form with fields appropriate to that specific payload type
**Validates: Requirements 6.1**

Property 10: Authentication Token Inclusion
*For any* API request made by the authenticated frontend, the request should include the authentication token in the headers
**Validates: Requirements 11.2**

Property 11: Page Load Performance
*For any* initial page load of the dashboard, the time from navigation to interactive should be less than 2 seconds under normal network conditions
**Validates: Requirements 14.1**

Property 12: Code Splitting Effectiveness
*For any* route navigation, only the JavaScript chunks required for that route should be loaded, not the entire application bundle
**Validates: Requirements 14.2**

Property 13: Data Caching Behavior
*For any* API endpoint marked as cacheable, repeated requests within the cache TTL should not trigger new network requests
**Validates: Requirements 14.4**

Property 14: Optimistic Update Pattern
*For any* mutation operation (create, update, delete), the UI should update immediately with the expected result before receiving server confirmation
**Validates: Requirements 14.5**

Property 15: Error State Recovery
*For any* error state, when the error is resolved or the user takes recovery action, the application should restore to the last valid state before the error occurred
**Validates: Requirements 15.5**

Property 16: Layout Consistency
*For any* dashboard page, the page should use the HydrogenLayout component as its layout wrapper
**Validates: Requirements 21.2**

Property 17: Active Menu Highlighting
*For any* current route, the corresponding menu item in the sidebar should be visually highlighted as active
**Validates: Requirements 22.6**

Property 18: Menu Link Validity
*For any* menu item with a link, clicking that link should navigate to a valid, implemented page (not a 404 or error page)
**Validates: Requirements 22.10**

Property 19: Icon Style Consistency
*For any* menu item icon, the icon should use the Duotone style from the Phosphor Icons library, consistent with existing menu items
**Validates: Requirements 22.8**

Property 20: Menu Structure Preservation
*For any* existing menu item that was present before adding dashboard items, that menu item should still exist with the same properties (name, href, icon) after the dashboard items are added
**Validates: Requirements 22.7**

## Testing Strategy

### Unit Testing

**Component Tests:**
- Test individual components in isolation with mock props
- Test component rendering with different prop combinations
- Test user interactions (clicks, form inputs, etc.)
- Test conditional rendering logic
- Test error boundaries

**Hook Tests:**
- Test custom hooks with various inputs
- Test hook state management
- Test hook side effects
- Test hook error handling

**Utility Tests:**
- Test utility functions with edge cases
- Test data transformation functions
- Test validation functions
- Test formatting functions

**Example Unit Tests:**
```typescript
// Component test
describe('ScraperCard', () => {
  it('should render scraper information correctly', () => {
    const scraper = mockScraper({ status: 'running' });
    render(<ScraperCard scraper={scraper} />);
    expect(screen.getByText(scraper.name)).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
  });
  
  it('should call onStart when start button is clicked', () => {
    const onStart = jest.fn();
    const scraper = mockScraper({ status: 'stopped' });
    render(<ScraperCard scraper={scraper} onStart={onStart} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    expect(onStart).toHaveBeenCalledWith(scraper.id);
  });
});

// Hook test
describe('useSSE', () => {
  it('should connect to SSE endpoint and receive data', async () => {
    const mockData = { stats: { totalTasks: 100 } };
    mockSSEServer.send(mockData);
    
    const { result } = renderHook(() => useSSE('/api/stream'));
    
    await waitFor(() => {
      expect(result.current.data).toEqual(mockData);
      expect(result.current.isConnected).toBe(true);
    });
  });
});
```

### Integration Testing

**API Integration Tests:**
- Test API client methods with mock server
- Test error handling for different HTTP status codes
- Test request/response transformations
- Test authentication token handling

**Component Integration Tests:**
- Test component interactions with API
- Test form submission flows
- Test data fetching and display
- Test real-time update handling

**Example Integration Tests:**
```typescript
describe('Task Management Integration', () => {
  it('should fetch and display tasks', async () => {
    server.use(
      rest.get('/api/v1/tasks/all', (req, res, ctx) => {
        return res(ctx.json({ tasks: mockTasks }));
      })
    );
    
    render(<TaskManagement />);
    
    await waitFor(() => {
      expect(screen.getByText(mockTasks[0].id)).toBeInTheDocument();
    });
  });
  
  it('should cancel task when cancel button is clicked', async () => {
    const taskId = 'task-123';
    let cancelCalled = false;
    
    server.use(
      rest.delete(`/api/v1/task/${taskId}`, (req, res, ctx) => {
        cancelCalled = true;
        return res(ctx.json({ message: 'Task cancelled' }));
      })
    );
    
    render(<TaskManagement />);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    
    await waitFor(() => {
      expect(cancelCalled).toBe(true);
      expect(screen.getByText(/task cancelled/i)).toBeInTheDocument();
    });
  });
});
```

### Property-Based Testing

Property-based tests will be implemented using **fast-check** library for JavaScript/TypeScript. Each test will run a minimum of 100 iterations with randomly generated inputs.

**Property Test Examples:**

```typescript
import fc from 'fast-check';

/**
 * Feature: react-dashboard-migration, Property 1: API Contract Stability
 * For any API endpoint that existed before migration, calling that endpoint 
 * after migration should return a response with the same schema and structure
 */
describe('Property 1: API Contract Stability', () => {
  it('should maintain response schema for all endpoints', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...Object.keys(API_ENDPOINTS)),
        async (endpointKey) => {
          const endpoint = API_ENDPOINTS[endpointKey];
          const response = await fetch(endpoint.url);
          const data = await response.json();
          
          // Verify response matches expected schema
          const isValid = validateSchema(data, endpoint.schema);
          expect(isValid).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: react-dashboard-migration, Property 3: Responsive Layout Adaptation
 * For any viewport width, the dashboard should display a layout appropriate 
 * for that screen size without horizontal scrolling or content overflow
 */
describe('Property 3: Responsive Layout Adaptation', () => {
  it('should adapt layout for any viewport width', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 320, max: 3840 }), // viewport widths
        fc.constantFrom(...DASHBOARD_PAGES),
        (viewportWidth, page) => {
          cy.viewport(viewportWidth, 1080);
          cy.visit(page);
          
          // Check no horizontal scroll
          cy.window().then((win) => {
            expect(win.document.body.scrollWidth).to.be.lte(viewportWidth);
          });
          
          // Check no content overflow
          cy.get('body').should('not.have.css', 'overflow-x', 'scroll');
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: react-dashboard-migration, Property 4: Table Feature Completeness
 * For any data table in the application, the table should provide sorting, 
 * filtering, and pagination capabilities
 */
describe('Property 4: Table Feature Completeness', () => {
  it('should provide sorting, filtering, and pagination for all tables', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...TABLE_COMPONENTS),
        (TableComponent) => {
          const { container } = render(<TableComponent data={mockData} />);
          
          // Check for sorting controls
          const sortButtons = container.querySelectorAll('[data-sort]');
          expect(sortButtons.length).toBeGreaterThan(0);
          
          // Check for filter controls
          const filterInputs = container.querySelectorAll('[data-filter]');
          expect(filterInputs.length).toBeGreaterThan(0);
          
          // Check for pagination controls
          const paginationControls = container.querySelector('[data-pagination]');
          expect(paginationControls).toBeInTheDocument();
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: react-dashboard-migration, Property 5: Action Feedback Consistency
 * For any user action, the UI should display a loading state during execution 
 * and success/error feedback upon completion
 */
describe('Property 5: Action Feedback Consistency', () => {
  it('should show loading and feedback for all actions', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...USER_ACTIONS),
        async (action) => {
          render(<DashboardPage />);
          
          // Trigger action
          const actionButton = screen.getByTestId(action.testId);
          fireEvent.click(actionButton);
          
          // Check loading state appears
          expect(screen.getByTestId('loading-indicator')).toBeInTheDocument();
          
          // Wait for completion
          await waitFor(() => {
            expect(screen.queryByTestId('loading-indicator')).not.toBeInTheDocument();
          });
          
          // Check feedback appears (success or error)
          const feedback = screen.getByTestId('action-feedback');
          expect(feedback).toBeInTheDocument();
          expect(feedback).toHaveTextContent(/success|error/i);
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: react-dashboard-migration, Property 8: Form Validation Consistency
 * For any form with validation rules, submitting with invalid data should 
 * prevent submission, highlight invalid fields, and display error messages
 */
describe('Property 8: Form Validation Consistency', () => {
  it('should validate all forms consistently', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...FORM_COMPONENTS),
        fc.record({
          // Generate invalid form data
          field1: fc.string().filter(s => s.length === 0), // empty string
          field2: fc.integer({ min: -100, max: -1 }), // negative number
        }),
        (FormComponent, invalidData) => {
          const onSubmit = jest.fn();
          render(<FormComponent onSubmit={onSubmit} />);
          
          // Fill form with invalid data
          Object.entries(invalidData).forEach(([field, value]) => {
            const input = screen.getByLabelText(new RegExp(field, 'i'));
            fireEvent.change(input, { target: { value } });
          });
          
          // Try to submit
          fireEvent.click(screen.getByRole('button', { name: /submit/i }));
          
          // Verify submission was prevented
          expect(onSubmit).not.toHaveBeenCalled();
          
          // Verify error messages are displayed
          const errorMessages = screen.getAllByRole('alert');
          expect(errorMessages.length).toBeGreaterThan(0);
          
          // Verify invalid fields are highlighted
          Object.keys(invalidData).forEach((field) => {
            const input = screen.getByLabelText(new RegExp(field, 'i'));
            expect(input).toHaveClass(/error|invalid/);
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: react-dashboard-migration, Property 10: Authentication Token Inclusion
 * For any API request made by the authenticated frontend, the request should 
 * include the authentication token in the headers
 */
describe('Property 10: Authentication Token Inclusion', () => {
  it('should include auth token in all API requests', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...API_ENDPOINTS),
        fc.string({ minLength: 20, maxLength: 100 }), // auth token
        async (endpoint, authToken) => {
          // Set auth token
          localStorage.setItem('auth_token', authToken);
          
          // Intercept request
          let requestHeaders: Headers | null = null;
          server.use(
            rest.get(endpoint.url, (req, res, ctx) => {
              requestHeaders = req.headers;
              return res(ctx.json({}));
            })
          );
          
          // Make request
          await apiClient.get(endpoint.url);
          
          // Verify token is in headers
          expect(requestHeaders?.get('Authorization')).toBe(`Bearer ${authToken}`);
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: react-dashboard-migration, Property 13: Data Caching Behavior
 * For any API endpoint marked as cacheable, repeated requests within the cache 
 * TTL should not trigger new network requests
 */
describe('Property 13: Data Caching Behavior', () => {
  it('should cache data for cacheable endpoints', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CACHEABLE_ENDPOINTS),
        fc.integer({ min: 1, max: 10 }), // number of repeated requests
        async (endpoint, requestCount) => {
          let networkRequestCount = 0;
          
          server.use(
            rest.get(endpoint.url, (req, res, ctx) => {
              networkRequestCount++;
              return res(ctx.json({ data: 'test' }));
            })
          );
          
          // Make multiple requests
          for (let i = 0; i < requestCount; i++) {
            await apiClient.get(endpoint.url);
          }
          
          // Verify only one network request was made
          expect(networkRequestCount).toBe(1);
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: react-dashboard-migration, Property 17: Active Menu Highlighting
 * For any current route, the corresponding menu item in the sidebar should be 
 * visually highlighted as active
 */
describe('Property 17: Active Menu Highlighting', () => {
  it('should highlight active menu item for any route', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...DASHBOARD_ROUTES),
        (route) => {
          render(
            <Router initialEntries={[route]}>
              <Sidebar />
            </Router>
          );
          
          // Find the menu item for this route
          const menuItem = screen.getByRole('link', { href: route });
          
          // Verify it has active styling
          expect(menuItem).toHaveClass(/active|selected|current/);
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: react-dashboard-migration, Property 18: Menu Link Validity
 * For any menu item with a link, clicking that link should navigate to a 
 * valid, implemented page (not a 404 or error page)
 */
describe('Property 18: Menu Link Validity', () => {
  it('should navigate to valid pages for all menu links', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...MENU_ITEMS),
        async (menuItem) => {
          render(<App />);
          
          // Click menu item
          const link = screen.getByRole('link', { name: menuItem.name });
          fireEvent.click(link);
          
          // Wait for navigation
          await waitFor(() => {
            // Verify we're not on a 404 page
            expect(screen.queryByText(/404|not found/i)).not.toBeInTheDocument();
            
            // Verify we're not on an error page
            expect(screen.queryByText(/error|something went wrong/i)).not.toBeInTheDocument();
            
            // Verify page content loaded
            expect(screen.getByRole('main')).toBeInTheDocument();
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});
```

### End-to-End Testing

**E2E Test Scenarios:**
- Complete user workflows (start scraper → view tasks → check logs)
- Multi-page navigation flows
- Real-time update scenarios
- Error recovery scenarios
- Authentication flows

**Example E2E Tests:**
```typescript
describe('Scraper Management E2E', () => {
  it('should complete full scraper workflow', () => {
    // Login
    cy.visit('/login');
    cy.get('[data-testid="username"]').type('admin');
    cy.get('[data-testid="password"]').type('password');
    cy.get('[data-testid="login-button"]').click();
    
    // Navigate to dashboard
    cy.url().should('include', '/dashboard');
    
    // Start a scraper
    cy.get('[data-testid="scraper-macmap-tariff"]').within(() => {
      cy.get('[data-testid="start-button"]').click();
    });
    
    // Verify scraper started
    cy.get('[data-testid="scraper-macmap-tariff"]').should('contain', 'Running');
    
    // Navigate to tasks
    cy.get('[data-testid="menu-tasks"]').click();
    cy.url().should('include', '/dashboard/tasks');
    
    // Verify tasks are visible
    cy.get('[data-testid="task-table"]').should('be.visible');
    cy.get('[data-testid="task-row"]').should('have.length.greaterThan', 0);
    
    // Navigate to logs
    cy.get('[data-testid="menu-logs"]').click();
    cy.url().should('include', '/dashboard/logs');
    
    // Verify logs are streaming
    cy.get('[data-testid="log-entry"]').should('have.length.greaterThan', 0);
    
    // Stop the scraper
    cy.get('[data-testid="menu-home"]').click();
    cy.get('[data-testid="scraper-macmap-tariff"]').within(() => {
      cy.get('[data-testid="stop-button"]').click();
    });
    
    // Verify scraper stopped
    cy.get('[data-testid="scraper-macmap-tariff"]').should('contain', 'Stopped');
  });
});
```

### Test Coverage Goals

- **Unit Test Coverage**: 80% of components, hooks, and utilities
- **Integration Test Coverage**: All API endpoints and critical user flows
- **Property-Based Test Coverage**: All 20 correctness properties
- **E2E Test Coverage**: All major user workflows

### Continuous Testing

- Run unit tests on every commit
- Run integration tests on every pull request
- Run E2E tests before deployment
- Run property-based tests nightly
- Monitor test execution time and optimize slow tests

## Conclusion

This design document provides a comprehensive blueprint for migrating the existing Python/FastAPI dashboard to a modern React frontend. The architecture maintains backward compatibility with the existing backend while introducing modern frontend patterns, real-time updates, and improved user experience. The correctness properties ensure that all critical functionality is properly tested and validated throughout the development process.
