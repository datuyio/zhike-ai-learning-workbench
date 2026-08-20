# Cases: turning architecture from answer into reasoning

> `tutorial/` teaches the method, `templates/` gives you maps, and `cases/` walks a concrete product from zero to launch, then into real pressure.

The case track is not "more templates." Templates answer: **what does this kind of system usually look like?** Cases answer: **in one concrete situation, why did the architecture get forced into this shape?**

---

## First batch

| Case | Related templates | What it drills |
|---|---|---|
| [01 · StarArena: a 20,000-seat concert ticketing system](stararena-ticketing/README.md) | [Online Ticketing / Ticket Rush](../templates/online-ticketing/README.md) · [E-commerce Platform](../templates/ecommerce-platform/README.md) · [Payment System](../templates/payment-system/README.md) | Limited inventory, virtual waiting room, seat locking, payment state machine, reconciliation and compensation |
| [02 · PatchDesk: a lightweight ticketing SaaS for 20-person teams](patchdesk-saas/README.md) | [Standard Web App](../templates/standard-web-app/README.md) · [Mobile App](../templates/mobile-app/README.md) · [Notification System](../templates/notification-system/README.md) | Modular monolith, tenant isolation, RBAC, ticket timeline, Outbox, async notifications, search/report evolution |
| [03 · DocuMind: an enterprise RAG knowledge base for a 500-person company](documind-rag/README.md) | [RAG Knowledge Base](../templates/rag-knowledge-base/README.md) · [AI Chat Product](../templates/ai-chat-product/README.md) · [Vector Database](../templates/vector-database/README.md) | Document ingestion, chunking, hybrid retrieval, Graph RAG, reranking, citations, permission filtering, prompt injection, eval regression |
| [04 · SyncRoom: a realtime collaboration workspace for remote teams](syncroom-collaboration/README.md) | [Realtime Chat](../templates/realtime-chat/README.md) · [Collaborative Doc](../templates/collaborative-doc/README.md) · [Notification System](../templates/notification-system/README.md) | Long connections, server seq, offline catch-up, multi-device sync, OT / CRDT, presence, notification degradation |
| [05 · FeedStream: social feed and video content distribution](feedstream-content/README.md) | [Social Feed](../templates/social-feed/README.md) · [Video Streaming](../templates/video-streaming/README.md) · [Search Engine](../templates/search-engine/README.md) | Hybrid fanout, top creator fanout, timeline inboxes, recommendation ranking, search indexes, video transcoding, CDN, moderation recall |
| [06 · CodePilot: an AI Agent / coding Agent platform](codepilot-agent/README.md) | [AI Agent / Workflow Platform](../templates/ai-agent-platform/README.md) · [OpenAI Codex](../templates/codex/README.md) · [Claude Code](../templates/claude-code/README.md) | Tool calls, permission gateway, sandboxing, human approval, context compaction, checkpoints, subagents, trace, eval gates |

The first batch of six core cases closes here. Later cases will extend with the same quality bar into industry depth or technology-stack drills.

---

## How to read cases

Do not memorize the diagram. Watch four things:

1. **Why was the old architecture reasonable at first?**
2. **Which quantified signal proved it could no longer continue?**
3. **What did the new architecture choose, and what did it give up?**
4. **If the constraints changed, would this answer still hold?**

One-line bar:

> **No numbers, not a case; no trade-offs, not architecture; no evolution, not case-track material.**
