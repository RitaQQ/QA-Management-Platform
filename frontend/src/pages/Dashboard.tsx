import { useAuth } from '@/hooks/useAuth';
import { useQuery } from '@tanstack/react-query';
import api from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { StatusBadge } from '@/components/StatusBadge';
import {
  Activity,
  FileText,
  FolderKanban,
  AlertTriangle,
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import type { ApiEndpoint, TestCase, TestProject, CoverageAlert } from '@/types';

export default function Dashboard() {
  const { user } = useAuth();

  const { data: endpoints, isLoading: loadingEndpoints } = useQuery({
    queryKey: ['endpoints'],
    queryFn: () => api.get<{ data: ApiEndpoint[] }>('/endpoints').then(r => r.data.data),
  });

  const { data: testCases, isLoading: loadingCases } = useQuery({
    queryKey: ['test-cases'],
    queryFn: () => api.get<{ data: TestCase[] }>('/test-cases').then(r => r.data.data),
  });

  const { data: projects, isLoading: loadingProjects } = useQuery({
    queryKey: ['test-projects'],
    queryFn: () => api.get<{ data: TestProject[] }>('/test-projects').then(r => r.data.data),
  });

  const { data: alerts, isLoading: loadingAlerts } = useQuery({
    queryKey: ['coverage-alerts'],
    queryFn: () => api.get<{ data: CoverageAlert[] }>('/coverage/alerts').then(r => r.data.data),
  });

  const healthyCount = endpoints?.filter(e => e.status === 'healthy').length ?? 0;
  const unhealthyCount = endpoints?.filter(e => e.status === 'unhealthy').length ?? 0;
  const activeProjects = projects?.filter(p => p.status === 'in_progress').length ?? 0;

  const pieData = endpoints && endpoints.length > 0
    ? [
        { name: 'Healthy', value: healthyCount, color: '#3FB950' },
        { name: 'Unhealthy', value: unhealthyCount, color: '#F85149' },
        { name: 'Unknown', value: endpoints.length - healthyCount - unhealthyCount, color: '#8B949E' },
      ].filter(d => d.value > 0)
    : [];

  const statCards = [
    {
      title: 'API Endpoints',
      value: endpoints?.length,
      description: `${healthyCount} healthy, ${unhealthyCount} unhealthy`,
      icon: Activity,
      color: 'text-[#58A6FF]',
      loading: loadingEndpoints,
    },
    {
      title: 'Test Cases',
      value: testCases?.length,
      description: 'Total test cases',
      icon: FileText,
      color: 'text-[#3FB950]',
      loading: loadingCases,
    },
    {
      title: 'Test Projects',
      value: projects?.length,
      description: `${activeProjects} active`,
      icon: FolderKanban,
      color: 'text-[#D2A8FF]',
      loading: loadingProjects,
    },
    {
      title: 'Alerts',
      value: alerts?.length,
      description: 'Open alerts',
      icon: AlertTriangle,
      color: 'text-[#D29922]',
      loading: loadingAlerts,
    },
  ];

  const topEndpoints = endpoints?.slice(0, 5) ?? [];
  const topProjects = projects?.filter(p => p.status === 'in_progress').slice(0, 3) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-[#C9D1D9]">
          Welcome back, {user?.username ?? 'User'}
        </h2>
        <p className="text-[#8B949E] mt-1">
          Here&apos;s an overview of your QA platform activity.
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => (
          <Card key={card.title} className="border-[#30363D] bg-[#0D1117]">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-[#8B949E]">
                {card.title}
              </CardTitle>
              <card.icon className={`h-4 w-4 ${card.color}`} />
            </CardHeader>
            <CardContent>
              {card.loading ? (
                <Skeleton className="h-8 w-16 bg-[#21262D]" />
              ) : (
                <div className="text-2xl font-bold text-[#C9D1D9]">
                  {card.value ?? '--'}
                </div>
              )}
              <p className="text-xs text-[#484F58] mt-1">{card.description}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Recent API Status */}
        <Card className="border-[#30363D] bg-[#0D1117] lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-[#C9D1D9] text-base">Recent API Status</CardTitle>
          </CardHeader>
          <CardContent>
            {loadingEndpoints ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 bg-[#21262D]" />)}
              </div>
            ) : topEndpoints.length === 0 ? (
              <p className="text-sm text-[#8B949E]">No API endpoints yet.</p>
            ) : (
              <div className="space-y-3">
                {topEndpoints.map(ep => (
                  <div key={ep.id} className="flex items-center justify-between rounded-md border border-[#30363D] bg-[#161B22] px-4 py-2.5">
                    <div className="flex items-center gap-3 min-w-0">
                      <StatusBadge status={ep.status} variant="api" />
                      <span className="text-sm text-[#C9D1D9] truncate">{ep.name}</span>
                    </div>
                    <span className="text-xs text-[#8B949E] shrink-0 ml-2">
                      {ep.response_time != null ? `${Math.round(ep.response_time)}ms` : '--'}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Coverage Pie Chart */}
        <Card className="border-[#30363D] bg-[#0D1117]">
          <CardHeader>
            <CardTitle className="text-[#C9D1D9] text-base">API Health</CardTitle>
          </CardHeader>
          <CardContent>
            {loadingEndpoints ? (
              <Skeleton className="h-[180px] bg-[#21262D] rounded-md" />
            ) : pieData.length === 0 ? (
              <p className="text-sm text-[#8B949E] text-center py-8">No data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={70}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {pieData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#161B22', border: '1px solid #30363D', borderRadius: 6 }}
                    itemStyle={{ color: '#C9D1D9' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
            {!loadingEndpoints && pieData.length > 0 && (
              <div className="flex justify-center gap-4 mt-2">
                {pieData.map(d => (
                  <div key={d.name} className="flex items-center gap-1.5 text-xs text-[#8B949E]">
                    <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                    {d.name} ({d.value})
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Active Projects */}
      {topProjects.length > 0 && (
        <Card className="border-[#30363D] bg-[#0D1117]">
          <CardHeader>
            <CardTitle className="text-[#C9D1D9] text-base">Active Projects</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {topProjects.map(p => (
              <div key={p.id} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-[#C9D1D9]">{p.name}</span>
                  <span className="text-xs text-[#8B949E]">
                    {p.stats.completion_rate.toFixed(0)}%
                  </span>
                </div>
                <Progress value={p.stats.completion_rate} className="h-2 bg-[#21262D]" />
                <div className="flex gap-3 text-xs text-[#8B949E]">
                  <span className="text-emerald-400">{p.stats.pass_count} pass</span>
                  <span className="text-red-400">{p.stats.fail_count} fail</span>
                  <span className="text-orange-400">{p.stats.blocked_count} blocked</span>
                  <span>{p.stats.not_tested_count} pending</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
