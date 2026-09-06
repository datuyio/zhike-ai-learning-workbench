import { request, requestBlob } from './client';
import type { Citation } from '../types';

/** 助教端与学生端互动 API 层：统一走 /api/v1 前缀的 request 封装。 */

// ===== 基础类型 =====

export type TaClass = {
  id: string;
  name: string;
  description: string | null;
  invite_code: string;
  course_id: string | null;
  student_count: number;
  is_active: boolean;
  max_students: number | null;
  created_at: string | null;
};

export type StudentClass = {
  id: string;
  name: string;
  description: string | null;
  invite_code: string;
  student_count: number;
  max_students: number | null;
  ta_name: string | null;
  joined_at: string | null;
};

export type TaStudent = {
  id: string;
  name: string;
  email: string | null;
  joined_at: string | null;
};

export type TaAssignment = {
  id: string;
  title: string;
  description: string | null;
  class_id: string;
  course_id: string | null;
  concept_id: string | null;
  question_type: string;
  options: string[];
  correct_answer: string | null;
  total_score: number;
  due_at: string | null;
  late_policy: string;
  late_penalty_ratio: number;
  status: 'draft' | 'published' | 'closed';
  created_at: string | null;
  submission_count?: number;
  graded_count?: number;
  question_count?: number;
  questions?: Array<{
    id: string;
    order_index: number;
    question_type: string;
    prompt: string;
    options: string[];
    answer: string | null;
    score: number;
  }>;
};

export type TaSubmission = {
  id: string;
  student_id: string;
  student_name: string;
  answer: string;
  answers?: Record<string, string> | null;
  questions?: Array<{
    id: string;
    question_type: string;
    prompt: string;
    options: string[];
    answer: string | null;
    score: number;
  }>;
  submitted_at: string | null;
  is_late: boolean;
  attempt_number: number;
  score: number | null;
  total_score: number | null;
  status: string | null;
};

export type TaGradingRecord = {
  id: string;
  title: string;
  student_id: string;
  student_name?: string;
  class_id: string | null;
  class_name?: string;
  course_id: string | null;
  concept_id: string | null;
  grader_type: string;
  question_type: string | null;
  score: number | null;
  total_score: number | null;
  student_answer: string | null;
  feedback: unknown;
  ai_comment: string | null;
  ta_comment: string | null;
  attempt_number: number;
  is_late: boolean;
  late_penalty: number | null;
  status: 'pending' | 'graded';
  created_at: string | null;
  updated_at: string | null;
  /** 多题作业：结构化逐题作答 {question_id: 作答} 与题目快照（含标准答案） */
  student_answers?: Record<string, string>;
  questions?: Array<{
    id: string;
    order_index: number;
    question_type: string;
    prompt: string;
    options: string[];
    answer: string | null;
    score: number;
  }>;
};

export type TaQuizQuestion = {
  id?: string;
  order_index?: number;
  prompt: string;
  question_type: string;
  options: string[] | null;
  answer?: string;
  score: number;
};

export type TaQuiz = {
  id: string;
  title: string;
  description: string | null;
  class_id: string;
  status: 'draft' | 'published' | 'closed';
  question_count: number;
  total_score: number;
  submission_count: number;
  created_at: string | null;
};

export type TaQuestionBankItem = {
  id: string;
  course_id: string | null;
  question_type: string;
  prompt: string;
  options: string[];
  answer: string;
  score: number;
  source: string;
};

export type TaAlert = {
  id: string;
  student_id: string;
  student_name?: string;
  class_id: string | null;
  class_name?: string;
  alert_type: string;
  severity: 'low' | 'medium' | 'high';
  title: string;
  description: string | null;
  resolved: boolean;
  created_at: string | null;
};

export type TaAnnouncement = {
  id: string;
  title: string;
  body: string;
  announcement_type: string;
  class_id: string | null;
  class_name: string | null;
  is_pinned: boolean;
  is_active: boolean;
  created_at: string | null;
};

export type TaLessonPlan = {
  id: string;
  title: string;
  course_id: string | null;
  course_name?: string | null;
  chapter: string | null;
  content: unknown;
  outline: string | null;
  version: number;
  is_published: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type TaNotification = {
  id: string;
  title: string;
  body: string;
  notification_type: string;
  source_type: string;
  source_id: string | null;
  is_read: boolean;
  created_at: string | null;
};

export type TaDashboardStats = {
  class_count: number;
  student_count: number;
  pending_grading: number;
  active_alerts: number;
  recent_tasks: Array<{ type: string; id: string; title: string; meta: string; href: string }>;
  recent_alerts: Array<{ id: string; title: string; severity: string; student_id: string; resolved: boolean; created_at: string | null }>;
  weekly_active_trend: Array<{ date: string; active_students: number }>;
};

// ===== 助教端接口 =====

export function taDashboard(): Promise<TaDashboardStats> {
  return request<TaDashboardStats>('/ta/dashboard');
}

export function taListClasses(): Promise<TaClass[]> {
  return request<TaClass[]>('/ta/classes');
}

export function taCreateClass(payload: { name: string; description?: string | null; course_id?: string | null; max_students?: number | null }): Promise<{ id: string; name: string; invite_code: string; message: string }> {
  return request<{ id: string; name: string; invite_code: string; message: string }>('/ta/classes', { method: 'POST', body: JSON.stringify(payload) });
}

export function taRegenerateClassCode(classId: string): Promise<{ id: string; invite_code: string; message: string }> {
  return request<{ id: string; invite_code: string; message: string }>(`/ta/classes/${encodeURIComponent(classId)}/regenerate-code`, { method: 'POST' });
}

export function taUpdateClass(classId: string, payload: { name?: string; description?: string | null; max_students?: number | null; is_active?: boolean }): Promise<{ id: string }> {
  return request<{ id: string }>(`/ta/classes/${encodeURIComponent(classId)}`, { method: 'PUT', body: JSON.stringify(payload) });
}

export function taDeleteClass(classId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/classes/${encodeURIComponent(classId)}`, { method: 'DELETE' });
}

export function taListClassStudents(classId: string): Promise<TaStudent[]> {
  return request<TaStudent[]>(`/ta/classes/${encodeURIComponent(classId)}/students`);
}

export function taAddStudent(classId: string, studentId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/classes/${encodeURIComponent(classId)}/students/${encodeURIComponent(studentId)}`, { method: 'POST' });
}

export function taRemoveStudent(classId: string, studentId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/classes/${encodeURIComponent(classId)}/students/${encodeURIComponent(studentId)}`, { method: 'DELETE' });
}

export function taExportClassGradesCsv(classId: string): Promise<Blob> {
  return requestBlob(`/ta/classes/${encodeURIComponent(classId)}/export/grades.csv`);
}

export function taListAssignments(): Promise<TaAssignment[]> {
  return request<TaAssignment[]>('/ta/assignments');
}

export type TaQuestionInput = {
  prompt: string;
  question_type: string;
  options?: string[] | null;
  answer?: string | null;
  score: number;
};

export function taCreateAssignment(payload: {
  title: string;
  description?: string | null;
  class_id: string;
  course_id?: string | null;
  concept_id?: string | null;
  question_type?: string;
  options?: string[] | null;
  correct_answer?: string | null;
  total_score?: number;
  due_at?: string | null;
  late_policy?: string;
  late_penalty_ratio?: number;
  question_ids?: string[];
  questions?: TaQuestionInput[];
}): Promise<{ id: string; question_count?: number }> {
  return request<{ id: string; question_count?: number }>('/ta/assignments', { method: 'POST', body: JSON.stringify(payload) });
}

export function taUpdateAssignment(assignmentId: string, payload: {
  title?: string;
  description?: string | null;
  question_type?: string;
  options?: string[] | null;
  correct_answer?: string | null;
  total_score?: number;
  due_at?: string | null;
  late_policy?: string;
  late_penalty_ratio?: number;
  question_ids?: string[];
  questions?: TaQuestionInput[];
}): Promise<{ id: string }> {
  return request<{ id: string }>(`/ta/assignments/${encodeURIComponent(assignmentId)}`, { method: 'PUT', body: JSON.stringify(payload) });
}

export function taPublishAssignment(assignmentId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/assignments/${encodeURIComponent(assignmentId)}/publish`, { method: 'POST' });
}

export function taCloseAssignment(assignmentId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/assignments/${encodeURIComponent(assignmentId)}/close`, { method: 'POST' });
}

export function taListAssignmentSubmissions(assignmentId: string): Promise<TaSubmission[]> {
  return request<TaSubmission[]>(`/ta/assignments/${encodeURIComponent(assignmentId)}/submissions`);
}

export function taListLessonPlans(): Promise<TaLessonPlan[]> {
  return request<TaLessonPlan[]>('/ta/lesson-plans');
}

export function taUpdateLessonPlan(planId: string, payload: { title?: string; chapter?: string | null; outline?: string | null; content?: Record<string, unknown> | null }): Promise<{ id: string }> {
  return request<{ id: string }>(`/ta/lesson-plans/${encodeURIComponent(planId)}`, { method: 'PUT', body: JSON.stringify(payload) });
}

export function taPublishLessonPlan(planId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/lesson-plans/${encodeURIComponent(planId)}/publish`, { method: 'POST' });
}

export function taDeleteLessonPlan(planId: string): Promise<{ id: string; message: string }> {
  return request<{ id: string; message: string }>(`/ta/lesson-plans/${encodeURIComponent(planId)}`, { method: 'DELETE' });
}

export function taDeleteLessonPlans(planIds: string[]): Promise<{ deleted: number; skipped: string[]; message: string }> {
  return request<{ deleted: number; skipped: string[]; message: string }>('/ta/lesson-plans', { method: 'DELETE', body: JSON.stringify({ plan_ids: planIds }) });
}

export function taGenerateLessonPlan(payload: { course_id?: string | null; chapter?: string | null; title: string; requirements?: string | null }): Promise<TaLessonPlan> {
  const query = new URLSearchParams();
  query.set('title', payload.title);
  if (payload.course_id) query.set('course_id', payload.course_id);
  if (payload.chapter) query.set('chapter', payload.chapter);
  if (payload.requirements) query.set('requirements', payload.requirements);
  return request<TaLessonPlan>(`/ta/lesson-plans/generate?${query.toString()}`, { method: 'POST', timeoutMs: 120_000 });
}

export function taListGrading(params?: { status?: string; class_id?: string }): Promise<TaGradingRecord[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set('status', params.status);
  if (params?.class_id) query.set('class_id', params.class_id);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return request<TaGradingRecord[]>(`/ta/grading/list${suffix}`);
}

export function taGradingStats(): Promise<{ total: number; pending: number; graded: number; avg_score: number | null }> {
  return request<{ total: number; pending: number; graded: number; avg_score: number | null }>('/ta/grading/stats');
}

export function taGetGradingDetail(recordId: string): Promise<TaGradingRecord> {
  return request<TaGradingRecord>(`/ta/grading/${encodeURIComponent(recordId)}`);
}

export function taManualGrade(recordId: string, score: number, taComment?: string): Promise<{ message: string }> {
  const query = new URLSearchParams({ record_id: recordId, score: String(score) });
  if (taComment) query.set('ta_comment', taComment);
  return request<{ message: string }>(`/ta/grading/manual-grade?${query.toString()}`, { method: 'POST', timeoutMs: 30_000 });
}

export function taAiGrade(recordId: string): Promise<{ id: string; score: number | null; source: string }> {
  return request<{ id: string; score: number | null; source: string }>(`/ta/grading/ai-grade?record_id=${encodeURIComponent(recordId)}`, {
    method: 'POST',
    timeoutMs: 120_000,
  });
}

export function taAiGradeBatch(recordIds: string[]): Promise<{ graded: number; failed: number; results: Array<{ record_id: string; ok: boolean; score?: number | null; source?: string; message?: string }>; message: string }> {
  return request<{ graded: number; failed: number; results: Array<{ record_id: string; ok: boolean; score?: number | null; source?: string; message?: string }>; message: string }>('/ta/grading/ai-grade/batch', {
    method: 'POST',
    body: JSON.stringify({ record_ids: recordIds }),
    timeoutMs: 600_000,
  });
}

export function taExportGradingCsv(): Promise<Blob> {
  return requestBlob('/ta/grading/export.csv');
}

export function taListQuizzes(): Promise<TaQuiz[]> {
  return request<TaQuiz[]>('/ta/quizzes');
}

export function taGetQuiz(quizId: string): Promise<TaQuiz & { questions: TaQuizQuestion[] }> {
  return request<TaQuiz & { questions: TaQuizQuestion[] }>(`/ta/quizzes/${encodeURIComponent(quizId)}`);
}

export function taListQuestionBank(params?: { question_type?: string; keyword?: string }): Promise<TaQuestionBankItem[]> {
  const query = new URLSearchParams();
  if (params?.question_type) query.set('question_type', params.question_type);
  if (params?.keyword) query.set('keyword', params.keyword);
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return request<TaQuestionBankItem[]>(`/ta/question-bank${suffix}`);
}

export function taCreateQuiz(payload: { title: string; class_id: string; course_id?: string | null; description?: string | null; question_ids?: string[]; questions?: TaQuizQuestion[] }): Promise<{ id: string }> {
  return request<{ id: string }>('/ta/quizzes', { method: 'POST', body: JSON.stringify(payload) });
}

export function taUpdateQuiz(quizId: string, payload: { title?: string; description?: string | null; questions?: TaQuizQuestion[] }): Promise<{ id: string }> {
  return request<{ id: string }>(`/ta/quizzes/${encodeURIComponent(quizId)}`, { method: 'PUT', body: JSON.stringify(payload) });
}

export function taPublishQuiz(quizId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/quizzes/${encodeURIComponent(quizId)}/publish`, { method: 'POST' });
}

export function taCloseQuiz(quizId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/quizzes/${encodeURIComponent(quizId)}/close`, { method: 'POST' });
}

export function taDeleteQuiz(quizId: string): Promise<{ id: string; message: string }> {
  return request<{ id: string; message: string }>(`/ta/quizzes/${encodeURIComponent(quizId)}`, { method: 'DELETE' });
}

export function taDeleteQuizzes(quizIds: string[]): Promise<{ deleted: number; skipped: string[]; message: string }> {
  return request<{ deleted: number; skipped: string[]; message: string }>('/ta/quizzes', { method: 'DELETE', body: JSON.stringify({ quiz_ids: quizIds }) });
}

export function taQuizStats(quizId: string): Promise<{ quiz_id: string; title: string; submission_count: number; avg_score: number | null; full_score: number; questions: Array<{ question_id: string; prompt: string; correct_count: number; total_count: number; accuracy: number }> }> {
  return request<{ quiz_id: string; title: string; submission_count: number; avg_score: number | null; full_score: number; questions: Array<{ question_id: string; prompt: string; correct_count: number; total_count: number; accuracy: number }> }>(`/ta/quizzes/${encodeURIComponent(quizId)}/stats`);
}

export function taListAlerts(params?: { resolved?: boolean }): Promise<TaAlert[]> {
  const query = params?.resolved !== undefined ? `?resolved=${params.resolved}` : '';
  return request<TaAlert[]>(`/ta/alerts${query}`);
}

export function taResolveAlert(alertId: string, resolutionNote?: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/alerts/${encodeURIComponent(alertId)}/resolve`, { method: 'POST', body: JSON.stringify({ resolution_note: resolutionNote ?? null }) });
}

export function taInterveneAlert(alertId: string, payload: { action_type: string; content?: string | null; resource_ids?: string[] | null; tutoring_time?: string | null }): Promise<{ id: string; action_type: string; notification_id: string | null; message: string }> {
  return request<{ id: string; action_type: string; notification_id: string | null; message: string }>(`/ta/alerts/${encodeURIComponent(alertId)}/intervene`, { method: 'POST', body: JSON.stringify(payload) });
}

export function taListAlertActions(alertId: string): Promise<Array<{ id: string; action_type: string; content: string | null; created_at: string | null }>> {
  return request<Array<{ id: string; action_type: string; content: string | null; created_at: string | null }>>(`/ta/alerts/${encodeURIComponent(alertId)}/actions`);
}

export function taListAnnouncements(): Promise<TaAnnouncement[]> {
  return request<TaAnnouncement[]>('/ta/announcements');
}

export function taCreateAnnouncement(payload: {
  title: string;
  body: string;
  announcement_type?: string;
  class_id?: string | null;
  class_ids?: string[] | null;
}): Promise<{ ids: string[]; id: string | null; title: string; count: number; message: string }> {
  return request<{ ids: string[]; id: string | null; title: string; count: number; message: string }>('/ta/announcements', { method: 'POST', body: JSON.stringify(payload) });
}

export function taUpdateAnnouncement(announcementId: string, payload: { title?: string; body?: string; announcement_type?: string }): Promise<{ id: string }> {
  return request<{ id: string }>(`/ta/announcements/${encodeURIComponent(announcementId)}`, { method: 'PUT', body: JSON.stringify(payload) });
}

export function taDeleteAnnouncement(announcementId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/announcements/${encodeURIComponent(announcementId)}`, { method: 'DELETE' });
}

export function taPinAnnouncement(announcementId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/announcements/${encodeURIComponent(announcementId)}/pin`, { method: 'POST' });
}

export function taWithdrawAnnouncement(announcementId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/announcements/${encodeURIComponent(announcementId)}/withdraw`, { method: 'POST' });
}

export function taPendingResources(): Promise<Array<{ id: string; title: string; resource_type: string; status: string; created_at: string | null; description?: string | null }>> {
  return request<Array<{ id: string; title: string; resource_type: string; status: string; created_at: string | null; description?: string | null }>>('/ta/resources/pending');
}

export function taApproveResource(resourceId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/resources/${encodeURIComponent(resourceId)}/approve`, { method: 'POST' });
}

export function taRejectResource(resourceId: string, comment?: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/resources/${encodeURIComponent(resourceId)}/reject`, { method: 'POST', body: JSON.stringify({ comment: comment ?? null }) });
}

// ===== 学情诊断 =====

export function taDiagnosisClass(classId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/class/${encodeURIComponent(classId)}`);
}

export function taDiagnosisCompare(): Promise<Array<Record<string, unknown>>> {
  return request<Array<Record<string, unknown>>>('/ta/diagnosis/classes/compare');
}

export function taDiagnosisStudent(studentId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/student/${encodeURIComponent(studentId)}`);
}

export function taDiagnosisStudentRadar(studentId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/student/${encodeURIComponent(studentId)}/radar`);
}

export function taDiagnosisStudentTrend(studentId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/student/${encodeURIComponent(studentId)}/trend`);
}

export function taDiagnosisClassProgress(classId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/class/${encodeURIComponent(classId)}/progress`);
}

export function taDiagnosisClassActivityTrend(classId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/class/${encodeURIComponent(classId)}/activity-trend`);
}

export function taDiagnosisClassWeakPoints(classId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/class/${encodeURIComponent(classId)}/weak-points`);
}

export function taDiagnosisClassHeatmap(classId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/class/${encodeURIComponent(classId)}/heatmap`);
}

export function taDiagnosisClassAdvice(classId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/ta/diagnosis/class/${encodeURIComponent(classId)}/advice`, { method: 'POST', body: JSON.stringify({ target: 'class' }) });
}

// ===== 学生端互动接口（前缀 /ta-student） =====

export function studentListMyClasses(): Promise<StudentClass[]> {
  return request<StudentClass[]>('/ta-student/classes');
}

export function studentJoinClass(inviteCode: string): Promise<{ message: string; already_member: boolean; class: StudentClass }> {
  return request<{ message: string; already_member: boolean; class: StudentClass }>('/ta-student/classes/join', {
    method: 'POST',
    body: JSON.stringify({ invite_code: inviteCode }),
  });
}

export function studentLeaveClass(classId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta-student/classes/${encodeURIComponent(classId)}/leave`, { method: 'DELETE' });
}

export type StudentAssignment = {
  id: string;
  title: string;
  description: string | null;
  question_type: string;
  options: string[];
  total_score: number;
  question_count: number;
  due_at: string | null;
  late_policy: string;
  status: string;
  created_at: string | null;
  submitted: boolean;
  attempt_number: number;
  score: number | null;
  submitted_at: string | null;
};

export type StudentAssignmentQuestion = {
  id: string;
  prompt: string;
  question_type: string;
  options: string[] | null;
  score: number;
};

export function studentListAssignments(): Promise<StudentAssignment[]> {
  return request<StudentAssignment[]>('/ta-student/assignments');
}

export function studentGetAssignmentQuestions(assignmentId: string): Promise<{
  id: string;
  title: string;
  description: string | null;
  question_type: string;
  options: string[];
  total_score: number;
  questions: StudentAssignmentQuestion[];
}> {
  return request<{
    id: string;
    title: string;
    description: string | null;
    question_type: string;
    options: string[];
    total_score: number;
    questions: StudentAssignmentQuestion[];
  }>(`/ta-student/assignments/${encodeURIComponent(assignmentId)}/questions`);
}

export function studentSubmitAssignment(assignmentId: string, payload: { answer?: string; answers?: Record<string, string> }): Promise<{
  id: string;
  is_late: boolean;
  attempt_number: number;
  grading_record_id: string;
  score: number | null;
  total_score?: number;
  has_subjective?: boolean;
  message: string;
}> {
  return request<{
    id: string;
    is_late: boolean;
    attempt_number: number;
    grading_record_id: string;
    score: number | null;
    total_score?: number;
    has_subjective?: boolean;
    message: string;
  }>(`/ta-student/assignments/${encodeURIComponent(assignmentId)}/submit`, { method: 'POST', body: JSON.stringify(payload) });
}

export function studentListQuizzes(): Promise<Array<{ id: string; title: string; description: string | null; created_at: string | null; submitted: boolean; score: number | null }>> {
  return request<Array<{ id: string; title: string; description: string | null; created_at: string | null; submitted: boolean; score: number | null }>>('/ta-student/quizzes');
}

export function studentGetQuizQuestions(quizId: string): Promise<{ id: string; title: string; description: string | null; questions: Array<{ id: string; prompt: string; question_type: string; options: string[] | null; score: number }> }> {
  return request<{ id: string; title: string; description: string | null; questions: Array<{ id: string; prompt: string; question_type: string; options: string[] | null; score: number }> }>(`/ta-student/quizzes/${encodeURIComponent(quizId)}`);
}

export function studentSubmitQuiz(quizId: string, answers: Record<string, string>): Promise<{ attempt_id: string; score: number | null; message: string }> {
  return request<{ attempt_id: string; score: number | null; message: string }>(`/ta-student/quizzes/${encodeURIComponent(quizId)}/submit`, { method: 'POST', body: JSON.stringify({ answers }) });
}

export function studentListNotifications(unreadOnly = false): Promise<{ items: TaNotification[]; unread_count: number }> {
  return request<{ items: TaNotification[]; unread_count: number }>(`/ta-student/notifications${unreadOnly ? '?unread_only=true' : ''}`);
}

export function studentReadNotification(notificationId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta-student/notifications/${encodeURIComponent(notificationId)}/read`, { method: 'POST' });
}

// ===== 教师端 AI Agent 对话 =====

export type TaAgentDataFact = {
  label: string;
  value: string;
  detail?: string | null;
};

export type TaAgentTraceEvent = {
  step: string;
  status: string;
  detail?: string | null;
  duration_ms?: number | null;
};

export type TaAgentPendingConfirmation = {
  confirmation_id: string;
  tool: string;
  summary: string;
  args: Record<string, unknown>;
};

export type TaAgentMessageResponse = {
  conversation_id: string;
  answer: string;
  citations: Citation[];
  data_facts: TaAgentDataFact[];
  agent_trace: TaAgentTraceEvent[];
  quality?: { cite_check?: string; safety?: string; citation_coverage?: string | null } | null;
  route: string;
  refused: boolean;
  refusal_reason?: string | null;
  pending_confirmation?: TaAgentPendingConfirmation | null;
};

/** 发送教师端 Agent 对话消息；requireCitations 缺省由后端按意图决定。 */
export function taAgentMessage(payload: { message: string; course_id?: string | null; conversation_id?: string | null; require_citations?: boolean | null }): Promise<TaAgentMessageResponse> {
  return request<TaAgentMessageResponse>('/ta/agent/messages', {
    method: 'POST',
    timeoutMs: 120_000,
    body: JSON.stringify(payload),
  });
}

/** 教师确认/取消待执行的写操作（布置作业、创建测验、发布公告等）。 */
export function taAgentConfirm(payload: { confirmation_id: string; action: 'confirm' | 'cancel' }): Promise<{ action: string; executed: boolean; summary?: string | null }> {
  return request<{ action: string; executed: boolean; summary?: string | null }>('/ta/agent/confirm', {
    method: 'POST',
    timeoutMs: 60_000,
    body: JSON.stringify(payload),
  });
}