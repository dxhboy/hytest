import request from "@/utils/api";

// 知识库文档

export function getKnowledgeDocs(projectId) {
  return request({
    url: "/requirement-analysis/knowledge/documents/",
    method: "get",
    params: { project_id: projectId },
  });
}

export function uploadKnowledgeDoc(projectId, file) {
  const formData = new FormData();
  formData.append("project_id", projectId);
  formData.append("file", file);
  return request({
    url: "/requirement-analysis/knowledge/documents/upload/",
    method: "post",
    data: formData,
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function deleteKnowledgeDoc(docId) {
  return request({
    url: `/requirement-analysis/knowledge/documents/${docId}/`,
    method: "delete",
  });
}

// 项目 Skills

export function getProjectSkill(projectId) {
  return request({
    url: "/requirement-analysis/knowledge/skill/",
    method: "get",
    params: { project_id: projectId },
  });
}

export function saveProjectSkill(projectId, content) {
  return request({
    url: "/requirement-analysis/knowledge/skill/save/",
    method: "put",
    data: { project_id: projectId, content },
  });
}