export interface User {
  id: string;
  username: string;
  email: string;
  role: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
  trial_ends_at: string | null;
  subscription_status: string;
}

// --- API Endpoints ---

export interface ApiEndpoint {
  id: number;
  name: string;
  url: string;
  method: string;
  request_body: string | null;
  headers: string | null;
  expected_status_code: number;
  check_interval_seconds: number;
  status: string;
  response_time: number;
  last_check: string | null;
  error_count: number;
  last_error: string | null;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApiCheckHistory {
  id: number;
  api_id: number;
  status: string;
  status_code: number | null;
  response_time_ms: number | null;
  error_message: string | null;
  checked_at: string;
}

export interface ApiUptime {
  uptime_percent: number;
  total_checks: number;
  healthy_checks: number;
  period_days: number;
}

// --- Test Cases ---

export interface TestCase {
  id: number;
  tc_id: string;
  title: string;
  user_role: string | null;
  feature_description: string | null;
  acceptance_criteria: string | null;
  test_notes: string | null;
  priority: string;
  status: string;
  test_project_id: number | null;
  responsible_user_id: string | null;
  estimated_hours: number;
  actual_hours: number;
  product_tags: ProductTag[];
  created_at: string | null;
  updated_at: string | null;
}

// --- Product Tags ---

export interface ProductTag {
  id: number;
  name: string;
  description?: string | null;
  color: string;
  created_at?: string | null;
  updated_at?: string | null;
}

// --- Test Projects ---

export interface ProjectStats {
  total: number;
  pass_count: number;
  fail_count: number;
  blocked_count: number;
  not_tested_count: number;
  completion_rate: number;
}

export interface TestResult {
  id: number;
  project_id: number;
  test_case_id: number;
  status: string;
  notes: string | null;
  known_issues: string | null;
  blocked_reason: string | null;
  tested_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProjectTestCase {
  id: number;
  tc_id: string;
  title: string;
  priority: string;
  status: string;
  assigned_user_id: string | null;
  assigned_user_name: string | null;
  result: TestResult | null;
}

export interface TestProject {
  id: number;
  name: string;
  description: string | null;
  status: string;
  responsible_user_id: string | null;
  responsible_user_name: string | null;
  start_time: string | null;
  end_time: string | null;
  created_at: string | null;
  updated_at: string | null;
  stats: ProjectStats;
  test_cases?: ProjectTestCase[];
}

// --- Coverage ---

export interface CoverageDashboard {
  total_apis: number;
  covered_apis: number;
  uncovered_apis: number;
  coverage_percent: number;
  uncovered_api_list: {
    id: number;
    name: string;
    url: string;
    status: string;
  }[];
}

export interface CoverageAlert {
  type: string;
  severity: string;
  message: string;
  target_id: number;
  target_name: string;
}

// --- Jira ---

export interface JiraStatus {
  connected: boolean;
  site_url: string | null;
  user_email: string | null;
}

export interface JiraProject {
  key: string;
  name: string;
  id: string;
}

export interface JiraIssueLink {
  id: number;
  test_case_id: number;
  test_result_id: number;
  jira_issue_key: string;
  jira_issue_summary: string;
  jira_status: string;
  jira_assignee: string | null;
  jira_priority: string | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

// --- Notifications ---

export interface NotificationSettings {
  notification_email: string | null;
  notification_webhook_url: string | null;
}

// --- Members ---

export interface Member {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

export interface InviteLinkInfo {
  id: string;
  token: string;
  role: string;
  max_uses: number | null;
  use_count: number;
  expires_at: string | null;
  is_active: boolean;
  created_at: string;
}

// --- Generic API Response ---

export interface ApiResponse<T> {
  data: T;
}

export interface CsvImportResult {
  created: number;
  errors: string[];
  total: number;
}
