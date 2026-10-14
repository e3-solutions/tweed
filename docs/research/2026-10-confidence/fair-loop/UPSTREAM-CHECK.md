# Independent upstream source check

Codex independently fetched the following public files at exact revisions. These checks establish the named source and license, not the effectiveness of their guidance or a retroactive pin of the original Opus fetch from `main`. No upstream code is installed or copied into the protocol by this check.

| Source | Revision | File | SHA-256 |
| --- | --- | --- | --- |
| mattpocock/skills | `49dd158d1076134a641b33efb035946536778336` | [skills/productivity/grilling/SKILL.md](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/productivity/grilling/SKILL.md) | `befdff1e27a1dfe2a294d5871169ac1afe16d983911daa4f32627514a48c1e15` |
| mattpocock/skills | `49dd158d1076134a641b33efb035946536778336` | [skills/engineering/diagnosing-bugs/SKILL.md](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/diagnosing-bugs/SKILL.md) | `849198df88cdb65fd0d97236604c1fca7ff2f22d2f705f9724a800d0266b118d` |
| mattpocock/skills | `49dd158d1076134a641b33efb035946536778336` | [skills/engineering/tdd/SKILL.md](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/skills/engineering/tdd/SKILL.md) | `5505d25bbaa8fc14a79e4d20163936958992a2995b7f1dd1d6197edc9ed722e0` |
| mattpocock/skills | `49dd158d1076134a641b33efb035946536778336` | [LICENSE](https://github.com/mattpocock/skills/blob/49dd158d1076134a641b33efb035946536778336/LICENSE) | `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5` |
| obra/superpowers | `bb92a77741419a4ab5f06e711a283343f1ada0c3` | [skills/systematic-debugging/SKILL.md](https://github.com/obra/superpowers/blob/bb92a77741419a4ab5f06e711a283343f1ada0c3/skills/systematic-debugging/SKILL.md) | `51c6435d98c83c42c96ba7c35725a0b2c376cd487fb1a4e6bd0ddbe7e33ef202` |
| obra/superpowers | `bb92a77741419a4ab5f06e711a283343f1ada0c3` | [skills/verification-before-completion/SKILL.md](https://github.com/obra/superpowers/blob/bb92a77741419a4ab5f06e711a283343f1ada0c3/skills/verification-before-completion/SKILL.md) | `2befe7fc55bcadaa3d97dd9e8efeb633d2561c0ebe74c5a8b17c4d9e7e4520b3` |
| obra/superpowers | `bb92a77741419a4ab5f06e711a283343f1ada0c3` | [LICENSE](https://github.com/obra/superpowers/blob/bb92a77741419a4ab5f06e711a283343f1ada0c3/LICENSE) | `a37e0e9697144819e1d965176ac4ae5bc3fa02d11e7812036bbcadf6dafe2400` |

Both repositories use MIT at these revisions. Their license files were retrieved at the same revision. The candidate may paraphrase their bounded patterns; any substantial copied text or code must retain its license.

Official source cross-checks:

- [OpenAI: Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills) supports defining and separately measuring outcome, process, style and efficiency goals. It is guidance, not proof that this candidate improves them.
- [OpenAI: Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra), September 11, 2026, recommends narrowly scoped descriptions and progressive disclosure. Its model-specific claims do not establish Opus behavior.
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), January 9, 2026, distinguishes the transcript from the actual environment outcome and coding graders from qualitative assessment.
- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) supplies checkpoint and incremental-work patterns. We are not implementing its complete harness.
- [SWE-bench harness documentation](https://www.swebench.com/SWE-bench/reference/harness/) supplies evaluation context. The grader concepts are adapted independently; no harness code is copied or introduced as a dependency.
- [Fork-and-Flush v1](https://arxiv.org/html/2610.07447v1) preserves workspace while refreshing context and selecting by a fixed grader under equal compute. This small serial comparison does not replicate its parallel periodic selection or inherit reported gains.

The original Opus research records an HTTP 402 on the requested X post and labels its search snippet anecdotal. No social-media claim is promoted as proof. Original source-access and proposal limitations remain preserved.

These are dated source checks for the current task; current model availability is established separately by actual provider receipts.
