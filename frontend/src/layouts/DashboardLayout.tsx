import { useState, useEffect } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  LayoutDashboard,
  Activity,
  FileText,
  FolderKanban,
  Link2,
  Settings,
  Users,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut,
  User,
  ChevronDown,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/api-monitor', label: 'API Monitor', icon: Activity },
  { to: '/test-cases', label: 'Test Cases', icon: FileText },
  { to: '/test-projects', label: 'Test Projects', icon: FolderKanban },
  { to: '/coverage', label: 'Coverage', icon: Link2 },
  { to: '/members', label: 'Members', icon: Users },
  { to: '/jira', label: 'Jira Settings', icon: Settings },
];

const SIDEBAR_KEY = 'sidebar_collapsed';

function getTrialDaysRemaining(trialEndsAt: string | null): number | null {
  if (!trialEndsAt) return null;
  const end = new Date(trialEndsAt);
  const now = new Date();
  const diff = Math.ceil((end.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  return diff > 0 ? diff : 0;
}

export default function DashboardLayout() {
  const { user, organization, logout } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem(SIDEBAR_KEY) === 'true';
  });

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, String(collapsed));
  }, [collapsed]);

  const trialDays = getTrialDaysRemaining(organization?.trial_ends_at ?? null);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="flex h-screen overflow-hidden bg-[#0D1117]">
      {/* Sidebar */}
      <aside
        className={`flex flex-col border-r border-[#30363D] bg-[#0D1117] transition-all duration-200 ${
          collapsed ? 'w-16' : 'w-60'
        }`}
      >
        {/* Logo area */}
        <div className="flex h-14 items-center border-b border-[#30363D] px-4">
          {!collapsed && (
            <span className="text-lg font-bold text-[#C9D1D9] truncate">
              QA Platform
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setCollapsed(!collapsed)}
            className={`text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#161B22] ${
              collapsed ? 'mx-auto' : 'ml-auto'
            }`}
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-1">
          {NAV_ITEMS.map((item) => {
            const link = (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-[#161B22] text-[#C9D1D9]'
                      : 'text-[#8B949E] hover:bg-[#161B22] hover:text-[#C9D1D9]'
                  } ${collapsed ? 'justify-center px-0' : ''}`
                }
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </NavLink>
            );

            if (collapsed) {
              return (
                <Tooltip key={item.to} delayDuration={0}>
                  <TooltipTrigger asChild>{link}</TooltipTrigger>
                  <TooltipContent side="right" className="bg-[#161B22] text-[#C9D1D9] border-[#30363D]">
                    {item.label}
                  </TooltipContent>
                </Tooltip>
              );
            }

            return link;
          })}
        </nav>

        {/* User section at bottom */}
        <div className="border-t border-[#30363D] p-2">
          {collapsed ? (
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleLogout}
                  className="w-full text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#161B22]"
                >
                  <LogOut className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right" className="bg-[#161B22] text-[#C9D1D9] border-[#30363D]">
                Logout ({user?.username})
              </TooltipContent>
            </Tooltip>
          ) : (
            <div className="flex items-center gap-2 rounded-md px-3 py-2">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#238636] text-xs font-bold text-white">
                {user?.username?.charAt(0).toUpperCase() ?? 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium text-[#C9D1D9]">
                  {user?.username}
                </p>
                <p className="truncate text-xs text-[#484F58]">{user?.role}</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleLogout}
                className="h-7 w-7 shrink-0 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#161B22]"
              >
                <LogOut className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 items-center justify-between border-b border-[#30363D] bg-[#161B22] px-6">
          <div className="flex items-center gap-3">
            {organization && (
              <span className="text-sm font-medium text-[#C9D1D9]">
                {organization.name}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            {trialDays !== null && trialDays > 0 && (
              <Badge
                variant="outline"
                className="border-[#D29922]/40 bg-[#D29922]/10 text-[#D29922]"
              >
                {trialDays} day{trialDays === 1 ? '' : 's'} left in trial
              </Badge>
            )}
            {trialDays === 0 && (
              <Badge
                variant="outline"
                className="border-red-500/40 bg-red-500/10 text-red-400"
              >
                Trial expired
              </Badge>
            )}

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="flex items-center gap-2 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#0D1117]"
                >
                  <User className="h-4 w-4" />
                  <span className="text-sm">{user?.username}</span>
                  <ChevronDown className="h-3 w-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="w-48 border-[#30363D] bg-[#161B22] text-[#C9D1D9]"
              >
                <div className="px-2 py-1.5">
                  <p className="text-sm font-medium">{user?.username}</p>
                  <p className="text-xs text-[#8B949E]">{user?.email}</p>
                </div>
                <DropdownMenuSeparator className="bg-[#30363D]" />
                <DropdownMenuItem
                  onClick={handleLogout}
                  className="text-[#8B949E] focus:bg-[#0D1117] focus:text-[#C9D1D9] cursor-pointer"
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Content area */}
        <main className="flex-1 overflow-y-auto bg-[#0D1117] p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
