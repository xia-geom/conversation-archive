# Learning progression

The first milestone is evidence handling: inspect a structure, predict a transformation, follow provenance, detect a failure, and explain what validation establishes. Learn those ideas before adding infrastructure. Routine coding can be delegated to AI; judging evidence and checking conclusions cannot be delegated without review.

| Later stage | Small exercise | Question to understand before proceeding |
| --- | --- | --- |
| Exploratory analysis | Count conversations, roles, missing timestamps, and content kinds | What is the unit of observation? Are message occurrences, unique IDs, and conversations different? |
| SQL | Load validated JSONL into separate conversation/message/reference tables | Can a join duplicate rows? Which keys preserve branch membership? |
| Visualization and statistics | Plot recording volume with explicit denominators and missing-data notes | Does the graph show behavior, export coverage, or use of the app? What population does a statistic describe? |
| Longitudinal work | Compare periods using a documented timestamp and sampling rule | Are recording dates confused with event dates? Did provider usage or export coverage change? |
| Rich annotations | Link one reviewed annotation to exact passages and versions | Who wrote it, with what evidence? What alternative interpretation remains? |
| Embeddings and search | Build a replaceable local index over clearly selected text representations | What was embedded? How do chunk boundaries, language, and retrieval misses affect the result? |
| AI-assisted interpretation | Record prompts, model versions, inputs, outputs, and human revisions | Does the annotation quote evidence, or fill gaps with plausible invention? |
| Evaluation | Compare AI annotations against reviewed examples, including disagreements | What errors matter? Is the reference judgment certain? What conclusions remain unsupported? |

Future annotation tables should add information beside the original text, never overwrite it. Keep authorship, uncertainty, alternatives, and revision history. Define evaluation examples before treating automated labels as measurements. Avoid diagnoses or causal claims from message frequencies alone.

Each stage should begin with a small question and a reproducible example. Ask the implementation agent to explain one consequential choice, propose a check, and show where its result could be misleading. Add dependencies only when they solve an understood problem.
