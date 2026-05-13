# Format Analysis for LLM Integration

This document analyzes the various output formats supported by code2logic and their suitability for LLM consumption and processing.

## Overview

code2logic supports multiple output formats, each optimized for different use cases:

1. **JSON** - Machine-readable, ideal for LLM processing
2. **YAML** - Human-readable, structured data
3. **CSV** - Tabular data for spreadsheet analysis
4. **Markdown** - Documentation-friendly format
5. **Compact** - Minimal text representation

### JSON Format

**Advantages for LLM:**

- Structured, hierarchical data
- Easy parsing and manipulation
- Preserves data types and relationships
- Widely supported by LLMs
- Supports nested objects and arrays

**Structure:**

```json
{
  "project": {
    "name": "project_name",
    "path": "/path/to/project",
    "statistics": {
      "total_modules": 10,
      "total_functions": 50,
      "total_classes": 20,
      "total_dependencies": 35,
      "total_lines_of_code": 5000
    },
    "modules": [
      {
        "name": "module_name",
        "path": "/path/to/module.py",
        "lines_of_code": 100,
        "imports": ["os", "sys"],
        "functions": [...],
        "classes": [...]
      }
    ],
    "dependencies": [...],
    "similarities": [...]
  }
}
```

**LLM Processing Tips:**

- Use for complex analysis requiring structured data access
- Ideal for programmatic processing and API integration
- Best for preserving complete project context

### YAML Format

**Advantages for LLM:**

- Human-readable and editable
- Less verbose than JSON
- Preserves structure and hierarchy
- Easy to convert to/from JSON

**Structure:**

```yaml
project:
  name: project_name
  path: /path/to/project
  metadata: {}
  modules:
    - name: module_name
      path: /path/to/module.py
      lines_of_code: 100
      imports:
        - os
        - sys
      functions:
        - name: function_name
          lines_of_code: 20
          complexity: 3
          parameters:
            - arg1
            - arg2
          docstring: "Function description"
          code: "def function_name(arg1, arg2):..."
      classes:
        - name: ClassName
          lines_of_code: 50
          base_classes: []
          methods: [...]
  dependencies:
    - source: module1
      target: module2
      type: import
      strength: 0.8
  similarities: []
```

**LLM Processing Tips:**

- Use when human readability is important
- Good for configuration files and documentation
- Can be easily converted to JSON for processing

### CSV Format

**Advantages for LLM:**

- Tabular structure for statistical analysis
- Easy to import into data analysis tools
- Simple format for numerical data
- Supports spreadsheet applications

**Structure:**

Multiple CSV files are generated:

**modules.csv:**

```csv
name,path,lines_of_code,functions,classes,imports
main.py,/project/main.py,150,5,2,"os,sys,json"
utils.py,/project/utils.py,80,3,1,"re,datetime"
```

**functions.csv:**

```csv
module,name,lines_of_code,complexity,docstring
main.py,calculate_sum,15,2,True
main.py,fibonacci,8,5,True
utils.py,validate_email,12,3,False
```

**classes.csv:**

```csv
module,name,methods,base_classes,lines_of_code
main.py,Calculator,4,,60
utils.py,DataProcessor,3,,45
```

**dependencies.csv:**

```csv
source,target,type,strength
main.py,os,import,0.8
main.py,utils,import,0.9
utils.py,re,import,0.8
```

**LLM Processing Tips:**

- Use for statistical analysis and data mining
- Ideal for generating metrics and reports
- Best for quantitative analysis
- Requires multiple files for complete project view

### Markdown Format

**Advantages for LLM:**

- Natural language documentation
- Rich formatting with headers and lists
- Easy to read and understand
- Supports code blocks and tables

**Structure:**

```markdown
# Project Name

**Path:** `/path/to/project`

## Statistics

| Metric | Value |
|--------|-------|
| Modules | 10 |
| Functions | 50 |
| Classes | 20 |
| Dependencies | 35 |
| Lines of Code | 5000 |

### main.py

**Path:** `/project/main.py`
**Lines of Code:** 150

**Imports:**
- `os`
- `sys`
- `json`

**Functions:**
- `calculate_sum()` (15 LOC, complexity: 2)
- `fibonacci()` (8 LOC, complexity: 5)

**Classes:**
- `Calculator` (4 methods)

### utils.py

**Path:** `/project/utils.py`
**Lines of Code:** 80

**Imports:**
- `re`
- `datetime`

**Functions:**
- `validate_email()` (12 LOC, complexity: 3)

**Classes:**
- `DataProcessor` (3 methods)

## Dependencies

| Source | Target | Type | Strength |
|--------|--------|------|----------|
| `main.py` | `os` | import | 0.80 |
| `main.py` | `utils` | import | 0.90 |
| `utils.py` | `re` | import | 0.80 |
```

**LLM Processing Tips:**

- Use for documentation generation
- Good for human-readable reports
- Ideal for presentations and summaries
- Natural language processing friendly

### Compact Format

**Advantages for LLM:**

- Minimal text representation
- Quick overview of project structure
- Easy to scan and understand
- Low memory footprint

**Structure:**

```text
Project: my_project (/path/to/project)
Modules: 10
Functions: 50
Classes: 20
Dependencies: 35
LOC: 5000

main.py (150 LOC)
  Functions: calculate_sum, fibonacci, process_data
  Classes: Calculator
  Imports: os, sys, json

utils.py (80 LOC)
  Functions: validate_email, format_date
  Classes: DataProcessor
  Imports: re, datetime

models.py (120 LOC)
  Classes: User, Product, Order
  Imports: datetime, typing
```

**LLM Processing Tips:**

- Use for quick project overviews
- Good for chat-based interactions
- Ideal for summarization tasks
- Minimal context for focused analysis

### For Complex Analysis Tasks

**Recommended Format:** JSON

**Use Cases:**

- Dependency graph analysis
- Code similarity detection
- Refactoring recommendations
- Architecture analysis

**Processing Strategy:**

1. Load JSON data into structured format
2. Extract relevant sections (modules, dependencies, etc.)
3. Apply analysis algorithms
4. Generate insights and recommendations

### For Documentation Generation

**Recommended Format:** Markdown

**Use Cases:**

- Project documentation
- API documentation
- Reports and summaries
- Readme generation

**Processing Strategy:**

1. Parse Markdown structure
2. Extract key sections and statistics
3. Generate natural language descriptions
4. Format output in desired documentation style

### For Statistical Analysis

**Recommended Format:** CSV

**Use Cases:**

- Code metrics analysis
- Trend analysis
- Quality metrics
- Performance analysis

**Processing Strategy:**

1. Load CSV data into dataframes
2. Perform statistical calculations
3. Generate visualizations
4. Create summary reports

### For Quick Interactions

**Recommended Format:** Compact

**Use Cases:**

- Chat-based queries
- Quick summaries
- Real-time analysis
- Minimal context processing

**Processing Strategy:**

1. Parse compact text format
2. Extract key metrics
3. Provide quick insights
4. Generate concise responses

### JSON to YAML

```python
import yaml
with open('data.json', 'r') as f:
    data = json.load(f)
with open('data.yaml', 'w') as f:
    yaml.dump(data, f, default_flow_style=False)
```

### YAML to JSON

```python
import yaml
import json
with open('data.yaml', 'r') as f:
    data = yaml.safe_load(f)
with open('data.json', 'w') as f:
    json.dump(data, f, indent=2)
```

### CSV to JSON

```python
import pandas as pd
df = pd.read_csv('data.csv')
data = df.to_dict('records')
```

### Markdown to Structured Data

```python
import re
from markdown import markdown

### For JSON Processing

```text
Analyze the following project structure in JSON format:
{json_data}

Focus on:
1. Dependency relationships
2. Code complexity patterns
3. Architectural insights
4. Refactoring opportunities

Provide structured recommendations with specific targets and actions.
```

### For Markdown Processing

```text
Review the following project documentation:
{markdown_content}

Extract key insights about:
1. Project organization
2. Code quality metrics
3. Documentation completeness
4. Areas for improvement

Generate a summary report with actionable recommendations.
```

### For CSV Analysis

```text
Analyze the following code metrics data:
{csv_data}

Calculate:
1. Average function complexity
2. Module dependency ratios
3. Code distribution patterns
4. Quality indicators

Provide statistical analysis with trends and recommendations.
```

### Memory Usage

- **JSON**: Higher memory usage due to verbosity
- **YAML**: Moderate memory usage
- **CSV**: Lower memory usage for tabular data
- **Markdown**: Higher memory for rich formatting
- **Compact**: Lowest memory usage

### Processing Speed

- **JSON**: Fast parsing with native libraries
- **YAML**: Slower parsing due to complexity
- **CSV**: Very fast for tabular data
- **Markdown**: Moderate parsing speed
- **Compact**: Fastest due to simplicity

### LLM Token Usage

- **JSON**: Higher token count
- **YAML**: Moderate token count
- **CSV**: Variable based on data size
- **Markdown**: Higher token count with formatting
- **Compact**: Lowest token count

## Best Practices

1. **Choose format based on use case**: Select the format that best matches your analysis needs
2. **Consider LLM context limits**: Use compact formats for large projects
3. **Validate data integrity**: Ensure format conversion preserves all information
4. **Optimize prompts**: Tailor prompts to specific format characteristics
5. **Handle errors gracefully**: Provide fallback mechanisms for format parsing

## Conclusion

Each format serves specific purposes in LLM integration:

- **JSON** for comprehensive, structured analysis
- **YAML** for human-readable configuration
- **CSV** for statistical analysis
- **Markdown** for documentation
- **Compact** for quick interactions

Understanding these characteristics enables optimal format selection for different LLM-powered code analysis tasks.
