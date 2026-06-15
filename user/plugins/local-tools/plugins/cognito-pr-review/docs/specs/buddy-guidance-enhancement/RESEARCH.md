# **Research-Backed Best Practices for AI-Assisted Pull Request Review**

The integration of large language model (LLM) agents into the software engineering lifecycle fundamentally alters the mechanics of peer code review. Historically, code review served as the primary human-driven quality gate, designed to detect defects, enforce architectural standards, and disseminate knowledge across engineering teams. However, the proliferation of AI-assisted coding tools has dramatically increased the velocity and volume of code generation, shifting the cognitive bottleneck directly onto the review process. This volume increase exacerbates well-documented human limitations, such as vigilance decrement and cognitive fatigue, threatening the integrity of the review stage.  
The analysis herein evaluates the architectural design of a conversational, AI-assisted code-review system intended to guide experienced senior software engineers through pull requests (PRs). The primary objective is to maximize the detection of real defects and ensure the construction of an accurate mental model of the code changes. By scrutinizing the empirical and practitioner literature spanning classic software inspection methodologies, cognitive load theory, and modern AI agent evaluations, this report identifies critical divergences between the proposed baseline design and empirically validated best practices. The investigation focuses on two primary vectors: the partitioning of code changes into reviewable units, and the guiding interaction loop utilized to direct expert reviewers.

## **A. Code-Review Effectiveness Fundamentals**

### **The Evolution from Fagan Inspections to Lightweight Pull Requests**

The formalization of code review originated with Michael Fagan's 1976 research at IBM, which established highly structured, synchronous, and multi-stage code inspections1. Fagan inspections were resource-intensive, requiring distinct roles (such as author, reader, tester, and moderator) and extensive preparation, consuming up to three percent of total project effort1. While empirically effective at defect detection, the cumbersome nature of synchronous meetings led the industry to adopt lightweight, tool-based, asynchronous code reviews, commonly known as Modern Code Review (MCR)1.  
Large-scale mining studies at Microsoft and Google reveal a significant shift in the actual outcomes of MCR compared to its theoretical goals. Research indicates that while developers state defect detection as their primary motivation for code review, the actual defect yield is relatively low1. Instead, the majority of review comments pertain to code style, system evolution, and knowledge transfer3. A study at Microsoft concluded that code reviews frequently do not catch deep, logic-level defects, but rather serve to improve maintainability and team awareness1. Consequently, relying purely on traditional asynchronous reading for deep defect detection is empirically insufficient, necessitating structured, cognitively optimized interventions to elevate the defect discovery rate.

### **Empirical Ceilings: Volume, Pace, and Duration**

Empirical research establishes strict ceilings on human cognitive capacity during code inspection. The largest and most frequently cited study on code review metrics, conducted by SmartBear examining Cisco Systems data (published initially around 2006–2009 and widely replicated in practice), provides concrete boundaries for review scope and pacing6. Defect detection efficiency adheres to a non-linear curve that degrades precipitously when specific thresholds are breached. The evidence strongly suggests that software engineering teams must strictly regulate the volume and duration of review sessions.

| Metric | Empirical Threshold | Source Type & Date | Consequence of Exceeding Threshold |
| :---- | :---- | :---- | :---- |
| **Review Unit Size** | 200–400 Lines of Code (LOC) | Large-scale industry study (SmartBear/Cisco, \~2006) | Defect discovery drops sharply beyond 400 LOC. Reviews under 200 LOC exhibit the highest defect density detection, capturing 70–90% of defects6. |
| **Inspection Rate** | \< 300–500 LOC per hour | Large-scale industry study (SmartBear/Cisco, \~2006) | Reviewing faster than 500 LOC/hour results in a severe drop in defect density. The optimal rate for maximizing detection is under 300 LOC/hour6. |
| **Session Duration** | 60 minutes (Max 90 mins) | Empirical ergonomics & cognitive science6 | Performance and focus decline rapidly after 60 minutes of sustained inspection. Defect detection rates plummet if sessions extend to 90 minutes6. |
| **Defect Rate Ceiling** | \~15 defects found per hour | Large-scale industry study (SmartBear/Cisco, \~2006) | The rate of human defect discovery remains relatively constant regardless of review size. Compressing a large review into a short time window guarantees missed defects9. |

The data implies that code review effectiveness is constrained by a fixed human processing bandwidth. A reviewer processes a consistent number of defects per hour; providing a massive volume of code merely dilutes the attention applied per line, allowing critical logic errors to escape into production. For an expert reviewer, while their internal schemas might allow them to read faster than a novice, the fundamental physiological limit on sustained vigilance remains immutable.

### **Fatigue and the Vigilance Decrement**

The degradation of defect detection over time is rooted in a psychological phenomenon known as the vigilance decrement. Sustained attention is a cognitively expensive resource. Decades of attention research demonstrate that detection performance in monitoring tasks declines significantly after the first 30 to 60 minutes12. This decline occurs not due to a loss of motivation, but because the brain's cognitive resources are physiologically depleted12.  
The introduction of AI coding assistants exacerbates this issue by inducing "review fatigue." Because LLMs generate code significantly faster than humans, engineers spend a disproportionate amount of their workday reviewing code they did not author12. This shift alters the cognitive load from the generative work of software design to the sustained vigilance required to evaluate external output. When vigilance decrement combines with the context-switching costs of reviewing multiple disparate files, developers default to "surface scanning"—checking for syntax and formatting rather than validating complex logical invariants12. Therefore, an AI-guided review system must actively combat the vigilance decrement by enforcing strict session boundaries and preventing continuous, unbroken review blocks.

## **B. Partitioning: The Review Unit and Its Ordering**

### **The Optimal Unit of Review: Untangling Composite Commits**

The baseline system partitions a PR into logical groups of files, organized by directory or module. However, software engineering literature strongly indicates that file-based or directory-based grouping is suboptimal for human comprehension, particularly for complex, multi-layered codebases.  
Developers frequently commit "tangled" or "composite" changes—changesets that bundle multiple unrelated development activities (such as adding a feature, applying a bug fix, and performing a cosmetic refactoring) into a single submission14. Studies show that up to 29% to 39% of commits in open-source and industrial projects are tangled17. Reviewing tangled changes imposes an immense cognitive burden because the reviewer must continuously context-switch to determine which lines of code correspond to which distinct objective18.  
Research into dynamic changeset decomposition advocates for "activity-oriented" or "semantic" clustering rather than file-level grouping14. Algorithmic approaches like *SmartCommit* and *EpiceaUntangler* utilize graph-partitioning techniques to analyze Abstract Syntax Trees (ASTs), data-flow dependencies, and structural links to cluster diff hunks into self-contained behavioral tasks14.  
Controlled user studies reveal that when a composite change is partitioned into cohesive, behavior-based "change-slices," reviewers achieve significantly better comprehension in the same amount of time compared to reviewing the original composite file18. The optimal review unit is therefore not a file, but an isolated, semantically linked dependency cluster (for instance, evaluating the database migration, the data access layer changes, and the associated business logic modifications that achieve a single narrative objective). For an expert reviewer, semantic clustering aligns perfectly with their highly structured internal mental models, allowing them to trace a single execution path across architectural boundaries without extraneous cognitive noise.

### **Reordering for Comprehension: Tests Alongside Code**

The baseline design enforces a "core/critical changes first, tests last" ordering policy. Empirical research directly contradicts the efficacy of reviewing tests last, especially when the goal is deep comprehension and defect detection.  
Test-Driven Code Review (TDR) investigates the practice of reading test files prior to, or alongside, production code19. A controlled experiment demonstrated that reviewers employing TDR identify significantly more functional defects in the test code itself19. While the proportion of defects found in the production code remained statistically similar, reviewing tests first or concurrently provides the reviewer with an executable specification of the code's intended behavior19.  
From a comprehension standpoint, tests serve as a critical orientation mechanism. By understanding the inputs, expected outputs, and edge cases defined in the test suite, the expert constructs a mental model of the software's contract *before* evaluating the implementation details. Relegating tests to the end of the review session ensures they are analyzed when the reviewer's cognitive resources are most depleted due to the vigilance decrement, resulting in superficial evaluations of the test suite's rigor12. Furthermore, reviewing tests alongside the code they exercise supports comparative code comprehension, allowing the reviewer to continuously validate the implementation against its specified oracle22.

### **Managing Unit Size and Splits**

Given the empirical ceiling of 200–400 LOC for optimal defect detection6, PRs exceeding this volume must be systematically partitioned. If a semantically clustered review unit surpasses 400 LOC, it must be subdivided based on architectural boundaries or data flow. An AI agent mediating the review should autonomously halt the review session after 60 minutes or 400 lines, enforcing a mandatory cognitive break before allowing the reviewer to proceed to the next partition6.

## **C. Guiding the Expert: Interaction, Cognitive Load, and Bias**

The interaction loop utilized to guide a reviewer is the most critical element of the proposed tool. The baseline loop dictates that the agent first *teaches* the reviewer what changed, then *surfaces findings*, asks a *Socratic prompt*, and captures a *verdict*. For an audience of experienced senior engineers, this specific sequencing contradicts the established principles of cognitive psychology and human-AI interaction.

### **Cognitive Load Theory and the Expertise-Reversal Effect**

Cognitive Load Theory (CLT) categorizes the mental effort required for learning and comprehension into intrinsic load (the inherent difficulty of the material), extraneous load (the manner in which information is presented), and germane load (the effort dedicated to processing and constructing schemas)23.  
A central tenet of CLT is the Expertise-Reversal Effect. Instructional techniques and guidance mechanisms that heavily benefit novices—such as front-loaded explanations, detailed walkthroughs, and worked examples—actually *harm* the performance and comprehension of domain experts23. Experts possess highly developed, automated schemas in their long-term memory24. When an AI agent preemptively "teaches" an expert what a block of code does, it forces the expert to cross-reference the agent's explanation against their own internal schema. This redundancy imposes extraneous cognitive load, interrupting their natural analytical flow and degrading comprehension23.  
Therefore, front-loading an explanation is actively detrimental to a senior software engineer. The interaction ratio must shift from *telling* to *eliciting*. Explanations should be strictly provided on-demand, or reserved for components explicitly identified as lying outside the reviewer's domain of expertise. The AI should serve as a facilitator of the expert's cognitive process rather than a didactic instructor.

### **Anchoring, Automation Bias, and Tool Timing**

The baseline model surfaces pre-computed automated findings *before* the reviewer engages with the code and answers questions. This sequencing induces severe cognitive biases that undermine the fundamental purpose of human oversight.  
When reviewers are presented with automated analysis before forming an independent judgment, they fall victim to Anchoring Bias and Automation Complacency11. Automation complacency occurs when a system is highly reliable in a narrow scope, causing the human operator to implicitly trust its outputs and cease independent verification12. If an LLM or static analysis tool flags three minor style issues, the human reviewer's attention is anchored to those exact lines. The reviewer addresses the minor issues and proceeds, subconsciously assuming the tool has exhaustively verified the remainder of the file.  
Empirical studies on static application security testing (SAST) and automated code review demonstrate that automated tools miss approximately 22% of real-world vulnerabilities and generate false-positive rates of 30-60%29. Furthermore, recent security evaluations reveal a critical flaw in LLMs known as "Abstraction Bias," culminating in Familiar Pattern Attacks (FPAs) presented at NDSS 202635. When an LLM processes a familiar coding pattern or algorithm, it overgeneralizes and abstracts the code's intent, completely overlooking small, deterministic logic errors (e.g., an off-by-one error or a flipped boolean) hidden within the boilerplate35.  
If the AI agent reveals its findings immediately, the senior engineer's attention is diverted from the deep logic flaws the AI inherently misses due to abstraction bias. The human focuses instead on the superficial findings the AI successfully caught. To mitigate this, the revelation of pre-computed tool findings must be delayed until *after* the human has formed an independent judgment, or integrated strictly as a post-reading reconciliation step33.

### **Perspective-Based Reading (PBR) vs. Ad-Hoc Checklists**

The system currently provides the reviewer with standard "what to look for" and "key questions" for each unit. While standard checklists (Checklist-Based Reading or CBR) improve defect detection by up to 66.7% compared to unstructured, ad-hoc reading8, research in software inspection advocates for a more rigorous methodology for experts known as Perspective-Based Reading (PBR)39.  
In PBR, the reviewer assumes a specific stakeholder role—such as a security auditor, a database administrator, or a performance tester—and evaluates the code strictly through that specialized lens42. PBR operates on the premise that no single reading pass can effectively evaluate all dimensions of software quality. By constraining the review's focus to a single perspective, PBR limits cognitive overload and ensures systematic coverage42.  
Instead of presenting a generic checklist, the conversational agent should dynamically assign a perspective based on the risk profile of the diff chunk. For example, if the chunk modifies a data-access layer, the agent should instruct the expert: "Review this chunk strictly from the perspective of an adversarial attacker looking for SQL injection flaws and resource exhaustion." This role-playing mechanism forces the expert to adopt a highly critical, focused mindset, significantly increasing the probability of uncovering severe defects.

### **Active Comprehension and the Socratic Method**

To build a correct mental model, comprehension must be an active, constructive process. Passive reading is insufficient. Techniques such as self-explanation, prediction, and summarization significantly improve code comprehension48. Modern biometric studies utilizing eye-tracking (such as the NRevisit metric) and EEG demonstrate that cognitive load maps directly to the number of times a developer must revisit a code region to confirm their understanding48.  
The Socratic method is an optimal vehicle for prompting active comprehension in experts without triggering the expertise-reversal effect52. However, the questions must be engineered to solicit deep structural reasoning rather than factual recall. Effective Socratic questions in technical contexts focus on boundary conditions, architectural limits, and predictive outcomes53.  
Examples of effective Socratic prompts for experts include:

* "If this external service latency increases by a factor of ten, how does this module's failure mode propagate?"  
* "What underlying assumptions does this function make regarding the mutability of the incoming state?"  
* "Predict the outcome if this database transaction is interrupted prior to the final commit."

These prompts force the expert to engage in predictive simulation, verifying the code's robustness against edge cases rather than merely tracing its optimal path.

## **D. Capturing Reviewer Judgment**

The current disposition model captures reviewer decisions using a vocabulary of: *keep*, *dismiss*, *will-comment*, and *add-own-observation*. This taxonomy is inadequate for scaling large engineering systems and fails to capture the nuance of software risk.  
Industry standards established by large-scale software organizations (e.g., Google, Microsoft, GitLab) and formal frameworks like Conventional Comments utilize taxonomies heavily weighted toward severity and blocking status10.  
The primary distinction that must be captured is whether a defect is a critical blocker or an optional enhancement. Mixing minor stylistic observations with severe security vulnerabilities in a single, unweighted feedback stream generates noise and friction10. Studies indicate that only 15% of review comments actually address logic defects, while the rest target superficial formatting5.  
A rigorous, evidence-based taxonomy should classify feedback into distinct tiers.

| Severity Tier | Description | Actionable Requirement |
| :---- | :---- | :---- |
| **Blocking (Critical)** | Security flaws, logic defects, data corruption risks, or requirement violations10. | Must be resolved before the code can be approved and merged. |
| **Important (Should-Fix)** | Architectural degradation, missing edge cases, or significant performance issues that introduce technical debt10. | Highly recommended for immediate resolution, but can be deferred with explicit agreement. |
| **Suggestion (Optional/Nit)** | Readability enhancements, stylistic preferences, or minor refactoring suggestions10. | Non-blocking. The author may merge the code without addressing these items. |

By forcing the reviewer (and the AI agent) to explicitly label the severity of a finding, the system immediately filters out low-value noise and allows the author to prioritize resolving critical defects.

## **E. AI/LLM-Assisted and Pair-Review Specifically**

The integration of LLMs into the code review pipeline presents unique opportunities and profound risks. A large-scale user study of the "RevMate" LLM review assistant, deployed at Mozilla (open-source) and Ubisoft (closed-source), analyzed over 587 patch reviews62. The empirical data reveals stark realities about AI performance in live engineering environments.  
The study found incredibly low direct acceptance of LLM suggestions. Only 7.2% to 8.1% of LLM-generated comments were directly accepted by developers as valid defects requiring modification62. However, the AI offered high indirect value. Despite the low acceptance rate, an additional 14.6% to 20.5% of the LLM comments were classified by senior engineers as "valuable tips" or helpful development context62. Furthermore, LLMs demonstrated significantly higher competency in identifying refactoring opportunities (accepted \~18% of the time) than deep functional or logic errors (accepted \~5% of the time)62.  
These findings correlate precisely with the phenomenon of "Abstraction Bias" outlined in the literature regarding Familiar Pattern Attacks35. Because LLMs process code via tokenized probabilistic abstraction, they excel at recognizing deviations in style, syntax, and standard refactoring templates. Conversely, they systematically fail to detect subtle, deterministic logic bugs hidden inside standard algorithmic boilerplate because the statistical weight of the familiar pattern overwhelms the model's local reasoning capabilities35.  
Consequently, utilizing an LLM as the primary detector of logical defects is mathematically flawed. The AI agent's role should be strictly scoped to detecting mechanical violations, surfacing cross-file dependencies, summarizing context upon request, and dynamically generating Socratic questions that force the human expert to evaluate the logic30. If the LLM acts as the primary inspector, the human reviewer acts as a passive supervisor, inevitably falling prey to automation bias and allowing critical vulnerabilities to slip through the quality gate29.

## **Specific Questions Answered**

The following section directly addresses the ten specific questions raised regarding the system architecture, providing concrete recommendations backed by empirical evidence.

### **1\. Optimal Review Unit**

**Is logical file-group the best review unit?** **Recommendation:** No. Evidence heavily favors semantic/dependency clusters (Activity-Oriented partitions). **Evidence:** Research into untangling composite commits proves that developers frequently bundle unrelated changes into single PRs14. Grouping purely by directory fails to capture cross-file behavioral logic. Studies on tools like *SmartCommit* show that reviewers comprehend changes significantly faster when code is partitioned by behavior rather than file location17. **Action:** Utilize graph-based AST and data-flow dependency mapping to slice the PR into self-contained behavioral chunks (e.g., evaluating a UI component alongside its associated API route and database schema)17. Review one behavioral thread at a time.

### **2\. Ordering Core vs. Tests**

**Is "core-first, tests-last" optimal?** **Recommendation:** No. Tests should be read first or concurrently with the code they exercise. **Evidence:** Empirical studies on Test-Driven Code Review (TDR) demonstrate that reviewing tests first yields higher defect detection within the test suite and prevents tests from being neglected due to late-stage fatigue19. Tests act as executable specifications, allowing the expert to build an accurate mental model of the contract before reading the implementation19. **Action:** Present the unit tests governing a specific behavioral chunk simultaneously with the implementation code to encourage comparative comprehension and validate the code against its oracle19.

### **3\. Maximum Size of a Review Unit**

**What is the evidence-based maximum size?** **Recommendation:** 200 to 400 Lines of Code (LOC) per continuous review block. **Evidence:** The seminal SmartBear/Cisco study (and supporting large-scale corroborations) definitively shows that defect detection density drops precipitously when a single review exceeds 400 lines of code6. **Action:** If a semantic cluster exceeds 400 LOC, the AI guide must algorithmically split it into sub-components based on data flow boundaries. Do not present more than 400 LOC in a continuous stream to the reviewer.

### **4\. Pacing and Fatigue Mitigation**

**What is the recommended session length and cadence?** **Recommendation:** Maximum 60 minutes per session, at a rate of under 500 LOC per hour. **Evidence:** Cognitive science and software inspection metrics prove that vigilance decrement destroys defect detection after 60 minutes of sustained attention6. **Action:** The AI agent must rigorously enforce pacing. If the reviewer's inspection rate exceeds 500 LOC/hour, the agent should tactfully halt the progression and prompt a deeper review. After 60 minutes of active session time, the agent must enforce a mandatory checkpoint and recommend a cognitive break.

### **5\. Teaching vs. Eliciting for Experts**

**Should the agent teach before the reviewer reads?** **Recommendation:** No. The system should elicit first and teach only on demand. **Evidence:** Cognitive Load Theory establishes the Expertise-Reversal Effect: providing detailed instructional explanations to experts increases extraneous cognitive load and harms comprehension by interfering with their established mental schemas23. **Action:** For senior engineers, invert the guidance loop. Do not summarize the code upfront. Instead, present the code, pose a predictive Socratic challenge, and offer the "Teach" summary strictly via an explicit opt-in mechanism (e.g., "Would you like a summary of the dependency changes?").

### **6\. Timing of Automated Findings**

**Should tool findings be revealed before, during, or after judgment?** **Recommendation:** After the human reads and forms an initial judgment. **Evidence:** Revealing automated findings before human judgment triggers severe Anchoring Bias and Automation Complacency11. Because LLMs suffer from Abstraction Bias and miss up to 22% of logic vulnerabilities29, anchoring the human to the AI's superficial findings causes them to prematurely conclude the review and miss critical deeper defects. **Action:** The human reads the code and formulates a verdict. The AI then reveals its findings as a reconciliation step ("I noticed you approved this chunk, but static analysis flagged an unhandled null exception on line 42\. Do you wish to revise?").

### **7\. Checklists vs. Perspective-Based Reading**

**Do checklists beat open reading, and what design is best?** **Recommendation:** Perspective-Based Reading (PBR) outperforms generic checklists. **Evidence:** While standard checklists outperform ad-hoc reading8, PBR forces the reviewer to adopt specific adversarial or functional personas (e.g., Security Auditor, Database Admin), drastically focusing attention and increasing specific defect detection rates42. **Action:** Replace static "Key Questions" with dynamic, role-based missions based on the code's context (e.g., instructing the reviewer to "Read this chunk strictly looking for thread-safety and race conditions").

### **8\. Active Comprehension Techniques**

**Which techniques most improve an expert's mental model?** **Recommendation:** Predictive simulation and boundary-condition Socratic questioning. **Evidence:** Active comprehension requires the reviewer to move beyond passive reading. Studies on Socratic dialogues and cognitive load show that asking experts to predict outcomes activates deep reasoning pathways52. **Action:** The agent should pose scenario-based questions such as: "If X input is null, how does this module gracefully degrade?" Require the reviewer to mentally simulate execution to answer the prompt.

### **9\. Capturing Reviewer Disposition**

**Is the current vocabulary (keep/dismiss/will-comment) optimal?** **Recommendation:** No. Adopt a Severity and Blocking taxonomy. **Evidence:** Large-scale engineering standards (Google, Microsoft, GitLab) emphasize distinguishing between critical defects and minor suggestions to prevent review bottlenecks and friction10. **Action:** Transition the vocabulary to capture severity: Blocking (Critical logic/security flaw), Important (Tech debt/Performance), Suggestion/Nit (Style/Refactor), and Dismiss.

### **10\. AI Failure Modes and Mitigations**

**What are the specific failure modes of AI-guided review?** **Recommendation:** Beware Abstraction Bias; use AI strictly for mechanical triage and facilitation, not logic validation. **Evidence:** LLMs suffer from Abstraction Bias, consistently missing deterministic bugs hidden inside familiar coding patterns35. Furthermore, empirical studies show LLM reviews have low direct acceptance (\~8%) but provide valuable secondary context62. **Action:** Frame the AI agent as a facilitator that handles cross-file dependency mapping, mechanical standards, and Socratic questioning. Never allow the AI to certify that complex business logic is correct. Maintain the human expert as the sole arbiter of algorithmic integrity.

## **Prioritized "What to Change" List**

Based on the empirical evidence, the system design should be overhauled to maximize defect detection in expert reviewers. The recommendations below are ranked by strength of evidence and expected impact on defect detection.

### **Tier 1: Well-Supported, Adopt Immediately (High Impact)**

1. **Delay Tool Findings (Anti-Anchoring):** Alter the interaction loop to move the "Surface Findings" step to *after* the "Capture Verdict" step. Presenting the LLM's findings as a post-reading reconciliation phase eliminates automation complacency and anchoring bias, forcing the expert to engage in deep local reasoning before seeing the tool's output.  
2. **Enforce Cognitive Ceilings:** The AI agent must algorithmically cap review sessions at 60 minutes and strictly limit review chunks to a maximum of 400 LOC. Enforcing mandatory breaks and chunk limits is the most empirically validated method to combat the vigilance decrement.  
3. **Implement Severity-Based Judgments:** Replace the current disposition vocabulary with a Blocking / Important / Suggestion model. This allows authors to triage defects efficiently and prevents reviewers from equating minor style nits with severe logical flaws.  
4. **Invert the Expert Loop (Combat Expertise-Reversal):** Remove the mandatory "Teach" step at the beginning of the unit. Present the code, allow the expert to read, and provide the explanation strictly via an "Explain Context" opt-in button. This prevents the system from imposing extraneous cognitive load on experts who already possess robust mental schemas.

### **Tier 2: Plausible, Try and Measure (Moderate to High Impact)**

5. **Semantic Partitioning (Untangling):** Abandon the baseline directory-based partitioning approach. Utilize the AI to perform AST and dependency analysis to slice the PR into behaviorally cohesive clusters. Measure the expert's time-to-comprehension against the old model to validate the reduction in context-switching overhead.  
6. **Test-Driven Review Placement:** Alter the presentation ordering to place tests sequentially *first* or in a side-by-side comparative pane with the relevant production code, rather than pooling them at the end. Measure if this increases the detection of edge-case failures.  
7. **Perspective-Based Socratic Prompts:** Shift the static "Key Questions" to dynamic PBR missions (for instance, explicitly assigning a "Security Auditor" persona to the reviewer for a specific API route) and ask predictive Socratic questions rather than descriptive ones. Measure the subsequent increase in critical defect identification.

#### **Works cited**

1. The End of Code Review: Coding Agents Supersede Human Inspection \- arXiv, [https://arxiv.org/html/2606.13175](https://arxiv.org/html/2606.13175)  
2. The End of Code Review: Coding Agents Supersede Human Inspection \- arXiv, [https://arxiv.org/pdf/2606.13175](https://arxiv.org/pdf/2606.13175)  
3. Expectations, Outcomes, and Challenges Of Modern Code Review | Microsoft Research, [https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ICSE202013-codereview.pdf](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ICSE202013-codereview.pdf)  
4. Modern Code Review: A Case Study at Google, [https://research.google/pubs/modern-code-review-a-case-study-at-google/](https://research.google/pubs/modern-code-review-a-case-study-at-google/)  
5. Code Reviews Do Not Find Bugs. How the Current Code Review Best Practice Slows Us Down | Request PDF \- ResearchGate, [https://www.researchgate.net/publication/308810818\_Code\_Reviews\_Do\_Not\_Find\_Bugs\_How\_the\_Current\_Code\_Review\_Best\_Practice\_Slows\_Us\_Down](https://www.researchgate.net/publication/308810818_Code_Reviews_Do_Not_Find_Bugs_How_the_Current_Code_Review_Best_Practice_Slows_Us_Down)  
6. Best Practices for Peer Code Review \- SmartBear, [https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/)  
7. Best Practices and Metrics for Code Review \- GlowTouch Technologies, [https://www.glowtouch.com/best-practices-and-metrics-for-code-review/](https://www.glowtouch.com/best-practices-and-metrics-for-code-review/)  
8. Empirically sup code review best practices \- Graphite, [https://graphite.com/blog/code-review-best-practices](https://graphite.com/blog/code-review-best-practices)  
9. Smart Bear, Cisco, and the Largest Study on Code Review Ever | A Blog by Mike Conley, [https://mikeconley.ca/blog/2009/09/14/smart-bear-cisco-and-the-largest-study-on-code-review-ever/](https://mikeconley.ca/blog/2009/09/14/smart-bear-cisco-and-the-largest-study-on-code-review-ever/)  
10. Code Review Checklist: 40 Questions Before You Approve, [https://www.augmentcode.com/guides/code-review-checklist-40-questions-before-you-approve](https://www.augmentcode.com/guides/code-review-checklist-40-questions-before-you-approve)  
11. How to Do Code Review: A Practical Guide for Developers, [https://www.augmentcode.com/guides/how-to-do-code-review-a-practical-guide-for-developers](https://www.augmentcode.com/guides/how-to-do-code-review-a-practical-guide-for-developers)  
12. AI Writes Better Code. We're Getting Worse at Reviewing It. \- Atomic Robot, [https://atomicrobot.com/blog/ai-review-fatigue/](https://atomicrobot.com/blog/ai-review-fatigue/)  
13. Coding agents are giving everyone decision fatigue \- The Stack Overflow Blog, [https://stackoverflow.blog/2026/05/21/coding-agents-are-giving-everyone-decision-fatigue/](https://stackoverflow.blog/2026/05/21/coding-agents-are-giving-everyone-decision-fatigue/)  
14. (PDF) Untangling Fine-Grained Code Changes \- ResearchGate, [https://www.researchgate.net/publication/272845723\_Untangling\_Fine-Grained\_Code\_Changes](https://www.researchgate.net/publication/272845723_Untangling_Fine-Grained_Code_Changes)  
15. Untangling Fine-Grained Code Changes \- arXiv, [https://arxiv.org/pdf/1502.06757](https://arxiv.org/pdf/1502.06757)  
16. \[1502.06757\] Untangling Fine-Grained Code Changes \- arXiv, [https://arxiv.org/abs/1502.06757](https://arxiv.org/abs/1502.06757)  
17. SmartCommit: A Graph-Based Interactive Assistant for Activity-Oriented Commits \- CMU School of Computer Science, [https://www.cs.cmu.edu/\~ckaestne/pdf/fse21\_sc.pdf](https://www.cs.cmu.edu/~ckaestne/pdf/fse21_sc.pdf)  
18. Partitioning Composite Code Changes to Facilitate Code Review \- Yida Tao, [https://yidatao.github.io/paper/tao\_msr2015.pdf](https://yidatao.github.io/paper/tao_msr2015.pdf)  
19. Test-Driven Code Review: An Empirical Study \- Alberto Bacchelli, [https://sback.it/publications/icse2019a.pdf](https://sback.it/publications/icse2019a.pdf)  
20. Test-Driven Code Review: An Empirical Study \- FABIO PALOMBA, [https://fpalomba.github.io/pdf/Conferencs/C37.pdf](https://fpalomba.github.io/pdf/Conferencs/C37.pdf)  
21. Code Review vs. Testing \- what is the difference? Are they interchangable? \- Codacy | Blog, [https://blog.codacy.com/code-review-vs-testing](https://blog.codacy.com/code-review-vs-testing)  
22. Reviewing Strategies Seen Through Code Comprehension Theories \- arXiv, [https://arxiv.org/html/2503.21455v1](https://arxiv.org/html/2503.21455v1)  
23. The Expertise Reversal Effect : Journal of Experimental Psychology: Applied \- Ovid, [https://www.ovid.com/journals/jepap/fulltext/10.1037/a0022243\~the-expertise-reversal-effect-cognitive-load-and](https://www.ovid.com/journals/jepap/fulltext/10.1037/a0022243~the-expertise-reversal-effect-cognitive-load-and)  
24. The Importance of Decreasing Cognitive Load in Software Development | iftrue, [https://www.iftrue.co/post/the-importance-of-decreasing-cognitive-load-in-software-development/](https://www.iftrue.co/post/the-importance-of-decreasing-cognitive-load-in-software-development/)  
25. Expertise Reversal Effect and Its Implications for Learner-Tailored Instruction, [https://www.uky.edu/\~gmswan3/EDC608/Kalyuga2007\_Article\_ExpertiseReversalEffectAndItsI.pdf](https://www.uky.edu/~gmswan3/EDC608/Kalyuga2007_Article_ExpertiseReversalEffectAndItsI.pdf)  
26. Expertise reversal effect \- Wikipedia, [https://en.wikipedia.org/wiki/Expertise\_reversal\_effect](https://en.wikipedia.org/wiki/Expertise_reversal_effect)  
27. AI-Generated Traces for Novice Programmers: Learning Effects and Learner Differences in a Multi-Institutional Study \- arXiv, [https://arxiv.org/html/2606.03288v1](https://arxiv.org/html/2606.03288v1)  
28. Worked-example effect \- Wikipedia, [https://en.wikipedia.org/wiki/Worked-example\_effect](https://en.wikipedia.org/wiki/Worked-example_effect)  
29. When to Use Manual Code Review Over Automation, [https://www.augmentcode.com/guides/when-to-use-manual-code-review-over-automation](https://www.augmentcode.com/guides/when-to-use-manual-code-review-over-automation)  
30. Rethinking Code Review in the Age of AI: A Vision for Agentic Code Review \- arXiv, [https://arxiv.org/pdf/2605.17548](https://arxiv.org/pdf/2605.17548)  
31. Automatic Bias Detection in Source Code Review \- arXiv, [https://arxiv.org/html/2504.18449v1](https://arxiv.org/html/2504.18449v1)  
32. The Productivity-Reliability Paradox: Specification-Driven Governance for AI-Augmented Software Development \- arXiv, [https://arxiv.org/html/2605.01160v1](https://arxiv.org/html/2605.01160v1)  
33. Th Ethics of AI Code Review | The Qodana Blog, [https://blog.jetbrains.com/qodana/2026/03/ethics-of-ai-code-review/](https://blog.jetbrains.com/qodana/2026/03/ethics-of-ai-code-review/)  
34. Manual vs Automated Code Review 2025: Which Delivers Better Security and Quality?, [https://deepstrike.io/blog/manual-vs-automated-code-review](https://deepstrike.io/blog/manual-vs-automated-code-review)  
35. Trust Me, I Know This Function: Hijacking LLM Static Analysis using Bias \- NDSS Symposium, [https://www.ndss-symposium.org/wp-content/uploads/2026-f2066-paper.pdf](https://www.ndss-symposium.org/wp-content/uploads/2026-f2066-paper.pdf)  
36. Trust Me, I Know This Function: Hijacking LLM Static Analysis using Bias, [https://www.ndss-symposium.org/ndss-paper/trust-me-i-know-this-function-hijacking-llm-static-analysis-using-bias/](https://www.ndss-symposium.org/ndss-paper/trust-me-i-know-this-function-hijacking-llm-static-analysis-using-bias/)  
37. Trust Me, I Know This Function: Hijacking LLM Static Analysis using Bias \- arXiv, [https://arxiv.org/html/2508.17361v2](https://arxiv.org/html/2508.17361v2)  
38. Static Code Analysis \- what is it? \- CodeScene, [https://codescene.com/blog/what-is-a-static-code-analysis](https://codescene.com/blog/what-is-a-static-code-analysis)  
39. The Role of Cognitive Abilities in Requirements Inspection: Comparing UML and Textual Representations Research supported by Grant PID2022-137846NB-I00, funded by MCIN/AEI/10.13039/501100011033 and by ERDF A way of making Europe. The authors would like to thank all the participants of the study. \- arXiv, [https://arxiv.org/html/2601.16009v1](https://arxiv.org/html/2601.16009v1)  
40. On Empirical Comparison of Checklist-based Reading and Adhoc Reading for Code Inspection \- ResearchGate, [https://www.researchgate.net/publication/262981901\_On\_Empirical\_Comparison\_of\_Checklist-based\_Reading\_and\_Adhoc\_Reading\_for\_Code\_Inspection](https://www.researchgate.net/publication/262981901_On_Empirical_Comparison_of_Checklist-based_Reading_and_Adhoc_Reading_for_Code_Inspection)  
41. On Empirical Comparison of Checklist-based Reading and Adhoc Reading for Code Inspection \- International Journal of Computer Applications, [https://research.ijcaonline.org/volume87/number1/pxc3893251.pdf](https://research.ijcaonline.org/volume87/number1/pxc3893251.pdf)  
42. How Perspective-Based Reading Can Improve Requirements Inspections, [https://www.computer.org/csdl/magazine/co/2000/07/r7073/13rRUygT7dA](https://www.computer.org/csdl/magazine/co/2000/07/r7073/13rRUygT7dA)  
43. The Empirical Investigation of Perspective-Based Reading \- ResearchGate, [https://www.researchgate.net/publication/220277633\_The\_Empirical\_Investigation\_of\_Perspective-Based\_Reading](https://www.researchgate.net/publication/220277633_The_Empirical_Investigation_of_Perspective-Based_Reading)  
44. Understanding Perspective-Based Reading | PDF | Cognitive Science \- Scribd, [https://www.scribd.com/document/77541792/PBR-Abstract](https://www.scribd.com/document/77541792/PBR-Abstract)  
45. Empirical Investigation of Perspective-based Reading: A Replicated Experiment, [https://www.researchgate.net/publication/259240755\_Empirical\_Investigation\_of\_Perspective-based\_Reading\_A\_Replicated\_Experiment](https://www.researchgate.net/publication/259240755_Empirical_Investigation_of_Perspective-based_Reading_A_Replicated_Experiment)  
46. An Experimental Comparison of Checklist-Based Reading and Perspective-Based Reading for UML Design Document Inspection, [https://sel.ist.osaka-u.ac.jp/lab-db/betuzuri/archive/380/380.pdf](https://sel.ist.osaka-u.ac.jp/lab-db/betuzuri/archive/380/380.pdf)  
47. Analyzing Requirements \- Qualitest, [https://www.qualitestgroup.com/insights/white-paper/analyzing-requirements/](https://www.qualitestgroup.com/insights/white-paper/analyzing-requirements/)  
48. NRevisit: A Cognitive Behavioral Metric for Code Understandability Assessment \- arXiv, [https://arxiv.org/html/2504.18345v1](https://arxiv.org/html/2504.18345v1)  
49. NRevisit: A Cognitive Behavioral Metric for Code Understandability Assessment \- arXiv, [https://arxiv.org/pdf/2504.18345](https://arxiv.org/pdf/2504.18345)  
50. Prediction in reading: A review of predictability effects, their theoretical implications, and beyond \- PMC, [https://pmc.ncbi.nlm.nih.gov/articles/PMC12092549/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12092549/)  
51. Production training and contextual similarity hurt the comprehension of new vocabulary \- NSF Public Access Repository, [https://par.nsf.gov/servlets/purl/10618345](https://par.nsf.gov/servlets/purl/10618345)  
52. Using the Socratic Method In Your Classroom \- Edutopia, [https://www.edutopia.org/article/using-socratic-method-your-classroom/](https://www.edutopia.org/article/using-socratic-method-your-classroom/)  
53. How to Help Someone with Their Code Using the Socratic Method \- freeCodeCamp, [https://www.freecodecamp.org/news/how-to-help-someone-with-their-code-using-the-socratic-method/](https://www.freecodecamp.org/news/how-to-help-someone-with-their-code-using-the-socratic-method/)  
54. The Socratic Method in Coding Education: Unlocking Deeper Understanding Through Questioning \- AlgoCademy, [https://algocademy.com/blog/the-socratic-method-in-coding-education-unlocking-deeper-understanding-through-questioning/](https://algocademy.com/blog/the-socratic-method-in-coding-education-unlocking-deeper-understanding-through-questioning/)  
55. LLM's are so much better when instructed to be socratic. : r/PromptEngineering \- Reddit, [https://www.reddit.com/r/PromptEngineering/comments/1re707k/llms\_are\_so\_much\_better\_when\_instructed\_to\_be/](https://www.reddit.com/r/PromptEngineering/comments/1re707k/llms_are_so_much_better_when_instructed_to_be/)  
56. Socratic Human Feedback (SoHF): Expert Steering Strategies for LLM Code Generation \- Amazon Science, [https://assets.amazon.science/bf/d7/04e34cc14e11b03e798dfec53e5a/socratic-human-feedback-sohf-expert-steering-strategies-for-llm-code-generation.pdf](https://assets.amazon.science/bf/d7/04e34cc14e11b03e798dfec53e5a/socratic-human-feedback-sohf-expert-steering-strategies-for-llm-code-generation.pdf)  
57. Conventional Comments, [https://conventionalcomments.org/](https://conventionalcomments.org/)  
58. Code Review Checklist and Anti-Pattern Catalog: A Reviewer's Reference for Modern and AI-Augmented Codebases | hidekazu-konishi.com, [https://hidekazu-konishi.com/entry/code\_review\_checklist\_and\_antipatterns.html](https://hidekazu-konishi.com/entry/code_review_checklist_and_antipatterns.html)  
59. Automating Code Review with Gemini CLI: Evidence-Based Patterns and Real Tradeoffs, [https://geminicli.one/blog/gemini-cli-code-review](https://geminicli.one/blog/gemini-cli-code-review)  
60. Build a Code Review Process That Handles 10x More PRs \[2026\] \- Qodo, [https://www.qodo.ai/blog/code-review-process/](https://www.qodo.ai/blog/code-review-process/)  
61. Code Review Examples: Before-and-After Walkthroughs, [https://www.augmentcode.com/guides/code-review-examples-before-and-after-walkthroughs](https://www.augmentcode.com/guides/code-review-examples-before-and-after-walkthroughs)  
62. Impact of an LLM-based Review Assistant in Practice: A Mixed Open-/Closed-source Case Study | IEEE Journals & Magazine, [https://ieeexplore.ieee.org/document/11393512/](https://ieeexplore.ieee.org/document/11393512/)  
63. Impact of LLM-based review comment generation in practice: A mixed open-/closed-source user study \- Mozilla Foundation, [https://www.mozillafoundation.org/en/research/library/impact-of-llm-based-review-comment-generation-in-practice-a-mixed-open-closed-source-user-study/](https://www.mozillafoundation.org/en/research/library/impact-of-llm-based-review-comment-generation-in-practice-a-mixed-open-closed-source-user-study/)