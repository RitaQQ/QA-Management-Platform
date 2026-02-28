import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import type { CoverageDashboard, CoverageAlert, ApiEndpoint, TestCase, ApiResponse } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import {
  Link2, Plus, AlertTriangle, Shield, Loader2,
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

export default function Coverage() {
  const qc = useQueryClient();
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkApiId, setLinkApiId] = useState('');
  const [linkCaseId, setLinkCaseId] = useState('');

  // Queries
  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['coverage-dashboard'],
    queryFn: () => api.get<ApiResponse<CoverageDashboard>>('/coverage/dashboard').then(r => r.data.data),
  });

  const { data: alerts } = useQuery({
    queryKey: ['coverage-alerts'],
    queryFn: () => api.get<ApiResponse<CoverageAlert[]>>('/coverage/alerts').then(r => r.data.data),
  });

  const { data: endpoints } = useQuery({
    queryKey: ['endpoints'],
    queryFn: () => api.get<ApiResponse<ApiEndpoint[]>>('/endpoints').then(r => r.data.data),
  });

  const { data: testCases } = useQuery({
    queryKey: ['test-cases-all'],
    queryFn: () => api.get<ApiResponse<TestCase[]>>('/test-cases').then(r => r.data.data),
  });

  // Mutations
  const linkMut = useMutation({
    mutationFn: (data: { api_id: number; test_case_id: number }) => api.post('/coverage/links', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['coverage-dashboard'] });
      qc.invalidateQueries({ queryKey: ['coverage-alerts'] });
      setLinkOpen(false);
      setLinkApiId('');
      setLinkCaseId('');
    },
  });

  const pieData = dashboard ? [
    { name: 'Covered', value: dashboard.covered_apis, color: '#3FB950' },
    { name: 'Uncovered', value: dashboard.uncovered_apis, color: '#F85149' },
  ].filter(d => d.value > 0) : [];

  const severityColor: Record<string, string> = {
    high: 'border-red-500/30 bg-red-500/10',
    medium: 'border-yellow-500/30 bg-yellow-500/10',
    low: 'border-blue-500/30 bg-blue-500/10',
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-[#C9D1D9]">Coverage</h2>
        <Button onClick={() => setLinkOpen(true)} className="bg-[#238636] hover:bg-[#2ea043]">
          <Plus className="h-4 w-4 mr-1" /> Create Link
        </Button>
      </div>

      {/* Stats */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24 bg-[#21262D]" />)}
        </div>
      ) : dashboard && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card className="border-[#30363D] bg-[#0D1117]">
            <CardContent className="p-4">
              <div className="text-sm text-[#8B949E]">Total APIs</div>
              <div className="text-2xl font-bold text-[#C9D1D9]">{dashboard.total_apis}</div>
            </CardContent>
          </Card>
          <Card className="border-[#30363D] bg-[#0D1117]">
            <CardContent className="p-4">
              <div className="text-sm text-[#8B949E]">Covered</div>
              <div className="text-2xl font-bold text-emerald-400">{dashboard.covered_apis}</div>
            </CardContent>
          </Card>
          <Card className="border-[#30363D] bg-[#0D1117]">
            <CardContent className="p-4">
              <div className="text-sm text-[#8B949E]">Uncovered</div>
              <div className="text-2xl font-bold text-red-400">{dashboard.uncovered_apis}</div>
            </CardContent>
          </Card>
          <Card className="border-[#30363D] bg-[#0D1117]">
            <CardContent className="p-4">
              <div className="text-sm text-[#8B949E]">Coverage</div>
              <div className="text-2xl font-bold text-[#C9D1D9]">{dashboard.coverage_percent.toFixed(1)}%</div>
              <Progress value={dashboard.coverage_percent} className="h-2 bg-[#21262D] mt-2" />
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Tabs */}
        <div className="lg:col-span-2">
          <Tabs defaultValue="uncovered">
            <TabsList className="bg-[#0D1117] border border-[#30363D]">
              <TabsTrigger value="uncovered" className="data-[state=active]:bg-[#21262D] text-[#8B949E] data-[state=active]:text-[#C9D1D9]">
                Uncovered ({dashboard?.uncovered_apis ?? 0})
              </TabsTrigger>
              <TabsTrigger value="alerts" className="data-[state=active]:bg-[#21262D] text-[#8B949E] data-[state=active]:text-[#C9D1D9]">
                Alerts ({alerts?.length ?? 0})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="uncovered">
              <Card className="border-[#30363D] bg-[#0D1117]">
                <CardContent className="p-0">
                  {!dashboard?.uncovered_api_list?.length ? (
                    <EmptyState icon={Shield} title="All covered" description="Every API endpoint has at least one linked test case." />
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow className="border-[#30363D] hover:bg-transparent">
                          <TableHead className="text-[#8B949E]">Name</TableHead>
                          <TableHead className="text-[#8B949E]">URL</TableHead>
                          <TableHead className="text-[#8B949E]">Status</TableHead>
                          <TableHead className="text-[#8B949E] text-right">Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {dashboard.uncovered_api_list.map(a => (
                          <TableRow key={a.id} className="border-[#30363D] hover:bg-[#161B22]">
                            <TableCell className="text-[#C9D1D9]">{a.name}</TableCell>
                            <TableCell className="text-[#8B949E] text-xs max-w-[200px] truncate">{a.url}</TableCell>
                            <TableCell><StatusBadge status={a.status} variant="api" /></TableCell>
                            <TableCell className="text-right">
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-[#58A6FF] hover:bg-[#21262D] text-xs"
                                onClick={() => { setLinkApiId(String(a.id)); setLinkOpen(true); }}
                              >
                                <Link2 className="h-3 w-3 mr-1" /> Link
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="alerts">
              {!alerts?.length ? (
                <Card className="border-[#30363D] bg-[#0D1117]">
                  <CardContent>
                    <EmptyState icon={AlertTriangle} title="No alerts" description="No coverage issues detected." />
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-3">
                  {alerts.map((a, i) => (
                    <Card key={i} className={`border ${severityColor[a.severity] ?? 'border-[#30363D]'}`}>
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <Badge variant="outline" className="text-xs capitalize border-[#30363D] text-[#8B949E]">{a.type.replace(/_/g, ' ')}</Badge>
                              <Badge variant="outline" className="text-xs capitalize border-[#30363D] text-[#8B949E]">{a.severity}</Badge>
                            </div>
                            <p className="text-sm text-[#C9D1D9]">{a.message}</p>
                            <p className="text-xs text-[#8B949E] mt-1">{a.target_name}</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>

        {/* Pie Chart */}
        <Card className="border-[#30363D] bg-[#0D1117]">
          <CardHeader>
            <CardTitle className="text-[#C9D1D9] text-base">Coverage Ratio</CardTitle>
          </CardHeader>
          <CardContent>
            {pieData.length === 0 ? (
              <p className="text-sm text-[#8B949E] text-center py-8">No data.</p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value">
                      {pieData.map(e => <Cell key={e.name} fill={e.color} />)}
                    </Pie>
                    <Tooltip
                      contentStyle={{ backgroundColor: '#161B22', border: '1px solid #30363D', borderRadius: 6 }}
                      itemStyle={{ color: '#C9D1D9' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex justify-center gap-4 mt-2">
                  {pieData.map(d => (
                    <div key={d.name} className="flex items-center gap-1.5 text-xs text-[#8B949E]">
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                      {d.name} ({d.value})
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Create Link Dialog */}
      <Dialog open={linkOpen} onOpenChange={open => { setLinkOpen(open); if (!open) { setLinkApiId(''); setLinkCaseId(''); } }}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-md">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">Create Coverage Link</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm text-[#C9D1D9]">API Endpoint</label>
              <Select value={linkApiId} onValueChange={setLinkApiId}>
                <SelectTrigger className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"><SelectValue placeholder="Select API" /></SelectTrigger>
                <SelectContent className="bg-[#161B22] border-[#30363D] max-h-[200px]">
                  {endpoints?.map(ep => (
                    <SelectItem key={ep.id} value={String(ep.id)} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">
                      {ep.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm text-[#C9D1D9]">Test Case</label>
              <Select value={linkCaseId} onValueChange={setLinkCaseId}>
                <SelectTrigger className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"><SelectValue placeholder="Select Test Case" /></SelectTrigger>
                <SelectContent className="bg-[#161B22] border-[#30363D] max-h-[200px]">
                  {testCases?.map(tc => (
                    <SelectItem key={tc.id} value={String(tc.id)} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">
                      {tc.tc_id} - {tc.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setLinkOpen(false)} className="text-[#8B949E] hover:bg-[#21262D]">Cancel</Button>
            <Button
              onClick={() => linkMut.mutate({ api_id: parseInt(linkApiId), test_case_id: parseInt(linkCaseId) })}
              disabled={!linkApiId || !linkCaseId || linkMut.isPending}
              className="bg-[#238636] hover:bg-[#2ea043]"
            >
              {linkMut.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              Link
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
