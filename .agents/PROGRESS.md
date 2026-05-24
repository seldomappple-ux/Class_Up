# PROGRESS

## Project Version

- Current project version: `0.1.0`

## Purpose

Use this file as a sliding index, not a long-form journal. Detailed history lives under `.agents/progress/entries/`.

## Active Architecture Decisions

| ID | Status | Title | Summary |
| --- | --- | --- | --- |
| `ADR-0001` | `active` | Lightweight governance source lives in .agents | The project keeps stable rules, project profile, architecture decisions, and progress records under .agents as the minimum governance source. |
| `ADR-0002` | `active` | Progress entries are the durable history | PROGRESS.md is only a current index; durable context is written as dated entries under .agents/progress/entries/YYYY/. |

## Active Entries

| Page ID | Date | Title | Status | Path | Related Commit Message |
| --- | --- | --- | --- | --- | --- |
| `20260524-7` | `2026-05-24` | Split subtitles on word-level speech gaps | `accepted` | `.agents/progress/entries/2026/2026-05-24-7.md` | fix(subtitles): split chunks on word-level speech gaps |
| `20260524-6` | `2026-05-24` | Align subtitle chunks with Doubao word timestamps | `accepted` | `.agents/progress/entries/2026/2026-05-24-6.md` | fix(subtitles): align chunks with doubao word timestamps |
| `20260524-5` | `2026-05-24` | Fix M1 subtitle timeline stability | `accepted` | `.agents/progress/entries/2026/2026-05-24-5.md` | fix(subtitles): stabilize audio timeline mapping and split bounds |
| `20260524-4` | `2026-05-24` | Record real subtitle timing drift findings | `accepted` | `.agents/progress/entries/2026/2026-05-24-4.md` | docs(subtitles): record real timing drift findings |
| `20260524-3` | `2026-05-24` | Add layered cleanup policy for remote temp audio and local caches | `accepted` | `.agents/progress/entries/2026/2026-05-24-3.md` | feat(cleanup): add layered cleanup and audit trail |
| `20260524-2` | `2026-05-24` | Improve subtitle readability, output naming, and same-source reuse | `accepted` | `.agents/progress/entries/2026/2026-05-24-2.md` | feat(transcription): improve subtitle output and reuse same-source cache |
| `20260524-1` | `2026-05-24` | Add SFTP upload integrity checks and segment retry | `accepted` | `.agents/progress/entries/2026/2026-05-24-1.md` | fix(transcription): verify sftp uploads and retry failed segments |
| `20260519-4` | `2026-05-19` | Implement Doubao ASR provider path | `accepted` | `.agents/progress/entries/2026/2026-05-19-4.md` | feat(m1): add doubao asr provider and sftp upload path |
| `20260519-3` | `2026-05-19` | Define Doubao ASR integration protocol | `draft` | `.agents/progress/entries/2026/2026-05-19-3.md` | docs(m1): define doubao asr integration protocol |
| `20260519-2` | `2026-05-19` | Add FastAPI Web UI for M1 Pipeline | `draft` | `.agents/progress/entries/2026/2026-05-19-2.md` | feat(web): add FastAPI web UI with start/start_mock and auto-shutdown |
| `20260519-1` | `2026-05-19` | Add one-click video to audio conversion command | `draft` | `.agents/progress/entries/2026/2026-05-19-1.md` | feat(audio): add standalone video to audio conversion command |
| `20260518-11` | `2026-05-18` | Implement M1 backend mock transcription pipeline | `draft` | `.agents/progress/entries/2026/2026-05-18-11.md` | feat(m1): implement backend mock transcription pipeline |
| `20260518-10` | `2026-05-18` | Resolve data protocol ambiguities | `draft` | `.agents/progress/entries/2026/2026-05-18-10.md` | docs(protocol): resolve data protocol ambiguities |
| `20260518-9` | `2026-05-18` | Add full data protocol for development workflow | `draft` | `.agents/progress/entries/2026/2026-05-18-9.md` | docs(protocol): add full data protocol for workflow |
| `20260518-8` | `2026-05-18` | Fix risks in M1 development plan | `draft` | `.agents/progress/entries/2026/2026-05-18-8.md` | docs(plan): fix M1 development plan risks |
| `20260518-7` | `2026-05-18` | Add dedicated M1 development plan | `draft` | `.agents/progress/entries/2026/2026-05-18-7.md` | docs(plan): add dedicated M1 development plan |
| `20260518-6` | `2026-05-18` | Align development plan with configurable domestic model strategy | `draft` | `.agents/progress/entries/2026/2026-05-18-6.md` | docs(plan): align M1 with configurable model services |
| `20260518-5` | `2026-05-18` | Split course assistant goal and execution plan | `draft` | `.agents/progress/entries/2026/2026-05-18-5.md` | docs(plan): split development goal and execution plan |
| `20260518-4` | `2026-05-18` | Formalize course assistant development plan | `draft` | `.agents/progress/entries/2026/2026-05-18-4.md` | docs(plan): formalize course assistant development plan |
| `20260518-3` | `2026-05-18` | Revise development plan for configurable domestic model stack | `draft` | `.agents/progress/entries/2026/2026-05-18-3.md` | docs(plan): make model stack configurable for domestic providers |
| `20260518-2` | `2026-05-18` | Establish base folders for a pure software project | `draft` | `.agents/progress/entries/2026/2026-05-18-2.md` | chore(structure): establish pure software project folders |

## Archive

- Active entries older than the latest 10 should remain in `.agents/progress/entries/` and be located by search or tooling.
