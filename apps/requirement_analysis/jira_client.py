import httpx
import base64
import re
from typing import Optional

ALLOWED_FIELDS = {'summary', 'description', 'acceptance_criteria', 'subtasks', 'labels', 'priority'}
MAX_EPIC_CHILDREN = 50


class JiraClientError(Exception):
    pass


class JiraClient:
    def __init__(self, domain: str, email: str, api_token: str):
        self.base_url = f'https://{domain}/rest/api/3'
        credentials = base64.b64encode(f'{email}:{api_token}'.encode()).decode()
        self.headers = {
            'Authorization': f'Basic {credentials}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def get_issue(self, issue_key: str, fields: list) -> dict:
        safe_fields = [f for f in fields if f in ALLOWED_FIELDS]
        if 'summary' not in safe_fields:
            safe_fields.insert(0, 'summary')
        params = {'fields': ','.join(safe_fields)}
        resp = httpx.get(
            f'{self.base_url}/issue/{issue_key}',
            headers=self.headers,
            params=params,
            timeout=10,
        )
        if resp.status_code == 404:
            raise JiraClientError(f'Issue {issue_key} not found')
        if resp.status_code == 401:
            raise JiraClientError('Jira authentication failed: check email and API token')
        if resp.status_code == 403:
            raise JiraClientError(f'No permission to access {issue_key}')
        if resp.status_code != 200:
            raise JiraClientError(f'Jira API error {resp.status_code} for {issue_key}')
        return resp.json()

    def get_epic_children(self, epic_key: str, fields: list) -> list:
        jql = f'"Epic Link" = {epic_key} OR parent = {epic_key}'
        params = {
            'jql': jql,
            'fields': ','.join(fields),
            'maxResults': MAX_EPIC_CHILDREN,
        }
        resp = httpx.get(
            f'{self.base_url}/search',
            headers=self.headers,
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            raise JiraClientError(f'Failed to fetch Epic children: {resp.status_code}')
        return resp.json().get('issues', [])

    def extract_content(self, issue: dict, selected_fields: list) -> str:
        fields = issue.get('fields', {})
        lines = [f'# {fields.get("summary", "")}']

        if 'description' in selected_fields and fields.get('description'):
            lines.append('\n## 需求描述')
            lines.append(self._adf_to_text(fields['description']))

        if 'acceptance_criteria' in selected_fields:
            for key, val in fields.items():
                if key.startswith('customfield_') and isinstance(val, dict):
                    text = self._adf_to_text(val)
                    if text:
                        lines.append('\n## 验收标准')
                        lines.append(text)
                        break

        if 'subtasks' in selected_fields and fields.get('subtasks'):
            lines.append('\n## 子任务')
            for sub in fields['subtasks']:
                lines.append(f'- {sub["fields"]["summary"]}')

        if 'priority' in selected_fields and fields.get('priority'):
            lines.append(f'\n**优先级:** {fields["priority"]["name"]}')

        if 'labels' in selected_fields and fields.get('labels'):
            lines.append(f'**标签:** {", ".join(fields["labels"])}')

        return '\n'.join(lines)

    def validate_connection(self) -> bool:
        try:
            resp = httpx.get(
                f'{self.base_url}/myself',
                headers=self.headers,
                timeout=8,
            )
            return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _adf_to_text(adf: dict) -> str:
        if not adf or not isinstance(adf, dict):
            return ''
        node_type = adf.get('type', '')
        content = adf.get('content', [])
        text = adf.get('text', '')

        if node_type == 'text':
            return text
        parts = [JiraClient._adf_to_text(child) for child in content]
        joined = ' '.join(p for p in parts if p)
        if node_type in ('paragraph', 'heading'):
            return joined + '\n'
        if node_type == 'listItem':
            return f'- {joined}'
        return joined

    @staticmethod
    def issue_key_from_url(url: str) -> Optional[str]:
        match = re.search(r'/browse/([A-Z][A-Z0-9]+-\d+)', url)
        if match:
            return match.group(1)
        if re.match(r'^[A-Z][A-Z0-9]+-\d+$', url.strip()):
            return url.strip()
        return None