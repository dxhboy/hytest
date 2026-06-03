import request from '@/utils/api'

export function validateJiraConnection() {
  return request({ url: '/requirement-analysis/jira/validate/', method: 'post' })
}

export function previewJiraIssues(data) {
  return request({ url: '/requirement-analysis/jira/preview/', method: 'post', data })
}

export function importJiraIssues(data) {
  return request({ url: '/requirement-analysis/jira/import/', method: 'post', data })
}

export function getJiraIssues(params) {
  return request({ url: '/requirement-analysis/jira/issues/', method: 'get', params })
}

export function linkCasesToIssue(issueId, data) {
  return request({ url: `/requirement-analysis/jira/issues/${issueId}/link-cases/`, method: 'post', data })
}

export function unlinkCasesFromIssue(issueId, data) {
  return request({ url: `/requirement-analysis/jira/issues/${issueId}/unlink-cases/`, method: 'post', data })
}

export function getIssueCases(issueId) {
  return request({ url: `/requirement-analysis/jira/issues/${issueId}/cases/`, method: 'get' })
}

export function recommendCasesByVersion(versionId) {
  return request({ url: '/requirement-analysis/jira/recommend/', method: 'post', data: { version_id: versionId } })
}