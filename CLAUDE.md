# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QA Management Platform — a multi-tenant SaaS tool for QA teams. Features include API health monitoring, test case management, test project tracking, coverage analysis, member invitation, and Jira integration. Built with a Flask REST API backend and React SPA frontend.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Flask 3.1, SQLAlchemy 2.0, Alembic, PostgreSQL |
| **Auth** | JWT (PyJWT) + bcrypt, stateless access/refresh tokens |
| **Frontend** | React 19, TypeScript, TanStack Query, shadcn/ui, Tailwind CSS 4, Recharts |
| **Routing** | React Router 7 |
| **Build** | Vite 7 |

## Development Principles

1. **模組化開發** — 單一職責、模組間通過接口通信、避免緊耦合
2. **完成開發後徹底自行驗證** — 測試所有交互路徑和邊界條件
3. **不得提交測試資料或 DB 資料** — `.gitignore` 已排除 `*.db`、`data/`、`*.png` 等

## Development Commands

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run dev server (port 5001)
flask --app app_factory:create_app run --port 5001

# Run tests
python -m pytest tests/ -v

# Alembic migrations
alembic upgrade head                    # Apply all migrations
alembic revision --autogenerate -m "description"  # Create new migration
```

### Frontend

```bash
cd frontend
npm install

# Dev server (port 5173, proxies /api to :5001)
npm run dev

# Type check + build
npx tsc --noEmit && npm run build
```

### Ports

- Backend API: `http://localhost:5001`
- Frontend dev: `http://localhost:5173`

## Architecture

### Monorepo Structure

```
backend/
  app_factory.py          # Flask app factory (creates app, registers blueprints)
  config.py               # Environment-based configuration
  database/
    models.py             # SQLAlchemy ORM models (13 tables)
    session.py            # Engine + SessionLocal factory
    migrations/versions/  # Alembic version files
  middleware/
    auth.py               # JWT creation, @jwt_required, @admin_required
    tenant.py             # Multi-tenant middleware (g.tenant_id)
  routes/                 # Flask Blueprints (one per feature)
    auth.py               # /api/auth/* (register, login, refresh, join, invite)
    members.py            # /api/members/* (list, role, deactivate, invite-links)
    api_monitor.py        # /api/apis/*
    test_cases.py         # /api/test-cases/*
    test_projects.py      # /api/test-projects/*
    coverage.py           # /api/coverage/*
    jira.py               # /api/jira/*
    product_tags.py       # /api/product-tags/*
    notifications.py      # /api/notifications/*
    reports.py            # /api/reports/*
  services/               # Business logic (one per feature)
  tests/                  # Pytest test suite

frontend/
  src/
    App.tsx               # Route definitions
    contexts/AuthProvider  # JWT state, login/register/joinViaInvite
    layouts/DashboardLayout # Sidebar + header + Outlet
    pages/                # One page per feature
      Dashboard, ApiMonitor, TestCases, TestProjects,
      Coverage, Members, JiraSettings, Join, Login, Register, Upgrade
    components/           # Shared UI (ConfirmDialog, EmptyState, StatusBadge)
    components/ui/        # shadcn/ui primitives
    services/api.ts       # Axios instance with JWT interceptor
    types/index.ts        # TypeScript interfaces
```

### Multi-Tenant Model

- Every org gets an `Organization` with a 14-day trial
- All business tables have `tenant_id` (UUID FK to organizations)
- `@jwt_required` sets `g.tenant_id` from JWT; all queries filter by it
- Tenant isolation verified in `tests/test_tenant_isolation.py`

### Auth Flow

- **Register**: POST `/api/auth/register` → creates Org + admin User → returns JWT
- **Login**: POST `/api/auth/login` → returns access_token (1h) + refresh_token (30d)
- **Refresh**: POST `/api/auth/refresh` → new access_token
- **Invite join**: GET `/api/auth/invite/<token>` (validate) → POST `/api/auth/join` (register into existing org)
- Trial enforcement: expired trials block POST/PUT/DELETE

### Database (13 tables)

organizations, users, invite_links, api_endpoints, api_check_history, product_tags, test_projects, test_cases, test_case_tags, test_results, api_testcase_links, jira_issue_links, alembic_version

Alembic migration chain: `742584645af3` → `a1b2c3d4e5f6` → `b2c3d4e5f6a7` → `c3d4e5f6a7b8` → `d4e5f6a7b8c9`

### Frontend Pages

| Page | Route | Key Features |
|------|-------|-------------|
| Dashboard | `/dashboard` | Stats cards, health PieChart, project progress bars |
| API Monitor | `/api-monitor` | CRUD, Check Now, response time LineChart, uptime % |
| Test Cases | `/test-cases` | CRUD, custom TC ID, filters, CSV import/export, product tags |
| Test Projects | `/test-projects` | CRUD, case assignment, per-case results, assignee dropdown, reports |
| Coverage | `/coverage` | Stats, uncovered APIs, alerts, PieChart |
| Members | `/members` | Member list, role changes, deactivation, invite links (create/copy/revoke) |
| Jira Settings | `/jira` | API Token auth (connect/test/disconnect), project list, bug template config |
| Join | `/join?token=xxx` | Public invite page |

## Color Scheme (GitHub dark theme)

- Background: `#0D1117` / `#161B22`
- Text: `#C9D1D9` (primary) / `#8B949E` (secondary)
- Borders: `#30363D`
- Green accent: `#238636`

## Testing

```bash
# Run all backend tests
cd backend && python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_members.py -v

# Frontend type check
cd frontend && npx tsc --noEmit
```

## API Response Convention

All API responses follow:
```json
{ "data": <payload> }           // success
{ "error": "message" }          // error
```

## Key Conventions

- **Route blueprints**: One file per feature in `backend/routes/`, registered in `app_factory.py`
- **Services**: One file per feature in `backend/services/`, receives `db` session as first arg
- **Tenant filtering**: All service queries must include `.filter_by(tenant_id=g.tenant_id)`
- **Frontend queries**: TanStack Query with `queryKey` arrays; mutations invalidate related queries
- **Components**: shadcn/ui for primitives; custom components for domain logic (StatusBadge, ConfirmDialog, EmptyState)
