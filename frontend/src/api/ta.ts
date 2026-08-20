import { request, requestBlob } from './client';

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
  total_score: number;
  due_at: string | null;
  late_policy: string;
  late_penalty_ratio: number;
  status: 'draft' | 'published' | 'closed';
  created_at: string | null;
};

export type TaSubmission = {
  id: string;
  student_id: string;
  student_name: string;
  answer: string;
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

export function taCreateAssignment(payload: {
  title: string;
  description?: string | null;
  class_id: string;
  course_id?: string | null;
  concept_id?: string | null;
  total_score?: number;
  due_at?: string | null;
  late_policy?: string;
  late_penalty_ratio?: number;
}): Promise<{ id: string }> {
  return request<{ id: string }>('/ta/assignments', { method: 'POST', body: JSON.stringify(payload) });
}

export function taUpdateAssignment(assignmentId: string, payload: {
  title?: string;
  description?: string | null;
  total_score?: number;
  due_at?: string | null;
  late_policy?: string;
  late_penalty_ratio?: number;
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

export function taUpdateLessonPlan(planId: string, payload: { title?: string; chapter?: string | null; outline?: string | null }): Promise<{ id: string }> {
  return request<{ id: string }>(`/ta/lesson-plans/${encodeURIComponent(planId)}`, { method: 'PUT', body: JSON.stringify(payload) });
}

export function taPublishLessonPlan(planId: string): Promise<{ message: string }> {
  return request<{ message: string }>(`/ta/lesson-plans/${encodeURIComponent(planId)}/publish`, { method: 'POST' });
}

export function taGenerateLessonPlan(payload: { course_id: string; chapter: string; title?: string }): Promise<TaLessonPlan> {
  return request<TaLessonPlan>('/ta/lesson-plans/generate', { method: 'POST', body: JSON.stringify(payload), timeoutMs: 120_000 });
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

export function taManualGrade(recordId: string, score: number, taComment?: string): Promise<{ message: string }> {
  const query = new URLSearchParams({ record_id: recordId, score: String(score) });
  if (taComment) query.set('ta_comment', taComment);
  return request<{ message: string }>(`/ta/grading/manual-grade?${query.toString()}`, { method: 'POST', timeoutMs: 30_000 });
}

export function taAiGrade(recordId: string): Promise<{ id: string; score: number | null; source: string }> {
  return request<{ id: string; score: number | null; source: string }>('/ta/grading/ai-grade', {
    method: 'POST',
    body: JSON.stringify({ record_id: recordId }),
    timeoutMs: 120_000,
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

export function taCreateQuiz(payload: { title: string; class_id: string; course_id?: string | null; description?: string | null; questions: TaQuizQuestion[] }): Promise<{ id: string }> {
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

export function taCreateAnnouncement(payload: { title: string; body: string; announcement_type?: string; class_id?: string | null }): Promise<TaAnnouncement> {
  return request<TaAnnouncement>('/ta/announcements', { method: 'POST', body: JSON.stringify(payload) });
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

export function studentListAssignments(): Promise<Array<{ id: string; title: string; description: string | null; total_score: number; due_at: string | null; late_policy: string; status: string; created_at: string | null; submitted: boolean; attempt_number: number; submitted_at: string | null }>> {
  return request<Array<{ id: string; title: string; description: string | null; total_score: number; due_at: string | null; late_policy: string; status: string; created_at: string | null; submitted: boolean; attempt_number: number; submitted_at: string | null }>>('/ta-student/assignments');
}

export function studentSubmitAssignment(assignmentId: string, answer: string): Promise<{ id: string; is_late: boolean; attempt_number: number; grading_record_id: string; message: string }> {
  return request<{ id: string; is_late: boolean; attempt_number: number; grading_record_id: string; message: string }>(`/ta-student/assignments/${encodeURIComponent(assignmentId)}/submit`, { method: 'POST', body: JSON.stringify({ answer }) });
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
