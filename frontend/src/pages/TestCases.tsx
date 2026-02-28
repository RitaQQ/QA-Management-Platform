import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import type { TestCase, ProductTag, ApiResponse, CsvImportResult } from '@/types';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
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
import { StatusBadge } from '@/components/StatusBadge';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState } from '@/components/EmptyState';
import {
  FileText, Plus, Pencil, Trash2, Download, Upload, Tags, Loader2,
} from 'lucide-react';

const PRIORITIES = ['low', 'medium', 'high'];
const STATUSES = ['draft', 'ready', 'in_progress', 'completed', 'blocked'];

interface CaseForm {
  title: string;
  user_role: string;
  feature_description: string;
  acceptance_criteria: string;
  test_notes: string;
  priority: string;
  status: string;
  estimated_hours: number;
  actual_hours: number;
  tag_ids: number[];
}

const emptyForm: CaseForm = {
  title: '', user_role: '', feature_description: '', acceptance_criteria: '',
  test_notes: '', priority: 'medium', status: 'draft', estimated_hours: 0, actual_hours: 0, tag_ids: [],
};

interface TagForm {
  name: string;
  color: string;
  description: string;
}

export default function TestCases() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  // State
  const [filterPriority, setFilterPriority] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterTag, setFilterTag] = useState('all');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<CaseForm>(emptyForm);
  const [deleteTarget, setDeleteTarget] = useState<TestCase | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importResult, setImportResult] = useState<CsvImportResult | null>(null);
  const [importFileName, setImportFileName] = useState<string | null>(null);
  const [tagOpen, setTagOpen] = useState(false);
  const [tagForm, setTagForm] = useState<TagForm>({ name: '', color: '#007bff', description: '' });
  const [editingTagId, setEditingTagId] = useState<number | null>(null);
  const [deleteTagTarget, setDeleteTagTarget] = useState<ProductTag | null>(null);

  // Queries
  const { data: testCases, isLoading } = useQuery({
    queryKey: ['test-cases', filterPriority, filterStatus, filterTag],
    queryFn: () => {
      const params = new URLSearchParams();
      if (filterPriority !== 'all') params.set('priority', filterPriority);
      if (filterStatus !== 'all') params.set('status', filterStatus);
      if (filterTag !== 'all') params.set('tag_id', filterTag);
      return api.get<ApiResponse<TestCase[]>>(`/test-cases?${params}`).then(r => r.data.data);
    },
  });

  const { data: tags } = useQuery({
    queryKey: ['product-tags'],
    queryFn: () => api.get<ApiResponse<ProductTag[]>>('/product-tags').then(r => r.data.data),
  });

  // Case Mutations
  const createMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => api.post('/test-cases', data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['test-cases'] }); setFormOpen(false); },
  });
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) => api.put(`/test-cases/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['test-cases'] }); setFormOpen(false); },
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => api.delete(`/test-cases/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['test-cases'] }); setDeleteTarget(null); },
  });
  const importMut = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return api.post<ApiResponse<CsvImportResult>>('/test-cases/import-csv', fd);
    },
    onSuccess: (res) => {
      setImportResult(res.data.data);
      qc.invalidateQueries({ queryKey: ['test-cases'] });
    },
  });

  // Tag Mutations
  const createTagMut = useMutation({
    mutationFn: (data: TagForm) => api.post('/product-tags', data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['product-tags'] }); resetTagForm(); },
  });
  const updateTagMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: TagForm }) => api.put(`/product-tags/${id}`, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['product-tags'] }); resetTagForm(); },
  });
  const deleteTagMut = useMutation({
    mutationFn: (id: number) => api.delete(`/product-tags/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['product-tags'] }); setDeleteTagTarget(null); },
  });

  // Handlers
  const openCreate = () => { setEditingId(null); setForm(emptyForm); setFormOpen(true); };

  const openEdit = (tc: TestCase) => {
    setEditingId(tc.id);
    setForm({
      title: tc.title,
      user_role: tc.user_role ?? '',
      feature_description: tc.feature_description ?? '',
      acceptance_criteria: tc.acceptance_criteria ?? '',
      test_notes: tc.test_notes ?? '',
      priority: tc.priority,
      status: tc.status,
      estimated_hours: tc.estimated_hours,
      actual_hours: tc.actual_hours,
      tag_ids: tc.product_tags.map(t => t.id),
    });
    setFormOpen(true);
  };

  const handleSubmit = () => {
    const payload = {
      ...form,
      user_role: form.user_role.trim() || null,
      feature_description: form.feature_description.trim() || null,
      acceptance_criteria: form.acceptance_criteria.trim() || null,
      test_notes: form.test_notes.trim() || null,
    };
    if (editingId) {
      updateMut.mutate({ id: editingId, data: payload });
    } else {
      createMut.mutate(payload);
    }
  };

  const handleExport = async () => {
    const res = await api.get('/test-cases/export-csv', { responseType: 'blob' });
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'test-cases.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportFileName(file.name);
      setImportResult(null);
      importMut.mutate(file);
    }
  };

  const resetTagForm = () => {
    setEditingTagId(null);
    setTagForm({ name: '', color: '#007bff', description: '' });
  };

  const startEditTag = (tag: ProductTag) => {
    setEditingTagId(tag.id);
    setTagForm({ name: tag.name, color: tag.color, description: tag.description ?? '' });
  };

  const handleTagSubmit = () => {
    if (editingTagId) {
      updateTagMut.mutate({ id: editingTagId, data: tagForm });
    } else {
      createTagMut.mutate(tagForm);
    }
  };

  const toggleTag = (id: number) => {
    setForm(f => ({
      ...f,
      tag_ids: f.tag_ids.includes(id) ? f.tag_ids.filter(t => t !== id) : [...f.tag_ids, id],
    }));
  };

  const isSaving = createMut.isPending || updateMut.isPending;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold text-[#C9D1D9]">Test Cases</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setTagOpen(true)} className="border-[#30363D] text-[#8B949E] hover:bg-[#21262D]">
            <Tags className="h-4 w-4 mr-1" /> Tags
          </Button>
          <Button variant="outline" onClick={handleExport} className="border-[#30363D] text-[#8B949E] hover:bg-[#21262D]">
            <Download className="h-4 w-4 mr-1" /> Export
          </Button>
          <Button variant="outline" onClick={() => { setImportResult(null); setImportFileName(null); if (fileRef.current) fileRef.current.value = ''; setImportOpen(true); }} className="border-[#30363D] text-[#8B949E] hover:bg-[#21262D]">
            <Upload className="h-4 w-4 mr-1" /> Import
          </Button>
          <Button onClick={openCreate} className="bg-[#238636] hover:bg-[#2ea043]">
            <Plus className="h-4 w-4 mr-1" /> Add Case
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4 flex-wrap">
        <Select value={filterPriority} onValueChange={setFilterPriority}>
          <SelectTrigger className="w-[140px] bg-[#0D1117] border-[#30363D] text-[#C9D1D9]">
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent className="bg-[#161B22] border-[#30363D]">
            <SelectItem value="all" className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">All Priority</SelectItem>
            {PRIORITIES.map(p => <SelectItem key={p} value={p} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] capitalize">{p}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-[140px] bg-[#0D1117] border-[#30363D] text-[#C9D1D9]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent className="bg-[#161B22] border-[#30363D]">
            <SelectItem value="all" className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">All Status</SelectItem>
            {STATUSES.map(s => <SelectItem key={s} value={s} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] capitalize">{s.replace(/_/g, ' ')}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filterTag} onValueChange={setFilterTag}>
          <SelectTrigger className="w-[160px] bg-[#0D1117] border-[#30363D] text-[#C9D1D9]">
            <SelectValue placeholder="Tag" />
          </SelectTrigger>
          <SelectContent className="bg-[#161B22] border-[#30363D]">
            <SelectItem value="all" className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">All Tags</SelectItem>
            {tags?.map(t => <SelectItem key={t.id} value={String(t.id)} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">{t.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card className="border-[#30363D] bg-[#0D1117]">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-12 bg-[#21262D]" />)}
            </div>
          ) : !testCases || testCases.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No test cases"
              description="Create your first test case to get started."
              actionLabel="Add Case"
              onAction={openCreate}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-[#30363D] hover:bg-transparent">
                  <TableHead className="text-[#8B949E]">TC ID</TableHead>
                  <TableHead className="text-[#8B949E]">Title</TableHead>
                  <TableHead className="text-[#8B949E]">Priority</TableHead>
                  <TableHead className="text-[#8B949E]">Status</TableHead>
                  <TableHead className="text-[#8B949E]">Tags</TableHead>
                  <TableHead className="text-[#8B949E] text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {testCases.map(tc => (
                  <TableRow key={tc.id} className="border-[#30363D] hover:bg-[#161B22]">
                    <TableCell className="text-[#58A6FF] font-mono text-xs">{tc.tc_id}</TableCell>
                    <TableCell className="text-[#C9D1D9] max-w-[250px] truncate">{tc.title}</TableCell>
                    <TableCell><StatusBadge status={tc.priority} variant="priority" /></TableCell>
                    <TableCell><StatusBadge status={tc.status} variant="testcase" /></TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {tc.product_tags.map(t => (
                          <Badge key={t.id} variant="outline" className="text-xs" style={{ borderColor: t.color, color: t.color }}>
                            {t.name}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]" onClick={() => openEdit(tc)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-[#8B949E] hover:text-red-400 hover:bg-[#21262D]" onClick={() => setDeleteTarget(tc)}>
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
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">{editingId ? 'Edit Test Case' : 'Add Test Case'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-[#C9D1D9]">Title *</Label>
              <Input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">User Role</Label>
              <Input value={form.user_role} onChange={e => setForm(f => ({ ...f, user_role: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" placeholder="e.g. Admin, Customer" />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Feature Description</Label>
              <Textarea value={form.feature_description} onChange={e => setForm(f => ({ ...f, feature_description: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" rows={3} />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Acceptance Criteria</Label>
              <Textarea value={form.acceptance_criteria} onChange={e => setForm(f => ({ ...f, acceptance_criteria: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" rows={3} />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Notes</Label>
              <Textarea value={form.test_notes} onChange={e => setForm(f => ({ ...f, test_notes: e.target.value }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" rows={2} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-[#C9D1D9]">Priority</Label>
                <Select value={form.priority} onValueChange={v => setForm(f => ({ ...f, priority: v }))}>
                  <SelectTrigger className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-[#161B22] border-[#30363D]">
                    {PRIORITIES.map(p => <SelectItem key={p} value={p} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] capitalize">{p}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-[#C9D1D9]">Status</Label>
                <Select value={form.status} onValueChange={v => setForm(f => ({ ...f, status: v }))}>
                  <SelectTrigger className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-[#161B22] border-[#30363D]">
                    {STATUSES.map(s => <SelectItem key={s} value={s} className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] capitalize">{s.replace(/_/g, ' ')}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-[#C9D1D9]">Estimated Hours</Label>
                <Input type="number" value={form.estimated_hours} onChange={e => setForm(f => ({ ...f, estimated_hours: parseFloat(e.target.value) || 0 }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" step="0.5" />
              </div>
              <div>
                <Label className="text-[#C9D1D9]">Actual Hours</Label>
                <Input type="number" value={form.actual_hours} onChange={e => setForm(f => ({ ...f, actual_hours: parseFloat(e.target.value) || 0 }))} className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1" step="0.5" />
              </div>
            </div>
            {/* Tags */}
            {tags && tags.length > 0 && (
              <div>
                <Label className="text-[#C9D1D9]">Tags</Label>
                <div className="flex flex-wrap gap-2 mt-2">
                  {tags.map(t => (
                    <Badge
                      key={t.id}
                      variant="outline"
                      className="cursor-pointer text-xs"
                      style={{
                        borderColor: form.tag_ids.includes(t.id) ? t.color : '#30363D',
                        color: form.tag_ids.includes(t.id) ? t.color : '#8B949E',
                        backgroundColor: form.tag_ids.includes(t.id) ? `${t.color}20` : 'transparent',
                      }}
                      onClick={() => toggleTag(t.id)}
                    >
                      {t.name}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setFormOpen(false)} className="text-[#8B949E] hover:bg-[#21262D]">Cancel</Button>
            <Button onClick={handleSubmit} disabled={!form.title.trim() || isSaving} className="bg-[#238636] hover:bg-[#2ea043]">
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
        title="Delete Test Case"
        description={`Delete "${deleteTarget?.title}"? This cannot be undone.`}
        onConfirm={() => deleteTarget && deleteMut.mutate(deleteTarget.id)}
      />

      {/* CSV Import Dialog */}
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-md">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">Import CSV</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <input ref={fileRef} type="file" accept=".csv" onChange={handleImportFile} className="hidden" />
            <div className="flex items-center gap-3">
              <Button variant="outline" onClick={() => fileRef.current?.click()} className="border-[#30363D] text-[#C9D1D9] hover:bg-[#21262D]">
                <Upload className="h-4 w-4 mr-1" /> Choose File
              </Button>
              <span className="text-sm text-[#8B949E]">
                {importFileName ?? 'No file selected'}
              </span>
            </div>
            {importMut.isPending && <p className="text-sm text-[#8B949E]">Importing...</p>}
            {importResult && (
              <div className="space-y-2 text-sm">
                <p className="text-emerald-400">Created: {importResult.created} / {importResult.total}</p>
                {importResult.errors.length > 0 && (
                  <div className="text-red-400 space-y-1">
                    {importResult.errors.map((e, i) => <p key={i}>{e}</p>)}
                  </div>
                )}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setImportOpen(false)} className="text-[#8B949E] hover:bg-[#21262D]">Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Tag Management Dialog */}
      <Dialog open={tagOpen} onOpenChange={open => { setTagOpen(open); if (!open) resetTagForm(); }}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-md max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">Manage Tags</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {tags && tags.length > 0 && (
              <div className="space-y-2">
                {tags.map(t => (
                  <div key={t.id} className="flex items-center justify-between border border-[#30363D] rounded px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: t.color }} />
                      <span className="text-sm text-[#C9D1D9]">{t.name}</span>
                    </div>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]" onClick={() => startEditTag(t)}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-[#8B949E] hover:text-red-400 hover:bg-[#21262D]" onClick={() => setDeleteTagTarget(t)}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="border-t border-[#30363D] pt-4 space-y-3">
              <p className="text-sm font-medium text-[#8B949E]">{editingTagId ? 'Edit Tag' : 'New Tag'}</p>
              <div className="flex gap-2">
                <Input
                  value={tagForm.name}
                  onChange={e => setTagForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="Tag name"
                  className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] flex-1"
                />
                <input
                  type="color"
                  value={tagForm.color}
                  onChange={e => setTagForm(f => ({ ...f, color: e.target.value }))}
                  className="h-9 w-9 rounded border border-[#30363D] bg-[#0D1117] cursor-pointer"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleTagSubmit}
                  disabled={!tagForm.name.trim() || createTagMut.isPending || updateTagMut.isPending}
                  className="bg-[#238636] hover:bg-[#2ea043]"
                >
                  {editingTagId ? 'Update' : 'Add'}
                </Button>
                {editingTagId && (
                  <Button size="sm" variant="ghost" onClick={resetTagForm} className="text-[#8B949E]">Cancel</Button>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Tag Confirm */}
      <ConfirmDialog
        open={deleteTagTarget !== null}
        onOpenChange={open => { if (!open) setDeleteTagTarget(null); }}
        title="Delete Tag"
        description={`Delete tag "${deleteTagTarget?.name}"? It will be removed from all test cases.`}
        onConfirm={() => deleteTagTarget && deleteTagMut.mutate(deleteTagTarget.id)}
      />
    </div>
  );
}
