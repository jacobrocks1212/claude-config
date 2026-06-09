# **Advanced Multi-Agent Pipeline Architectures for Automated Code Review**

## **Executive Summary**

The transition of automated code review systems from monolithic, deterministic static analysis toward dynamic, multi-agent cognitive architectures represents a fundamental paradigm shift in software engineering automation. This report provides a rigorous architectural evaluation of a proposed multi-agent Large Language Model (LLM) pipeline intended to review pull requests within a substantial monorepo environment, comprising a C\#.NET backend and a Vue 2.7/TypeScript frontend with approximately 500,000 lines of code. The objective of this evaluation is to establish the optimal design patterns, orchestration mechanics, and human-in-the-loop calibration strategies required to execute investigation-level code analysis, triage-driven prioritization, and seamless iterative re-reviews.

The analysis indicates that the proposed "v2" architecture—which implements a sequential pipeline moving from a Journey Agent to a Triage Agent, followed by parallel Investigation Agents and a Sweeper—represents a vast improvement over the purely rule-based parallel scanning of the "v1" system. The v2 model correctly identifies that modern code review must function as a decision and validation layer rather than a mere commenting automaton.1 However, the proposed sequential orchestration pattern introduces profound systemic vulnerabilities, particularly concerning context degradation, cascading triage failures, and exponential token cost scaling across a sprawling legacy codebase.2

Extensive evaluations of state-of-the-art multi-agent systems, including architectures utilized by CodeRabbit, Qodo Merge, OpenHands, and academic frameworks like CONSENSAGENT, demonstrate that purely linear workflows concentrate catastrophic risk at stage boundaries. If the Triage Agent hallucinates or misinterprets the blast radius of a C\# interface modification, the downstream Investigation Agents inherit this poisoned context, leading to superficial reviews of critical vulnerabilities.2 To mitigate this, the architecture must transition from a strict sequential pipeline to a Hierarchical Coordinator model, where a central planning layer actively manages task decomposition and validates agent outputs.6

Furthermore, the operational mechanics of codebase exploration require immediate revision. Granting Investigation Agents unrestricted read access to a 500,000-line repository via text-based search utilities virtually guarantees context collapse and token exhaustion. The current frontier of agentic code exploration relies on structural indexing. By integrating Abstract Syntax Tree (AST) parsers, such as Tree-Sitter, exposed to the agents via the Model Context Protocol (MCP), the system can execute graph-native queries. This approach reduces token consumption by an order of magnitude while radically improving the agent's comprehension of cross-file dependencies.8

Iterative re-reviews introduce another layer of complexity. As the Journey file accumulates state across multiple commits, the context window scales quadratically, threatening response latency and API budgets. Implementing context condensation algorithms transforms this scaling from quadratic to linear, preserving essential task variables while summarizing historical dialogue.3 Additionally, continuous calibration of the system's YAML rule weights must utilize an Exponential Moving Average (EMA) to ensure the framework rapidly adapts to evolving team standards, suppressing outdated false positives and avoiding the mathematical stagnation inherent in simple running averages.11

The findings synthesized in this report compel a strategic restructuring of the v2 pipeline into a "v2.1" configuration. This optimized architecture leverages deterministic code health heuristics for triage override, specialized sub-agents for domain-specific investigation, and rigorous verification loops to combat multi-agent sycophancy.

## **Per-Research-Area Findings**

### **1\. Multi-Agent LLM Pipeline Orchestration**

The orchestration of multiple LLM agents dictates the fundamental reliability and scalability of the entire code review pipeline. The landscape of LLM-powered agents has transformed from isolated, task-specific deployments to complex ecosystems of collaborating entities, mirroring the evolution of distributed computing architectures.13

Current production systems predominantly utilize three core architectural patterns for multi-agent orchestration, each carrying distinct operational trade-offs regarding latency, predictability, and failure isolation.

| Architecture Pattern | Execution Mechanism | Primary Strengths | Inherent Vulnerabilities | Optimal Application in Code Review |
| :---- | :---- | :---- | :---- | :---- |
| **Sequential Pipeline** | Output from Agent A becomes the unadulterated input for Agent B, moving linearly.14 | Simple traceability; deterministic execution paths; easy to debug individual stage transformations.2 | Boundary risk; upstream hallucinations or context drops irrevocably poison all downstream tasks.2 | Parsing raw DevOps API data; basic linting sweeps; deterministic ETL operations.14 |
| **Hierarchical (Hub-and-Spoke)** | A central Orchestrator (Planner) delegates isolated subtasks to specialized worker agents, aggregating the results.2 | High fault tolerance; isolates hallucinations to specific branches; allows heterogeneous model selection based on task complexity.6 | Increased system latency due to constant round-trips to the central coordinator; the orchestrator becomes a computational bottleneck.2 | Deep codebase investigation; triage validation; coordinating multiple domain specialists (Security, Architecture).6 |
| **Peer-to-Peer (Swarm / Debate)** | Agents interact directly without a central controller, negotiating and passing messages autonomously.2 | Excellent for exploratory problem-solving and self-correction through adversarial debate.5 | Highly unpredictable execution paths; high risk of "sycophancy" where agents blindly reinforce each other's errors.2 | Resolving ambiguous architectural patterns; generating consensus on complex refactoring strategies.5 |

The proposed v2 architecture inherently relies on a Sequential Pipeline model. While this linear flow (Understand → Prioritize → Investigate) appears logical, production analyses of frameworks like Google's Agent Development Kit (ADK) and AutoGen demonstrate that this pattern struggles with complex software engineering tasks.13 Advanced systems, such as OpenHands and SWE-Agent, overcome these limitations by utilizing a compound AI system architecture featuring a dual-agent structure that strictly separates planning from execution.16

To optimize the v2 pipeline, the orchestration must shift toward a Hierarchical model. The Journey Agent should be elevated to a "Planner" status, powered by Claude Opus. Rather than simply passing a static document to the Triage Agent, the Planner must dynamically delegate tasks, evaluate the output of the Triage Agent against the original PR objectives, and orchestrate the parallel Investigation Agents via a divide-and-conquer strategy.7 Furthermore, context passing between agents must abandon raw, full-context handoffs in favor of adaptive context compaction, progressively summarizing older observations to prevent reasoning degradation.16

### **2\. LLM-Based Code Review Systems**

The application of Large Language Models to automated code review has rapidly matured, evolving from basic semantic commenting tools into comprehensive platforms that integrate directly with CI/CD workflows and version control systems. Industry-leading platforms such as CodeRabbit, Qodo Merge, and Calimero demonstrate that effective code review requires a fusion of high-level strategic planning and granular, localized code analysis.1

A critical differentiation among modern code review systems is how they distinguish actionable, high-value findings from trivial noise. CodeRabbit achieves a high signal-to-noise ratio through a methodology termed "context engineering." Rather than analyzing a code diff in isolation, the system retrieves the entire repository history, prior pull requests, and architectural patterns, filtering and organizing this information before presenting it to the reasoning model.19 Qodo Merge similarly emphasizes that PR reviews must function as an executable policy decision layer rather than a commenting bot, requiring full codebase context to enforce organizational standards systematically.1

The architectural configuration of these systems heavily influences model selection. It is economically and computationally inefficient to route every task to a frontier model. CodeRabbit addresses this by utilizing a dual-model approach. Claude Opus acts as the strategic planner, conducting cross-file reasoning and determining missing architectural context. Conversely, Claude Haiku is deployed for granular, lower-complexity tasks, such as context distillation and scanning trivial files, resulting in substantial cost reductions while maintaining review quality.6

Another vital pattern is the deployment of consensus-based scoring mechanisms. The Calimero AI Code Reviewer mitigates false positives by running 2 to 5 specialized LLM agents in parallel (e.g., focusing on security, performance, or logic). Findings are only surfaced if a weighted majority of agents agree, ensuring that isolated hallucinations are suppressed before reaching the end user.18

For the proposed pipeline, it is imperative to adopt a multi-model orchestration strategy. The Sweep Agent should utilize Claude Sonnet or Haiku to enforce the 100 YAML rules on non-critical files, while the Investigation Agents utilize Opus for deep architectural validation.6 Additionally, implementing a consensus layer among the Investigation Agents will drastically reduce the noise commonly associated with automated review outputs, ensuring only high-confidence vulnerabilities are synthesized into the final markdown review.15

### **3\. Triage and Criticality Classification**

Accurate triage and criticality classification serve as the fulcrum of an efficient multi-agent code review pipeline. If the system cannot reliably distinguish between a superficial CSS change and a foundational modification to a C\# database context, it will inevitably misallocate computational resources, leading to bloated API costs and inadequate scrutiny of severe vulnerabilities.

State-of-the-art triage mechanisms have moved beyond purely semantic LLM classification. Relying solely on a language model to read a diff and estimate its "blast radius" is highly unreliable, as LLMs struggle with multi-step logical traversals across undocumented dependencies. Recent research introduces frameworks that combine semantic understanding with quantitative code health metrics to construct a robust routing signal.4

The "Triage" framework evaluates code health sub-factors—such as cyclomatic complexity, component coupling, and historical churn—prior to LLM invocation. These deterministic metrics accurately indicate software maintainability and dependency weight. The evaluation establishes a mathematical condition: tier-dependent asymmetry demonstrates that medium-tier LLMs (e.g., Claude Sonnet) perform adequately on healthy, loosely coupled code, whereas frontier models (e.g., Claude Opus) are strictly required for highly complex, degraded, or tightly coupled legacy components.4

For the 500,000-line monorepo, estimating the blast radius requires structural analysis. Tools like Greptile construct a repository-wide dependency graph to capture how changes propagate across modules and services.23 The deterministic TypeScript prep script in the v2 architecture must be enhanced to parse the Abstract Syntax Tree (AST) of the modified files. By calculating the number of downstream dependents, interface implementations, and cross-project references, the script can generate a definitive blast radius score.

This deterministic score must be fed into the Triage Agent alongside the PR's semantic objectives. The system must enforce heuristic thresholds: if a code change exhibits a high blast radius or touches historically vulnerable modules, the system must automatically escalate the file to the Investigation tier, overriding any semantic assessment that might classify the PR as a "skim" task.4 This hybrid approach—combining LLM semantic comprehension of the PR's intent with deterministic structural gravity—ensures flawless resource allocation.

### **4\. Investigation-Depth Review with Codebase Exploration**

Providing LLM agents with the capability to autonomously explore a large codebase is fraught with inefficiencies. Traditional text-based exploration strategies, where an agent utilizes tools to read raw files, list directory contents, and execute grep searches, scale poorly. These methods consume hundreds of thousands of tokens per session as the agent blindly navigates through files, lacking any inherent structural understanding of the software architecture.8

The structural mismatch between how LLMs process unstructured text and how compilers understand code necessitates a shift toward graph-native exploration. The most effective methodology for grounding LLM agents in a sprawling codebase utilizes Abstract Syntax Trees (AST) via tools like Tree-Sitter, exposed through the Model Context Protocol (MCP).8

Systems implementing this architecture, such as Codebase-Memory, construct a persistent knowledge graph of the repository. Rather than reading raw text, agents execute semantic and structural queries. They can identify symbol usages, traverse call graphs, execute impact analyses, and discover module boundaries natively.8 Empirical evaluations across real-world repositories demonstrate that Tree-Sitter-backed agents achieve higher answer quality regarding structural codebase questions (83% versus 92% for baseline) while consuming ten times fewer tokens and executing half the number of tool calls compared to traditional file-exploration agents.8

Retrieval-Augmented Generation (RAG) approaches present another avenue for context gathering, utilizing vector databases to retrieve relevant historical comments and codebase snippets.26 However, applying RAG to code review requires caution. While retrieval augmentation improves feedback relevance for larger models (increasing alignment scores by 17.9% at a retrieval depth of k=3), smaller models frequently suffer from "context collapse," where excessive retrieved context paradoxically degrades reasoning accuracy.26

To prevent Investigation Agents from deviating on tangents within the C\# and Vue monorepo, the v2 pipeline must revoke broad, unstructured read access. Instead, provide the Opus agents with a curated toolset interfacing with a Tree-Sitter MCP server. Agents must explore the repository by querying repo.find\_symbol\_usages or repo.get\_file\_tree to map dependencies structurally before requesting specific code snippets.9 This structural grounding prevents token exhaustion and ensures that proposed architectural alternatives are strictly validated against the repository's actual dependency graph.

### **5\. Calibration Against Human Feedback**

Continuous calibration of the automated review system against human developer feedback is essential to prevent "alert fatigue" and ensure the pipeline's YAML rule weights accurately reflect the engineering team's current standards. The primary obstacle in this calibration process is the "matching problem"—determining whether an automated finding and a human reviewer's comment refer to the identical underlying issue when expressed in fundamentally different vocabularies.27

Traditional string comparison techniques and Levenshtein distances are inadequate for identifying semantic equivalence in software engineering discourse. Advanced calibration frameworks deploy natural language processing techniques, specifically Sentence Transformers, Universal Sentence Encoders, and LLM-based judges, to assess argument alignment and semantic similarity.27

Furthermore, assessing algorithmic similarity requires moving beyond surface-level syntax. Methodologies like BehaveSim measure algorithmic similarity by evaluating Problem-Solving Trajectories (PSTrajs)—the sequence of intermediate solutions generated during execution. By utilizing dynamic time warping (DTW) to quantify the alignment between these trajectories, systems can confirm whether an LLM's suggested refactor addresses the same logical flaw identified by a human, even if the implementation syntax diverges entirely.30

Once a match between an AI finding and human feedback is confirmed (e.g., a human developer accepts, modifies, or explicitly rejects a rule violation), the system must adjust the relevance weight of that specific YAML rule. The integration of an Exponential Moving Average (EMA) algorithm is paramount for this weight convergence.

Unlike a simple running average, which treats all historical data points equally, an EMA applies a mathematically exponential decay to older data, heavily prioritizing the most recent feedback.12 In machine learning training dynamics, EMA naturally reduces stochastic noise and introduces implicit regularization.11 Applied to code review calibration, EMA ensures that if a team suddenly deprecates a legacy coding pattern, the system's weights will rapidly converge to reflect this new standard within a minimal number of data points, rather than being perpetually dragged down by years of obsolete historical acceptance.12

### **6\. Re-Review and Incremental Review Patterns**

The lifecycle of a pull request is highly iterative. Developers push continuous commits in response to review feedback, requiring the automated system to conduct subsequent re-reviews. Analyzing these iterations using a naive "diff-of-diffs" approach or, conversely, triggering a full re-analysis of the entire PR upon every commit, is computationally wasteful and degrades the user experience by resurfacing previously dismissed comments.18

Modern code review platforms manage incremental reviews by establishing a persistent state machine that tracks finding resolution status. Systems like Calimero and Qodo Merge utilize delta tracking to classify findings across pushes dynamically as *New*, *Fixed*, or *Open*.18 They employ convergence logic that halts the review process entirely when findings stabilize, preventing infinite evaluation loops.18 Qodo explicitly supports an incremental review mode that isolates changes introduced since the last review, enabling iterative development without loss of broader context.32

A critical phenomenon in iterative LLM code generation and review is the Debugging Decay Index (DDI). Mathematical frameworks analyzing LLM self-debugging reveal a predictable exponential decay pattern: models lose 60% to 80% of their debugging and reasoning capabilities within just 2 to 3 iterative attempts.33 If an automated agent continuously debates a developer over a specific line of code across multiple commits, its feedback will rapidly degrade in coherence and relevance, contributing to "AI feedback rot" and severely impacting the developer's trust in the system.33

To support first-class re-reviews, the v2 architecture's Journey Agent must function as the definitive state manager. It must maintain an immutable registry of all surfaced findings and their current resolution status. During a re-review, the pipeline should selectively route only the modified AST nodes to the Investigation Agents. Crucially, the system must incorporate a DDI-informed circuit breaker: if a specific finding remains unresolved or is actively disputed by the developer after three distinct PR iterations, the automated system must autonomously silence the rule for that specific PR and explicitly flag the thread for senior human intervention.33

### **7\. Large File Review Strategies**

Reviewing modifications within massive files—such as monolithic C\# controllers or expansive Vue components exceeding 10,000 lines—presents severe challenges for LLM context windows. While modern frontier models support context lengths exceeding 200,000 tokens, injecting an entire massive file into the prompt degrades reasoning performance through the "lost in the middle" phenomenon and incurs prohibitive per-turn API costs.35

Two primary strategies dominate the industry for handling massive files in automated code review: Sliding Window Chunking and Context Distillation.

| Large File Strategy | Execution Methodology | Key Advantages | Technical Limitations |
| :---- | :---- | :---- | :---- |
| **Sliding Window Chunking** | The text is divided into fixed-size windows (e.g., 500 words) with overlapping boundaries (e.g., 100 words) to maintain sequential continuity.36 | Ensures no discrete logic is missed at chunk boundaries; mathematically simple to implement via token counting.36 | Blind to logical code structures (classes, functions); may split a critical algorithm across two chunks, destroying semantic meaning. |
| **Context Distillation** | A faster, highly efficient model (e.g., Claude Haiku) parses the entire file structurally, extracting only the specific functions relevant to the diff and mapping their local dependencies.6 | Preserves exact structural logic; radically reduces the token payload sent to the primary reasoning model; eliminates irrelevant noise.6 | Requires an orchestration layer to manage the sub-agent handoffs; slightly higher initial system latency. |

For the proposed codebase, relying on sliding window chunking for complex C\# backend logic is insufficient, as the overlap may fail to capture distributed class state variables. The optimal strategy is Context Distillation. When the Triage Agent identifies that a modified file exceeds a predefined token threshold, it should invoke a Context Distiller sub-agent powered by Claude Haiku.6

This sub-agent utilizes the Tree-Sitter AST to locate the specific modified functions and extracts them along with their immediate callers, callees, and class-level variable definitions. This highly concentrated, structurally coherent code snippet is then passed to the Claude Opus Investigation Agent. By executing context engineering proactively, the architecture ensures that the frontier model applies its advanced reasoning solely to the highest-signal data, maintaining both extreme accuracy and cost efficiency across massive codebases.19

### **8\. Prompt Engineering for Code Review Agents**

The quality of an automated code review is inextricably linked to the structural rigor of its underlying prompts. The inherent asymmetry in Large Language Models—whereby they are measurably superior at verifying and analyzing existing content than they are at generating perfect novel solutions—forms the basis of advanced prompt engineering for code review.37

This "Solver-Verifier Gap" dictates that prompts should not simply demand a zero-shot review. Instead, they must enforce a cyclical "Generate → Review → Refine" verification loop within the prompt itself. The model must be instructed to generate an initial hypothesis regarding a code defect, and then immediately act as a distinct verifier (e.g., a compiler or static analyzer) to validate its own hypothesis against the provided codebase context.37

The utilization of precise personas significantly enhances this process. Generic personas degrade review quality, while hyper-specific personas grounded in the repository's technology stack yield superior results. Prompts should explicitly define the agent's role, constraints, and objective framework (e.g., "You are a Principal.NET Security Architect auditing this C\# implementation against enterprise zero-trust directives").38

Furthermore, incorporating few-shot examples into the agent prompts is critical for aligning the LLM with the monorepo's specific idiosyncrasies. Providing 3 to 5 concrete examples of historical pull requests—demonstrating exact input-output pairs of how the team prefers to resolve specific YAML rule violations—anchors the model's pattern recognition, reducing theoretical hallucinations and driving actionable, highly relevant feedback.38

In multi-agent configurations, prompt engineering must directly combat "sycophancy," a phenomenon where agents superficially agree with one another to rapidly achieve consensus, bypassing rigorous critical debate. Frameworks such as CONSENSAGENT demonstrate that prompts must be dynamically refined during agent interactions, explicitly instructing agents to demand evidentiary proof from their peers and mathematically penalizing premature agreement without structural validation.5 For the Investigation Agents, prompts must strictly mandate that all proposed architectural alternatives be validated against the AST knowledge graph before being submitted to the Synthesizer.

## **Specific Question Answers**

### **1\. Pipeline failure handling**

**Question:** *In a 5-phase sequential pipeline, if Phase 3 (triage) produces poor classification, it cascades through investigation and sweep. What circuit-breaker or self-correction patterns exist for multi-agent pipelines?*

Sequential pipelines inherently concentrate critical risk at phase boundaries; an undetected error or hallucination in an upstream agent irrevocably toxifies all downstream processes.2 To prevent a triage failure from cascading, the architecture must implement a **Verification Loop** acting as a circuit breaker.37 This requires shifting from a pure pipeline to a hierarchical orchestration model where a central Planner oversees the stage transitions.7

The primary circuit-breaker pattern involves cross-referencing semantic LLM outputs with deterministic heuristics.4 If the Triage Agent classifies a pull request modifying 40 core interface files as a "skim" task, the Planner agent must evaluate this classification against the deterministic AST blast radius generated by the prep script. Upon detecting this mathematical anomaly, the Planner triggers a circuit breaker, halting the pipeline progression. It then executes a self-correction loop, re-prompting the Triage Agent with the conflicting deterministic data and forcing a reassessment, or autonomously overriding the classification to ensure critical investigation.24

### **2\. Context compression**

**Question:** *The journey file accumulates across re-reviews. When it gets large, how should it be compressed for injection into agent prompts without losing critical information? Are there proven summarization patterns for this?*

Allowing conversational context to accumulate infinitely across re-reviews results in quadratic token scaling, which drastically inflates API costs, increases latency, and pushes critical task instructions out of the LLM's effective attention window.3 The proven summarization pattern for this issue is **Intelligent Context Condensation**, famously implemented in the OpenHands agent architecture.

As the journey file breaches a predefined token threshold, a condensation protocol is triggered. This pattern does not summarize the text uniformly. Instead, it strictly preserves the most recent exchanges verbatim to maintain immediate conversational continuity. The older history is aggressively compressed into an encoded memory state focusing exclusively on task-relevant vectors: *User Goals* (the ultimate PR objective), *Agent Progress* (resolved YAML rules), *Remaining Tasks*, and *Technical Details* (preserving the exact file paths, critical symbol names, and failing test signatures).3 By amortizing the cost of rebuilding this summarized context across multiple turns via LLM prompt caching, the system converts quadratic context growth into highly efficient linear scaling.3

### **3\. Calibration matching**

**Question:** *When comparing a plugin finding ("prefer abstract class over lambda-based strategy pattern") against a human comment ("this is a funky pattern, could we use an abstract class?"), how can we reliably determine these refer to the same issue? Semantic similarity? File:line matching? Hybrid?*

Determining equivalence between highly structured automated findings and colloquial human developer comments cannot be achieved through basic string comparison or Levenshtein distances.27 The most reliable mechanism is a **Hybrid LLM-as-a-Judge semantic matching system combined with spatial heuristics**.28

The system must first filter the dataset using file and line-number proximity logic to ensure the comments are targeting the same localized code block. Subsequently, the plugin finding and the human comment are passed into a lightweight LLM judge (e.g., Claude Haiku) prompted specifically to evaluate semantic similarity and argument alignment.28 For highly complex architectural debates, the system can utilize logic akin to BehaveSim, analyzing the problem-solving trajectories (PSTrajs) to evaluate if the behavioral intent of both suggestions aligns, thus confirming a match despite severe syntactic divergence.30

### **4\. Investigation agent grounding**

**Question:** *How do we prevent investigation agents from hallucinating alternatives that don't work in the specific codebase? What "grounding" techniques ensure suggestions are validated against real code?*

Investigation agents operating in text-based isolation frequently hallucinate APIs and libraries that do not exist within the local monorepo. To ensure suggestions are valid, agents must be grounded through **Structural Verification** and the **Solver-Verifier Pattern**.8

First, restrict the agent's ability to invent abstractions by exposing an Abstract Syntax Tree (AST) parser via the Model Context Protocol (MCP).8 If an agent intends to suggest an alternative utilizing an existing factory class, it must first execute a find\_symbol query against the Tree-Sitter index to definitively verify the class signature and its accessibility within the current project scope.9 Second, leverage the model's superior verification capabilities by mandating that the agent write a localized mock unit test or compilation check for its proposed alternative before surfacing it to the user.37 This sandbox execution completely eliminates physically impossible hallucinations.41

### **5\. Weight convergence**

**Question:** *With a per-rule weight system updated via running average, how many data points are typically needed for weights to converge to useful values? Should we use exponential moving average instead to weight recent feedback more heavily?*

A Simple Moving Average (SMA) is highly susceptible to historical bias and requires an extensive number of data points to dilute the impact of older, potentially obsolete rule preferences.12 For a code review system, utilizing an **Exponential Moving Average (EMA)** is mathematically and operationally superior.11

EMA applies an exponential decay multiplier to historical data, placing the highest mathematical weight on the most recent human feedback.12 In deep learning optimization, EMA naturally reduces stochastic noise and introduces implicit regularization.11 In the context of rule weights, applying an EMA allows the system to converge rapidly to new useful values—often within just 10 to 15 data points—when a development team organically shifts its coding standards. This ensures the system remains highly responsive to current preferences without requiring manual weight resets or purging the historical database.11

### **6\. Triage accuracy**

**Question:** *If the triage agent misclassifies a critical area as "skim," it gets superficial review. What confidence calibration or validation techniques can improve triage accuracy? Should investigation agents be able to "escalate" a finding from sweep tier?*

Improving triage accuracy requires bridging the gap between semantic intent and structural reality. Confidence calibration must be achieved by integrating **Code Health and Blast Radius Heuristics** into the routing logic.4 Before the LLM makes a classification, deterministic tools must calculate component coupling and historical churn. If the data indicates that the code health requires a high-tier model, this empirical signal must supersede the LLM's semantic confidence score.4

Furthermore, the Sweep Agent must possess explicit **Escalation Rights**. Automated code review platforms routinely utilize multi-stage security gates.24 If the Sweep Agent, while conducting a superficial linting scan on a file classified as "skim," detects a critical security pattern (e.g., hardcoded credentials or an insecure API call), its internal rule-matching engine must trigger an immediate escalation. This circuit breaker dynamically promotes the file to the Investigation tier, ensuring that a triage misclassification does not result in deployed vulnerabilities.43

### **7\. Cost optimization**

**Question:** *The v2 pipeline has more agent calls than v1 (journey \+ triage \+ N investigation \+ sweep \+ synthesizer). What are practical strategies for controlling cost while maintaining quality? Token budgets? Model selection per phase? Caching between re-reviews?*

Cost optimization in a highly active multi-agent pipeline cannot rely solely on arbitrary token budgets, as these prematurely truncate reasoning. The most effective strategies encompass **Multi-Model Routing**, **Context Distillation**, and **Prompt Caching**.3

Implement a rigid model-tiering hierarchy. Reserve the expensive frontier model (Claude Opus) strictly for the Journey orchestration and Investigation specialists, where complex cross-file reasoning is paramount. Delegate the Triage, Sweep, and Synthesizer phases to Claude Sonnet, and utilize Claude Haiku exclusively for reading massive log files and executing Tree-Sitter AST extractions.6 This dual-model approach can reduce costs by nearly 50%.21 Additionally, leverage LLM prompt caching heavily; by setting specific context size breakpoints for the Journey document, the system amortizes the cost of rebuilding the summarized context across the entirety of the re-review iterations.3

### **8\. Agent specialization vs. generalization**

**Question:** *v1 had 6 domain-specialist agents. v2 has investigation agents that are generalists assigned to critical areas. Research on when specialization (expert agents per domain) outperforms generalization (capable agents per task area)?*

Extensive research into multi-agent systems definitively establishes that **specialization outperforms generalization** for complex reasoning and software engineering tasks.7 As task complexity increases, generalist agents suffer from reasoning bottlenecks and instruction fade-out, struggling to balance competing priorities (e.g., security versus performance) within a single context window.7

The optimal approach is a "Divide-and-Conquer" architecture utilizing a task forest structure.7 Instead of assigning a single generalist agent to deeply investigate a critical area, the central orchestrator should spawn temporary, highly specialized sub-agents—such as a Security Specialist, an Architecture Specialist, and a Performance Specialist. These specialists evaluate the same code concurrently from distinct perspectives, utilizing a consensus mechanism to merge their findings, which ensures a broader coverage of issue categories and drastically reduces hallucinatory redundancy.15

### **9\. Evaluation metrics**

**Question:** *How should we measure whether v2 is actually better than v1? Beyond precision/recall of findings vs. human comments, what qualitative metrics matter for code review systems?*

Evaluating an AI coding agent requires transitioning from static benchmarks to operational and behavioral metrics. From a deterministic standpoint, systems should be evaluated using **pass@k**, which measures the probability that the agent generates at least one correctly compiling and test-passing solution within *k* attempts.40

Qualitatively, the impact of the v2 system must be measured using industry-standard Developer Experience (DX) metrics. Key indicators include the **Change Fail Percentage** (the rate at which merged PRs degrade production systems) and the **PR Revert Rate**.44 Furthermore, track the **Debugging Decay Index (DDI)** to evaluate whether the v2 system requires fewer iterative correction attempts than v1 to reach a resolvable state.33 Finally, evaluate Engagement Metrics: analyze the ratio of automated comments that developers actively respond to or implement versus those they silently ignore, providing a true measure of the system's signal-to-noise ratio.45

### **10\. Incremental adoption**

**Question:** *Can we phase the v2 rollout to run v1 and v2 in parallel for comparison, or is the architectural change too fundamental? What A/B testing approaches work for code review tools?*

Despite the fundamental architectural overhaul, parallel execution is entirely viable and highly recommended through a **Shadow Deployment** strategy.46 In a shadow deployment, real-time incoming pull request webhooks trigger both the v1 and v2 pipelines simultaneously.

The v1 pipeline executes normally, posting its review comments directly to the active pull request. The v2 pipeline processes the identical event context but is configured to route its synthesized output to a hidden database or a private Slack channel dedicated to engineering leadership.46 This permits rigorous, head-to-head A/B testing of the systems across live production data—comparing token costs, latency, triage accuracy, and finding validity—without disrupting the engineering team's active workflow or risking development velocity during the evaluation phase.46

## **Recommended Architecture Adjustments**

Synthesizing the exhaustive research on multi-agent LLM orchestration, code health routing, and context engineering, the proposed v2 architecture must be refined to mitigate profound structural vulnerabilities. The transition from deterministic scanning to an investigative cognitive architecture is sound, but its execution mechanics require precise adjustment to prevent cost inflation and context collapse.

### **Revised Architecture (v2.1)**

| Pipeline Stage | Executing Entity | Primary Function and Execution Logic |
| :---- | :---- | :---- |
| **1\. Structural Prep** | Deterministic Script (TypeScript) | Generates AST metrics via Tree-Sitter, calculates dependency blast radius, and tracks PR lifecycle timelines. |
| **2\. Hierarchical Planning** | Journey Agent (Opus) | Acts as the central orchestrator. Maintains the persistent, condensed Journey document and dictates task decomposition based on PR objectives. |
| **3\. Hybrid Triage** | Triage Engine (Sonnet \+ Heuristics) | Routes files mathematically based on the Planner's directives and deterministic AST metrics (overriding semantic analysis when blast radius is critical). |
| **4\. Deep Investigation** | Domain Specialists (Opus) *Supported by* Context Distiller (Haiku) | Specialized parallel agents (e.g., Security, Architecture) utilize MCP to query the AST. Haiku distills files \>10K lines into structural summaries to prevent context bloat. |
| **5\. Superficial Sweep** | Sweep Agent (Sonnet) | Scans non-critical files for YAML violations, retaining the explicit authority to escalate files to Investigation upon detecting hazard patterns. |
| **6\. Verification & Calibration** | Calibration Engine (Deterministic) | Executes a "Hostile Compiler" verification loop. Calculates Exponential Moving Average (EMA) weights against human feedback to ensure dynamic alignment. |
| **7\. Final Synthesis** | Synthesizer Agent (Sonnet) | Deduplicates specialist findings and generates the markdown narrative review. |

### **Core Strategic Adjustments Explained**

1. **Elevation to a Hierarchical Planner:** The linear pipeline concentrates failure risk at the triage boundary.2 By elevating the Journey Agent into a "Hierarchical Planner," the system establishes an overarching coordinator capable of managing task decomposition and validating the progression of the review prior to delegating tasks to specialists.7  
2. **Implementation of Hybrid Triage:** Exclusively relying on an LLM to determine the criticality of a file is highly unreliable.8 Triage must incorporate Tree-Sitter AST heuristics, guaranteeing that high-churn or highly coupled files are mathematically escalated to the Investigation tier regardless of the semantic evaluation.4  
3. **Reintroduction of Specialists via Divide-and-Conquer:** Research confirms that specialized agents outperform generalists in reasoning fidelity.13 The Investigation phase must abandon generalist assignment in favor of spawning highly specialized sub-agents (e.g., Security, Performance) that concurrently analyze critical areas and merge findings via a consensus matrix.15  
4. **Context Distillation for Massive Files:** Providing agents with unstructured read access guarantees token exhaustion.3 For legacy components exceeding 10,000 lines, the system must deploy a Claude Haiku Context Distiller to parse the AST and extract only relevant logic blocks and direct callers, feeding a condensed payload to the Opus models.6

## **Risk Register**

The deployment of the v2 cognitive architecture introduces significant operational and qualitative risks. The following matrix outlines the top five systemic risks, their potential impacts on the monorepo environment, and precise mitigation strategies derived from applied LLM research.

| Risk ID | Risk Description | Primary Impact | Mitigation Strategy |
| :---- | :---- | :---- | :---- |
| **R-01** | **Cascading Triage Failure** The Triage Agent misinterprets a complex structural change, incorrectly classifying a critical architectural modification as a "skim" task, leading to a superficial review.2 | Severe vulnerabilities are merged into the main branch; false sense of security; credibility of the automated system is critically undermined. | Implement Hybrid Triage using deterministic Tree-Sitter AST heuristics to enforce strict mathematical thresholds that unconditionally override semantic triage. Grant Sweep Agents systemic authority to escalate files.4 |
| **R-02** | **Quadratic Context Bloat** Across iterative re-reviews, the persistent Journey file accumulates raw conversational history, exceeding the model's effective context window and degrading reasoning.3 | Exponential API cost inflation; severe latency spikes; the "lost in the middle" attention failure where the LLM forgets primary task objectives. | Deploy an Intelligent Context Condenser algorithm to compress historical iterations into static state variables (Goals, Progress) while retaining only the latest iteration verbatim, enforcing linear token scaling.3 |
| **R-03** | **Sycophancy & Consensus Illusion** In parallel execution, Investigation Agents reinforce each other's hallucinations or defer to aggressive prompts without critically evaluating the codebase.5 | Presentation of highly confident, entirely fabricated architectural recommendations; extensive developer time wasted pursuing impossible APIs. | Integrate anti-sycophancy prompts dynamically during interaction. Enforce a "Solver-Verifier" protocol where agents must explicitly adopt an adversarial persona to structurally validate findings before reaching consensus.5 |
| **R-04** | **Unbounded Token Cost Scaling** Utilizing frontier models (Claude Opus) without strict bounds on codebase exploration leads to rapid depletion of financial API budgets.16 | The automated pipeline becomes financially unviable to operate at scale, forcing a premature shutdown or forced downgrade to inadequate models. | Implement a rigid Multi-Model Tiering strategy. Restrict Opus strictly to orchestration and specialized investigation. Delegate massive file reading and structural distillation exclusively to Claude Haiku.6 |
| **R-05** | **AI Feedback Decay (The DDI Effect)** The system continuously attempts to correct a developer across multiple push iterations, entering a cyclical loop where debugging effectiveness drops exponentially.33 | High PR Revert Rates; developer frustration leading to Alert Fatigue; developers actively bypass or ignore the automated system. | Implement the Debugging Decay Index (DDI) circuit breaker. Track the lifespan of every finding; if unresolved by the 3rd commit iteration, autonomously silence the prompt and flag the issue for mandatory human intervention.33 |

#### **Works cited**

1. How to Build an AI-Powered Pull Request Review That Scales With Development Speed?, accessed May 6, 2026, [https://www.qodo.ai/blog/ai-pull-request-review/](https://www.qodo.ai/blog/ai-pull-request-review/)  
2. Multi-Agent AI Systems: Architecture & Failure Modes | Augment Code, accessed May 6, 2026, [https://www.augmentcode.com/guides/multi-agent-ai-systems](https://www.augmentcode.com/guides/multi-agent-ai-systems)  
3. OpenHands Context Condensensation for More Efficient AI Agents ..., accessed May 6, 2026, [https://openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents](https://openhands.dev/blog/openhands-context-condensensation-for-more-efficient-ai-agents)  
4. Triage: Routing Software Engineering Tasks to Cost-Effective LLM Tiers via Code Quality Signals \- arXiv, accessed May 6, 2026, [https://arxiv.org/html/2604.07494v1](https://arxiv.org/html/2604.07494v1)  
5. CONSENSAGENT: Towards Efficient and Effective Consensus in Multi-Agent LLM Interactions through Sycophancy Mitigation \- ACL Anthology, accessed May 6, 2026, [https://aclanthology.org/2025.findings-acl.1141.pdf](https://aclanthology.org/2025.findings-acl.1141.pdf)  
6. How CodeRabbit built a planning layer on Claude, accessed May 6, 2026, [https://www.coderabbit.ai/blog/how-coderabbit-built-a-planning-layer-on-claude](https://www.coderabbit.ai/blog/how-coderabbit-built-a-planning-layer-on-claude)  
7. AgentGroupChat-V2 : Divide-and-Conquer Is What LLM-Based Multi-Agent System Need, accessed May 6, 2026, [https://arxiv.org/html/2506.15451v1](https://arxiv.org/html/2506.15451v1)  
8. Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP \- arXiv, accessed May 6, 2026, [https://arxiv.org/pdf/2603.27277](https://arxiv.org/pdf/2603.27277)  
9. LLM Best Practices \- kit, accessed May 6, 2026, [https://kit.cased.com/core-concepts/llm-context-best-practices/](https://kit.cased.com/core-concepts/llm-context-best-practices/)  
10. GitHub \- PatWie/polyglot\_ls: An LLM-based LS implementation that makes use of tree-sitter context to perform code actions, accessed May 6, 2026, [https://github.com/PatWie/polyglot\_ls](https://github.com/PatWie/polyglot_ls)  
11. Exponential Moving Average of Weights in Deep Learning: Dynamics and Benefits \- arXiv, accessed May 6, 2026, [https://arxiv.org/html/2411.18704v1](https://arxiv.org/html/2411.18704v1)  
12. Intuitive Explanation of Exponential Moving Average | Towards Data Science, accessed May 6, 2026, [https://towardsdatascience.com/intuitive-explanation-of-exponential-moving-average-2eb9693ea4dc/](https://towardsdatascience.com/intuitive-explanation-of-exponential-moving-average-2eb9693ea4dc/)  
13. The Orchestration of Multi-Agent Systems: Architectures, Protocols, and Enterprise Adoption, accessed May 6, 2026, [https://arxiv.org/html/2601.13671v1](https://arxiv.org/html/2601.13671v1)  
14. Multi-Agent Architectures: Patterns Every AI Engineer Should Know \- Medium, accessed May 6, 2026, [https://medium.com/@satvallu/multi-agent-architectures-patterns-every-ai-engineer-should-know-de1544d7ce78](https://medium.com/@satvallu/multi-agent-architectures-patterns-every-ai-engineer-should-know-de1544d7ce78)  
15. MULTI-AGENT SYSTEM FOR AUTOMATED CODE REVIEWS \- Trepo, accessed May 6, 2026, [https://trepo.tuni.fi/bitstream/10024/232334/2/PremasunderaSavidya.pdf](https://trepo.tuni.fi/bitstream/10024/232334/2/PremasunderaSavidya.pdf)  
16. Building AI Coding Agents for the Terminal: Scaffolding, Harness, Context Engineering, and Lessons Learned \- arXiv, accessed May 6, 2026, [https://arxiv.org/html/2603.05344v1](https://arxiv.org/html/2603.05344v1)  
17. OpenHands: An Open Platform for AI Software Developers as Generalist Agents \- arXiv, accessed May 6, 2026, [https://arxiv.org/abs/2407.16741](https://arxiv.org/abs/2407.16741)  
18. calimero-network/ai-code-reviewer \- GitHub, accessed May 6, 2026, [https://github.com/calimero-network/ai-code-reviewer](https://github.com/calimero-network/ai-code-reviewer)  
19. How CodeRabbit delivers accurate AI code reviews on massive codebases, accessed May 6, 2026, [https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases](https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases)  
20. The Qodo Code Review experience \- Qodo Documentation, accessed May 6, 2026, [https://docs.qodo.ai/code-review](https://docs.qodo.ai/code-review)  
21. How we built a cost-effective Generative AI application \- CodeRabbit, accessed May 6, 2026, [https://www.coderabbit.ai/blog/how-we-built-cost-effective-generative-ai-application](https://www.coderabbit.ai/blog/how-we-built-cost-effective-generative-ai-application)  
22. How Multi-Agent Consensus Makes Security Audits More Reliable \- DEV Community, accessed May 6, 2026, [https://dev.to/ecap0/how-multi-agent-consensus-makes-security-audits-more-reliable-1p8m](https://dev.to/ecap0/how-multi-agent-consensus-makes-security-audits-more-reliable-1p8m)  
23. AI Code Review Tools for GitLab Merge Requests \- Panto AI, accessed May 6, 2026, [https://www.getpanto.ai/blog/ai-code-review-tools-gitlab-merge-requests](https://www.getpanto.ai/blog/ai-code-review-tools-gitlab-merge-requests)  
24. What is Automated Code Review? | Tools & Best Practices \- Sonar, accessed May 6, 2026, [https://www.sonarsource.com/resources/library/what-is-automated-code-review/](https://www.sonarsource.com/resources/library/what-is-automated-code-review/)  
25. Designing Effective Tree-sitter Grammars | by Lince Mathew \- Medium, accessed May 6, 2026, [https://medium.com/@linz07m/designing-effective-tree-sitter-grammars-84411ebdf830](https://medium.com/@linz07m/designing-effective-tree-sitter-grammars-84411ebdf830)  
26. Context-Aware Code Review Automation: A Retrieval-Augmented Approach \- MDPI, accessed May 6, 2026, [https://www.mdpi.com/2076-3417/16/4/1875](https://www.mdpi.com/2076-3417/16/4/1875)  
27. Evaluating semantic text similarity using SBERT and NLTK | by Michael Robinson | Medium, accessed May 6, 2026, [https://medium.com/@merobi/evaluating-semantic-text-similarity-using-sbert-and-nltk-18f08e51566d](https://medium.com/@merobi/evaluating-semantic-text-similarity-using-sbert-and-nltk-18f08e51566d)  
28. Beyond Rating: A Comprehensive Evaluation and Benchmark for AI Reviews \- arXiv, accessed May 6, 2026, [https://arxiv.org/html/2604.19502v1](https://arxiv.org/html/2604.19502v1)  
29. Code Comments: A Way of Identifying Similarities in the Source Code \- MDPI, accessed May 6, 2026, [https://www.mdpi.com/2227-7390/12/7/1073](https://www.mdpi.com/2227-7390/12/7/1073)  
30. Rethinking Code Similarity for Automated Algorithm Design with LLMs | OpenReview, accessed May 6, 2026, [https://openreview.net/forum?id=HIUqeO9OOr](https://openreview.net/forum?id=HIUqeO9OOr)  
31. How to Scale Your EMA \- NIPS, accessed May 6, 2026, [https://papers.neurips.cc/paper\_files/paper/2023/file/e7681dd6fe16052433ab68cd1555bdc9-Paper-Conference.pdf](https://papers.neurips.cc/paper_files/paper/2023/file/e7681dd6fe16052433ab68cd1555bdc9-Paper-Conference.pdf)  
32. Preventing outages with Qodo Merge (formerly PR-Agent): AI-powered code reviews, accessed May 6, 2026, [https://www.qodo.ai/blog/preventing-outages-with-qodo-merge-with-ai-powered-code-reviews/](https://www.qodo.ai/blog/preventing-outages-with-qodo-merge-with-ai-powered-code-reviews/)  
33. Measuring and mitigating debugging effectiveness decay in code language models \- PMC, accessed May 6, 2026, [https://pmc.ncbi.nlm.nih.gov/articles/PMC12715212/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12715212/)  
34. AI Code Rot and Its Impact on Code Quality Through the Feedback Loop \- Medium, accessed May 6, 2026, [https://medium.com/@clint360.rebase/ai-code-rot-and-its-impact-on-code-quality-through-the-feedback-loop-98532096bafd](https://medium.com/@clint360.rebase/ai-code-rot-and-its-impact-on-code-quality-through-the-feedback-loop-98532096bafd)  
35. Context Length Guide 2025: Master AI Context Windows for Optimal Performance & Results, accessed May 6, 2026, [https://local-ai-zone.github.io/guides/context-length-optimization-ultimate-guide-2025.html](https://local-ai-zone.github.io/guides/context-length-optimization-ultimate-guide-2025.html)  
36. RAG 2.0 : Advanced Chunking Strategies with Examples. | by Vishal Mysore \- Medium, accessed May 6, 2026, [https://medium.com/@visrow/rag-2-0-advanced-chunking-strategies-with-examples-d87d03adf6d1](https://medium.com/@visrow/rag-2-0-advanced-chunking-strategies-with-examples-d87d03adf6d1)  
37. LLM Verification Loops: Best Practices and Patterns | by Tim Williams | Mar, 2026 | Medium, accessed May 6, 2026, [https://timjwilliams.medium.com/llm-verification-loops-best-practices-and-patterns-07541c854fd8](https://timjwilliams.medium.com/llm-verification-loops-best-practices-and-patterns-07541c854fd8)  
38. How to Prompt LLMs for Better, Faster Security Reviews \- Crash Override, accessed May 6, 2026, [https://crashoverride.com/blog/prompting-llm-security-reviews](https://crashoverride.com/blog/prompting-llm-security-reviews)  
39. Is Your Paper Being Reviewed by an LLM? Benchmarking AI Text Detection in Peer Review \- arXiv, accessed May 6, 2026, [https://arxiv.org/html/2502.19614v3](https://arxiv.org/html/2502.19614v3)  
40. Demystifying evals for AI agents \\ Anthropic, accessed May 6, 2026, [https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)  
41. Auto-review of agent actions without synchronous human oversight \- OpenAI Alignment Blog, accessed May 6, 2026, [https://alignment.openai.com/auto-review/](https://alignment.openai.com/auto-review/)  
42. Moving Average Crossover Strategies: Types, Calculations, Pros & Cons for Trading, accessed May 6, 2026, [https://blog.quantinsti.com/moving-average-trading-strategies/](https://blog.quantinsti.com/moving-average-trading-strategies/)  
43. What is automated code review? Tools and best practices \- Wiz, accessed May 6, 2026, [https://www.wiz.io/academy/application-security/automated-code-review](https://www.wiz.io/academy/application-security/automated-code-review)  
44. Three metrics for measuring the impact of AI on code quality \- DX, accessed May 6, 2026, [https://getdx.com/blog/3-metrics-for-measuring-the-impact-of-ai-on-code-quality/](https://getdx.com/blog/3-metrics-for-measuring-the-impact-of-ai-on-code-quality/)  
45. How to evaluate AI code review tools: A practical framework \- CodeRabbit, accessed May 6, 2026, [https://www.coderabbit.ai/blog/framework-for-evaluating-ai-code-review-tools](https://www.coderabbit.ai/blog/framework-for-evaluating-ai-code-review-tools)  
46. 8 Types of Deployment Strategies (And How Feature Flags Help), accessed May 6, 2026, [https://www.flagsmith.com/blog/deployment-strategies](https://www.flagsmith.com/blog/deployment-strategies)  
47. Model Deployment Strategies: Discover How to Boost your ML Deployment Success | by Juan C Olamendy | Medium, accessed May 6, 2026, [https://medium.com/@juanc.olamendy/model-deployment-strategies-discover-how-to-boost-your-ml-deployment-success-d82b320ac118](https://medium.com/@juanc.olamendy/model-deployment-strategies-discover-how-to-boost-your-ml-deployment-success-d82b320ac118)  
48. Top Deployment Strategies: How to Test and Implement Them \- testRigor, accessed May 6, 2026, [https://testrigor.com/blog/top-deployment-strategies/](https://testrigor.com/blog/top-deployment-strategies/)