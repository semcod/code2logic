# Using LLM Context for Code Analysis

This guide shows how to use the generated LLM context effectively.

## Quick Start

Generate LLM context for your project:

```bash
code2flow llm-context /path/to/project -o ./context.md
```

### 1. Architecture Understanding

**Query:**
```
Based on the provided architecture, what are the main modules and their responsibilities?
```

**Expected Response:**
- Overview of module hierarchy
- Key responsibilities of each major module
- Dependencies between modules

### 2. Finding Entry Points

**Query:**
```
What are the main entry points for this application? How does execution flow through the system?
```

**Expected Response:**
- List of entry point functions
- Execution flow description
- User interaction points

### 3. Understanding Data Flow

**Query:**
```
Trace the data flow for [specific feature]. What functions process the data and how is it transformed?
```

**Expected Response:**
- Step-by-step data transformation
- Functions involved in processing
- Output destinations

### 4. API Usage

**Query:**
```
What is the public API surface? Which functions are intended for external use?
```

**Expected Response:**
- List of public API functions
- Their parameters and return types
- Usage examples

### 5. Code Review

**Query:**
```
Review the [module_name] module. What are potential issues or improvements?
```

**Expected Response:**
- Code quality observations
- Potential bugs or edge cases
- Refactoring suggestions

### 6. Adding Features

**Query:**
```
I want to add [feature]. Where should I make changes and what functions should I call?
```

**Expected Response:**
- Recommended insertion points
- Functions to extend or call
- Integration considerations

### 7. Debugging

**Query:**
```
I'm seeing [error] in [function]. What could be causing this and how does the error propagate?
```

**Expected Response:**
- Call chain analysis
- Potential error sources
- Debugging strategy

### 8. Documentation

**Query:**
```
Generate documentation for the [module] module including usage examples.
```

**Expected Response:**
- Module overview
- Function documentation
- Usage examples
- Integration patterns

### 1. Context Size Management

The LLM context is optimized for size:
- **35KB** for typical projects (few hundred files)
- **690 lines** with structured sections
- Fits within common LLM context windows

### 2. Section Utilization

Reference specific sections in your queries:

```
Looking at "## Architecture by Module", which modules have the most functions?
```

```
From "## Process Flows", trace how data moves through the pipeline.
```

### 3. Combining with Code

For detailed analysis, combine context with actual code snippets:

```
Given the context showing that `process_data` calls `validate_input`,
here's the actual code: [code snippet]

Can you suggest improvements?
```

### Custom Queries

Create custom queries for specific needs:

**Security Analysis:**
```
Analyze the "## Public API Surface" section. Which functions accept external input
and might need input validation? Check "## Data Transformation Functions" for
serialization/deserialization points that could be vulnerable.
```

**Performance Optimization:**
```
Looking at "## Key Entry Points" and "## System Interactions", which functions
are called most frequently? What optimization strategies would you recommend?
```

**Testing Strategy:**
```
Based on "## Process Flows" and "## Key Classes", what test coverage would you
recommend? Which are the critical paths that need thorough testing?
```

### Automation

Integrate with CI/CD:

```bash
# Generate context in CI
code2flow llm-context . -o ./context.md

# Use with LLM API
curl -X POST https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "system", "content": "You are a code analysis assistant."},
      {"role": "user", "content": "Analyze this codebase: $(cat ./context.md)"}
    ]
  }'
```

### 1. Be Specific

❌ **Vague:** "Tell me about this code"
✅ **Specific:** "What is the role of the generation.template_generator module?"

### 2. Reference Sections

❌ **Generic:** "How does it work?"
✅ **Contextual:** "Based on the Process Flows section, how does execution flow through the pipeline?"

### 3. Ask for Comparisons

```
Compare the adapters.browser and adapters.kubernetes modules.
What patterns do they share and how do they differ?
```

### 4. Request Examples

```
From the Public API Surface, pick 3 important functions and show
how they would be used in practice.
```

### 5. Debugging Context

When debugging, include both context and error:

```
Context: [paste relevant section]

Error: AttributeError: 'NoneType' object has no attribute 'process'

Traceback shows it's in pipeline_runner.execute_action

What could be causing this?
```

### Context Too Long

If context exceeds LLM limits:

1. Use `--strategy quick` for smaller output
2. Focus on specific modules: `code2flow llm-context ./specific_module`
3. Manually extract relevant sections

### Missing Information

If specific details are missing:

1. Check if files are excluded by filters (tests, private)
2. Use `--strategy deep` for more complete analysis
3. Ensure docstrings are present in source code

### LLM Misunderstands

If LLM gives incorrect responses:

1. Provide more specific section references
2. Include actual code snippets alongside context
3. Break complex queries into simpler steps

# Generate context
$ code2flow llm-context ../src/nlp2cmd -o context.md -v
Generating LLM context for: ../src/nlp2cmd

✓ LLM context generated: ./context.md
  Functions: 3567
  Classes: 398
  Modules: 197

# Use with LLM
$ cat context.md | llm "What are the main architectural patterns used?"

The codebase follows several architectural patterns:

1. **Template Method Pattern**: The generation.template_generator module
   uses this for different output formats...

2. **Adapter Pattern**: The adapters.* modules provide consistent interfaces
   for different execution environments...

3. **Pipeline Pattern**: The pipeline_runner modules process actions
   through sequential stages...
```

### With VS Code

Create a custom command:

```json
{
  "key": "ctrl+shift+a",
  "command": "workbench.action.terminal.sendSequence",
  "args": {
    "text": "code2flow llm-context . -o /tmp/context.md && cat /tmp/context.md | pbcopy\u000D"
  }
}
```

### With ChatGPT Web

1. Generate context: `code2flow llm-context . -o context.md`
2. Copy to clipboard: `cat context.md | pbcopy`
3. Paste into ChatGPT with your query

### With Claude Desktop

Create a workflow:

```bash
#!/bin/bash
# analyze.sh
CONTEXT=$(code2flow llm-context . -o - 2>/dev/null)
echo "Analyze this codebase and suggest improvements:"
echo "$CONTEXT" | head -n 100  # Limit for demo
```

## Success Metrics

Good LLM context should enable:

- ✓ Accurate architectural descriptions
- ✓ Correct identification of entry points
- ✓ Understanding of data flows
- ✓ Identification of key components
- ✓ Sensible refactoring suggestions
- ✓ Detection of potential issues

If responses are inaccurate, check:
1. Is context up to date? (re-generate after code changes)
2. Are source files properly parsed? (check for syntax errors)
3. Is context complete? (use `--strategy deep` for full analysis)
