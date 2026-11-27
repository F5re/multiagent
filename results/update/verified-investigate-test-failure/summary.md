# Eval summary

## fix-failing-test

- old: 3/3 passed; routing errors: 0; average tokens: 21955.0; usage complete: 3/3; MCP calls: 1; errors: 0; tools: {'load_skill': 3, 'read_file': 6, 'write_file': 5, 'Bash': 8, 'mcp__project_tracker__get_issue': 1}
- new: 3/3 passed; routing errors: 1; average tokens: 24948.67; usage complete: 3/3; MCP calls: 3; errors: 0; tools: {'load_skill': 2, 'mcp__project_tracker__get_issue': 3, 'read_file': 8, 'write_file': 4, 'Bash': 7}

## python-review

- old: 1/3 passed; routing errors: 2; average tokens: 20950.0; usage complete: 3/3; MCP calls: 0; errors: 2; tools: {'read_file': 3, 'write_file': 5, 'load_skill': 1, 'list_files': 4}
- new: 3/3 passed; routing errors: 1; average tokens: 9141.0; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'read_file': 3, 'write_file': 3, 'load_skill': 2}

## no-matching-skill

- old: 3/3 passed; routing errors: 0; average tokens: 7818.33; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'read_file': 3, 'write_file': 3}
- new: 3/3 passed; routing errors: 1; average tokens: 7313.0; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'load_skill': 1, 'read_file': 3, 'write_file': 3}

## missing-data

- old: 0/3 passed; routing errors: 0; average tokens: 8093.33; usage complete: 3/3; MCP calls: 0; errors: 3; tools: {}
- new: 2/3 passed; routing errors: 0; average tokens: 14164.67; usage complete: 3/3; MCP calls: 0; errors: 3; tools: {'read_file': 8, 'list_files': 2}

## mcp-failure

- old: 2/3 passed; routing errors: 1; average tokens: 12125.0; usage complete: 3/3; MCP calls: 6; errors: 3; tools: {'mcp__project_tracker__get_issue': 6, 'load_skill': 1}
- new: 1/3 passed; routing errors: 2; average tokens: 19288.0; usage complete: 3/3; MCP calls: 3; errors: 3; tools: {'load_skill': 2, 'mcp__project_tracker__get_issue': 3, 'read_file': 5}

## Trials

- fix-failing-test old1: pass=True; routing=True; [events](fix-failing-test/old/1/events.jsonl)
- fix-failing-test new1: pass=True; routing=True; [events](fix-failing-test/new/1/events.jsonl)
- fix-failing-test old2: pass=True; routing=True; [events](fix-failing-test/old/2/events.jsonl)
- fix-failing-test new2: pass=True; routing=True; [events](fix-failing-test/new/2/events.jsonl)
- fix-failing-test old3: pass=True; routing=True; [events](fix-failing-test/old/3/events.jsonl)
- fix-failing-test new3: pass=True; routing=False; [events](fix-failing-test/new/3/events.jsonl)
- python-review old1: pass=True; routing=False; [events](python-review/old/1/events.jsonl)
- python-review new1: pass=True; routing=False; [events](python-review/new/1/events.jsonl)
- python-review old2: pass=False; routing=False; [events](python-review/old/2/events.jsonl)
- python-review new2: pass=True; routing=True; [events](python-review/new/2/events.jsonl)
- python-review old3: pass=False; routing=True; [events](python-review/old/3/events.jsonl)
- python-review new3: pass=True; routing=True; [events](python-review/new/3/events.jsonl)
- no-matching-skill old1: pass=True; routing=True; [events](no-matching-skill/old/1/events.jsonl)
- no-matching-skill new1: pass=True; routing=False; [events](no-matching-skill/new/1/events.jsonl)
- no-matching-skill old2: pass=True; routing=True; [events](no-matching-skill/old/2/events.jsonl)
- no-matching-skill new2: pass=True; routing=True; [events](no-matching-skill/new/2/events.jsonl)
- no-matching-skill old3: pass=True; routing=True; [events](no-matching-skill/old/3/events.jsonl)
- no-matching-skill new3: pass=True; routing=True; [events](no-matching-skill/new/3/events.jsonl)
- missing-data old1: pass=False; routing=True; [events](missing-data/old/1/events.jsonl)
- missing-data new1: pass=False; routing=True; [events](missing-data/new/1/events.jsonl)
- missing-data old2: pass=False; routing=True; [events](missing-data/old/2/events.jsonl)
- missing-data new2: pass=True; routing=True; [events](missing-data/new/2/events.jsonl)
- missing-data old3: pass=False; routing=True; [events](missing-data/old/3/events.jsonl)
- missing-data new3: pass=True; routing=True; [events](missing-data/new/3/events.jsonl)
- mcp-failure old1: pass=True; routing=True; [events](mcp-failure/old/1/events.jsonl)
- mcp-failure new1: pass=False; routing=False; [events](mcp-failure/new/1/events.jsonl)
- mcp-failure old2: pass=False; routing=False; [events](mcp-failure/old/2/events.jsonl)
- mcp-failure new2: pass=True; routing=True; [events](mcp-failure/new/2/events.jsonl)
- mcp-failure old3: pass=True; routing=True; [events](mcp-failure/old/3/events.jsonl)
- mcp-failure new3: pass=False; routing=False; [events](mcp-failure/new/3/events.jsonl)
