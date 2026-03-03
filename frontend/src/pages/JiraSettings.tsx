import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import type { JiraStatus, JiraProject, NotificationSettings, ApiResponse } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Link2, Bell, ExternalLink, Loader2, Check, AlertCircle, Unplug, Pencil,
} from 'lucide-react';

export default function JiraSettings() {
  const qc = useQueryClient();

  // ----- Jira queries -----
  const { data: jiraStatus, isLoading: loadingJira } = useQuery({
    queryKey: ['jira-status'],
    queryFn: () => api.get<ApiResponse<JiraStatus>>('/jira/status').then(r => r.data.data),
  });

  const { data: jiraProjects } = useQuery({
    queryKey: ['jira-projects'],
    queryFn: () => api.get<ApiResponse<JiraProject[]>>('/jira/projects').then(r => r.data.data),
    enabled: jiraStatus?.connected === true,
  });

  // ----- Notification queries -----
  const { data: notifSettings, isLoading: loadingNotif } = useQuery({
    queryKey: ['notification-settings'],
    queryFn: () => api.get<ApiResponse<NotificationSettings>>('/notifications/settings').then(r => r.data.data),
  });

  // ----- Local state -----
  const [siteUrl, setSiteUrl] = useState('');
  const [jiraEmail, setJiraEmail] = useState('');
  const [apiToken, setApiToken] = useState('');
  const [editing, setEditing] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const [titleTemplate, setTitleTemplate] = useState('');
  const [descTemplate, setDescTemplate] = useState('');

  const [notifEmail, setNotifEmail] = useState('');
  const [webhook, setWebhook] = useState('');
  const [notifSaved, setNotifSaved] = useState(false);

  // ----- Bug template query -----
  const templateQuery = useQuery({
    queryKey: ['jira-bug-template'],
    queryFn: () => api.get<ApiResponse<{
      title_template: string | null;
      description_template: string | null;
      default_title: string;
      default_description: string;
      available_placeholders: { key: string; label: string; example: string }[];
    }>>('/jira/bug-template').then(r => r.data.data),
    enabled: jiraStatus?.connected === true,
  });

  useEffect(() => {
    if (templateQuery.data) {
      setTitleTemplate(templateQuery.data.title_template ?? '');
      setDescTemplate(templateQuery.data.description_template ?? '');
    }
  }, [templateQuery.data]);

  useEffect(() => {
    if (notifSettings) {
      setNotifEmail(notifSettings.notification_email ?? '');
      setWebhook(notifSettings.notification_webhook_url ?? '');
    }
  }, [notifSettings]);

  // Populate form when editing
  useEffect(() => {
    if (editing && jiraStatus?.connected) {
      setSiteUrl(jiraStatus.site_url ?? '');
      setJiraEmail(jiraStatus.user_email ?? '');
      setApiToken('');
    }
  }, [editing, jiraStatus]);

  // ----- Jira mutations -----
  const connectMut = useMutation({
    mutationFn: (data: { site_url: string; email: string; api_token: string }) =>
      api.post<ApiResponse<{ connected: boolean; site_url: string; user_email: string }>>('/jira/connect', data).then(r => r.data.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jira-status'] });
      qc.invalidateQueries({ queryKey: ['jira-projects'] });
      setApiToken('');
      setEditing(false);
      setTestResult(null);
    },
  });

  const testMut = useMutation({
    mutationFn: () =>
      api.post<ApiResponse<{ ok: boolean; display_name: string }>>('/jira/test-connection').then(r => r.data.data),
    onSuccess: (data) => {
      setTestResult({ ok: true, message: `Connected as ${data.display_name}` });
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error ?? 'Connection failed';
      setTestResult({ ok: false, message: msg });
    },
  });

  const disconnectMut = useMutation({
    mutationFn: () => api.post('/jira/disconnect'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jira-status'] });
      qc.invalidateQueries({ queryKey: ['jira-projects'] });
      setSiteUrl('');
      setJiraEmail('');
      setApiToken('');
      setTestResult(null);
      setEditing(false);
    },
  });

  // ----- Bug template mutation -----
  const saveTemplateMut = useMutation({
    mutationFn: (data: { title_template: string; description_template: string }) =>
      api.put('/jira/bug-template', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jira-bug-template'] });
    },
  });

  // ----- Notification mutations -----
  const notifMut = useMutation({
    mutationFn: (data: { notification_email: string | null; notification_webhook_url: string | null }) =>
      api.put('/notifications/settings', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notification-settings'] });
      setNotifSaved(true);
      setTimeout(() => setNotifSaved(false), 2000);
    },
  });

  const handleConnect = () => {
    connectMut.mutate({ site_url: siteUrl.trim(), email: jiraEmail.trim(), api_token: apiToken });
  };

  const handleSaveNotif = () => {
    notifMut.mutate({
      notification_email: notifEmail.trim() || null,
      notification_webhook_url: webhook.trim() || null,
    });
  };

  const showForm = !jiraStatus?.connected || editing;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-[#C9D1D9]">Settings</h2>

      {/* ===================== Jira Integration ===================== */}
      <Card className="border-[#30363D] bg-[#0D1117]">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-[#C9D1D9]">
            <Link2 className="h-5 w-5 text-[#58A6FF]" />
            Jira Integration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {loadingJira ? (
            <Skeleton className="h-12 bg-[#21262D]" />
          ) : (
            <>
              {/* Status bar */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-sm text-[#8B949E]">Status:</span>
                  {jiraStatus?.connected ? (
                    <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30" variant="outline">
                      Connected
                    </Badge>
                  ) : (
                    <Badge className="bg-gray-500/20 text-gray-400 border-gray-500/30" variant="outline">
                      Disconnected
                    </Badge>
                  )}
                </div>

                {jiraStatus?.connected && !editing && (
                  <div className="flex gap-2">
                    <Button
                      onClick={() => testMut.mutate()}
                      disabled={testMut.isPending}
                      variant="outline"
                      size="sm"
                      className="border-[#30363D] text-[#C9D1D9] hover:bg-[#21262D]"
                    >
                      {testMut.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                      Test Connection
                    </Button>
                    <Button
                      onClick={() => setEditing(true)}
                      variant="outline"
                      size="sm"
                      className="border-[#30363D] text-[#C9D1D9] hover:bg-[#21262D]"
                    >
                      <Pencil className="h-4 w-4 mr-1" />
                      Edit
                    </Button>
                    <Button
                      onClick={() => disconnectMut.mutate()}
                      disabled={disconnectMut.isPending}
                      variant="outline"
                      size="sm"
                      className="border-red-500/30 text-red-400 hover:bg-red-500/10"
                    >
                      {disconnectMut.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                      <Unplug className="h-4 w-4 mr-1" />
                      Disconnect
                    </Button>
                  </div>
                )}
              </div>

              {/* Connected info (non-edit mode) */}
              {jiraStatus?.connected && !editing && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm border border-[#30363D] rounded-lg p-4">
                  <div>
                    <span className="text-[#8B949E]">Site URL</span>
                    <p className="text-[#C9D1D9] mt-1 flex items-center gap-1">
                      {jiraStatus.site_url}
                      <a href={jiraStatus.site_url ?? '#'} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="h-3 w-3 text-[#58A6FF]" />
                      </a>
                    </p>
                  </div>
                  <div>
                    <span className="text-[#8B949E]">Email</span>
                    <p className="text-[#C9D1D9] mt-1">{jiraStatus.user_email}</p>
                  </div>
                  <div>
                    <span className="text-[#8B949E]">API Token</span>
                    <p className="text-[#C9D1D9] mt-1 font-mono tracking-widest">{'••••••••'}</p>
                  </div>
                </div>
              )}

              {/* Test result feedback */}
              {testResult && (
                <div
                  className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
                    testResult.ok
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}
                >
                  {testResult.ok ? <Check className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  {testResult.message}
                </div>
              )}

              {/* Connection form */}
              {showForm && (
                <div className="space-y-3 border border-[#30363D] rounded-lg p-4">
                  <div>
                    <Label className="text-[#C9D1D9]">Jira Site URL</Label>
                    <Input
                      value={siteUrl}
                      onChange={e => setSiteUrl(e.target.value)}
                      placeholder="https://your-org.atlassian.net"
                      className="bg-[#161B22] border-[#30363D] text-[#C9D1D9] mt-1 max-w-md"
                    />
                  </div>
                  <div>
                    <Label className="text-[#C9D1D9]">Email</Label>
                    <Input
                      type="email"
                      value={jiraEmail}
                      onChange={e => setJiraEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="bg-[#161B22] border-[#30363D] text-[#C9D1D9] mt-1 max-w-md"
                    />
                  </div>
                  <div>
                    <Label className="text-[#C9D1D9]">API Token</Label>
                    <Input
                      type="password"
                      value={apiToken}
                      onChange={e => setApiToken(e.target.value)}
                      placeholder="Paste your Jira API token"
                      className="bg-[#161B22] border-[#30363D] text-[#C9D1D9] mt-1 max-w-md"
                    />
                    <p className="text-xs text-[#484F58] mt-1">
                      Generate a token at{' '}
                      <a
                        href="https://id.atlassian.com/manage-profile/security/api-tokens"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#58A6FF] hover:underline"
                      >
                        id.atlassian.com/manage-profile/security/api-tokens
                      </a>
                    </p>
                  </div>

                  <div className="flex gap-2 pt-1">
                    <Button
                      onClick={handleConnect}
                      disabled={connectMut.isPending || !siteUrl.trim() || !jiraEmail.trim() || !apiToken}
                      className="bg-[#238636] hover:bg-[#2ea043]"
                    >
                      {connectMut.isPending && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                      Save & Connect
                    </Button>
                    {editing && (
                      <Button
                        onClick={() => { setEditing(false); setTestResult(null); }}
                        variant="outline"
                        className="border-[#30363D] text-[#C9D1D9] hover:bg-[#21262D]"
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>
              )}

              {/* Jira Projects */}
              {jiraStatus?.connected && jiraProjects && jiraProjects.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-sm font-medium text-[#8B949E] mb-2">Available Projects</h4>
                  <Table>
                    <TableHeader>
                      <TableRow className="border-[#30363D] hover:bg-transparent">
                        <TableHead className="text-[#8B949E]">Key</TableHead>
                        <TableHead className="text-[#8B949E]">Name</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {jiraProjects.map(p => (
                        <TableRow key={p.id} className="border-[#30363D] hover:bg-[#161B22]">
                          <TableCell className="text-[#58A6FF] font-mono text-xs">{p.key}</TableCell>
                          <TableCell className="text-[#C9D1D9] text-sm">{p.name}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* ===================== Bug Template ===================== */}
      {jiraStatus?.connected && (
        <Card className="bg-[#161B22] border-[#30363D]">
          <CardHeader>
            <CardTitle className="text-[#C9D1D9] text-lg">Bug Template</CardTitle>
            <p className="text-xs text-[#484F58]">
              Customize the title and description when creating Jira bugs from test results. Leave empty to use defaults.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Available placeholders */}
            <div className="flex flex-wrap gap-1.5">
              {(templateQuery.data?.available_placeholders ?? []).map(p => (
                <code
                  key={p.key}
                  className="px-1.5 py-0.5 bg-[#0D1117] border border-[#30363D] rounded text-xs text-[#58A6FF] cursor-pointer hover:border-[#58A6FF] transition-colors"
                  title={`${p.label} — e.g. ${p.example}`}
                  onClick={() => navigator.clipboard.writeText(`{${p.key}}`)}
                >
                  {`{${p.key}}`}
                </code>
              ))}
              <span className="text-xs text-[#484F58] self-center ml-1">Click to copy</span>
            </div>

            {/* Title template */}
            <div>
              <Label className="text-[#C9D1D9]">Title Template</Label>
              <Input
                value={titleTemplate}
                onChange={e => setTitleTemplate(e.target.value)}
                placeholder={templateQuery.data?.default_title || '[{tc_id}] {title} - Test Failed'}
                className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1 font-mono text-sm"
              />
            </div>

            {/* Description template */}
            <div>
              <Label className="text-[#C9D1D9]">Description Template</Label>
              <textarea
                value={descTemplate}
                onChange={e => setDescTemplate(e.target.value)}
                placeholder={templateQuery.data?.default_description || 'Test Case: {tc_id} - {title}\nUser Role: {user_role}\n...'}
                rows={8}
                className="flex w-full rounded-md bg-[#0D1117] border border-[#30363D] text-[#C9D1D9] mt-1 font-mono text-sm px-3 py-2 placeholder:text-[#484F58] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#58A6FF] resize-y"
              />
            </div>

            <Button
              onClick={() => saveTemplateMut.mutate({
                title_template: titleTemplate,
                description_template: descTemplate,
              })}
              disabled={saveTemplateMut.isPending}
              className="bg-[#238636] hover:bg-[#2ea043]"
            >
              {saveTemplateMut.isPending ? 'Saving...' : 'Save Template'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ===================== Notifications ===================== */}
      <Card className="border-[#30363D] bg-[#0D1117]">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-[#C9D1D9]">
            <Bell className="h-5 w-5 text-[#D29922]" />
            Notifications
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {loadingNotif ? (
            <Skeleton className="h-24 bg-[#21262D]" />
          ) : (
            <>
              <div>
                <Label className="text-[#C9D1D9]">Notification Email</Label>
                <Input
                  type="email"
                  value={notifEmail}
                  onChange={e => setNotifEmail(e.target.value)}
                  placeholder="alerts@example.com"
                  className="bg-[#161B22] border-[#30363D] text-[#C9D1D9] mt-1 max-w-md"
                />
                <p className="text-xs text-[#484F58] mt-1">Receive email alerts when APIs go down.</p>
              </div>
              <div>
                <Label className="text-[#C9D1D9]">Webhook URL</Label>
                <Input
                  value={webhook}
                  onChange={e => setWebhook(e.target.value)}
                  placeholder="https://hooks.slack.com/services/..."
                  className="bg-[#161B22] border-[#30363D] text-[#C9D1D9] mt-1 max-w-md"
                />
                <p className="text-xs text-[#484F58] mt-1">Send webhook notifications (Slack, Discord, etc).</p>
              </div>
              <Button
                onClick={handleSaveNotif}
                disabled={notifMut.isPending}
                className="bg-[#238636] hover:bg-[#2ea043]"
              >
                {notifMut.isPending ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : notifSaved ? (
                  <Check className="h-4 w-4 mr-1" />
                ) : null}
                {notifSaved ? 'Saved!' : 'Save Settings'}
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
