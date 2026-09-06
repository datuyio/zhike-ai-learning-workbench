"""写入深度学习演示课程与默认画像数据

Revision ID: 0002_seed_deep_learning
Revises: 0001_initial_schema
Create Date: 2026-05-25 17:05:00
"""
from __future__ import annotations

import json
from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "0002_seed_deep_learning"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

IDS = {
    "role_student": "d34196d1-a71a-5f76-9a1b-5700be5f6725",
    "role_admin": "f0e1aba6-dbeb-522e-a6ef-a0c5ae2a217c",
    "user_zhang": "c030ebbb-d09d-5b5f-b720-7a60950abd8e",
    "user_admin": "4221d673-7425-5a1a-ac26-1feaa3689d54",
    "course_dl": "77a4dad0-af04-5fe2-813d-724a4ffb56ea",
    "course_ml": "ea60a8e3-5506-5f50-89a0-1d7815d288da",
    "section_dl_1": "7443155d-0279-5c83-bc8b-a76f24336d80",
    "section_dl_2": "627daa1c-5640-558a-adfd-f4dbbc70158c",
    "section_dl_3": "dab8744f-7481-5876-9516-0dfa7a26c754",
    "section_dl_4": "497e5428-3fc3-5dff-aff7-2a5362ef5b16",
    "section_dl_5": "fc6d9115-3ee3-50e0-860e-08d788e2fbd9",
    "section_dl_6": "920ba059-7e98-58e6-981b-2a43dd5f9bfc",
    "section_dl_7": "bff325ef-736f-539a-a49e-3aac12f40d23",
    "section_dl_8": "b5580cd8-dfbb-5970-a854-f81126128059",
    "concept_nn": "55cdf13a-0a58-50d0-bee0-3e2286bb2549",
    "concept_bp": "07725b03-d76b-5dfd-8dd1-1cc20c6dc9c2",
    "concept_reg": "92ecc8d4-3b39-516d-b765-0039764d991b",
    "concept_cnn": "9bd625d6-9fbb-5c51-a836-6df10806b34c",
    "concept_rnn": "e3ce6cfc-0770-5c92-8100-ddc861c7a1b7",
    "concept_attention": "9b885add-e75d-5811-921f-9dd9fb2b4cdc",
    "concept_autoencoder": "03756fe2-f055-51b3-8b15-0567d0b9d720",
    "concept_project": "3da78808-2868-5ab9-b6f4-d4ad6222e252",
    "path_dl_user_zhang": "43598f87-6a41-5131-8ecd-0c8a89b7a59f",
    "node_001": "e7a023bb-0c38-5d6d-ac6a-94484993179e",
    "node_002": "c8a69d56-a2cd-5dee-9aa5-f1748c638a7e",
    "node_002_r": "a038beb1-e781-5341-a6b8-490875cbcf61",
    "node_003": "f799af4e-4c65-590d-ab3b-f1103002833f",
    "node_004": "d143bac7-4f0f-5436-bacc-6e9e0c135c5a",
    "node_005": "1af770e6-2191-596f-844c-97a29a6d1ad5",
    "node_006": "6aad4fbf-0448-5a66-8dd7-f2aba45c014c",
    "node_007": "d95d964a-5dca-5da4-8306-029efc90f446",
    "node_008": "cc23cf92-7a03-54a2-9f23-8b6230926df4",
    "doc_ch8": "14e743c6-f7f9-5411-96f7-5ce6c3e14044",
    "chunk_cnn": "244d0c4b-fa99-56be-b8d4-3ee764860b53",
    "chunk_bp": "f5ea05e4-0754-50d5-9843-98a9f31d309c",
    "chunk_reg": "c12f45c2-2022-5317-962e-785537096f78",
    "res_bp_video": "f8037e5d-8093-5c89-8c99-44df6cf595e3",
    "res_cnn_lab": "400b9b8f-85bd-5dd0-beec-a61be0a696ad",
    "res_bn_video": "9baf4c03-d502-5a1d-a0ad-8038206e2787",
    "res_reg_quiz": "a4a1c651-aaf0-5c64-b0f7-e6b0c5a93451",
    "profile_dl": "dfca1063-7eca-584c-8220-35124733ec78",
    "provider_spark": "a91279f1-2a77-526d-957c-1112e4d7f6ca",
    "provider_deepseek": "686bae5d-104e-57cc-a35e-511d59e24483",
    "provider_zhipu": "0903938d-4586-59c1-8467-b2c1dd6696b1",
    "provider_kimi": "02aebe9b-ddb4-539e-8c2a-f1a3bda51b87",
    "provider_ollama": "cb573998-3599-57af-ab0e-b2c8ce1028a1",
    "metrics_today": "fea5dd0f-413f-5ed9-a0c5-75c0fbd14282",
}


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def execute(sql: str, **params: object) -> None:
    op.get_bind().execute(sa.text(sql), params)


def upgrade() -> None:
    # 角色和用户
    for role_id, code, name in [
        (IDS["role_student"], "student", "用户"),
        (IDS["role_admin"], "admin", "管理员"),
    ]:
        execute(
            """
            INSERT INTO roles (id, code, name, description)
            VALUES (:id, :code, :name, :description)
            ON CONFLICT (id) DO NOTHING
            """,
            id=role_id,
            code=code,
            name=name,
            description=f"系统内置{ name }角色",
        )

    for user_id, external_id, name, email, role in [
        (IDS["user_zhang"], "user_zhang", "张同学", "zhang@example.edu.cn", "student"),
        (IDS["user_admin"], "admin_default", "管理员", "admin@example.edu.cn", "admin"),
    ]:
        execute(
            """
            INSERT INTO users (id, external_id, display_name, email, role_code, status)
            VALUES (:id, :external_id, :display_name, :email, :role_code, 'active')
            ON CONFLICT (id) DO NOTHING
            """,
            id=user_id,
            external_id=external_id,
            display_name=name,
            email=email,
            role_code=role,
        )

    # 课程
    courses = [
        (
            IDS["course_dl"],
            "deep_learning_001",
            "深度学习",
            "以神经网络、CNN、RNN、Transformer 和实践项目为核心的课程。",
            "计算机 / 人工智能",
            True,
            {"color": "blue", "icon": "brain", "default_view": "dashboard"},
        ),
        (
            IDS["course_ml"],
            "machine_learning_001",
            "机器学习",
            "监督学习、无监督学习、模型评估与工程实践。",
            "计算机 / 数据科学",
            False,
            {"color": "emerald", "icon": "network", "default_view": "dashboard"},
        ),
    ]
    for course in courses:
        execute(
            """
            INSERT INTO courses (id, slug, title, description, applicable_major, status, is_default, display_config)
            VALUES (:id, :slug, :title, :description, :major, 'published', :is_default, CAST(:display_config AS JSONB))
            ON CONFLICT (id) DO NOTHING
            """,
            id=course[0],
            slug=course[1],
            title=course[2],
            description=course[3],
            major=course[4],
            is_default=course[5],
            display_config=dumps(course[6]),
        )

    # 用户与课程绑定关系
    execute(
        """
        INSERT INTO course_memberships (id, course_id, user_id, role, status)
        VALUES (gen_random_uuid(), :course_id, :user_id, 'student', 'active')
        ON CONFLICT (course_id, user_id) DO NOTHING
        """,
        course_id=IDS["course_dl"],
        user_id=IDS["user_zhang"],
    )
    execute(
        """
        INSERT INTO user_current_courses (id, user_id, course_id)
        VALUES (gen_random_uuid(), :user_id, :course_id)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id=IDS["user_zhang"],
        course_id=IDS["course_dl"],
    )
    execute(
        """
        INSERT INTO user_settings (id, user_id, default_course_id, learning_goals, learning_cadence, resource_preferences, personal_model_enabled, privacy_policy)
        VALUES (gen_random_uuid(), :user_id, :course_id, CAST(:goals AS JSONB), '每周 5 天', CAST(:prefs AS JSONB), true, CAST(:privacy AS JSONB))
        ON CONFLICT (id) DO NOTHING
        """,
        user_id=IDS["user_zhang"],
        course_id=IDS["course_dl"],
        goals=dumps(["考试", "项目实践"]),
        prefs=dumps(["图解讲义", "代码实验", "自测题"]),
        privacy=dumps({"learning_behavior_retention_days": 180, "personal_document_cleanup_days": 30}),
    )

    # 深度学习章节和知识点
    sections = [
        (IDS["section_dl_1"], "dl_ch_01", "第 1 章 神经网络基础", 1),
        (IDS["section_dl_2"], "dl_ch_02", "第 2 章 反向传播与优化", 2),
        (IDS["section_dl_3"], "dl_ch_03", "第 3 章 正则化与泛化", 3),
        (IDS["section_dl_4"], "dl_ch_04", "第 4 章 卷积神经网络", 4),
        (IDS["section_dl_5"], "dl_ch_05", "第 5 章 循环神经网络与序列建模", 5),
        (IDS["section_dl_6"], "dl_ch_06", "第 6 章 注意力机制与 Transformer", 6),
        (IDS["section_dl_7"], "dl_ch_07", "第 7 章 自编码器与生成模型", 7),
        (IDS["section_dl_8"], "dl_ch_08", "第 8 章 深度学习实验与项目实践", 8),
    ]
    for section_id, code, title, order_index in sections:
        execute(
            """
            INSERT INTO course_sections (id, course_id, code, title, description, order_index)
            VALUES (:id, :course_id, :code, :title, :description, :order_index)
            ON CONFLICT (id) DO NOTHING
            """,
            id=section_id,
            course_id=IDS["course_dl"],
            code=code,
            title=title,
            description="深度学习 MVP 示例课程章节",
            order_index=order_index,
        )

    concepts = [
        (IDS["concept_nn"], IDS["section_dl_1"], "nn_basic", "神经网络基础", "掌握感知机、多层感知机、激活函数与前向传播。", "basic", 1, []),
        (IDS["concept_bp"], IDS["section_dl_2"], "backpropagation", "反向传播与优化", "反向传播通过链式法则高效计算损失函数对网络参数的梯度，是训练神经网络的核心方法。", "medium", 2, ["nn_basic"]),
        (IDS["concept_reg"], IDS["section_dl_3"], "regularization", "正则化与泛化", "理解 L1/L2、Dropout、数据增强和泛化误差。", "medium", 3, ["backpropagation"]),
        (IDS["concept_cnn"], IDS["section_dl_4"], "cnn_convolution", "卷积神经网络", "理解卷积层、池化层、局部感受野、权重共享和经典 CNN 架构。", "medium", 4, ["regularization"]),
        (IDS["concept_rnn"], IDS["section_dl_5"], "rnn_transformer", "循环神经网络与序列建模", "理解 RNN、LSTM、GRU 和序列建模基本思想。", "advanced", 5, ["cnn_convolution"]),
        (IDS["concept_attention"], IDS["section_dl_6"], "transformer_attention", "注意力机制与 Transformer", "理解自注意力、位置编码、多头注意力和 Transformer 编码器结构。", "advanced", 6, ["rnn_transformer"]),
        (IDS["concept_autoencoder"], IDS["section_dl_7"], "autoencoder_generative", "自编码器与生成模型", "理解自编码器、VAE、GAN 和生成模型基本思想。", "advanced", 7, ["transformer_attention"]),
        (IDS["concept_project"], IDS["section_dl_8"], "deep_learning_project", "深度学习实验与项目实践", "围绕 PyTorch 实验、项目复现、调试和结果分析建立实践能力。", "advanced", 8, ["cnn_convolution", "transformer_attention"]),
    ]
    for concept in concepts:
        execute(
            """
            INSERT INTO course_concepts (id, course_id, section_id, code, title, definition, difficulty, recommended_order, prerequisites_json, status)
            VALUES (:id, :course_id, :section_id, :code, :title, :definition, :difficulty, :recommended_order, CAST(:prerequisites AS JSONB), 'published')
            ON CONFLICT (id) DO NOTHING
            """,
            id=concept[0],
            course_id=IDS["course_dl"],
            section_id=concept[1],
            code=concept[2],
            title=concept[3],
            definition=concept[4],
            difficulty=concept[5],
            recommended_order=concept[6],
            prerequisites=dumps(concept[7]),
        )

    # 学习画像和路径
    execute(
        """
        INSERT INTO course_profiles (id, course_id, user_id, summary, confidence)
        VALUES (:id, :course_id, :user_id, :summary, 0.78)
        ON CONFLICT (id) DO NOTHING
        """,
        id=IDS["profile_dl"],
        course_id=IDS["course_dl"],
        user_id=IDS["user_zhang"],
        summary="基础水平中等偏上，偏好图解和代码实验，目标为课程项目与考试。当前风险点集中在反向传播链式法则、池化层差异和 BatchNorm 推理阶段。",
    )
    dimensions = [
        ("knowledge_base", "知识基础", 72, "中等偏上", 0.82, [{"source": "自测", "note": "高于班级 68%"}]),
        ("cognitive_style", "认知风格", 80, "图解型", 0.74, [{"source": "资源反馈", "note": "偏好可视化与结构化表达"}]),
        ("learning_goal", "学习目标", 85, "课程项目 + 考试", 0.9, [{"source": "个人设置", "note": "明确选择考试与项目实践"}]),
        ("hands_on", "动手偏好", 78, "高", 0.76, [{"source": "代码实验", "note": "多次完成 PyTorch 实验"}]),
        ("autonomy", "自主性", 62, "中", 0.68, [{"source": "任务完成", "note": "需要阶段性目标牵引"}]),
        ("risk", "风险预警", 42, "反向传播概念混淆", 0.72, [{"source": "AI 学习室追问", "note": "链式法则表达不稳定"}]),
    ]
    for key, name, score, label, confidence, evidence in dimensions:
        execute(
            """
            INSERT INTO profile_dimensions (id, profile_id, dimension_key, dimension_name, score, label, confidence, evidence_json)
            VALUES (gen_random_uuid(), :profile_id, :dimension_key, :dimension_name, :score, :label, :confidence, CAST(:evidence AS JSONB))
            ON CONFLICT (profile_id, dimension_key) DO NOTHING
            """,
            profile_id=IDS["profile_dl"],
            dimension_key=key,
            dimension_name=name,
            score=score,
            label=label,
            confidence=confidence,
            evidence=dumps(evidence),
        )

    execute(
        """
        INSERT INTO learning_paths (id, course_id, user_id, title, version, status, source, meta_json)
        VALUES (:id, :course_id, :user_id, '深度学习个性化路径', 1, 'active', 'seed', CAST(:meta AS JSONB))
        ON CONFLICT (id) DO NOTHING
        """,
        id=IDS["path_dl_user_zhang"],
        course_id=IDS["course_dl"],
        user_id=IDS["user_zhang"],
        meta=dumps({"overall_mastery": 64, "generated_by": "PathPlanningAgent"}),
    )
    nodes = [
        (IDS["node_001"], "node_001", "神经网络基础", IDS["concept_nn"], "mastered", 92, False, 1, []),
        (IDS["node_002"], "node_002", "反向传播与优化", IDS["concept_bp"], "learning", 68, False, 2, ["node_001"]),
        (IDS["node_002_r"], "node_002_r", "链式求导与梯度理解", IDS["concept_bp"], "needs_remedial", 35, True, 3, ["node_001"]),
        (IDS["node_003"], "node_003", "正则化与泛化", IDS["concept_reg"], "review", 75, False, 4, ["node_002"]),
        (IDS["node_004"], "node_004", "卷积神经网络", IDS["concept_cnn"], "mastered", 88, False, 5, ["node_003"]),
        (IDS["node_005"], "node_005", "循环神经网络与序列建模", IDS["concept_rnn"], "not_started", 0, False, 6, ["node_004"]),
        (IDS["node_006"], "node_006", "注意力机制与 Transformer", IDS["concept_attention"], "not_started", 0, False, 7, ["node_005"]),
        (IDS["node_007"], "node_007", "自编码器与生成模型", IDS["concept_autoencoder"], "not_started", 0, False, 8, ["node_006"]),
        (IDS["node_008"], "node_008", "深度学习实验与项目实践", IDS["concept_project"], "not_started", 0, False, 9, ["node_004"]),
    ]
    for node in nodes:
        execute(
            """
            INSERT INTO path_nodes (id, learning_path_id, course_id, concept_id, code, title, status, mastery, is_remedial, order_index, prerequisites_json, recommendation_json)
            VALUES (:id, :path_id, :course_id, :concept_id, :code, :title, :status, :mastery, :is_remedial, :order_index, CAST(:prerequisites AS JSONB), CAST(:recommendation AS JSONB))
            ON CONFLICT (id) DO NOTHING
            """,
            id=node[0],
            path_id=IDS["path_dl_user_zhang"],
            course_id=IDS["course_dl"],
            concept_id=node[3],
            code=node[1],
            title=node[2],
            status=node[4],
            mastery=node[5],
            is_remedial=node[6],
            order_index=node[7],
            prerequisites=dumps(node[8]),
            recommendation=dumps({"next_action": "去学习" if node[4] in ["learning", "needs_remedial"] else "查看详情"}),
        )
        execute(
            """
            INSERT INTO concept_mastery (id, course_id, user_id, concept_id, mastery, status, evidence_json)
            VALUES (gen_random_uuid(), :course_id, :user_id, :concept_id, :mastery, :status, CAST(:evidence AS JSONB))
            ON CONFLICT (course_id, user_id, concept_id) DO NOTHING
            """,
            course_id=IDS["course_dl"],
            user_id=IDS["user_zhang"],
            concept_id=node[3],
            mastery=node[5],
            status=node[4],
            evidence=dumps([{"source": "seed_path", "node": node[1]}]),
        )

    # RAG 引用卡片使用的文档和切片
    execute(
        """
        INSERT INTO documents (id, course_id, uploaded_by_user_id, title, filename, mime_type, source_type, parse_status, vector_status, text_vector_status, visual_vector_status, review_status, publish_readiness, chapter_code, file_uri, content_hash, ingestion_version, meta_json)
        VALUES (:id, :course_id, :user_id, '深度学习讲义第 8 章.pdf', '深度学习讲义第8章.pdf', 'application/pdf', 'course_material', 'completed', 'indexed', 'pending_review', 'pending_review', 'pending', 'blocked', 'dl_ch_04', 'storage/course/deep_learning/ch8.pdf', 'seed-doc-ch8', 1, CAST(:meta AS JSONB))
        ON CONFLICT (id) DO NOTHING
        """,
        id=IDS["doc_ch8"],
        course_id=IDS["course_dl"],
        user_id=IDS["user_admin"],
        meta=dumps({"pages": 146, "quality": 0.92}),
    )
    chunks = [
        (IDS["chunk_cnn"], IDS["concept_cnn"], 3, 118, "第 8 章 / 卷积神经网络", "卷积神经网络（CNN）通过局部感受野、权重共享和池化操作，有效提取输入数据的层次化特征。其中，卷积层负责特征提取，池化层在降低维度的同时增强模型的平移不变性。", 0.82),
        (IDS["chunk_bp"], IDS["concept_bp"], 4, 86, "第 5 章 / 反向传播", "反向传播算法将复合函数的梯度计算拆解为局部梯度的乘积，利用链式法则从输出层向输入层逐层传播误差信号。", 0.79),
        (IDS["chunk_reg"], IDS["concept_reg"], 5, 92, "第 6 章 / 正则化", "正则化通过约束模型复杂度、随机失活或数据增强等方式减轻过拟合，使模型在未见数据上保持更稳定的泛化性能。", 0.76),
    ]
    for chunk in chunks:
        execute(
            """
            INSERT INTO document_chunks (id, document_id, course_id, concept_id, chunk_index, page_no, section_path, content, content_hash, token_count, embedding_model, embedding_dim, anchor_json, quality_score, asset_type, heading_path_json, quality_reasons_json, quality_ignored, lifecycle_status, embedding_status, content_version, quality_rule_version)
            VALUES (:id, :document_id, :course_id, :concept_id, :chunk_index, :page_no, :section_path, :content, :content_hash, :token_count, 'bge-m3', 1024, CAST(:anchor AS JSONB), :quality_score, 'TEXT', '[]'::jsonb, '[]'::jsonb, false, 'active', 'pending', 1, 'quality-v1')
            ON CONFLICT (id) DO NOTHING
            """,
            id=chunk[0],
            document_id=IDS["doc_ch8"],
            course_id=IDS["course_dl"],
            concept_id=chunk[1],
            chunk_index=chunk[2],
            page_no=chunk[3],
            section_path=chunk[4],
            content=chunk[5],
            content_hash=f"seed-{chunk[2]}",
            token_count=160,
            anchor=dumps({"bbox": None, "page_label": f"P{chunk[3]}"}),
            quality_score=chunk[6],
        )

    # 资源大厅种子数据
    resources = [
        (IDS["res_bp_video"], "res_001", IDS["concept_bp"], IDS["node_002_r"], "反向传播动画讲解", "video", "basic", "featured", "通过动画展示链式法则与梯度流动。", 92, 128),
        (IDS["res_cnn_lab"], "res_002", IDS["concept_cnn"], IDS["node_004"], "PyTorch CNN 实验模板", "code_lab", "medium", "featured", "基于 CIFAR-10 的 CNN 分类实验，含数据加载、模型训练与评估流程。", 94, 86),
        (IDS["res_bn_video"], "res_003", IDS["concept_reg"], IDS["node_003"], "Batch Normalization 原理与实践", "video", "medium", "featured", "系统讲解 BN 的原理与作用，并通过实验对比训练效果与收敛速度。", 88, 92),
        (IDS["res_reg_quiz"], "res_004", IDS["concept_reg"], IDS["node_003"], "正则化错题训练", "quiz", "basic", "featured", "针对 L1/L2、Dropout、Weight Decay 等正则化方法的经典错题训练与解析。", 76, 56),
    ]
    for resource in resources:
        execute(
            """
            INSERT INTO resources (id, course_id, concept_id, path_node_id, code, title, resource_type, difficulty, status, summary, generation_basis_json, citations_json, quality_check_result, safety_status, quality_score, view_count, copied_count, created_by_user_id)
            VALUES (:id, :course_id, :concept_id, :path_node_id, :code, :title, :resource_type, :difficulty, :status, :summary, CAST(:basis AS JSONB), CAST(:citations AS JSONB), CAST(:quality AS JSONB), 'passed', :quality_score, :view_count, :copied_count, :user_id)
            ON CONFLICT (id) DO NOTHING
            """,
            id=resource[0],
            course_id=IDS["course_dl"],
            concept_id=resource[2],
            path_node_id=resource[3],
            code=resource[1],
            title=resource[4],
            resource_type=resource[5],
            difficulty=resource[6],
            status=resource[7],
            summary=resource[8],
            basis=dumps({"course": "深度学习", "personalized_for": "图解型 + 实践偏好"}),
            citations=dumps([{"source_id": IDS["doc_ch8"], "source_title": "深度学习讲义第 8 章.pdf", "page_no": 118, "chunk_id": IDS["chunk_cnn"], "similarity": 0.82, "snippet": "卷积神经网络通过局部感受野、权重共享和池化操作提取层次化特征。"}]),
            quality=dumps({"grade": "A+" if resource[9] >= 90 else "A" if resource[9] >= 85 else "B", "citation_complete": True}),
            quality_score=resource[9],
            view_count=resource[10],
            copied_count=max(8, resource[10] // 8),
            user_id=IDS["user_admin"],
        )
        execute(
            """
            INSERT INTO community_resources (id, resource_id, course_id, submitted_by_user_id, review_status, review_result_json)
            VALUES (gen_random_uuid(), :resource_id, :course_id, :user_id, 'featured', CAST(:review AS JSONB))
            ON CONFLICT (id) DO NOTHING
            """,
            resource_id=resource[0],
            course_id=IDS["course_dl"],
            user_id=IDS["user_admin"],
            review=dumps({"accuracy": 92, "clarity": 88, "personalized_match": 84}),
        )

    # 模型网关供应商
    # 注意：DeepSeek 是纯 Chat 供应商（无 /embeddings 端点），必须显式 provider_type=chat
    # 且清空 embedding_model；否则健康检查会探测 embedding 能力并 404，把供应商标记为
    # down 并进入冷却，导致 chat 调用全部被跳过（教案生成/AI 批改等随之降级）。
    providers = [
        (IDS["provider_spark"], "iflytek_spark", "讯飞星火", "https://spark-api-open.xf-yun.com", "openai_compatible", "spark-x1", "bge-m3", None, True, True, True, "healthy", 1),
        (IDS["provider_deepseek"], "deepseek", "DeepSeek", "https://api.deepseek.com", "openai_compatible", "deepseek-chat", None, None, True, False, True, "healthy", 2),
        (IDS["provider_zhipu"], "zhipu_glm", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "openai_compatible", "glm-4", "embedding-3", "glm-4v", True, True, True, "degraded", 4),
        (IDS["provider_kimi"], "kimi", "Kimi", "https://api.moonshot.cn/v1", "openai_compatible", "moonshot-v1-32k", None, None, True, False, True, "healthy", 5),
        (IDS["provider_ollama"], "ollama", "Ollama", "http://localhost:11434/v1", "openai_compatible", "qwen2.5", "bge-m3", None, True, False, False, "standby", 6),
    ]
    for provider in providers:
        # 仅 DeepSeek 显式声明为 chat 类型；其余保持既有语义（both/embedding 由列默认与模型字段决定）
        provider_type = "chat" if provider[1] == "deepseek" else "both"
        execute(
            """
            INSERT INTO model_providers (id, provider, display_name, base_url, protocol, chat_model, embedding_model, vision_model, supports_stream, supports_tool_call, supports_json_mode, health_status, priority, provider_type, meta_json)
            VALUES (:id, :provider, :display_name, :base_url, :protocol, :chat_model, :embedding_model, :vision_model, :supports_stream, :supports_tool_call, :supports_json_mode, :health_status, :priority, :provider_type, CAST(:meta AS JSONB))
            ON CONFLICT (id) DO NOTHING
            """,
            id=provider[0],
            provider=provider[1],
            display_name=provider[2],
            base_url=provider[3],
            protocol=provider[4],
            chat_model=provider[5],
            embedding_model=provider[6],
            vision_model=provider[7],
            supports_stream=provider[8],
            supports_tool_call=provider[9],
            supports_json_mode=provider[10],
            health_status=provider[11],
            priority=provider[12],
            provider_type=provider_type,
            meta=dumps({"seed": True}),
        )
        execute(
            """
            INSERT INTO model_provider_health (id, provider_id, status, success_rate, avg_latency_ms, consecutive_failures, last_error)
            VALUES (gen_random_uuid(), :provider_id, :status, :success_rate, :avg_latency_ms, :failures, :last_error)
            ON CONFLICT (id) DO NOTHING
            """,
            provider_id=provider[0],
            status=provider[11],
            success_rate=0.96 if provider[11] == "healthy" else 0.88,
            avg_latency_ms=420 if provider[1] != "ollama" else 120,
            failures=0 if provider[11] == "healthy" else 2,
            last_error="tool call latency warning" if provider[11] == "degraded" else None,
        )

    # 运营指标
    execute(
        """
        INSERT INTO usage_metrics_daily (id, metric_date, course_id, dau, course_visits, path_nodes_completed, rag_hit_rate, citation_coverage, resource_success_rate, p95_latency, model_failure_rate, queue_backlog, safety_blocks, meta_json)
        VALUES (:id, :metric_date, :course_id, 428, 1862, 734, 0.86, 0.83, 0.94, 4.8, 0.016, 12, 17, CAST(:meta AS JSONB))
        ON CONFLICT (id) DO NOTHING
        """,
        id=IDS["metrics_today"],
        metric_date=date(2026, 5, 25),
        course_id=IDS["course_dl"],
        meta=dumps({"source": "seed", "window": "latest_demo"}),
    )


def downgrade() -> None:
    # 演示种子数据使用确定性 ID，可安全删除。
    for table, keys in [
        ("usage_metrics_daily", ["metrics_today"]),
        ("model_providers", ["provider_spark", "provider_deepseek", "provider_zhipu", "provider_kimi", "provider_ollama"]),
        ("resources", ["res_bp_video", "res_cnn_lab", "res_bn_video", "res_reg_quiz"]),
        ("document_chunks", ["chunk_cnn", "chunk_bp", "chunk_reg"]),
        ("documents", ["doc_ch8"]),
        ("path_nodes", ["node_001", "node_002", "node_002_r", "node_003", "node_004", "node_005", "node_006", "node_007", "node_008"]),
        ("learning_paths", ["path_dl_user_zhang"]),
        ("course_profiles", ["profile_dl"]),
        ("course_concepts", ["concept_nn", "concept_bp", "concept_reg", "concept_cnn", "concept_rnn", "concept_attention", "concept_autoencoder", "concept_project"]),
        ("course_sections", ["section_dl_1", "section_dl_2", "section_dl_3", "section_dl_4", "section_dl_5", "section_dl_6", "section_dl_7", "section_dl_8"]),
        ("courses", ["course_dl", "course_ml"]),
        ("users", ["user_zhang", "user_admin"]),
        ("roles", ["role_student", "role_admin"]),
    ]:
        for key in keys:
            execute(f"DELETE FROM {table} WHERE id = :id", id=IDS[key])