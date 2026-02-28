import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import type { ApiEndpoint, ApiCheckHistory, ApiUptime, ApiResponse } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { StatusBadge } from '@/components/StatusBadge';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState } from '@/components/EmptyState';
import {
  Activity,
  Plus,
  Pencil,
  Trash2,
  Play,
  Eye,
  Loader2,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'];

interface EndpointForm {
  name: string;
  url: string;
  method: string;
  expected_status_code: number;
  headers: string;
  request_body: string;
  check_interval_seconds: number;
  is_active: boolean;
}

const emptyForm: EndpointForm = {
  name: '',
  url: '',
  method: 'GET',
  expected_status_code: 200,
  headers: '',
  request_body: '',
  check_interval_seconds: 60,
  is_active: true,
};

export default function ApiMonitor() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string>('all');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<EndpointForm>(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState<ApiEndpoint | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [checkingId, setCheckingId] = useState<number | null>(null);

  // --- Queries ---
  const { data: endpoints, isLoading } = useQuery({
    queryKey: ['endpoints'],
    queryFn: () => api.get<ApiResponse<ApiEndpoint[]>>('/endpoints').then(r => r.data.data),
  });

  const { data: history } = useQuery({
    queryKey: ['endpoint-history', detailId],
    queryFn: () => api.get<ApiResponse<ApiCheckHistory[]>>(`/endpoints/${detailId}/history?days=7`).then(r => r.data.data),
    enabled: detailId !== null,
  });

  const { data: uptime } = useQuery({
    queryKey: ['endpoint-uptime', detailId],
    queryFn: () => api.get<ApiResponse<ApiUptime>>(`/endpoints/${detailId}/uptime?days=7`).then(r => r.data.data),
    enabled: detailId !== null,
  });

  // --- Mutations ---
  const createMut = useMutation({
    mutationFn: (data: Partial<ApiEndpoint>) => api.post('/endpoints', data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['endpoints'] }); setFormOpen(false); },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ApiEndpoint> }) => api.put(`/endpoints/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['endpoints'] }); setFormOpen(false); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/endpoints/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['endpoints'] }); setDeleteTarget(null); },
  });

  const checkMut = useMutation({
    mutationFn: (id: number) => api.post(`/endpoints/${id}/check`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['endpoints'] }),
    onSettled: () => setCheckingId(null),
  });

  // --- Handlers ---
  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setFormOpen(true);
  };

  const openEdit = (ep: ApiEndpoint) => {
    setEditingId(ep.id);
    setForm({
      name: ep.name,
      url: ep.url,
      method: ep.method,
      expected_status_code: ep.expected_status_code,
      headers: ep.headers ?? '',
      request_body: ep.request_body ?? '',
      check_interval_seconds: ep.check_interval_seconds,
      is_active: ep.is_active,
    });
    setFormOpen(true);
  };

  const handleSubmit = () => {
    const payload = {
      ...form,
      headers: form.headers.trim() || null,
      request_body: form.request_body.trim() || null,
    };
    if (editingId) {
      updateMut.mutate({ id: editingId, data: payload });
    } else {
      createMut.mutate(payload);
    }
  };

  const handleCheck = (id: number) => {
    setCheckingId(id);
    checkMut.mutate(id);
  };

  // --- Filter ---
  const filtered = endpoints?.filter(ep => {
    if (filter === 'all') return true;
    return ep.status === filter;
  }) ?? [];

  const detailEndpoint = endpoints?.find(e => e.id === detailId);

  const chartData = history?.map(h => ({
    time: new Date(h.checked_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    ms: h.response_time_ms ?? 0,
  })).reverse() ?? [];

  const isSaving = createMut.isPending || updateMut.isPending;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-[#C9D1D9]">API Monitor</h2>
        <Button onClick={openCreate} className="bg-[#238636] hover:bg-[#2ea043]">
          <Plus className="h-4 w-4 mr-1" /> Add Endpoint
        </Button>
      </div>

      {/* Filter Badges */}
      <div className="flex gap-2">
        {['all', 'healthy', 'unhealthy', 'unknown'].map(f => (
          <Badge
            key={f}
            variant={filter === f ? 'default' : 'outline'}
            className={`cursor-pointer capitalize ${
              filter === f
                ? 'bg-[#238636] text-white hover:bg-[#2ea043]'
                : 'border-[#30363D] text-[#8B949E] hover:bg-[#21262D]'
            }`}
            onClick={() => setFilter(f)}
          >
            {f} {f !== 'all' && endpoints ? `(${endpoints.filter(e => f === 'all' || e.status === f).length})` : ''}
          </Badge>
        ))}
      </div>

      {/* Table */}
      <Card className="border-[#30363D] bg-[#0D1117]">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-12 bg-[#21262D]" />)}
            </div>
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={Activity}
              title="No endpoints"
              description="Add your first API endpoint to start monitoring."
              actionLabel="Add Endpoint"
              onAction={openCreate}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-[#30363D] hover:bg-transparent">
                  <TableHead className="text-[#8B949E]">Name</TableHead>
                  <TableHead className="text-[#8B949E]">URL</TableHead>
                  <TableHead className="text-[#8B949E]">Method</TableHead>
                  <TableHead className="text-[#8B949E]">Status</TableHead>
                  <TableHead className="text-[#8B949E]">Response</TableHead>
                  <TableHead className="text-[#8B949E]">Last Check</TableHead>
                  <TableHead className="text-[#8B949E] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map(ep => (
                  <TableRow key={ep.id} className="border-[#30363D] hover:bg-[#161B22]">
                    <TableCell className="text-[#C9D1D9] font-medium">{ep.name}</TableCell>
                    <TableCell className="text-[#8B949E] text-xs max-w-[200px] truncate">{ep.url}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="border-[#30363D] text-[#8B949E] text-xs">
                        {ep.method}
                      </Badge>
                    </TableCell>
                    <TableCell><StatusBadge status={ep.status} variant="api" /></TableCell>
                    <TableCell className="text-[#8B949E] text-sm">
                      {ep.response_time != null ? `${Math.round(ep.response_time)}ms` : '--'}
                    </TableCell>
                    <TableCell className="text-[#8B949E] text-xs">
                      {ep.last_check ? new Date(ep.last_check).toLocaleString() : 'Never'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]"
                          onClick={() => handleCheck(ep.id)}
                          disabled={checkingId === ep.id}
                        >
                          {checkingId === ep.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]"
                          onClick={() => setDetailId(ep.id)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]"
                          onClick={() => openEdit(ep)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-[#8B949E] hover:text-red-400 hover:bg-[#21262D]"
                          onClick={() => setDeleteTarget(ep)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create / Edit Dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">
              {editingId ? 'Edit Endpoint' : 'Add Endpoint'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-[#C9D1D9]">Name *</Label>
              <Input
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"
                placeholder="My API"
              />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">URL *</Label>
              <Input
                value={form.url}
                onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
                className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"
                placeholder="https://api.example.com/health"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-[#C9D1D9]">Method</Label>
                <Select value={form.method} onValueChange={v => setForm(f => ({ ...f, method: v }))}>
                  <SelectTrigger className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#161B22] border-[#30363D]">
                    {HTTP_METHODS.map(m => (
                      <SelectItem key={m} value={m} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-[#C9D1D9]">Expected Status</Label>
                <Input
                  type="number"
                  value={form.expected_status_code}
                  onChange={e => setForm(f => ({ ...f, expected_status_code: parseInt(e.target.value) || 200 }))}
                  className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"
                />
              </div>
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Headers (JSON)</Label>
              <Textarea
                value={form.headers}
                onChange={e => setForm(f => ({ ...f, headers: e.target.value }))}
                className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1 font-mono text-xs"
                rows={3}
                placeholder='{"Authorization": "Bearer ..."}'
              />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Request Body</Label>
              <Textarea
                value={form.request_body}
                onChange={e => setForm(f => ({ ...f, request_body: e.target.value }))}
                className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1 font-mono text-xs"
                rows={3}
                placeholder='{"key": "value"}'
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-[#C9D1D9]">Interval (sec)</Label>
                <Input
                  type="number"
                  value={form.check_interval_seconds}
                  onChange={e => setForm(f => ({ ...f, check_interval_seconds: parseInt(e.target.value) || 60 }))}
                  className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))}
                    className="rounded"
                  />
                  <span className="text-sm text-[#C9D1D9]">Active</span>
                </label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setFormOpen(false)} className="text-[#8B949E] hover:bg-[#21262D]">
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!form.name.trim() || !form.url.trim() || isSaving}
              className="bg-[#238636] hover:bg-[#2ea043]"
            >
              {isSaving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              {editingId ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirm */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={open => { if (!open) setDeleteTarget(null); }}
        title="Delete Endpoint"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        onConfirm={() => deleteTarget && deleteMut.mutate(deleteTarget.id)}
      />

      {/* Detail Dialog */}
      <Dialog open={detailId !== null} onOpenChange={open => { if (!open) setDetailId(null); }}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">
              {detailEndpoint?.name ?? 'Endpoint Detail'}
            </DialogTitle>
          </DialogHeader>
          {detailEndpoint && (
            <div className="space-y-6">
              {/* Info */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-[#8B949E]">URL: </span>
                  <span className="text-[#C9D1D9] break-all">{detailEndpoint.url}</span>
                </div>
                <div>
                  <span className="text-[#8B949E]">Method: </span>
                  <Badge variant="outline" className="border-[#30363D] text-[#8B949E]">{detailEndpoint.method}</Badge>
                </div>
                <div>
                  <span className="text-[#8B949E]">Status: </span>
                  <StatusBadge status={detailEndpoint.status} variant="api" />
                </div>
                <div>
                  <span className="text-[#8B949E]">Uptime (7d): </span>
                  <span className="text-[#C9D1D9]">{uptime ? `${uptime.uptime_percent.toFixed(1)}%` : '--'}</span>
                </div>
              </div>

              {/* Response Time Chart */}
              <Card className="border-[#30363D] bg-[#0D1117]">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-[#8B949E]">Response Time (7 days)</CardTitle>
                </CardHeader>
                <CardContent>
                  {chartData.length === 0 ? (
                    <p className="text-sm text-[#8B949E] text-center py-4">No history data.</p>
                  ) : (
                    <ResponsiveContainer width="100%" height={200}>
                      <LineChart data={chartData}>
                        <XAxis dataKey="time" tick={{ fill: '#8B949E', fontSize: 10 }} />
                        <YAxis tick={{ fill: '#8B949E', fontSize: 10 }} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#161B22', border: '1px solid #30363D', borderRadius: 6 }}
                          itemStyle={{ color: '#C9D1D9' }}
                          labelStyle={{ color: '#8B949E' }}
                        />
                        <Line type="monotone" dataKey="ms" stroke="#58A6FF" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              {/* History */}
              {history && history.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-[#8B949E] mb-2">Recent Checks</h4>
                  <div className="space-y-1 max-h-[200px] overflow-y-auto">
                    {history.slice(0, 20).map(h => (
                      <div key={h.id} className="flex items-center justify-between text-xs px-3 py-1.5 rounded border border-[#30363D] bg-[#0D1117]">
                        <div className="flex items-center gap-2">
                          <StatusBadge status={h.status} variant="api" />
                          <span className="text-[#8B949E]">{h.status_code ?? '--'}</span>
                        </div>
                        <div className="flex items-center gap-4">
                          <span className="text-[#8B949E]">{h.response_time_ms != null ? `${h.response_time_ms}ms` : '--'}</span>
                          <span className="text-[#484F58]">{new Date(h.checked_at).toLocaleString()}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
