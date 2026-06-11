# **System Design for Personalized Interview Preparation via Work Log Synthesis and Large Language Models**

## **Executive Summary**

The paradigm of technical interview preparation is undergoing a fundamental shift. The traditional methodology of rote memorization, characterized by grinding abstract algorithmic puzzles and studying canonical, generalized system design architectures, is increasingly recognized as suboptimal for senior engineering roles. Modern technical interviews demand the strategic articulation of applied, localized engineering experience. This report details the architectural, cognitive, and structural design requirements for a sophisticated Model Context Protocol (MCP) server plugin. The primary objective of this system is to synthesize a software engineer's unstructured, passively captured daily work logs into a highly interconnected, personalized study vault formatted for Obsidian.

Based on an exhaustive analysis of personal knowledge management (PKM) methodologies, cognitive psychology literature, and large language model (LLM) agent architectures, the analysis yields a series of core recommendations for the v2 implementation of this tool. First, the system must establish its cognitive foundation on the Self-Reference Effect (SRE). Empirical evidence from cognitive science demonstrates that encoding complex information in direct relation to personal experience drastically improves memory retention, vividness, and retrieval speed under cognitive load. Consequently, the study materials generated must be deeply grounded in the user's specific commits, planning artifacts, and architectural decisions.

Second, the structural engineering of interview narratives requires domain-specific frameworks. Standard STAR (Situation, Task, Action, Result) frameworks are insufficient for conveying the depth required in senior-level system design interviews. The system must be engineered to generate Architecture Decision Records (ADRs) for distributed systems narratives, and it must utilize an expanded (I)STAR(T) framework (Introduction, Situation, Task, Action, Result, Takeaway) to properly convey trade-offs, bottlenecks, and the technical depth required in behavioral and object-oriented design scenarios.

Third, the data synthesis strategy must embrace a hybrid architecture. While users should retain the option to tag granular work logs at the moment of creation, the system must employ LLM-based post-hoc semantic clustering. This is critical for aggregating granular daily logs into broader "initiatives" or features, particularly when the system is bootstrapping itself by importing existing planning artifacts such as specifications and phased rollouts.

Fourth, the preservation of human-authored data within the generated Obsidian vault is paramount. The vault architecture must utilize a strict "managed block" parsing pattern. To prevent the destructive overwriting of user annotations during continuous LLM regeneration cycles, all programmatically generated content must be confined within explicit delimiters, ensuring that surrounding user text remains untouched and fully preserved.

Finally, regarding the interaction model and execution surface, the latency inherent in correlating extensive work histories with a corpus of 154 canonical knowledge bank topics necessitates asynchronous protocol handling. The FastMCP implementation must aggressively utilize the Model Context Protocol's progress notification specifications. By streaming continuous progress tokens to the Claude Code CLI, the server can prevent timeout failures during massive vault generation and artifact ingestion operations, ensuring a seamless human-in-the-loop experience.

## **Prior Art and Cognitive Foundations**

To effectively design an interview preparation tool that transforms daily engineering logs into a study curriculum, one must first examine the psychological mechanisms of memory retrieval and the current landscape of personal knowledge management systems.

The foundational premise of correlating real work history with interview topics rests entirely on the "Self-Reference Effect" (SRE). Cognitive psychology dictates that information encoded through self-related processing is retained, consolidated, and recollected with significantly higher accuracy than information processed through standard semantic or structural means.1 The SRE activates specific cortical midline structures, most notably the medial prefrontal cortex (MPFC), which promotes the rapid organization and elaboration of memory traces.3

In the high-pressure context of software engineering interviews, candidates who attempt to study abstract system design concepts—such as designing a generalized rate limiter or a globally distributed cache—often struggle to recall nuanced trade-offs when probed by an interviewer. The cognitive load required to construct a hypothetical scenario in real-time frequently leads to failure. Conversely, when these same abstract concepts are mapped directly to the candidate's localized, historical experiences—such as recalling the specific week they implemented a token bucket for their company's authentication service—the mnemonic advantage is profound. SRE disproportionately enhances source memory, specific visual details, and the recall of internal mental operations.4 This translates directly to higher fidelity in technical storytelling, greater credibility during behavioral rounds, and a distinct reduction in interview anxiety.7

Within the realm of Personal Knowledge Management (PKM), the tools currently utilized by software engineers vary widely, but they generally gravitate toward systems that allow for networked thought rather than rigid hierarchical filing. Applications like Notion, Obsidian, and enterprise tools like Guru and Document360 offer varying degrees of flexibility.9 For technical professionals, Obsidian has emerged as a premier choice due to its local-first, markdown-based architecture, which perfectly mirrors standard software development workflows.12 Advanced practitioners within the Obsidian ecosystem favor a "bottom-up" approach to PKM, emphasizing emergent structure, bidirectional linking, and dynamic querying over rigid, predefined folder hierarchies.12

Historically, attempting to synthesize granular daily developer logs into structured documentation has been a manual, high-friction process. However, recent advancements in Large Language Models (LLMs) have enabled new paradigms in log parsing and activity synthesis. Open-source frameworks like GitSage demonstrate the viability of using LLM-driven multi-agent workflows to automatically synthesize developer activity, such as raw git commits, into structured, context-aware artifacts like release notes.14 Similarly, research in mapping unstructured software engineering work to standardized skill taxonomies has shown that LLMs utilizing semantic similarity and Retrieval-Augmented Generation (RAG) can effectively categorize complex technical tasks with a high degree of accuracy.16

Despite these advancements, there is currently no mainstream open-source tool or commercial product that natively and passively correlates localized engineering logs specifically against standard technical interview taxonomies (such as System Design, Object-Oriented Design, and Behavioral frameworks). Existing platforms either function as generalized note-taking apps requiring massive manual curation, or they are automated documentation generators that lack the specific pedagogical structures required for interview preparation. The proposed v2 plugin directly addresses this vacuum by combining the mnemonic power of the Self-Reference Effect with the emergent graph structures of Obsidian and the semantic reasoning capabilities of modern LLMs.

## **Obsidian Vault Design Patterns**

The presentation layer of the synthesized engineering data is an Obsidian-compatible Markdown vault. This vault must be meticulously engineered to serve two distinct, occasionally conflicting, cognitive modes: exploration and drilling. Exploration requires a graph-based topology allowing the user to organically browse connections between their past projects and various architectural concepts. Drilling requires focused, high-repetition exposure to specific narratives and flashcards. Achieving both necessitates a precise topological and programmatic design.

### **Structural Topology and File Organization**

Following established PKM best practices, the vault architecture should actively minimize deep, nested folder hierarchies. Engineering concepts are inherently multi-disciplinary; a single feature deployment might touch upon distributed caching, asynchronous message queues, cross-functional team conflict, and object-oriented factory patterns simultaneously. Forcing such a feature into a single categorical folder destroys its multidimensional value.12

Instead, a flat, tag-driven structure supported by robust metadata is optimal.18 A recommended directory structure segregates files by their structural role rather than their conceptual category, utilizing four primary collections alongside a hidden administrative directory:

| Directory | Primary Function | Content Characteristics |
| :---- | :---- | :---- |
| 01\_Knowledge\_Bank/ | The canonical interview corpus. | Static representations of the 154 YAML topics converted to Markdown. These serve as the gravitational hubs of the vault. |
| 02\_Work\_History/ | Chronological ledger of granular activities. | Daily work logs ingested directly from the JSONL data store. Highly granular, serving as raw evidence. |
| 03\_Features/ | Synthesized initiative-level documents. | Aggregations of daily logs mapping to specific epics or projects, heavily enriched with context imported from SPEC.md files. |
| 04\_Interview\_Stories/ | The primary study artifacts. | LLM-generated narratives that explicitly correlate the Features to specific Knowledge Bank topics. |
| Meta/ | System administration and templating. | Dataview scripts, Obsidian templates, graphical assets, and macro definitions.13 |

### **Metadata Conventions and Dynamic Querying**

To facilitate both the exploration and drilling modes, the vault relies heavily on Obsidian's Dataview plugin, which requires strictly typed, consistent YAML frontmatter across all generated files.18 The programmatic generator must inject standardized metadata to enable dynamic querying, effectively turning the flat markdown files into a highly relational database.13

For a generated Knowledge Bank concept page, the frontmatter schema should look like this:

YAML

\---  
id: sys-design-rate-limiting  
type: concept  
domain: system-design  
difficulty: hard  
correlated\_features:   
  \- "\]"  
  \- "\[\[Feature-API-Gateway-Overhaul\]\]"  
tags:  
  \- interview/system-design  
  \- concept/network-security  
\---

This strict metadata schema allows the generation of dynamic dashboards using Dataview queries. For example, a central System Design Dashboard can execute a query to display a table of all system design topics, sorted by the number of correlated features. This provides the user with an immediate visual representation of their strongest interview subjects (topics with multiple real-world examples) and their weakest areas (topics lacking any grounded experience), allowing them to direct their study time efficiently.18

### **Graph View Physics and Link Optimization**

A common failure mode in programmatically generated Obsidian vaults is the degradation of the Graph View into an unreadable, hyper-connected "hairball." If an LLM is instructed to aggressively cross-reference files, it will indiscriminately link common terms, rendering the visual graph useless for spatial reasoning.13

To optimize the graph, the linking strategy must be hierarchically constrained:

1. **Restrict Granular Linking:** Granular work logs (02\_Work\_History) should only contain outbound links to their parent Feature. They should not link directly to abstract concepts.  
2. **Hub-and-Spoke Topology:** Features (03\_Features) serve as the intermediate nodes. They link outbound to the specific Interview\_Stories generated from them.  
3. **Gravitational Hubs:** The Knowledge Bank topics act as the massive central hubs. All interview stories link inward to these topics.

This directed acyclic graph (DAG) approach ensures that when a user views the graph, they see a clean, structural representation of their career: daily tasks rolling up into major features, which in turn branch out into specific, studyable interview narratives anchored to core computer science concepts.

### **The Managed Block Pattern for User Preservation**

A critical challenge in generating study material programmatically is handling the inevitable vault regeneration. As the user completes more work, the LLM will need to update the correlated stories and dashboards. However, users will naturally open these Markdown files to highlight text, add their own mnemonics, or type out personal reflections. If the MCP tool simply overwrites the file during a /interview-generate execution, all human annotations will be catastrophically lost.

Furthermore, relying on Obsidian's native APIs or community plugins to update specific frontmatter fields programmatically is fraught with risk, as many of these tools are known to destructively reformat YAML and strip out human-written comments without warning.22

To achieve absolute idempotency and preserve user edits, the system must employ the **"Managed Block"** (or protected region) architectural pattern.24 When the FastMCP Python server generates or updates a file, it writes its content strictly inside explicit HTML comment delimiters.

The structure of an interview story file would be:

# **Rate Limiting via Token Bucket**

User's personal thoughts, scratchpad notes, and whiteboard photos go here. These are completely ignored by the generation script.

## **Grounded Experience: Auth Service Migration**

During the authentication service migration, the primary bottleneck identified was the legacy database's inability to handle burst traffic from brute-force login attempts.

**Architectural Decision:**

A Redis-backed token bucket was implemented at the API Gateway level.

* **Tradeoff:** Chose Redis for low-latency atomic operations (INCR) over a relational table, accepting the cost of managing an additional infrastructure dependency.  
  More user annotations or specific flashcards can be placed down here.

During any subsequent regeneration cycles, the Python server reads the file, uses regular expressions or Abstract Syntax Tree (AST) parsing to locate the BEGIN and END delimiters, and replaces only the content existing between them. Everything outside the delimiters is preserved exactly as the user wrote it.26 This pattern is critical for maintaining user trust in an automated system.

## **Engineering the Interview Narrative Formats**

Translating raw, unstructured technical work into compelling, high-signal interview narratives requires domain-specific structural frameworks. A monolithic approach—applying the exact same storytelling template to a behavioral conflict question as to a distributed database scaling question—will result in superficial and unconvincing responses. The LLM prompts responsible for synthesizing the work logs must be strictly instructed to format outputs according to the specific domain of the knowledge bank topic.

### **The Behavioral Domain: Beyond the STAR Method**

The STAR method (Situation, Task, Action, Result) has been the unquestioned industry standard for behavioral interviews for decades.28 However, for senior software engineers interviewing at top-tier technology companies, a rote STAR response frequently feels mechanical, abrupt, and lacking in introspection.30 The standard format often fails to capture the "so what?"—the underlying engineering philosophy or leadership principle the candidate utilized.

For the behavioral domain (e.g., questions regarding team conflict, project failure, or timeline pressure), the system should synthesize logs into the expanded **(I)STAR(T)** or **SHARE** frameworks.30

The generated Markdown template for behavioral stories must enforce the following structure:

* **Introduction:** A one-sentence hook that establishes the overarching theme before diving into the details. (e.g., "While I've navigated several shifting roadmaps, let me share a specific instance where I had to balance accumulating technical debt with a hard product launch deadline.").30  
* **Situation:** The contextual background and the business stakes.  
* **Task:** The specific engineering mandate.  
* **Action:** The execution phase. The LLM must be prompted to prioritize first-person singular pronouns ("I decided," "I orchestrated") over plural ("We built") to ensure the candidate is taking direct ownership of the technical decisions.30  
* **Result:** Quantifiable metrics. The LLM must extract concrete numbers from the work logs whenever possible (e.g., "reduced latency by 40ms," "prevented 3 hours of weekly manual operational toil").  
* **Takeaway / Learnings:** This is the critical addition for senior candidates. The story must conclude with a retrospective insight demonstrating maturity, adaptability, or a shift in engineering philosophy.30

Research indicates that candidates should have 8 to 10 of these deeply prepared stories ready, mapped against common behavioral dimensions such as leadership, navigating ambiguity, managing difficult coworkers, and recovering from production failures.32

### **The System Design Domain: Architecture Decision Records (ADRs)**

Attempting to use a behavioral STAR format for a complex system design interview is a fundamental error. System design interviews do not assess a candidate's ability to recall the "correct" architecture; they assess the candidate's ability to navigate constraints, identify bottlenecks, and articulate the trade-offs of various solutions.34

Therefore, system design narratives must be formatted as **Architecture Decision Records (ADRs)**.36 When the LLM correlates a work feature to a system design topic, it must generate a study artifact structured as an ADR narrative:

* **Context & Constraints:** The business requirement and the specific load constraints that necessitated the design (e.g., handling 10k QPS, read-heavy workload, strict data sovereignty laws).  
* **Baseline Design:** A description of the initial, naive approach or the legacy system that was failing.  
* **Bottleneck Identification:** The specific point of failure at scale (e.g., database lock contention, network I/O saturation, memory exhaustion).36  
* **Decision & Trade-offs:** The architectural pivot (e.g., introducing a Kafka message broker). Crucially, the LLM must explicitly generate the *accepted cost* of this decision (e.g., "We accepted eventual consistency and the operational overhead of maintaining ZooKeeper in exchange for decoupling the ingestion pipeline and ensuring high availability").36  
* **Operational Reality:** Details on how the system was instrumented, monitored, and maintained post-deployment.

This format trains the candidate to speak like an architect, proactively surfacing trade-offs before the interviewer has to ask for them.35

### **The Object-Oriented Design (OOD) Domain**

For OOD topics, the synthesized output must map the user's software modules to canonical design patterns.39 The interview format here relies on translating broad requirements into clean, extensible class structures.

The generated OOD study template should follow:

* **Core Entities:** Identification of the primary objects, actors, and state within the user's specific feature.  
* **Pattern Applied:** Explicit identification of the Gang of Four (GoF) design pattern utilized (e.g., Singleton, Factory Method, Strategy, Observer).40  
* **Extensibility Justification:** How the user's design adhered to SOLID principles, specifically illustrating how the architecture allows for future expansion without necessitating modifications to the core business logic.

### **Narrative Depth and Cognitive Load**

Optimal interview stories must strike a delicate balance regarding detail. A story that is too brief lacks credibility and invites aggressive probing from the interviewer. A story that is overly detailed bogs down the interview, consumes too much of the allotted 45 minutes, and loses the interviewer's attention.

To manage cognitive load, the LLM prompts generating these stories must enforce a strict "Rule of Three." The prompt should instruct the model to identify and articulate a maximum of three core technical challenges or three distinct phases of execution per narrative. This ensures the generated study material remains punchy, digestible, and easy to recall under the stress of a live whiteboard session.

## **Work Log to Feature Synthesis Strategies**

The v1 iteration of this system captures highly granular task completions, resulting in an append-only JSONL log containing individual bug fixes, minor refactors, and specification writing sessions. However, interviews are rarely conducted at the level of a single pull request; they focus on broad initiatives, multi-month epics, and comprehensive "features." Therefore, transforming granular logs into feature-level aggregations is a primary requirement for v2.

### **Evaluation of Synthesis Approaches**

Three distinct architectural approaches present themselves for aggregating granular work logs into coherent feature initiatives:

| Synthesis Approach | Mechanism | Advantages | Disadvantages |
| :---- | :---- | :---- | :---- |
| **A: Tag at Log Time** | The user manually inputs a feature\_id or epic name during their daily logging session. | Ensures 100% deterministic accuracy. Results in clean relational data requiring minimal post-processing. | Imposes high cognitive friction on the user. Engineers frequently address isolated bugs or tech debt without knowing the broader feature context at the time of execution. |
| **B: Post-Hoc LLM Synthesis** | An LLM periodically reads the entire corpus of JSONL entries, utilizing semantic embeddings to cluster related tasks into newly proposed feature groupings. | Zero user friction during daily work. Highly capable of discovering emergent patterns and non-obvious relationships across long time horizons.14 | Prone to miscategorization. If tasks are highly intertwined across microservices, the LLM may create a massive "hairball" cluster, requiring heavy manual review. |
| **C: Hybrid Strategy** | Opportunistic manual tagging when the feature is explicitly known; background LLM semantic clustering for orphaned or untagged logs; periodic user reconciliation. | Balances high accuracy with low daily friction. Seamlessly leverages existing metadata from imported planning artifacts. | Represents the highest architectural complexity. Requires an intermediate data state to handle reconciliations and un-merging of incorrect clusters. |

### **The Recommended Hybrid Architecture**

The **Hybrid Approach (C)** is the definitively superior strategy for a tool designed to operate passively in the background of a senior engineer's workflow.

The workflow operates as follows: When the user utilizes the /interview-import skill to ingest a planning document (such as a SPEC.md or PHASES.md), the FastMCP server parses the document, extracting the title, primary objectives, and phase markers.42 It then establishes a canonical Feature entity within the vault.

As the passive daily logger captures subsequent engineering work, it presents the user with an optional, lightweight contextual hook to tag the log against known Features. If the user skips this step to maintain velocity, the log is stored as an orphaned entry.

Periodically, or upon explicit invocation of the /interview-synthesize skill, the background MCP tool vectorizes the orphaned JSONL logs. It executes an unsupervised clustering algorithm—or a targeted LLM-as-a-judge prompting routine—to map these orphaned logs to the semantic neighborhood of the nearest established Feature.14 This ensures no engineering effort is lost, while avoiding the friction of mandatory daily categorization.

### **Resolving the "Cold Start" Dilemma**

The system context presents a distinct "cold start" problem: the current work log contains only 23 granular entries, yet there are 491 comprehensive planning artifacts available for import. Generating useful study material immediately requires prioritizing these artifacts.

The solution requires a specialized ingestion pipeline. The /interview-import skill must be designed to parse the 491 artifacts using a map-reduce summarization pattern. An LLM pipeline will extract the core architecture, the primary engineering challenges, and the intended outcomes from these raw markdown documents. These condensed summaries will bypass the granular JSONL work log stage entirely and be directly instantiated as fully synthesized Features in the vault. This instantly populates the user's knowledge base with years of high-quality, narrative-ready material, circumventing the sparse daily log data.

## **Topic Correlation Strategy and Quality Control**

Correlating unstructured, highly variable engineering work descriptions to a rigid, structured taxonomy of 154 specific YAML interview topics is a high-dimensional classification challenge.

### **LLM-as-a-Judge vs. Semantic Similarity**

Simple keyword matching is entirely insufficient for software engineering contexts. A developer log mentioning "Redis" could legitimately correlate to Caching Strategies, Rate Limiting, Distributed Locking, Session Management, or Message Queues. Furthermore, standard semantic similarity (e.g., using cosine distance on vector embeddings) captures general conceptual proximity but frequently fails on the specific, instructional nuances required for interview preparation.

The recommended strategy is a two-stage pipeline utilizing an **LLM-as-a-Judge**.44

1. **Candidate Retrieval (Vector Search):** To prevent exorbitant token costs and latency, the system first generates an embedding for the synthesized Feature. It performs a vector search against the 154 Knowledge Bank topics, retrieving only the top 10 most semantically proximate candidates.  
2. **Evaluation Rubric (LLM Judge):** The LLM is then invoked in a pointwise evaluation mode to act as an impartial judge. It evaluates the Feature against each of the 10 candidate topics using a strict, multi-dimensional rubric.48

The prompt rubric provided to the LLM must strictly adhere to three principles of evaluation engineering: Specificity, Measurability, and Independence.50 Vague prompts asking "Is this feature related to the topic?" will result in massive false-positive rates.

**Example LLM-as-a-Judge Rubric for Topic Correlation:**

You are an expert technical interviewer evaluating whether a candidate's project experience demonstrates mastery of a specific architectural concept.

* *Score 0 (Irrelevant):* The feature happens to use the technology, but the core engineering challenge does not map to the topic's principles (e.g., using a Postgres DB to store user configs does not demonstrate mastery of Distributed Database Sharding).  
* *Score 1 (Tangential):* The feature touches on the topic, but the user's specific actions and decisions were not primarily focused on it.  
* *Score 2 (Strong Match):* The feature demonstrates direct, intentional engagement with the topic, highlighting trade-offs, bottlenecks, and architectural decisions directly relevant to the domain.

Only topics receiving a definitive Score 2 from the LLM judge are permanently correlated in the vault's metadata. This aggressive threshold mitigates false positives, which are highly detrimental in interview prep; a candidate attempting to use a tangential, low-depth story to answer a deep architectural question will quickly fail the interview.

### **Directionality and Narrative Density**

Correlations within the Obsidian vault must be strictly bidirectional.

* **Topic → Work (Top-Down):** When a user is studying a specific concept (e.g., "Consistent Hashing"), the vault must present a Dataview list of their past features that utilized it, providing immediate, grounded examples.  
* **Work → Topic (Bottom-Up):** When a user is reviewing a past project to refresh their memory (e.g., "User Data Migration 2024"), the vault must display all the canonical interview concepts demonstrated within that specific project, allowing them to extract multiple stories from a single epic.

Regarding density, the optimal number of work examples per interview topic is between **one and three**. A single strong, deeply technical example is generally sufficient to answer a targeted interview question. Maintaining up to three examples provides strategic redundancy, allowing the candidate to choose the story that best fits the specific phrasing or constraints introduced by the interviewer. Attempting to correlate five or more examples per topic causes cognitive overload and dilutes the candidate's focus during study sessions.

## **Idempotent Import and Log Normalization**

Appending 491 historical planning artifacts to an append-only JSONL log requires robust idempotency guarantees. Without strict deduplication, repeated executions of the /interview-import skill will result in duplicate log entries, ballooning data sizes, and corrupted graph topologies.51

### **Content Hashing and Document Evolution**

Relying solely on path-based deduplication is a fragile strategy; within software repositories, specification files and architectural documents are frequently moved, reorganized, or renamed. Conversely, relying on timestamp-based deduplication (such as checking mtime) will fail if the file is touched by a fresh git checkout or a CI/CD pipeline script.

The system must implement an ingestion architecture utilizing **Content Hashing combined with Path Metadata**.

1. When a file like SPEC.md is targeted for import, the FastMCP server reads the file and generates a cryptographic hash (e.g., SHA-256) of its entire text contents.  
2. The server queries the JSONL append-only log. If the exact hash already exists within the log, the file is identical to a previous import. The operation is skipped entirely, guaranteeing idempotency.  
3. If the hash is novel, the server checks if the file's origin path matches an existing entry. If the path matches but the hash differs, this indicates the document has evolved over time.  
4. The tool then registers a new entry in the append-only log, assigning it the same persistent UUID as the original entry, but with a new timestamp and the updated hash.

This architecture allows the system to maintain a pure append-only log while seamlessly tracking the historical evolution of architectural documents, ensuring the LLM always has access to the most current state of a feature without losing the context of its initial design phase.

## **MCP Tool Design for LLM-Driven Workflows**

The Claude Code plugin interfaces with the local system via FastMCP, a framework that translates standard Python functions into LLM-callable tools utilizing the Model Context Protocol.53 Tool granularity, interaction design, and lifecycle management are critical to the stability of the plugin.

### **Tool Granularity and Interaction Models**

The architecture must delineate clearly between coarse-grained user interactions and fine-grained programmatic operations. The system should expose a mix of composite skills (slash commands initiated by the human) and atomic tools (callable autonomously by the LLM).

* **Human Skills (The / commands):** /interview-import, /interview-synthesize, /interview-generate. These are macro-commands. When a user invokes them via the Claude Code CLI, they trigger massive, multi-step orchestrations.  
* **LLM Tools (The Primitives):** The FastMCP server should expose highly granular operations to the model: read\_jsonl\_log, get\_knowledge\_topic, write\_managed\_markdown\_block, evaluate\_topic\_match, calculate\_file\_hash.

Vault generation itself should not be a single monolithic script hidden behind a user command. Instead, it should be orchestrated by the LLM. When the user types /interview-generate, the system prompts the LLM to begin the generation cycle. The LLM then autonomously utilizes its atomic tools to read the logs, evaluate the matches using the scoring rubric, and construct the Markdown files block by block. This ensures the LLM retains agency to handle edge cases, correct formatting errors, and adapt the narrative style dynamically.

### **Asynchronous Execution and Progress Reporting**

A severe architectural risk in this design is latency. Correlating hundreds of historical artifacts against 154 knowledge topics and subsequently writing an interconnected Markdown vault is a computationally expensive, heavily I/O-bound, long-running operation. Standard JSON-RPC tool calls executed by LLM agents will routinely timeout and crash if the server blocks for minutes without responding.

To mitigate this, the system must natively implement the Model Context Protocol specification for asynchronous progress tracking.55

1. When the Claude Code client initiates the generation sequence, it sends a request including a progressToken in the payload metadata.  
2. The FastMCP Python server must explicitly capture this token and yield interim notifications/progress messages back to the client while the generation loop runs in a background thread.  
3. These JSON-RPC notifications contain the progressToken, the current progress integer (e.g., the number of files processed), the total integer (e.g., 491), and a human-readable message string (e.g., "Synthesizing Feature: Auth Service Migration...").

Implementing this continuous progressToken loop serves two vital functions: it provides the user with real-time UI feedback within the CLI, and crucially, it actively resets the client-side timeout clock with every notification.56 This guarantees that massive vault generation and artifact ingestion operations can run for extended periods without silently failing or destroying the active LLM session mid-execution.

## **Spaced Repetition and Cognitive Scheduling**

While generating high-quality narratives is the primary function of the tool, interview preparation is ultimately a test of rapid memory retrieval. This process benefits enormously from Spaced Repetition Systems (SRS), which optimize memory consolidation by scheduling reviews of material at mathematically expanding intervals.57

### **Integration with Obsidian SRS Plugins**

Building a bespoke spaced repetition scheduling engine within the FastMCP server is an unnecessary reinvention of the wheel. Instead, the MCP server should format the generated vault content to be natively compatible with the highly mature plugins already existing within the Obsidian ecosystem, specifically the community Spaced Repetition plugin.58

The generation tools must be programmed to execute the following formatting tasks:

1. **Tag Injection:** Inject the required SRS identification tags into the YAML frontmatter of the generated stories (e.g., tags: \- \#review).  
2. **Flashcard Syntax:** Format specific, highly critical interview questions and architectural trade-offs as inline flashcards. The generator must utilize the multiline ? or :: delimiter syntax expected by the Obsidian SRS parsers.57  
3. **Metadata Preservation:** Allow the Obsidian plugin to write its proprietary scheduling metadata (e.g., sr-due, sr-interval, sr-ease) directly into the file's frontmatter as the user completes their daily reviews.

By strictly utilizing the "Managed Block" pattern detailed in Section 2.4, the MCP regeneration tool will exclusively target the narrative blocks inside the HTML comments. It will entirely ignore the frontmatter modifications made by the Obsidian SRS plugin, thereby preserving the user's highly personalized, algorithmically calculated study schedule seamlessly across infinite vault regeneration cycles.

## **Risk Analysis and Mitigation Strategies**

Deploying an autonomous, LLM-driven application to process thousands of localized engineering documents carries several inherent risks that must be architecturally mitigated.

| Risk Factor | Impact Level | Architectural Mitigation Strategy |
| :---- | :---- | :---- |
| **LLM Hallucination & Confabulation** | **Critical.** The LLM invents technical details, metrics, or architectural components not present in the original work log to force a narrative to fit a canonical interview topic. | Strict prompting boundaries instructing the LLM to operate in an *extraction-only* mode. The LLM-as-a-judge rubric must heavily penalize and flag "unsupported claims".49 Raw SPEC.md chunks must be injected into the prompt via targeted RAG to ensure grounding. |
| **User Data Destruction** | **Critical.** A programmatic vault regeneration cycle overwrites, deletes, or corrupts human-authored study notes, mnemonics, or custom flashcards. | Absolute adherence to the and HTML block pattern. The FastMCP server must run pre-flight AST integrity checks verifying the presence of delimiters before executing any file write operations. |
| **Graph Degradation (The Hairball)** | **Medium.** The Obsidian vault becomes visually and structurally unnavigable due to indiscriminate hyper-linking by the LLM. | Cap programmatic correlations to the top 3 strongest feature matches per topic. Utilize Dataview tables for querying and aggregating tangential concepts rather than hardcoding static \[\[links\]\] throughout the markdown body. |
| **Context Window & Token Exhaustion** | **High.** Processing 491 dense architectural artifacts simultaneously exceeds LLM context windows or accrues massive API costs. | Implement map-reduce chunking for SPEC.md ingestion. Utilize local, lightweight embeddings for initial candidate topic retrieval, invoking the heavy, expensive LLM-as-a-judge prompt only on the top 5 most relevant candidates. |

## **Recommendations Matrix**

The following decision table resolves the open design questions presented in the system baseline spec, providing the recommended architectural choice, the confidence level of the recommendation, and the supporting justification.

| Open Design Decision | Recommended Choice | Confidence | Justification |
| :---- | :---- | :---- | :---- |
| **Feature Synthesis Approach** | Hybrid (Opportunistic User Tags \+ LLM Semantic Clustering) | **High** | Drastically reduces user friction during daily work while ensuring orphaned, granular logs are not lost. Scales elegantly when executing bulk artifact imports from legacy repositories. |
| **Study Material Format** | Hybrid (Reference Notes \+ Inline Drill Cards) | **High** | Top-level markdown pages act as rich ADR reference documents for deep reading; embedded inline tags (::) enable rapid SRS drilling for spaced repetition. |
| **Vault Freshness Strategy** | Generation-time (On-Demand) | **Medium** | Pre-computing correlations passively in the background is computationally wasteful if the user never studies that specific domain. Generating the vault strictly on-demand via /interview-generate optimizes token usage. |
| **Work Log Schema Normalization** | Content Hashing (SHA-256) \+ Path UUIDs | **High** | Guarantees absolute idempotency on append-only JSONL files during repeated document imports, while simultaneously tracking document evolution and updates over time. |
| **MCP Tool Surface Granularity** | Composite User Skills \+ Atomic LLM Tools | **High** | Users demand one-click macro execution (/generate); LLMs require atomic, specialized tools (read\_log, write\_managed\_file) to reason effectively, handle edge cases, and correct formatting errors autonomously. |
| **Story Format (System Design)** | Architecture Decision Records (ADRs) | **High** | Accurately mirrors real-world senior engineering communication. Forces the articulation of structural trade-offs, bottlenecks, and operational constraints rather than merely reciting buzzwords. |
| **Story Format (Behavioral)** | The (I)STAR(T) Framework | **High** | Adds crucial "Takeaway" and "Introduction" elements to the standard STAR methodology. Demonstrates senior-level introspection, narrative control, and engineering maturity to the interviewer. |

#### **Works cited**

1. Older adults show a self-reference effect for narrative information \- Morris Moscovitch \- University of Toronto, accessed May 1, 2026, [https://neuropsychologylab.psych.utoronto.ca/files/Older%20adults%20show%20a%20self%20reference%20effect%20for%20narrative%20information.pdf](https://neuropsychologylab.psych.utoronto.ca/files/Older%20adults%20show%20a%20self%20reference%20effect%20for%20narrative%20information.pdf)  
2. Self-reference effect | Psychology | Research Starters \- EBSCO, accessed May 1, 2026, [https://www.ebsco.com/research-starters/psychology/self-reference-effect](https://www.ebsco.com/research-starters/psychology/self-reference-effect)  
3. Episodic memory and self-reference via semantic autobiographical memory: insights from an fMRI study in younger and older adults \- Frontiers, accessed May 1, 2026, [https://www.frontiersin.org/journals/behavioral-neuroscience/articles/10.3389/fnbeh.2014.00449/full](https://www.frontiersin.org/journals/behavioral-neuroscience/articles/10.3389/fnbeh.2014.00449/full)  
4. Memory for Details with Self-Referencing \- ResearchGate, accessed May 1, 2026, [https://www.researchgate.net/publication/51809405\_Memory\_for\_Details\_with\_Self-Referencing](https://www.researchgate.net/publication/51809405_Memory_for_Details_with_Self-Referencing)  
5. A self-reference false memory effect in the DRM paradigm: Evidence from Eastern and Western samples \- PMC, accessed May 1, 2026, [https://pmc.ncbi.nlm.nih.gov/articles/PMC6351515/](https://pmc.ncbi.nlm.nih.gov/articles/PMC6351515/)  
6. Memory for Details with Self-Referencing \- PMC \- NIH, accessed May 1, 2026, [https://pmc.ncbi.nlm.nih.gov/articles/PMC3226761/](https://pmc.ncbi.nlm.nih.gov/articles/PMC3226761/)  
7. Lockheed Martin Research Engineer Interview: Process \+ Questions \- Nora AI, accessed May 1, 2026, [https://interview.norahq.com/interview-guides/lockheed-martin-research-engineer-interview-guide-2025](https://interview.norahq.com/interview-guides/lockheed-martin-research-engineer-interview-guide-2025)  
8. Top ways to showcase AI skills for faster career growth \- Zen van Riel, accessed May 1, 2026, [https://zenvanriel.com/ai-engineer-blog/showcase-ai-skills-faster-career-growth/](https://zenvanriel.com/ai-engineer-blog/showcase-ai-skills-faster-career-growth/)  
9. 12 Best Personal Knowledge Management Tools for 2025 | Obsibrain, accessed May 1, 2026, [https://www.obsibrain.com/blog/personal-knowledge-management-tools](https://www.obsibrain.com/blog/personal-knowledge-management-tools)  
10. Best Knowledge Management (KM) Software Reviews 2026 | Gartner Peer Insights, accessed May 1, 2026, [https://www.gartner.com/reviews/market/knowledge-management-software](https://www.gartner.com/reviews/market/knowledge-management-software)  
11. A Guide to Personal Knowledge Management Software for Video Learners | HoverNotes, accessed May 1, 2026, [https://hovernotes.io/en/blog/personal-knowledge-management-software](https://hovernotes.io/en/blog/personal-knowledge-management-software)  
12. Obsidian Vault Template \- Slate Blog, accessed May 1, 2026, [https://slate-blog-demo.vercel.app/blog/obsidian-vault-template](https://slate-blog-demo.vercel.app/blog/obsidian-vault-template)  
13. How I use Obsidian \- Steph Ango, accessed May 1, 2026, [https://stephango.com/vault](https://stephango.com/vault)  
14. bred91/git-data-llm-workflow-code-review-analysis \- GitHub, accessed May 1, 2026, [https://github.com/bred91/git-data-llm-workflow-code-review-analysis](https://github.com/bred91/git-data-llm-workflow-code-review-analysis)  
15. GitSage: An AI Agent for Automated Release Notes, accessed May 1, 2026, [https://practical-engineer.ai/gitsage-an-ai-agent-for-automated-release-notes/](https://practical-engineer.ai/gitsage-an-ai-agent-for-automated-release-notes/)  
16. SkiLLens: Recognising and Mapping Novel Skills from Millions of Job Ads Across Europe Using Language Models \- ACL Anthology, accessed May 1, 2026, [https://aclanthology.org/2026.eacl-industry.65.pdf](https://aclanthology.org/2026.eacl-industry.65.pdf)  
17. System Log Parsing with Large Language Models: A Review \- arXiv, accessed May 1, 2026, [https://arxiv.org/html/2504.04877v2](https://arxiv.org/html/2504.04877v2)  
18. How I use Obsidian Dataview \- Cassidy Williams, accessed May 1, 2026, [https://cassidoo.co/post/obsidian-dataview/](https://cassidoo.co/post/obsidian-dataview/)  
19. GitHub \- s-blu/obsidian\_dataview\_example\_vault: A example vault to collect and showcase various dataview queries. Created on behalf of AB1908, accessed May 1, 2026, [https://github.com/s-blu/obsidian\_dataview\_example\_vault](https://github.com/s-blu/obsidian_dataview_example_vault)  
20. The Project Templates I Use in Obsidian (White-Collar Edition) \- Construct's Substack, accessed May 1, 2026, [https://constructbydee.substack.com/p/the-project-templates-i-use-in-obsidian](https://constructbydee.substack.com/p/the-project-templates-i-use-in-obsidian)  
21. Obsidian Meeting Note Template | Dann Berg: blog, newsletter, shop, and more, accessed May 1, 2026, [https://dannb.org/blog/2023/obsidian-meeting-note-template/](https://dannb.org/blog/2023/obsidian-meeting-note-template/)  
22. Does the Obsidian Properties update cause any destructive changes to note metadata?, accessed May 1, 2026, [https://www.reddit.com/r/ObsidianMD/comments/175me2n/does\_the\_obsidian\_properties\_update\_cause\_any/](https://www.reddit.com/r/ObsidianMD/comments/175me2n/does_the_obsidian_properties_update_cause_any/)  
23. YAML & Properties & API: processFrontMatter removes / alters string quotes, comments, types, formatting \- Page 2 \- Obsidian Forum, accessed May 1, 2026, [https://forum.obsidian.md/t/yaml-properties-api-processfrontmatter-removes-alters-string-quotes-comments-types-formatting/65851?page=2](https://forum.obsidian.md/t/yaml-properties-api-processfrontmatter-removes-alters-string-quotes-comments-types-formatting/65851?page=2)  
24. Hand-Written Code Preservation in Model-to-Text Transformation using Intrinsic Redundancy \- White Rose Research Online, accessed May 1, 2026, [https://eprints.whiterose.ac.uk/id/eprint/232214/1/Hand\_Written\_Code\_Preservation\_in\_Model\_to\_Text\_Transformation\_using\_Intrinsic\_Redundancy-2.pdf](https://eprints.whiterose.ac.uk/id/eprint/232214/1/Hand_Written_Code_Preservation_in_Model_to_Text_Transformation_using_Intrinsic_Redundancy-2.pdf)  
25. README.md \- garrytan/gbrain \- GitHub, accessed May 1, 2026, [https://github.com/garrytan/gbrain/blob/master/README.md](https://github.com/garrytan/gbrain/blob/master/README.md)  
26. llms-full.txt \- Next.js, accessed May 1, 2026, [https://nextjs.org/docs/llms-full.txt](https://nextjs.org/docs/llms-full.txt)  
27. How to add a new task in crontab using a script \- Stack Overflow, accessed May 1, 2026, [https://stackoverflow.com/questions/42940093/how-to-add-a-new-task-in-crontab-using-a-script](https://stackoverflow.com/questions/42940093/how-to-add-a-new-task-in-crontab-using-a-script)  
28. Using the STAR method for your next behavioral interview (worksheet included), accessed May 1, 2026, [https://capd.mit.edu/resources/the-star-method-for-behavioral-interviews/](https://capd.mit.edu/resources/the-star-method-for-behavioral-interviews/)  
29. The STAR Method for Designers: How to Structure Interview Answers That Get You Noticed, accessed May 1, 2026, [https://mockin.work/blog/the-star-method-for-designers-how-to-structure-interview-answers](https://mockin.work/blog/the-star-method-for-designers-how-to-structure-interview-answers)  
30. Go Beyond the STAR Structure \- Use the (I)STAR(T) Framework | OmniInterview, accessed May 1, 2026, [https://www.omniinterview.com/post/beyond-star-structure](https://www.omniinterview.com/post/beyond-star-structure)  
31. Navigating Behavioral Interviews: Beyond the STAR Method | by Natalie Gray \- Career Progress Coach | Medium, accessed May 1, 2026, [https://medium.com/@info\_73918/navigating-behavioral-interviews-beyond-the-star-method-f9dd99b5d267](https://medium.com/@info_73918/navigating-behavioral-interviews-beyond-the-star-method-f9dd99b5d267)  
32. Technical Interview Preparation Roadmap 2026 \- Hakia, accessed May 1, 2026, [https://hakia.com/skills/technical-interview-prep/](https://hakia.com/skills/technical-interview-prep/)  
33. 11 most-asked software engineer behavioral interview questions (+ answers) \- IGotAnOffer, accessed May 1, 2026, [https://igotanoffer.com/blogs/tech/software-engineer-behavioral-interview-questions](https://igotanoffer.com/blogs/tech/software-engineer-behavioral-interview-questions)  
34. How to Answer System Design Interview Questions \- Exponent, accessed May 1, 2026, [https://www.tryexponent.com/courses/system-design-interviews/intro-architecture](https://www.tryexponent.com/courses/system-design-interviews/intro-architecture)  
35. System Design Tradeoffs: How to Think and Explain in Interviews, accessed May 1, 2026, [https://www.systemdesignhandbook.com/blog/system-design-tradeoffs/](https://www.systemdesignhandbook.com/blog/system-design-tradeoffs/)  
36. System Architecture Design: The Complete Guide 2026, accessed May 1, 2026, [https://www.systemdesignhandbook.com/guides/system-architecture-design/](https://www.systemdesignhandbook.com/guides/system-architecture-design/)  
37. What are lightweight Architecture Decision Records? | by Richard Gall \- Medium, accessed May 1, 2026, [https://medium.com/@richggall/what-are-lightweight-architecture-decision-records-61ffca1056aa](https://medium.com/@richggall/what-are-lightweight-architecture-decision-records-61ffca1056aa)  
38. Blueprint for Brilliance: A Software Architect's Guide to Decision-Making \- Medium, accessed May 1, 2026, [https://medium.com/@kennybrast/blueprint-for-brilliance-a-software-architects-guide-to-decision-making-20e302e3959d](https://medium.com/@kennybrast/blueprint-for-brilliance-a-software-architects-guide-to-decision-making-20e302e3959d)  
39. Approach Object-Oriented Design Questions in Interview \- GeeksforGeeks, accessed May 1, 2026, [https://www.geeksforgeeks.org/interview-experiences/steps-to-approach-object-oriented-design-questions-in-interview/](https://www.geeksforgeeks.org/interview-experiences/steps-to-approach-object-oriented-design-questions-in-interview/)  
40. Object-Oriented Design Interview: A step-by-step Guide \- System Design Handbook, accessed May 1, 2026, [https://www.systemdesignhandbook.com/guides/object-oriented-design-interview/](https://www.systemdesignhandbook.com/guides/object-oriented-design-interview/)  
41. A Feature-Based Method for Detecting Design Patterns in Source Code \- MDPI, accessed May 1, 2026, [https://www.mdpi.com/2073-8994/14/7/1491](https://www.mdpi.com/2073-8994/14/7/1491)  
42. How to extract title, description or metadata from markdown \- DEV Community, accessed May 1, 2026, [https://dev.to/codingnninja/how-to-extract-title-description-or-metadata-from-markdown-3nn8](https://dev.to/codingnninja/how-to-extract-title-description-or-metadata-from-markdown-3nn8)  
43. Integration Patterns \- Skills Pool, accessed May 1, 2026, [https://skillspool.org/en/skills/prismatic-io-prismatic-skills-skills-integration-patterns-skill-md](https://skillspool.org/en/skills/prismatic-io-prismatic-skills-skills-integration-patterns-skill-md)  
44. A Survey on LLM-as-a-Judge \- arXiv, accessed May 1, 2026, [https://arxiv.org/html/2411.15594v6](https://arxiv.org/html/2411.15594v6)  
45. How to Evaluate LLMs \- Metrics, Benchmarks & Python Code \- machinelearningplus, accessed May 1, 2026, [https://machinelearningplus.com/gen-ai/llm-evaluation-guide/](https://machinelearningplus.com/gen-ai/llm-evaluation-guide/)  
46. Exploring LLM-as-a-Judge \- Weights & Biases \- Wandb, accessed May 1, 2026, [https://wandb.ai/site/articles/exploring-llm-as-a-judge/](https://wandb.ai/site/articles/exploring-llm-as-a-judge/)  
47. How to Calibrate LLM-as-a-Judge with Human Corrections \- LangChain, accessed May 1, 2026, [https://www.langchain.com/articles/llm-as-a-judge](https://www.langchain.com/articles/llm-as-a-judge)  
48. Primers • LLM-as-a-Judge / Autoraters \- aman.ai, accessed May 1, 2026, [https://aman.ai/primers/ai/LLM-as-a-judge/](https://aman.ai/primers/ai/LLM-as-a-judge/)  
49. GitHub \- langchain-ai/openevals: Readymade evaluators for your LLM apps, accessed May 1, 2026, [https://github.com/langchain-ai/openevals](https://github.com/langchain-ai/openevals)  
50. Rubric-Based Evaluations & LLM-as-a-Judge — Methodologies, Biases, and Empirical Validation in Domain-Specific Contexts. | by Adnan Masood, PhD. | Apr, 2026 | Medium, accessed May 1, 2026, [https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80)  
51. Chapter 3.1 \- Append only log and hash indexes (Storage and retrieval) \- YouTube, accessed May 1, 2026, [https://www.youtube.com/watch?v=XS7EGm-15Cg](https://www.youtube.com/watch?v=XS7EGm-15Cg)  
52. Append-Only Logs: The Immutable Diary of Data | by komal shehzadi | Medium, accessed May 1, 2026, [https://medium.com/@komalshehzadi/append-only-logs-the-immutable-diary-of-data-58c36a871c7c](https://medium.com/@komalshehzadi/append-only-logs-the-immutable-diary-of-data-58c36a871c7c)  
53. Tools \- FastMCP, accessed May 1, 2026, [https://gofastmcp.com/servers/tools](https://gofastmcp.com/servers/tools)  
54. PrefectHQ/fastmcp: The fast, Pythonic way to build MCP servers and clients. \- GitHub, accessed May 1, 2026, [https://github.com/prefecthq/fastmcp](https://github.com/prefecthq/fastmcp)  
55. Progress \- Model Context Protocol, accessed May 1, 2026, [https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/progress](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/progress)  
56. Tools \- Model Context Protocol, accessed May 1, 2026, [https://modelcontextprotocol.io/docs/concepts/tools](https://modelcontextprotocol.io/docs/concepts/tools)  
57. Obsidian for flashcards and spaced repetition? : r/ObsidianMD \- Reddit, accessed May 1, 2026, [https://www.reddit.com/r/ObsidianMD/comments/14ini8v/obsidian\_for\_flashcards\_and\_spaced\_repetition/](https://www.reddit.com/r/ObsidianMD/comments/14ini8v/obsidian_for_flashcards_and_spaced_repetition/)  
58. Spaced Repetition Plugins \- Obsidian Hub, accessed May 1, 2026, [https://publish.obsidian.md/hub/02+-+Community+Expansions/02.01+Plugins+by+Category/Spaced+Repetition+Plugins](https://publish.obsidian.md/hub/02+-+Community+Expansions/02.01+Plugins+by+Category/Spaced+Repetition+Plugins)  
59. All spaced-repetition Obsidian Plugins., accessed May 1, 2026, [https://www.obsidianstats.com/tags/spaced-repetition](https://www.obsidianstats.com/tags/spaced-repetition)  
60. Spaced Repetition \- Fight the forgetting curve by reviewing flashcards & entire notes on Obsidian, accessed May 1, 2026, [https://www.obsidianstats.com/plugins/obsidian-spaced-repetition](https://www.obsidianstats.com/plugins/obsidian-spaced-repetition)  
61. Repeat \- Review notes using periodic or spaced repetition. \- Obsidian Stats, accessed May 1, 2026, [https://www.obsidianstats.com/plugins/repeat-plugin](https://www.obsidianstats.com/plugins/repeat-plugin)