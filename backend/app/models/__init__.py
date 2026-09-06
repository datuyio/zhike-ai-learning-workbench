from app.models.base import Base
from app.models.user import CourseMembership, Role, Session, User, UserCurrentCourse, UserSetting
from app.models.course import ConceptPrerequisite, Course, CourseConcept, CourseContextSnapshot, CourseSection
from app.models.knowledge import (
    ChunkDuplicateCandidate,
    ChunkQualityFeedback,
    ChunkRegion,
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentParseTask,
    KnowledgePublishGeneration,
    RetrievalVerificationQuestion,
    RetrievalVerificationRun,
    TaskEvent,
    VectorIndex,
    VectorizationTask,
)
from app.models.learning import ConceptMastery, CourseProfile, LearningEvent, LearningPath, LearningScheduleItem, PathNode, ProfileDimension, ProfileEvidence, UserProfile
from app.models.resource import CommunityResource, Resource, ResourceAsset, ResourceGenerationTask, ResourceVersion
from app.models.assessment import Assessment, AssessmentItem, WrongAnswerAnalysis
from app.models.model_gateway import ModelCallLog, ModelProvider, ModelProviderHealth, UserModelOverride
from app.models.conversation import AgentTraceEvent, Conversation, Message, MessageCitation
from app.models.ops import AdminAuditLog, ContentReviewLog, CourseMetricsDaily, RagQueryLog, SafetyEvent, UsageMetricsDaily
from app.models.rag_integration import RagIntegrationConfig
from app.models.chatdoc_vendor_quota import ChatdocVendorQuota
from app.models.chatdoc_extracted_qa import ChatdocExtractedQa
from app.models.chatdoc_native_chunk_revision import ChatdocNativeChunkRevision
from app.models.announcement import Announcement, AnnouncementDismissal, AnnouncementRead
from app.models.site_setting import SiteSetting

__all__ = [
    "Base",
    "Role",
    "User",
    "UserSetting",
    "Session",
    "CourseMembership",
    "UserCurrentCourse",
    "Course",
    "CourseSection",
    "CourseConcept",
    "ConceptPrerequisite",
    "CourseContextSnapshot",
    "Document",
    "DocumentPage",
    "DocumentChunk",
    "ChunkRegion",
    "ChunkDuplicateCandidate",
    "ChunkQualityFeedback",
    "DocumentParseTask",
    "TaskEvent",
    "RetrievalVerificationQuestion",
    "RetrievalVerificationRun",
    "KnowledgePublishGeneration",
    "VectorIndex",
    "VectorizationTask",
    "UserProfile",
    "CourseProfile",
    "ProfileDimension",
    "ProfileEvidence",
    "LearningPath",
    "LearningEvent",
    "LearningScheduleItem",
    "PathNode",
    "ConceptMastery",
    "Resource",
    "ResourceAsset",
    "ResourceVersion",
    "ResourceGenerationTask",
    "CommunityResource",
    "Assessment",
    "AssessmentItem",
    "WrongAnswerAnalysis",
    "ModelProvider",
    "ModelProviderHealth",
    "ModelCallLog",
    "UserModelOverride",
    "Conversation",
    "Message",
    "MessageCitation",
    "AgentTraceEvent",
    "SafetyEvent",
    "ContentReviewLog",
    "AdminAuditLog",
    "UsageMetricsDaily",
    "CourseMetricsDaily",
    "RagQueryLog",
    "RagIntegrationConfig",
    "ChatdocVendorQuota",
    "ChatdocExtractedQa",
    "ChatdocNativeChunkRevision",
    "Announcement",
    "AnnouncementRead",
    "AnnouncementDismissal",
    "SiteSetting",
]

# === TA Portal Models ===
from .ta_class import TaClass
from .ta_class_student import TaClassStudent
from .ta_lesson_plan import TaLessonPlan
from .ta_grading_record import TaGradingRecord
from .student_learning_event import StudentLearningEvent
from .ta_alert_record import TaAlertRecord
from .ta_announcement import TaAnnouncement
from .ta_assignment import TaAssignment, TaAssignmentQuestion, TaSubmission
from .ta_alert_action import TaAlertAction
from .ta_notification import TaNotification
from .ta_quiz import TaQuiz, TaQuizQuestion, TaQuizAttempt
from .ta_question_bank import TaQuestionBank
from .ta_agent_confirmation import TaAgentConfirmation
