import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import { useAuth } from '@/hooks/useAuth';
import type { Member, InviteLinkInfo, ApiResponse } from '@/types';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState } from '@/components/EmptyState';
import {
  Users, Plus, Copy, Loader2, Trash2, Check,
} from 'lucide-react';

interface InviteForm {
  role: string;
  max_uses: string;
  expires_hours: string;
}

const emptyInviteForm: InviteForm = { role: 'user', max_uses: '', expires_hours: '' };

export default function Members() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const isAdmin = user?.role === 'admin';

  const [inviteFormOpen, setInviteFormOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState<InviteForm>(emptyInviteForm);
  const [deactivateTarget, setDeactivateTarget] = useState<Member | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Queries
  const { data: members, isLoading: loadingMembers } = useQuery({
    queryKey: ['members'],
    queryFn: () => api.get<ApiResponse<Member[]>>('/members').then(r => r.data.data),
  });

  const { data: inviteLinks, isLoading: loadingLinks } = useQuery({
    queryKey: ['invite-links'],
    queryFn: () => api.get<ApiResponse<InviteLinkInfo[]>>('/members/invite-links').then(r => r.data.data),
    enabled: isAdmin,
  });

  // Mutations
  const createInviteMut = useMutation({
    mutationFn: (data: Record<string, unknown>) => api.post('/members/invite-links', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['invite-links'] });
      setInviteFormOpen(false);
      setInviteForm(emptyInviteForm);
    },
  });

  const revokeInviteMut = useMutation({
    mutationFn: (id: string) => api.delete(`/members/invite-links/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['invite-links'] }),
  });

  const updateRoleMut = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) =>
      api.put(`/members/${id}/role`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['members'] }),
  });

  const deactivateMut = useMutation({
    mutationFn: (id: string) => api.post(`/members/${id}/deactivate`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['members'] });
      setDeactivateTarget(null);
    },
  });

  const handleCreateInvite = () => {
    const payload: Record<string, unknown> = { role: inviteForm.role };
    if (inviteForm.max_uses) payload.max_uses = parseInt(inviteForm.max_uses);
    if (inviteForm.expires_hours) payload.expires_hours = parseInt(inviteForm.expires_hours);
    createInviteMut.mutate(payload);
  };

  const copyInviteUrl = (token: string, linkId: string) => {
    const url = `${window.location.origin}/join?token=${token}`;
    navigator.clipboard.writeText(url);
    setCopiedId(linkId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-[#C9D1D9]">Members</h2>
        {isAdmin && (
          <Button onClick={() => setInviteFormOpen(true)} className="bg-[#238636] hover:bg-[#2ea043]">
            <Plus className="h-4 w-4 mr-1" /> Invite Member
          </Button>
        )}
      </div>

      {/* Members Table */}
      <Card className="border-[#30363D] bg-[#0D1117]">
        <CardContent className="p-0">
          {loadingMembers ? (
            <div className="p-6 space-y-3">
              {[1, 2, 3].map(i => <Skeleton key={i} className="h-14 bg-[#21262D]" />)}
            </div>
          ) : !members || members.length === 0 ? (
            <EmptyState icon={Users} title="No members" description="Invite team members to collaborate." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-[#30363D] hover:bg-transparent">
                  <TableHead className="text-[#8B949E]">Username</TableHead>
                  <TableHead className="text-[#8B949E]">Email</TableHead>
                  <TableHead className="text-[#8B949E]">Role</TableHead>
                  <TableHead className="text-[#8B949E]">Status</TableHead>
                  {isAdmin && <TableHead className="text-[#8B949E] text-right">Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map(m => (
                  <TableRow key={m.id} className="border-[#30363D] hover:bg-[#161B22]">
                    <TableCell className="text-[#C9D1D9] font-medium">
                      <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#238636] text-xs font-bold text-white">
                          {m.username.charAt(0).toUpperCase()}
                        </div>
                        {m.username}
                        {m.id === user?.id && (
                          <span className="text-xs text-[#484F58]">(you)</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-[#8B949E]">{m.email}</TableCell>
                    <TableCell>
                      {isAdmin && m.id !== user?.id ? (
                        <Select
                          value={m.role}
                          onValueChange={(v) => updateRoleMut.mutate({ id: m.id, role: v })}
                        >
                          <SelectTrigger className="h-7 w-[100px] bg-[#0D1117] border-[#30363D] text-xs text-[#C9D1D9]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-[#161B22] border-[#30363D]">
                            <SelectItem value="admin" className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] text-xs">admin</SelectItem>
                            <SelectItem value="user" className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9] text-xs">user</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <span className="text-[#C9D1D9] text-sm capitalize">{m.role}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {m.is_active ? (
                        <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">Active</span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-400">Inactive</span>
                      )}
                    </TableCell>
                    {isAdmin && (
                      <TableCell className="text-right">
                        {m.id !== user?.id && m.is_active && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 text-[#8B949E] hover:text-red-400 hover:bg-[#21262D]"
                            onClick={() => setDeactivateTarget(m)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Invite Links Section (admin only) */}
      {isAdmin && (
        <>
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-[#C9D1D9]">Invite Links</h3>
          </div>
          <Card className="border-[#30363D] bg-[#0D1117]">
            <CardContent className="p-0">
              {loadingLinks ? (
                <div className="p-6 space-y-3">
                  {[1, 2].map(i => <Skeleton key={i} className="h-10 bg-[#21262D]" />)}
                </div>
              ) : !inviteLinks || inviteLinks.length === 0 ? (
                <div className="p-6 text-center text-sm text-[#8B949E]">
                  No invite links created yet.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="border-[#30363D] hover:bg-transparent">
                      <TableHead className="text-[#8B949E]">Link</TableHead>
                      <TableHead className="text-[#8B949E]">Role</TableHead>
                      <TableHead className="text-[#8B949E]">Uses</TableHead>
                      <TableHead className="text-[#8B949E]">Expires</TableHead>
                      <TableHead className="text-[#8B949E]">Status</TableHead>
                      <TableHead className="text-[#8B949E] text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {inviteLinks.map(link => (
                      <TableRow key={link.id} className="border-[#30363D] hover:bg-[#161B22]">
                        <TableCell className="font-mono text-xs text-[#58A6FF] max-w-[200px] truncate">
                          ...{link.token.slice(-12)}
                        </TableCell>
                        <TableCell className="text-[#C9D1D9] text-sm capitalize">{link.role}</TableCell>
                        <TableCell className="text-[#8B949E] text-sm">
                          {link.use_count}{link.max_uses !== null ? ` / ${link.max_uses}` : ''}
                        </TableCell>
                        <TableCell className="text-[#8B949E] text-sm">
                          {link.expires_at
                            ? new Date(link.expires_at).toLocaleDateString()
                            : 'Never'}
                        </TableCell>
                        <TableCell>
                          {link.is_active ? (
                            <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">Active</span>
                          ) : (
                            <span className="inline-flex items-center rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-400">Revoked</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            {link.is_active && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 text-[#8B949E] hover:text-[#C9D1D9] hover:bg-[#21262D]"
                                  onClick={() => copyInviteUrl(link.token, link.id)}
                                >
                                  {copiedId === link.id ? (
                                    <Check className="h-4 w-4 text-emerald-400" />
                                  ) : (
                                    <Copy className="h-4 w-4" />
                                  )}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 text-[#8B949E] hover:text-red-400 hover:bg-[#21262D]"
                                  onClick={() => revokeInviteMut.mutate(link.id)}
                                  disabled={revokeInviteMut.isPending}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Create Invite Dialog */}
      <Dialog open={inviteFormOpen} onOpenChange={setInviteFormOpen}>
        <DialogContent className="bg-[#161B22] border-[#30363D] max-w-md">
          <DialogHeader>
            <DialogTitle className="text-[#C9D1D9]">Create Invite Link</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label className="text-[#C9D1D9]">Role</Label>
              <Select value={inviteForm.role} onValueChange={v => setInviteForm(f => ({ ...f, role: v }))}>
                <SelectTrigger className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#161B22] border-[#30363D]">
                  <SelectItem value="user" className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">User</SelectItem>
                  <SelectItem value="admin" className="text-[#C9D1D9] focus:bg-[#21262D] focus:text-[#C9D1D9]">Admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Max Uses (optional)</Label>
              <Input
                type="number"
                min="1"
                placeholder="Unlimited"
                value={inviteForm.max_uses}
                onChange={e => setInviteForm(f => ({ ...f, max_uses: e.target.value }))}
                className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1 placeholder:text-[#484F58]"
              />
            </div>
            <div>
              <Label className="text-[#C9D1D9]">Expires After (hours, optional)</Label>
              <Input
                type="number"
                min="1"
                placeholder="Never"
                value={inviteForm.expires_hours}
                onChange={e => setInviteForm(f => ({ ...f, expires_hours: e.target.value }))}
                className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1 placeholder:text-[#484F58]"
              />
            </div>
            {createInviteMut.isError && (
              <p className="text-sm text-red-400">
                {(createInviteMut.error as Error)?.message ?? 'Failed to create invite link'}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setInviteFormOpen(false)} className="text-[#8B949E] hover:bg-[#21262D]">
              Cancel
            </Button>
            <Button
              onClick={handleCreateInvite}
              disabled={createInviteMut.isPending}
              className="bg-[#238636] hover:bg-[#2ea043]"
            >
              {createInviteMut.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Deactivate Confirm */}
      <ConfirmDialog
        open={deactivateTarget !== null}
        onOpenChange={open => { if (!open) setDeactivateTarget(null); }}
        title="Deactivate Member"
        description={`Deactivate "${deactivateTarget?.username}"? They will no longer be able to log in.`}
        onConfirm={() => deactivateTarget && deactivateMut.mutate(deactivateTarget.id)}
      />
    </div>
  );
}
