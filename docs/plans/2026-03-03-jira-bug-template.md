# Jira Bug Template 實作計畫

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 讓每個組織自訂 Jira Bug 的標題和描述模板，建立 Bug 時套用模板而非硬編碼格式。

**Architecture:** 在 Organization 表新增兩個欄位儲存模板字串，模板支援佔位符（如 `{tc_id}`、`{title}`）。建立 Bug 時用 Python `str.format_map()` 將佔位符替換為實際值。前端在 Jira Settings 頁面新增模板設定區塊。

**Tech Stack:** Flask, SQLAlchemy, Alembic, React 19, TypeScript, TanStack Query, shadcn/ui

---

## 佔位符清單

模板中可使用的佔位符（來自 TestCase + TestResult）：

| 佔位符 | 來源 | 範例值 |
|--------|------|--------|
| `{tc_id}` | TestCase.tc_id | AUTH-001 |
| `{title}` | TestCase.title | Login Feature Test |
| `{user_role}` | TestCase.user_role | Admin |
| `{feature_description}` | TestCase.feature_description | User authentication system |
| `{acceptance_criteria}` | TestCase.acceptance_criteria | Should login successfully |
| `{test_notes}` | TestResult.notes | Username field broken |
| `{known_issues}` | TestResult.known_issues | DB timeout |
| `{status}` | TestResult.status | fail |
| `{project_key}` | 使用者選擇的 Jira project key | PROJ |

## 預設模板

**標題預設值（與目前硬編碼一致）：**
```
[{tc_id}] {title} - Test Failed
```

**描述預設值：**
```
Test Case: {tc_id} - {title}
User Role: {user_role}
Feature: {feature_description}
Acceptance Criteria: {acceptance_criteria}

Test Notes: {test_notes}
Known Issues: {known_issues}
```

---

### Task 1: DB Model — 新增模板欄位

**Files:**
- Modify: `backend/database/models.py` (Organization class, ~line 46)

**Step 1: 在 Organization model 的 jira_api_token 後方新增兩個欄位**

```python
    jira_bug_title_template = Column(Text)       # e.g. "[{tc_id}] {title} - Test Failed"
    jira_bug_description_template = Column(Text)  # multi-line template with placeholders
```

**Step 2: 驗證 model 語法**

Run: `cd backend && python -c "from database.models import Organization; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/database/models.py
git commit -m "feat(model): add jira bug template fields to Organization"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/database/migrations/versions/d4e5f6a7b8c9_add_jira_bug_template_fields.py`

Migration chain: `c3d4e5f6a7b8` → `d4e5f6a7b8c9`

**Step 1: 建立 migration 檔**

```python
"""Add Jira bug template fields to organizations.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('jira_bug_title_template', sa.Text(), nullable=True))
    op.add_column('organizations', sa.Column('jira_bug_description_template', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'jira_bug_description_template')
    op.drop_column('organizations', 'jira_bug_title_template')
```

**Step 2: 驗證 migration**

Run: `cd backend && alembic upgrade head`
Expected: 無錯誤

**Step 3: Commit**

```bash
git add backend/database/migrations/versions/d4e5f6a7b8c9_add_jira_bug_template_fields.py
git commit -m "feat(migration): add jira_bug_title/description_template columns"
```

---

### Task 3: Backend Service — 模板渲染邏輯

**Files:**
- Modify: `backend/services/jira_service.py` (~line 262-291)

**Step 1: 寫測試 — 模板渲染和 fallback**

在 `backend/tests/test_jira.py` 新增測試：

```python
class TestBugTemplate:
    """Tests for Jira bug template rendering."""

    def test_create_issue_uses_custom_title_template(self, app, tenant_data, mocker):
        """When org has a custom title template, the Issue summary uses it."""
        client = app.test_client()
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(id=tenant_data['tenant1_id']).first()
            org.jira_bug_title_template = 'BUG: {tc_id} | {title}'
            db.commit()

            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {'key': 'PROJ-999', 'id': '99999'}
            mocker.patch('services.jira_service.requests.post', return_value=mock_resp)

            resp = client.post('/api/jira/create-issue', json={
                'test_result_id': tenant_data['result1_id'],
                'project_key': 'PROJ',
            }, headers={'Authorization': f"Bearer {tenant_data['token1']}"})

            assert resp.status_code == 200
            # Verify the payload sent to Jira
            call_kwargs = mocker.patch.return_value  # check actual call
            sent_payload = requests.post.call_args[1]['json']
            assert sent_payload['fields']['summary'].startswith('BUG:')
        finally:
            # Reset template
            org = db.query(Organization).filter_by(id=tenant_data['tenant1_id']).first()
            org.jira_bug_title_template = None
            db.commit()
            db.close()

    def test_create_issue_uses_custom_description_template(self, app, tenant_data, mocker):
        """When org has a custom description template, the Issue body uses it."""
        client = app.test_client()
        db = SessionLocal()
        try:
            org = db.query(Organization).filter_by(id=tenant_data['tenant1_id']).first()
            org.jira_bug_description_template = '## Bug Report\nTC: {tc_id}\nTitle: {title}\nNotes: {test_notes}'
            db.commit()

            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {'key': 'PROJ-888', 'id': '88888'}
            mocker.patch('services.jira_service.requests.post', return_value=mock_resp)

            resp = client.post('/api/jira/create-issue', json={
                'test_result_id': tenant_data['result1_id'],
                'project_key': 'PROJ',
            }, headers={'Authorization': f"Bearer {tenant_data['token1']}"})

            assert resp.status_code == 200
            sent_payload = requests.post.call_args[1]['json']
            desc_text = sent_payload['fields']['description']['content'][0]['content'][0]['text']
            assert '## Bug Report' in desc_text
        finally:
            org = db.query(Organization).filter_by(id=tenant_data['tenant1_id']).first()
            org.jira_bug_description_template = None
            db.commit()
            db.close()

    def test_create_issue_falls_back_to_default_when_no_template(self, app, tenant_data, mocker):
        """When org has no template set, uses the default hardcoded format."""
        client = app.test_client()

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {'key': 'PROJ-777', 'id': '77777'}
        mocker.patch('services.jira_service.requests.post', return_value=mock_resp)

        resp = client.post('/api/jira/create-issue', json={
            'test_result_id': tenant_data['result1_id'],
            'project_key': 'PROJ',
        }, headers={'Authorization': f"Bearer {tenant_data['token1']}"})

        assert resp.status_code == 200
        sent_payload = requests.post.call_args[1]['json']
        # Default format: [{tc_id}] {title} - Test Failed
        assert '- Test Failed' in sent_payload['fields']['summary']
```

**Step 2: 執行測試確認失敗**

Run: `cd backend && JWT_SECRET=test-secret python -m pytest tests/test_jira.py::TestBugTemplate -v`
Expected: FAIL（因為還沒改 service）

**Step 3: 修改 `create_issue_from_test_result()`**

在 `jira_service.py` 的 `create_issue_from_test_result()` 中，將硬編碼的 summary/description 改為模板渲染。在 line 258（`case = ...` 之後）加入以下邏輯：

```python
    # --- Fetch org templates ---
    org = db.query(Organization).filter_by(id=get_tenant_id()).first()

    # Build placeholder values (missing fields default to empty string)
    placeholders = {
        'tc_id': case.tc_id or '',
        'title': case.title or '',
        'user_role': case.user_role or '',
        'feature_description': case.feature_description or '',
        'acceptance_criteria': case.acceptance_criteria or '',
        'test_notes': result.notes or '',
        'known_issues': result.known_issues or '',
        'status': result.status or '',
        'project_key': project_key,
    }

    # Render summary from template (fallback to default)
    DEFAULT_TITLE = '[{tc_id}] {title} - Test Failed'
    DEFAULT_DESCRIPTION = (
        'Test Case: {tc_id} - {title}\n'
        'User Role: {user_role}\n'
        'Feature: {feature_description}\n'
        'Acceptance Criteria: {acceptance_criteria}\n'
        '\nTest Notes: {test_notes}\n'
        'Known Issues: {known_issues}'
    )

    title_template = org.jira_bug_title_template or DEFAULT_TITLE if org else DEFAULT_TITLE
    desc_template = org.jira_bug_description_template or DEFAULT_DESCRIPTION if org else DEFAULT_DESCRIPTION

    summary_text = title_template.format_map(placeholders)
    description_text = desc_template.format_map(placeholders)
```

然後 **刪除** 原本的 `desc_parts` 構建邏輯（line 263-274）和舊的 `summary`（line 280），改用新的 `summary_text` 和 `description_text`：

```python
    payload = {
        'fields': {
            'project': {'key': project_key},
            'summary': summary_text,
            'description': {
                'type': 'doc',
                'version': 1,
                'content': [{
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': description_text}],
                }],
            },
            'issuetype': {'name': issue_type},
        }
    }
```

同時更新 `JiraIssueLink` 的 summary 也用 `summary_text`：
```python
    link = JiraIssueLink(
        ...
        jira_issue_summary=summary_text,
        ...
    )
```

注意：移除重複的 `org` 查詢（原 line 312），因為前面已經查過了。

**Step 4: 執行測試確認通過**

Run: `cd backend && JWT_SECRET=test-secret python -m pytest tests/test_jira.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/services/jira_service.py backend/tests/test_jira.py
git commit -m "feat(jira): render bug title/description from org template with fallback"
```

---

### Task 4: Backend Route — 模板 CRUD API

**Files:**
- Modify: `backend/routes/jira.py`

**Step 1: 寫測試 — GET/PUT 模板端點**

在 `backend/tests/test_jira.py` 新增：

```python
class TestBugTemplateApi:
    """Tests for GET/PUT /api/jira/bug-template endpoints."""

    def test_get_template_returns_defaults_when_empty(self, app, tenant_data):
        """GET /api/jira/bug-template returns null templates when not set."""
        client = app.test_client()
        resp = client.get('/api/jira/bug-template',
                          headers={'Authorization': f"Bearer {tenant_data['token1']}"})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['title_template'] is None
        assert data['description_template'] is None
        assert len(data['available_placeholders']) > 0

    def test_put_template_saves_and_get_returns_it(self, app, tenant_data):
        """PUT then GET returns the saved templates."""
        client = app.test_client()
        headers = {'Authorization': f"Bearer {tenant_data['token1']}"}

        resp = client.put('/api/jira/bug-template', json={
            'title_template': 'BUG: {tc_id} - {title}',
            'description_template': 'Case: {tc_id}\n{feature_description}',
        }, headers=headers)
        assert resp.status_code == 200

        resp = client.get('/api/jira/bug-template', headers=headers)
        data = resp.get_json()['data']
        assert data['title_template'] == 'BUG: {tc_id} - {title}'
        assert data['description_template'] == 'Case: {tc_id}\n{feature_description}'

    def test_put_template_clears_with_empty_string(self, app, tenant_data):
        """PUT with empty strings resets to null (will use defaults)."""
        client = app.test_client()
        headers = {'Authorization': f"Bearer {tenant_data['token1']}"}

        resp = client.put('/api/jira/bug-template', json={
            'title_template': '',
            'description_template': '',
        }, headers=headers)
        assert resp.status_code == 200

        resp = client.get('/api/jira/bug-template', headers=headers)
        data = resp.get_json()['data']
        assert data['title_template'] is None
        assert data['description_template'] is None
```

**Step 2: 執行測試確認失敗**

Run: `cd backend && JWT_SECRET=test-secret python -m pytest tests/test_jira.py::TestBugTemplateApi -v`
Expected: FAIL（404，端點不存在）

**Step 3: 在 `routes/jira.py` 新增兩個端點**

```python
# ---------------------------------------------------------------------------
# GET /api/jira/bug-template -- Get bug template settings
# ---------------------------------------------------------------------------

@jira_bp.route('/bug-template', methods=['GET'])
@jwt_required
def get_bug_template():
    """Return the org's Jira bug title/description templates and available placeholders."""
    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(id=g.tenant_id).first()
        return jsonify({'data': {
            'title_template': org.jira_bug_title_template if org else None,
            'description_template': org.jira_bug_description_template if org else None,
            'available_placeholders': [
                {'key': 'tc_id', 'label': 'TC ID', 'example': 'AUTH-001'},
                {'key': 'title', 'label': 'Test Case Title', 'example': 'Login Feature Test'},
                {'key': 'user_role', 'label': 'User Role', 'example': 'Admin'},
                {'key': 'feature_description', 'label': 'Feature Description', 'example': 'User authentication'},
                {'key': 'acceptance_criteria', 'label': 'Acceptance Criteria', 'example': 'Should login successfully'},
                {'key': 'test_notes', 'label': 'Test Notes', 'example': 'Field not accepting input'},
                {'key': 'known_issues', 'label': 'Known Issues', 'example': 'DB timeout'},
                {'key': 'status', 'label': 'Test Result Status', 'example': 'fail'},
                {'key': 'project_key', 'label': 'Jira Project Key', 'example': 'PROJ'},
            ],
            'default_title': '[{tc_id}] {title} - Test Failed',
            'default_description': 'Test Case: {tc_id} - {title}\nUser Role: {user_role}\nFeature: {feature_description}\nAcceptance Criteria: {acceptance_criteria}\n\nTest Notes: {test_notes}\nKnown Issues: {known_issues}',
        }}), 200
    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /api/jira/bug-template -- Update bug template settings
# ---------------------------------------------------------------------------

@jira_bp.route('/bug-template', methods=['PUT'])
@jwt_required
def update_bug_template():
    """Save the org's Jira bug title/description templates."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'Request body required'}), 400

    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(id=g.tenant_id).first()
        if not org:
            return jsonify({'error': 'Organization not found'}), 404

        title = (body.get('title_template') or '').strip() or None
        description = (body.get('description_template') or '').strip() or None

        org.jira_bug_title_template = title
        org.jira_bug_description_template = description
        db.commit()

        return jsonify({'data': {
            'title_template': org.jira_bug_title_template,
            'description_template': org.jira_bug_description_template,
        }}), 200
    finally:
        db.close()
```

需要在檔案頂部確認已匯入 `Organization` 和 `g`：
```python
from flask import Blueprint, request, jsonify, Response, g
from database.models import Organization
```

**Step 4: 執行測試確認通過**

Run: `cd backend && JWT_SECRET=test-secret python -m pytest tests/test_jira.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/routes/jira.py backend/tests/test_jira.py
git commit -m "feat(jira): add GET/PUT /api/jira/bug-template endpoints"
```

---

### Task 5: Frontend — Jira Settings 頁面新增 Bug Template 區塊

**Files:**
- Modify: `frontend/src/pages/JiraSettings.tsx`

**Step 1: 新增 TypeScript 介面和狀態**

在 JiraSettings 元件內新增：

```typescript
// Bug template state
const [titleTemplate, setTitleTemplate] = useState('');
const [descTemplate, setDescTemplate] = useState('');
const [templateDefaults, setTemplateDefaults] = useState<{
  default_title: string;
  default_description: string;
  available_placeholders: { key: string; label: string; example: string }[];
}>({ default_title: '', default_description: '', available_placeholders: [] });
```

**Step 2: 新增 TanStack Query 查詢和 mutation**

```typescript
// Fetch bug template
const templateQuery = useQuery({
  queryKey: ['jira-bug-template'],
  queryFn: () => api.get<ApiResponse<{
    title_template: string | null;
    description_template: string | null;
    default_title: string;
    default_description: string;
    available_placeholders: { key: string; label: string; example: string }[];
  }>>('/jira/bug-template').then(r => r.data.data),
  enabled: jiraStatus === 'connected',
});

// When template data loads, populate state
useEffect(() => {
  if (templateQuery.data) {
    setTitleTemplate(templateQuery.data.title_template ?? '');
    setDescTemplate(templateQuery.data.description_template ?? '');
    setTemplateDefaults({
      default_title: templateQuery.data.default_title,
      default_description: templateQuery.data.default_description,
      available_placeholders: templateQuery.data.available_placeholders,
    });
  }
}, [templateQuery.data]);

// Save bug template
const saveTemplateMut = useMutation({
  mutationFn: (data: { title_template: string; description_template: string }) =>
    api.put('/jira/bug-template', data),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['jira-bug-template'] });
  },
});
```

**Step 3: 新增 UI 區塊（放在 Jira Integration Card 和 Notifications Card 之間）**

```tsx
{/* Bug Template Card — only show when connected */}
{jiraStatus === 'connected' && (
  <Card className="bg-[#161B22] border-[#30363D]">
    <CardHeader>
      <CardTitle className="text-[#C9D1D9] text-lg">Bug Template</CardTitle>
      <p className="text-xs text-[#484F58]">
        Customize the title and description when creating Jira bugs from test results.
        Leave empty to use defaults.
      </p>
    </CardHeader>
    <CardContent className="space-y-4">
      {/* Available placeholders */}
      <div className="flex flex-wrap gap-1.5">
        {templateDefaults.available_placeholders.map(p => (
          <code
            key={p.key}
            className="px-1.5 py-0.5 bg-[#0D1117] border border-[#30363D] rounded text-xs text-[#58A6FF] cursor-pointer"
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
          placeholder={templateDefaults.default_title || '[{tc_id}] {title} - Test Failed'}
          className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1 font-mono text-sm"
        />
      </div>

      {/* Description template */}
      <div>
        <Label className="text-[#C9D1D9]">Description Template</Label>
        <Textarea
          value={descTemplate}
          onChange={e => setDescTemplate(e.target.value)}
          placeholder={templateDefaults.default_description || 'Test Case: {tc_id} - {title}\nUser Role: {user_role}\n...'}
          rows={8}
          className="bg-[#0D1117] border-[#30363D] text-[#C9D1D9] mt-1 font-mono text-sm"
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
```

注意：需要確認 `Textarea` 元件是否已從 shadcn/ui 匯入。如果沒有，需要從 `@/components/ui/textarea` 匯入，或用原生 `<textarea>` 搭配樣式。

**Step 4: Frontend 類型檢查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 無錯誤

**Step 5: Commit**

```bash
git add frontend/src/pages/JiraSettings.tsx
git commit -m "feat(frontend): add bug template config UI in Jira Settings"
```

---

### Task 6: 全面測試驗證

**Step 1: 後端全部測試**

Run: `cd backend && JWT_SECRET=test-secret python -m pytest tests/ -v`
Expected: ALL PASS

**Step 2: 前端建置**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 無錯誤

**Step 3: 手動驗證流程**

1. 啟動前後端 → 進入 Jira Settings
2. 連接 Jira 後，看到 Bug Template 區塊
3. 點擊佔位符標籤可複製
4. 輸入自定義 Title：`BUG: {tc_id} | {title}`
5. 輸入自定義 Description：`## Bug Report\n\nTC: {tc_id} - {title}\nRole: {user_role}\n\nNotes: {test_notes}`
6. 點擊 Save Template
7. 到 Test Projects → 對 failed 案例建立 Jira Bug
8. 確認建立的 Issue 使用自定義模板
9. 清空模板 → 確認 fallback 到預設格式

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: jira bug template — org-level customizable title and description"
```

---

### Task 7: 更新文件

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Step 1: 更新 CLAUDE.md**

在 Jira Settings 頁面描述中加入 Bug Template 功能說明。

**Step 2: 更新 README.md**

在 Jira Integration 功能描述中加入模板自訂說明：
```
Connect your Jira instance with API Token, create issues from test results with customizable bug templates, sync status bidirectionally.
```

**Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update CLAUDE.md and README.md for jira bug template feature"
```

---

## 關鍵檔案

| 檔案 | 動作 |
|------|------|
| `backend/database/models.py` | 新增 2 欄位 |
| `backend/database/migrations/versions/d4e5f6a7b8c9_...py` | 新增 migration |
| `backend/services/jira_service.py` | 模板渲染邏輯取代硬編碼 |
| `backend/routes/jira.py` | 新增 GET/PUT bug-template 端點 |
| `backend/tests/test_jira.py` | 新增模板相關測試 |
| `frontend/src/pages/JiraSettings.tsx` | Bug Template UI 區塊 |
| `CLAUDE.md` | 文件更新 |
| `README.md` | 文件更新 |

## 風險和注意事項

1. **`format_map` 安全性** — 使用 `str.format_map()` 搭配固定的 placeholder dict，不接受任意 Python expressions，安全無虞
2. **無效佔位符容錯** — 如果使用者打了 `{typo}`，`format_map` 會拋 KeyError。需要用 `collections.defaultdict` 或 `string.Template` 來安全處理。建議在 service 中用 `defaultdict(str)` 包裝 placeholders：
   ```python
   from collections import defaultdict
   safe_placeholders = defaultdict(str, placeholders)
   summary_text = title_template.format_map(safe_placeholders)
   ```
3. **ADF 限制** — 目前描述只支援純文字（一個 paragraph）。未來如需支援 markdown 到 ADF 轉換，可單獨擴展，不在本次範圍
