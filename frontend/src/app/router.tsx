import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { AuthGate } from "./AuthGate";
import { AdminGate } from "./AdminGate";
import { TAGate } from "./TAGate";
import { WorkspaceLayout } from "./WorkspaceLayout";
import { TaLayout } from "./TaLayout";

const AuthPage = lazy(() => import("../pages/auth/AuthPage").then((module) => ({ default: module.AuthPage })));
const DashboardPage = lazy(() => import("../pages/dashboard/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const AiStudyRoomPage = lazy(() => import("../pages/ai-room/AiStudyRoomPage").then((module) => ({ default: module.AiStudyRoomPage })));
const LearningPathPage = lazy(() => import("../pages/learning-path/LearningPathPage").then((module) => ({ default: module.LearningPathPage })));
const LearningCalendarPage = lazy(() => import("../pages/calendar/LearningCalendarPage").then((module) => ({ default: module.LearningCalendarPage })));
const CurriculumPage = lazy(() => import("../pages/curriculum/CurriculumPage").then((module) => ({ default: module.CurriculumPage })));
const ResourceWorkshopPage = lazy(() => import("../pages/resource-workshop/ResourceWorkshopPage").then((module) => ({ default: module.ResourceWorkshopPage })));
const LearningBehaviorPage = lazy(() => import("../pages/learning-behavior/LearningBehaviorPage").then((m) => ({ default: m.LearningBehaviorPage })));
const AssessmentPage = lazy(() => import("../pages/assessment/AssessmentPage").then((module) => ({ default: module.AssessmentPage })));
const AssessmentReportPage = lazy(() => import("../pages/learning-assessment/AssessmentReportPage").then((module) => ({ default: module.AssessmentReportPage })));
const LearningAssessmentReportPage = lazy(() => import("../pages/learning-assessment/LearningAssessmentReportPage").then((module) => ({ default: module.LearningAssessmentReportPage })));
const ResourceHallPage = lazy(() => import("../pages/resource-hall/ResourceHallPage").then((module) => ({ default: module.ResourceHallPage })));
const LearningProfilePage = lazy(() => import("../pages/learning-profile/LearningProfilePage").then((module) => ({ default: module.LearningProfilePage })));
const AnnouncementsPage = lazy(() => import("../pages/announcements/AnnouncementsPage").then((module) => ({ default: module.AnnouncementsPage })));
const PersonalSettingsPage = lazy(() => import("../pages/personal-settings/PersonalSettingsPage").then((module) => ({ default: module.PersonalSettingsPage })));
const StudentAssignmentsPage = lazy(() => import("../pages/ta-student/StudentAssignmentsPage").then((m) => ({ default: m.StudentAssignmentsPage })));
const StudentQuizzesPage = lazy(() => import("../pages/ta-student/StudentQuizzesPage").then((m) => ({ default: m.StudentQuizzesPage })));
const StudentNotificationsPage = lazy(() => import("../pages/ta-student/StudentNotificationsPage").then((m) => ({ default: m.StudentNotificationsPage })));
const StudentClassesPage = lazy(() => import("../pages/ta-student/StudentClassesPage").then((m) => ({ default: m.StudentClassesPage })));

const CodeSandboxDemoPage = lazy(() => import("../pages/dev/CodeSandboxDemoPage").then((module) => ({ default: module.default })));
const SandboxPage = lazy(() => import("../pages/sandbox/SandboxPage").then((module) => ({ default: module.default })));

const CourseBuilderPage = lazy(() => import("../pages/admin/CourseBuilderPage").then((module) => ({ default: module.CourseBuilderPage })));
const ChatDocConfigPage = lazy(() => import("../pages/admin/ChatDocConfigPage").then((module) => ({ default: module.ChatDocConfigPage })));
const KnowledgeBasePage = lazy(() => import("../pages/admin/KnowledgeBasePage").then((module) => ({ default: module.KnowledgeBasePage })));
const ModelGatewayPage = lazy(() => import("../pages/admin/ModelGatewayPage").then((module) => ({ default: module.ModelGatewayPage })));
const ResourceReviewPage = lazy(() => import("../pages/admin/ResourceReviewPage").then((module) => ({ default: module.ResourceReviewPage })));
const OperationsMonitoringPage = lazy(() => import("../pages/admin/OperationsMonitoringPage").then((module) => ({ default: module.OperationsMonitoringPage })));
const AdminAnnouncementsPage = lazy(() => import("../pages/admin/AdminAnnouncementsPage").then((module) => ({ default: module.AdminAnnouncementsPage })));
const InterfaceSettingsPage = lazy(() => import("../pages/admin/InterfaceSettingsPage").then((module) => ({ default: module.InterfaceSettingsPage })));

// TA 端页面懒加载
const TaDashboardPage = lazy(() => import("../pages/ta/TaDashboardPage").then((m) => ({ default: m.TaDashboardPage })));
const TaLessonPrepPage = lazy(() => import("../pages/ta/TaLessonPrepPage").then((m) => ({ default: m.TaLessonPrepPage })));
const TaGradingPage = lazy(() => import("../pages/ta/TaGradingPage").then((m) => ({ default: m.TaGradingPage })));
const TaDiagnosisPage = lazy(() => import("../pages/ta/TaDiagnosisPage").then((m) => ({ default: m.TaDiagnosisPage })));
const TaClassManagementPage = lazy(() => import("../pages/ta/TaClassManagementPage").then((m) => ({ default: m.TaClassManagementPage })));
const TaResourceReviewPage = lazy(() => import("../pages/ta/TaResourceReviewPage").then((m) => ({ default: m.TaResourceReviewPage })));
const TaAnnouncementsPage = lazy(() => import("../pages/ta/TaAnnouncementsPage").then((m) => ({ default: m.TaAnnouncementsPage })));
const TaAiAssistantPage = lazy(() => import("../pages/ta/TaAiAssistantPage").then((m) => ({ default: m.TaAiAssistantPage })));

function RouteFallback(): JSX.Element {
  return (
    <main className="grid min-h-dvh place-items-center bg-slate-50 px-6 text-sm font-semibold text-slate-600">
      正在加载工作台...
    </main>
  );
}

function withSuspense(node: ReactNode): JSX.Element {
  return <Suspense fallback={<RouteFallback />}>{node}</Suspense>;
}

// 子路径 basename：与 Vite base（import.meta.env.BASE_URL）保持一致，部署在 /zhike/ 时自动带上前缀
const routerBaseName = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

export const router = createBrowserRouter([
  { path: "/login", element: withSuspense(<AuthPage mode="login" />) },
  { path: "/register", element: withSuspense(<AuthPage mode="register" />) },
  {
    path: "/",
    element: <AuthGate />,
    children: [
      // 学生端路由
      {
        element: <WorkspaceLayout />,
        children: [
          { index: true, element: <Navigate to="/dashboard" replace /> },
          { path: "dashboard", element: withSuspense(<DashboardPage />) },
          { path: "ai-room", element: withSuspense(<AiStudyRoomPage />) },
          { path: "learning-path", element: withSuspense(<LearningPathPage />) },
          { path: "calendar", element: withSuspense(<LearningCalendarPage />) },
          { path: "curriculum", element: withSuspense(<CurriculumPage />) },
          { path: "resource-workshop", element: withSuspense(<ResourceWorkshopPage />) },
          { path: "sandbox", element: withSuspense(<SandboxPage />) },
          { path: 'learning-assessment/report', element: withSuspense(<LearningAssessmentReportPage />) },
          { path: "assessment", element: withSuspense(<AssessmentPage />) },
          { path: "assessment/report", element: withSuspense(<AssessmentReportPage />) },
          { path: "resource-hall", element: withSuspense(<ResourceHallPage />) },
          { path: "learning-behavior", element: withSuspense(<LearningBehaviorPage />) },
          { path: "learning-profile", element: withSuspense(<LearningProfilePage />) },
          { path: "announcements", element: withSuspense(<AnnouncementsPage />) },
          { path: "classes", element: withSuspense(<StudentClassesPage />) },
          { path: "assignments", element: withSuspense(<StudentAssignmentsPage />) },
          { path: "quizzes", element: withSuspense(<StudentQuizzesPage />) },
          { path: "notifications", element: withSuspense(<StudentNotificationsPage />) },
          { path: "personal-settings", element: withSuspense(<PersonalSettingsPage />) },
          { path: "dev/code-sandbox", element: withSuspense(<CodeSandboxDemoPage />) },
          // 管理端路由（仅 admin）
          {
            element: <AdminGate />,
            children: [
              { path: "admin/course-builder", element: withSuspense(<CourseBuilderPage />) },
              { path: "admin/knowledge-base", element: withSuspense(<KnowledgeBasePage />) },
              { path: "admin/chatdoc-config", element: withSuspense(<ChatDocConfigPage />) },
              { path: "admin/model-gateway", element: withSuspense(<ModelGatewayPage />) },
              { path: "admin/resource-review", element: withSuspense(<ResourceReviewPage />) },
              { path: "admin/operations-monitoring", element: withSuspense(<OperationsMonitoringPage />) },
              { path: "admin/announcements", element: withSuspense(<AdminAnnouncementsPage />) },
              { path: "admin/interface-settings", element: withSuspense(<InterfaceSettingsPage />) },
            ],
          },
        ],
      },
      // 助教端路由（仅 ta 和 admin）
      {
        path: "ta",
        element: <TAGate />,
        children: [
          {
            element: <TaLayout />,
            children: [
              { index: true, element: <Navigate to="/ta/dashboard" replace /> },
              { path: "dashboard", element: withSuspense(<TaDashboardPage />) },
              { path: "ai-assistant", element: withSuspense(<TaAiAssistantPage />) },
              { path: "lesson-prep", element: withSuspense(<TaLessonPrepPage />) },
              { path: "grading", element: withSuspense(<TaGradingPage />) },
              { path: "diagnosis", element: withSuspense(<TaDiagnosisPage />) },
              { path: "class-management", element: withSuspense(<TaClassManagementPage />) },
              { path: "resource-review", element: withSuspense(<TaResourceReviewPage />) },
              { path: "announcements", element: withSuspense(<TaAnnouncementsPage />) },
            ],
          },
        ],
      },
    ],
  },
], { basename: routerBaseName });
