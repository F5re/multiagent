# Eval summary

## fix-failing-test

- old: 3/3 passed; routing errors: 1; average tokens: 28730.33; usage complete: 3/3; MCP calls: 2; errors: 0; tools: {'load_skill': 2, 'mcp__project_tracker__get_issue': 2, 'read_file': 6, 'write_file': 6, 'Bash': 9}
- new: 3/3 passed; routing errors: 1; average tokens: 32978.33; usage complete: 3/3; MCP calls: 3; errors: 0; tools: {'load_skill': 3, 'mcp__project_tracker__get_issue': 3, 'read_file': 6, 'write_file': 7, 'Bash': 11}

## python-review

- old: 3/3 passed; routing errors: 0; average tokens: 9141.33; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'load_skill': 3, 'read_file': 3, 'write_file': 3}
- new: 3/3 passed; routing errors: 0; average tokens: 11345.33; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'load_skill': 3, 'read_file': 3, 'write_file': 3}

## no-matching-skill

- old: 3/3 passed; routing errors: 0; average tokens: 8550.67; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'read_file': 3, 'write_file': 3}
- new: 3/3 passed; routing errors: 2; average tokens: 9349.33; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'read_file': 3, 'write_file': 3, 'load_skill': 2}

## missing-data

- old: 0/3 passed; routing errors: 1; average tokens: 6724.33; usage complete: 3/3; MCP calls: 0; errors: 3; tools: {'load_skill': 1}
- new: 2/3 passed; routing errors: 1; average tokens: 16482.0; usage complete: 3/3; MCP calls: 0; errors: 3; tools: {'load_skill': 1, 'read_file': 16}

## mcp-failure

- old: 2/3 passed; routing errors: 2; average tokens: 26517.33; usage complete: 3/3; MCP calls: 6; errors: 3; tools: {'load_skill': 2, 'list_files': 2, 'read_file': 6, 'Bash': 3, 'mcp__project_tracker__get_issue': 6}
- new: 2/3 passed; routing errors: 2; average tokens: 17208.67; usage complete: 3/3; MCP calls: 5; errors: 3; tools: {'mcp__project_tracker__get_issue': 6, 'load_skill': 2}

## Trials

- fix-failing-test old1: pass=True; routing=True; [events](fix-failing-test/old/1/events.jsonl)
- fix-failing-test new1: pass=True; routing=True; [events](fix-failing-test/new/1/events.jsonl)
- fix-failing-test old2: pass=True; routing=False; [events](fix-failing-test/old/2/events.jsonl)
- fix-failing-test new2: pass=True; routing=True; [events](fix-failing-test/new/2/events.jsonl)
- fix-failing-test old3: pass=True; routing=True; [events](fix-failing-test/old/3/events.jsonl)
- fix-failing-test new3: pass=True; routing=False; [events](fix-failing-test/new/3/events.jsonl)
- python-review old1: pass=True; routing=True; [events](python-review/old/1/events.jsonl)
- python-review new1: pass=True; routing=True; [events](python-review/new/1/events.jsonl)
- python-review old2: pass=True; routing=True; [events](python-review/old/2/events.jsonl)
- python-review new2: pass=True; routing=True; [events](python-review/new/2/events.jsonl)
- python-review old3: pass=True; routing=True; [events](python-review/old/3/events.jsonl)
- python-review new3: pass=True; routing=True; [events](python-review/new/3/events.jsonl)
- no-matching-skill old1: pass=True; routing=True; [events](no-matching-skill/old/1/events.jsonl)
- no-matching-skill new1: pass=True; routing=True; [events](no-matching-skill/new/1/events.jsonl)
- no-matching-skill old2: pass=True; routing=True; [events](no-matching-skill/old/2/events.jsonl)
- no-matching-skill new2: pass=True; routing=False; [events](no-matching-skill/new/2/events.jsonl)
- no-matching-skill old3: pass=True; routing=True; [events](no-matching-skill/old/3/events.jsonl)
- no-matching-skill new3: pass=True; routing=False; [events](no-matching-skill/new/3/events.jsonl)
- missing-data old1: pass=False; routing=True; [events](missing-data/old/1/events.jsonl)
- missing-data new1: pass=True; routing=False; [events](missing-data/new/1/events.jsonl)
- missing-data old2: pass=False; routing=True; [events](missing-data/old/2/events.jsonl)
- missing-data new2: pass=False; routing=True; [events](missing-data/new/2/events.jsonl)
- missing-data old3: pass=False; routing=False; [events](missing-data/old/3/events.jsonl)
- missing-data new3: pass=True; routing=True; [events](missing-data/new/3/events.jsonl)
- mcp-failure old1: pass=False; routing=False; [events](mcp-failure/old/1/events.jsonl)
- mcp-failure new1: pass=True; routing=True; [events](mcp-failure/new/1/events.jsonl)
- mcp-failure old2: pass=True; routing=True; [events](mcp-failure/old/2/events.jsonl)
- mcp-failure new2: pass=True; routing=False; [events](mcp-failure/new/2/events.jsonl)
- mcp-failure old3: pass=True; routing=False; [events](mcp-failure/old/3/events.jsonl)
- mcp-failure new3: pass=False; routing=False; [events](mcp-failure/new/3/events.jsonl)
