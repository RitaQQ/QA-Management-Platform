import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import type { TestProject, TestCase, ProjectTestCase, ApiResponse, JiraStatus, JiraProject, Member } from '@/types';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
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
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState } from '@/components/EmptyState';
import {
  FolderKanban, Plus, Pencil, Trash2, Eye, Loader2, Download, ListChecks, Bug, ExternalLink,
} from 'lucide-react';

const PROJECT_STATUSES = ['draft', 'in_progress', 'completed'];

interface ProjectForm {
  name: string;
  description: string;
  status: string;
  start_time: string;
  end_time: string;
}

const emptyForm: ProjectForm = {
  name: '', description: '', status: 'draft', start_time: '', end_time: '',
};

interface ResultForm {
  test_case_id: number;
  status: string;
  notes: string;
  known_issues: string;
  blocked_reason: string;
}

export default function TestProjects() {
  const qc = useQueryClient();

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ProjectForm>(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState<TestProject | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const [selectedCaseIds, setSelectedCaseIds] = useState<number[]>([]);
  const [resultOpen, setResultOpen] = useState(false);
  const [resultForm, setResultForm] = useState<ResultForm>({ test_case_id: 0, status: 'not_tested', notes: '', known_issues: '', blocked_reason: '' });
  const [jiraDialogOpen, setJiraDialogOpen] = useState(false);
  const [jiraProjectKey, setJiraProjectKey] = useState('');
  const [jiraTargetResultId, setJiraTargetResultId] = useState<number | null>(null);
  const [jiraResult, setJiraResult] = useState<{ key: string; url: string } | null>(null);

  // Queries
  const { data: projects, isLoading } = useQuery({
    queryKey: ['test-projects'],
    queryFn: () => api.get<ApiResponse<TestProject[]>>('/test-projects').then(r => r.data.data),
  });

  const { data: projectDetail, isLoading: loadingDetail } = useQuery({
    queryKey: ['test-project', detailId],
    queryFn: () => api.get<ApiResponse<TestProject>>(`/test-projects/${detailId}`).then(r => r.data.data),
    enabled: detailId !== null,
  });

  const { data: allCases } = useQuery({
    queryKey: ['test-cases-all'],
    queryFn: () => api.get<ApiResponse<TestCase[]>>('/test-cases').then(r => r.data.data),
    enabled: assignOpen,
  });

  const { data: members } = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<ApiResponse<Member[]>>('/members').then(r => r.data.data),
    enabled: detailId !== null,
  });

  const { data: jiraStatus } = useQuery({
    queryKey: ['jira-status'],
    queryFn: () => api.get<ApiResponse<JiraStatus>>('/jira/status').then(r => r.data.data),
    enabled: detailId !== null,
  });

  const { data: jiraProjects } = useQuery({
    queryKey: ['jira-projects'],
    queryFn: () => api.get<ApiResponse<JiraProject[]>>('/jira/projects').then(r => r.data.data),
    enabled: jiraStatus?.connected === true,
  });

  // Mutations
  const createMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => api.post('/test-projects', data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['test-projects'] }); setFormOpen(false); },
  });
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => api.put(`/test-projects/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['test-projects'] }); setFormOpen(false); },
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/test-projects/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['test-projects'] }); setDeleteTarget(null); },
  });
  const assignMut = useMutation({
    mutationFn: ({ id, ids }: { id: number; ids: number[] }) => api.post(`/test-projects/${id}/assign-cases`, { test_case_ids: ids }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-project', detailId] });
      qc.invalidateQueries({ queryKey: ['test-projects'] });
      setAssignOpen(false);
    },
  });
  const resultMut = useMutation({
    mutationFn: ({ projId, data }: { projId: number; data: ResultForm }) =>
      api.put(`/test-projects/${projId}/results`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-project', detailId] });
      qc.invalidateQueries({ queryKey: ['test-projects'] });
    },
  });
  const createIssueMut = useMutation({
    mutationFn: (body: { test_result_id: number; project_key: string }) =>
      api.post<ApiResponse<{ jira_issue_key: string; jira_issue_url: string }>>('/jira/create-issue', body),
    onSuccess: (res) => {
      const d = res.data.data;
      setJiraResult({ key: d.jira_issue_key, url: d.jira_issue_url });
      qc.invalidateQueries({ queryKey: ['test-project', detailId] });
    },
  });

  const assignUserMut = useMutation({
    mutationFn: ({ projId, caseId, userId }: { projId: number; caseId: number; userId: string | null }) =>
      api.put(`/test-projects/${projId}/assign-user`, { test_case_id: caseId, user_id: userId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['test-project', detailId] });
    },
  });

  // Handlers
  const openCreate = () => { setEditingId(null); setForm(emptyForm); setFormOpen(true); };
  const openEdit = (p: TestProject) => {
    setEditingId(p.id);
    setForm({
      name: p.name,
      description: p.description ?? '',
      status: p.status,
      start_time: p.start_time?.slice(0, 10) ?? '',
      end_time: p.end_time?.slice(0, 10) ?? '',
    });
    setFormOpen(true);
  };

  const handleSubmit = () => {
    const payload = {
      ...form,
      description: form.description.trim() || null,
      start_time: form.start_time || null,
      end_time: form.end_time || null,
    };
    if (editingId) updateMut.mutate({ id: editingId, data: payload });
    else createMut.mutate(payload);
  };

  const openAssign = () => {
    const existingIds = projectDetail?.test_cases?.map(tc => tc.id) ?? [];
    setSelectedCaseIds(existingIds);
    setAssignOpen(true);
  };

  const toggleCase = (id: number) => {
    setSelectedCaseIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleInlineStatusChange = (tc: ProjectTestCase, newStatus: string) => {
    if (!detailId) return;
    const data: ResultForm = {
      test_case_id: tc.id,
      status: newStatus,
      notes: tc.result?.notes ?? '',
      known_issues: tc.result?.known_issues ?? '',
      blocked_reason: tc.result?.blocked_reason ?? '',
    };
    resultMut.mutate({ projId: detailId, data });
    // Auto-open notes dialog when selecting "blocked" so user can fill reason
    if (newStatus === 'blocked') {
      setResultForm(data);
      setResultOpen(true);
    }
  };

  const openResult = (tc: ProjectTestCase) => {
    setResultForm({
      test_case_id: tc.id,
      status: tc.result?.status ?? 'not_tested',
      notes: tc.result?.notes ?? '',
      known_issues: tc.result?.known_issues ?? '',
      blocked_reason: tc.result?.blocked_reason ?? '',
    });
    setResultOpen(true);
  };

  const handleDownloadReport = async (format: 'json' | 'pdf') => {
    if (!detailId) return;
    const res = await api.get(`/test-projects/${detailId}/report?format=${format}`, {
      responseType: format === 'pdf' ? 'blob' : 'json',
    });
    if (format === 'pdf') {
      const url = URL.createObjectURL(res.data as Blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report-${detailId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report-${detailId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const isSaving = createMut.isPending || updateMut.isPending;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-[#C9D1D9]">Test Projects</h2>
        <Button onClick={openCreate} className="bg-[#238636] hover:bg-[#2ea043]">
          <Plus className="h-4 w-4 mr-1" /> New Project
        </Button>
      </div>

      {/* Table */}
      <Card className="border-[#30363D] bg-[#0D1117]">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-14 bg-[#21262D]" />)}
            </div>
          ) : !projects || projects.length === 0 ? (
            <EmptyState icon={FolderKanban} title="No projects" description="Create a test project to organize your test cases." actionLabel="New Project" onAction={openCreate} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-[#30363D] hover:bg-transparent">
                  <TableHead className="text-[#8B949E]">Name</TableHead>
                  <TableHead className="text-[#8B949E]">Status</TableHead>
                  <TableHead className="text-[#8B949E] w-[200px]">Progress</TableHead>
                  <TableHead className="text-[#8B949E]">Results</TableHead>
                  <TableHead className="text-[#8B949E] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {projects.map(p => (
                  <TableRow key={p.id} className="border-[#30363D] hover:bg-[#161B22]">
                    <TableCell className="text-[#C9D1D9] font-medium">{p.name}</TableCell>
                    <TableCell><StatusBadge status={p.status} variant="project" /></TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <Progress value={p.stats.completion_rate} className="h-2 bg-[#21262D]" />
                        <span className="text-xs text-[#8B949E]">{p.stats.completion_rate.toFixed(0)}%</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2 text-xs">
                        <span className="text-emerald-400">{p.stats.pass_count}P</span>
                        <span className="text-red-400">{p.stats.fail_count}F</span>
                        <span className="text-orange-400">{p.stats.blocked_count}B</span>
                        <span className="text-[#8B949E]">{p.stats.not_tested_count}N</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]" onClick={() => setDetailId(p.id)}>
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]" onClick={() => openEdit(p)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-[#8B949E] hover:text-red-400 hover:bg-[#21262D]" onClick={() => setDeleteTarget(p)}>
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

      {/* Create/Edit Dialog */}
      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-md">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">{editingId ? 'Edit Project' : 'New Project'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-[#C9D1D9]">Name *</Label>
              <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Description</Label>
              <Textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" rows={3} />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Status</Label>
              <Select value={form.status} onValueChange={v => setForm(f => ({ ...f, status: v }))}>
                <SelectTrigger className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#161B22] border-[#30363D]">
                  {PROJECT_STATUSES.map(s => <SelectItem key={s} value={s} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] capitalize">{s.replace(/_/g, ' ')}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-[#C9D1D9]">Start Date</Label>
                <Input type="date" value={form.start_time} onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" />
              </div>
              <div>
                <Label className="text-[#C9D1D9]">End Date</Label>
                <Input type="date" value={form.end_time} onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setFormOpen(false)} className="text-[#8B949E] hover:bg-[#21262D]">Cancel</Button>
            <Button onClick={handleSubmit} disabled={!form.name.trim() || isSaving} className="bg-[#238636] hover:bg-[#2ea043]">
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
        title="Delete Project"
        description={`Delete "${deleteTarget?.name}"? All test results will be lost.`}
        onConfirm={() => deleteTarget && deleteMut.mutate(deleteTarget.id)}
      />

      {/* Detail Dialog */}
      <Dialog open={detailId !== null} onOpenChange={open => { if (!open) setDetailId(null); }}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-[95vw] sm:max-w-[95vw] w-full max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">{projectDetail?.name ?? 'Project Detail'}</DialogTitle>
          </DialogHeader>
          {loadingDetail ? (
            <div className="space-y-3">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 bg-[#21262D]" />)}
            </div>
          ) : projectDetail && (
            <div className="space-y-6">
              {/* Stats Cards */}
              <div className="grid grid-cols-5 gap-3">
                {[
                  { label: 'Total', value: projectDetail.stats.total, color: 'text-[#C9D1D9]' },
                  { label: 'Pass', value: projectDetail.stats.pass_count, color: 'text-emerald-400' },
                  { label: 'Fail', value: projectDetail.stats.fail_count, color: 'text-red-400' },
                  { label: 'Blocked', value: projectDetail.stats.blocked_count, color: 'text-orange-400' },
                  { label: 'Pending', value: projectDetail.stats.not_tested_count, color: 'text-[#8B949E]' },
                ].map(s => (
                  <Card key={s.label} className="border-[#30363D] bg-[#0D1117]">
                    <CardContent className="p-3 text-center">
                      <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
                      <div className="text-xs text-[#8B949E]">{s.label}</div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <Tabs defaultValue="cases">
                <TabsList className="bg-[#0D1117] border border-[#30363D]">
                  <TabsTrigger value="cases" className="data-[state=active]:bg-[#21262D] text-[#8B949E] data-[state=active]:text-[#C9D1D9]">Test Cases</TabsTrigger>
                  <TabsTrigger value="report" className="data-[state=active]:bg-[#21262D] text-[#8B949E] data-[state=active]:text-[#C9D1D9]">Report</TabsTrigger>
                </TabsList>

                <TabsContent value="cases" className="space-y-4">
                  <Button size="sm" onClick={openAssign} className="bg-[#238636] hover:bg-[#2ea043]">
                    <ListChecks className="h-4 w-4 mr-1" /> Assign Cases
                  </Button>
                  {(!projectDetail.test_cases || projectDetail.test_cases.length === 0) ? (
                    <p className="text-sm text-[#8B949E]">No test cases assigned.</p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow className="border-[#30363D] hover:bg-transparent">
                          <TableHead className="text-[#8B949E]">TC ID</TableHead>
                          <TableHead className="text-[#8B949E]">Title</TableHead>
                          <TableHead className="text-[#8B949E]">Priority</TableHead>
                          <TableHead className="text-[#8B949E]">Assignee</TableHead>
                          <TableHead className="text-[#8B949E]">Result</TableHead>
                          <TableHead className="text-[#8B949E] text-right">Action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {projectDetail.test_cases.map(tc => (
                          <TableRow key={tc.id} className="border-[#30363D] hover:bg-[#0D1117]">
                            <TableCell className="text-[#58A6FF] font-mono text-xs">{tc.tc_id}</TableCell>
                            <TableCell className="text-[#C9D1D9] text-sm">{tc.title}</TableCell>
                            <TableCell><StatusBadge status={tc.priority} variant="priority" /></TableCell>
                            <TableCell>
                              <Select
                                value={tc.assigned_user_id ?? '__none__'}
                                onValueChange={v => detailId && assignUserMut.mutate({
                                  projId: detailId,
                                  caseId: tc.id,
                                  userId: v === '__none__' ? null : v,
                                })}
                              >
                                <SelectTrigger className="h-7 w-[130px] bg-[#0D1117] border-[#30363D] text-xs text-[#C9D1D9]">
                                  <SelectValue placeholder="Unassigned" />
                                </SelectTrigger>
                                <SelectContent className="bg-[#161B22] border-[#30363D]">
                                  <SelectItem value="__none__" className="text-[#8B949E] focus:bg-[#21262D] focus:text-[#C9D1D9] text-xs">
                                    Unassigned
                                  </SelectItem>
                                  {members?.filter(m => m.is_active).map(m => (
                                    <SelectItem key={m.id} value={m.id} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] text-xs">
                                      {m.username}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </TableCell>
                            <TableCell>
                              <Select
                                value={tc.result?.status ?? 'not_tested'}
                                onValueChange={v => handleInlineStatusChange(tc, v)}
                              >
                                <SelectTrigger className="h-7 w-[130px] bg-[#0D1117] border-[#30363D] text-xs text-[#C9D1D9]">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent className="bg-[#161B22] border-[#30363D]">
                                  {['pass', 'fail', 'blocked', 'not_tested'].map(s => (
                                    <SelectItem key={s} value={s} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] capitalize text-xs">
                                      {s.replace(/_/g, ' ')}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </TableCell>
                            <TableCell className="text-right">
                              <div className="flex items-center justify-end gap-1">
                                <Button variant="ghost" size="icon" className="h-7 w-7 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]" onClick={() => openResult(tc)} title="Edit notes">
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                {tc.result?.status === 'fail' && jiraStatus?.connected && (
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7 text-red-400 hover:text-red-300 hover:bg-red-950/30"
                                    title="Create Jira Bug"
                                    onClick={() => {
                                      setJiraTargetResultId(tc.result!.id);
                                      setJiraProjectKey(jiraProjects?.[0]?.key ?? '');
                                      setJiraResult(null);
                                      setJiraDialogOpen(true);
                                    }}
                                  >
                                    <Bug className="h-3.5 w-3.5" />
                                  </Button>
                                )}
                              </div>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </TabsContent>

                <TabsContent value="report" className="space-y-4">
                  <div className="flex gap-3">
                    <Button variant="outline" onClick={() => handleDownloadReport('json')} className="border-[#30363D] text-[#8B949E] hover:bg-[#21262D]">
                      <Download className="h-4 w-4 mr-1" /> JSON Report
                    </Button>
                    <Button variant="outline" onClick={() => handleDownloadReport('pdf')} className="border-[#30363D] text-[#8B949E] hover:bg-[#21262D]">
                      <Download className="h-4 w-4 mr-1" /> PDF Report
                    </Button>
                  </div>
                  <p className="text-xs text-[#484F58]">Reports include project stats, test case results, and Jira issue summary.</p>
                </TabsContent>
              </Tabs>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Assign Cases Dialog */}
      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">Assign Test Cases</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            {allCases?.map(tc => (
              <label key={tc.id} className="flex items-center gap-3 px-3 py-2 rounded border border-[#30363D] cursor-pointer hover:bg-[#0D1117]">
                <input
                  type="checkbox"
                  checked={selectedCaseIds.includes(tc.id)}
                  onChange={() => toggleCase(tc.id)}
                  className="rounded"
                />
                <span className="text-[#58A6FF] font-mono text-xs">{tc.tc_id}</span>
                <span className="text-sm text-[#C9D1D9] truncate">{tc.title}</span>
              </label>
            ))}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAssignOpen(false)} className="text-[#8B949E] hover:bg-[#21262D]">Cancel</Button>
            <Button
              onClick={() => detailId && assignMut.mutate({ id: detailId, ids: selectedCaseIds })}
              disabled={assignMut.isPending}
              className="bg-[#238636] hover:bg-[#2ea043]"
            >
              {assignMut.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              Assign ({selectedCaseIds.length})
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Notes Dialog */}
      <Dialog open={resultOpen} onOpenChange={setResultOpen}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-4xl">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">Edit Notes & Issues</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-[#C9D1D9]">Notes</Label>
              <Textarea value={resultForm.notes} onChange={e => setResultForm(f => ({ ...f, notes: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" rows={5} />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Known Issues</Label>
              <Textarea value={resultForm.known_issues} onChange={e => setResultForm(f => ({ ...f, known_issues: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" rows={4} />
            </div>
            {resultForm.status === 'blocked' && (
              <div>
                <Label className="text-[#C9D1D9]">Blocked Reason</Label>
                <Textarea value={resultForm.blocked_reason} onChange={e => setResultForm(f => ({ ...f, blocked_reason: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" rows={4} />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setResultOpen(false)} className="text-[#8B949E] hover:bg-[#21262D]">Cancel</Button>
            <Button
              onClick={() => detailId && resultMut.mutate(
                { projId: detailId, data: resultForm },
                { onSuccess: () => setResultOpen(false) },
              )}
              disabled={resultMut.isPending}
              className="bg-[#238636] hover:bg-[#2ea043]"
            >
              {resultMut.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Jira Bug Dialog */}
      <Dialog open={jiraDialogOpen} onOpenChange={open => { if (!open) { setJiraDialogOpen(false); setJiraResult(null); } }}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-md">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">Create Jira Bug</DialogTitle>
          </DialogHeader>
          {jiraResult ? (
            <div className="space-y-4">
              <div className="rounded-md border border-emerald-800 bg-emerald-950/30 p-4 text-center space-y-2">
                <p className="text-emerald-400 font-medium">Issue created successfully</p>
                <a
                  href={jiraResult.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[#58A6FF] hover:underline font-mono text-sm"
                >
                  {jiraResult.key} <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </div>
              <DialogFooter>
                <Button onClick={() => { setJiraDialogOpen(false); setJiraResult(null); }} className="bg-[#238636] hover:bg-[#2ea043]">
                  Done
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <Label className="text-[#C9D1D9]">Jira Project</Label>
                <Select value={jiraProjectKey} onValueChange={setJiraProjectKey}>
                  <SelectTrigger className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"><SelectValue placeholder="Select project" /></SelectTrigger>
                  <SelectContent className="bg-[#161B22] border-[#30363D]">
                    {jiraProjects?.map(p => (
                      <SelectItem key={p.key} value={p.key} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">
                        {p.key} — {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-[#C9D1D9]">Issue Type</Label>
                <Input value="Bug" disabled className="bg-[#0D1117] border-[#30363D] text-[#8B949E] mt-1" />
              </div>
              {createIssueMut.isError && (
                <p className="text-sm text-red-400">
                  {(createIssueMut.error as Error)?.message ?? 'Failed to create issue'}
                </p>
              )}
              <DialogFooter>
                <Button variant="ghost" onClick={() => { setJiraDialogOpen(false); setJiraResult(null); }} className="text-[#8B949E] hover:bg-[#21262D]">Cancel</Button>
                <Button
                  onClick={() => jiraTargetResultId && jiraProjectKey && createIssueMut.mutate({ test_result_id: jiraTargetResultId, project_key: jiraProjectKey })}
                  disabled={!jiraProjectKey || createIssueMut.isPending}
                  className="bg-red-600 hover:bg-red-700"
                >
                  {createIssueMut.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                  <Bug className="h-4 w-4 mr-1" /> Create
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
