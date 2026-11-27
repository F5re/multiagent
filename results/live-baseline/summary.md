# Eval summary

## fix-failing-test

- A: 2/3 passed; routing errors: 0; average tokens: 19509.67; usage complete: 3/3; MCP calls: 3; errors: 0; tools: {'mcp__project_tracker__get_issue': 3, 'read_file': 5, 'write_file': 3, 'Bash': 5}
- B: 3/3 passed; routing errors: 0; average tokens: 26280.0; usage complete: 3/3; MCP calls: 2; errors: 0; tools: {'load_skill': 3, 'mcp__project_tracker__get_issue': 2, 'read_file': 6, 'write_file': 5, 'Bash': 8}

## python-review

- A: 3/3 passed; routing errors: 0; average tokens: 5497.33; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'read_file': 3, 'write_file': 3}
- B: 3/3 passed; routing errors: 0; average tokens: 11117.67; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'load_skill': 3, 'read_file': 3, 'write_file': 3}

## no-matching-skill

- A: 3/3 passed; routing errors: 0; average tokens: 6428.67; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'read_file': 3, 'write_file': 3}
- B: 3/3 passed; routing errors: 0; average tokens: 10803.0; usage complete: 3/3; MCP calls: 0; errors: 0; tools: {'read_file': 3, 'write_file': 3, 'list_files': 1}

## missing-data

- A: 2/3 passed; routing errors: 0; average tokens: 9906.0; usage complete: 3/3; MCP calls: 0; errors: 3; tools: {'read_file': 10}
- B: 3/3 passed; routing errors: 1; average tokens: 23685.67; usage complete: 3/3; MCP calls: 0; errors: 3; tools: {'read_file': 11, 'list_files': 5, 'load_skill': 1, 'NO_SKILL': 1}

## mcp-failure

- A: 3/3 passed; routing errors: 0; average tokens: 10762.67; usage complete: 3/3; MCP calls: 9; errors: 3; tools: {'mcp__project_tracker__get_issue': 11}
- B: 3/3 passed; routing errors: 0; average tokens: 19015.33; usage complete: 3/3; MCP calls: 9; errors: 3; tools: {'mcp__project_tracker__get_issue': 10}

## Trials

- fix-failing-test A1: pass=True; routing=n/a; [events](fix-failing-test/A/1/events.jsonl)
- fix-failing-test B1: pass=True; routing=True; [events](fix-failing-test/B/1/events.jsonl)
- fix-failing-test A2: pass=True; routing=n/a; [events](fix-failing-test/A/2/events.jsonl)
- fix-failing-test B2: pass=True; routing=True; [events](fix-failing-test/B/2/events.jsonl)
- fix-failing-test A3: pass=False; routing=n/a; [events](fix-failing-test/A/3/events.jsonl)
- fix-failing-test B3: pass=True; routing=True; [events](fix-failing-test/B/3/events.jsonl)
- python-review A1: pass=True; routing=n/a; [events](python-review/A/1/events.jsonl)
- python-review B1: pass=True; routing=True; [events](python-review/B/1/events.jsonl)
- python-review A2: pass=True; routing=n/a; [events](python-review/A/2/events.jsonl)
- python-review B2: pass=True; routing=True; [events](python-review/B/2/events.jsonl)
- python-review A3: pass=True; routing=n/a; [events](python-review/A/3/events.jsonl)
- python-review B3: pass=True; routing=True; [events](python-review/B/3/events.jsonl)
- no-matching-skill A1: pass=True; routing=n/a; [events](no-matching-skill/A/1/events.jsonl)
- no-matching-skill B1: pass=True; routing=True; [events](no-matching-skill/B/1/events.jsonl)
- no-matching-skill A2: pass=True; routing=n/a; [events](no-matching-skill/A/2/events.jsonl)
- no-matching-skill B2: pass=True; routing=True; [events](no-matching-skill/B/2/events.jsonl)
- no-matching-skill A3: pass=True; routing=n/a; [events](no-matching-skill/A/3/events.jsonl)
- no-matching-skill B3: pass=True; routing=True; [events](no-matching-skill/B/3/events.jsonl)
- missing-data A1: pass=False; routing=n/a; [events](missing-data/A/1/events.jsonl)
- missing-data B1: pass=True; routing=True; [events](missing-data/B/1/events.jsonl)
- missing-data A2: pass=True; routing=n/a; [events](missing-data/A/2/events.jsonl)
- missing-data B2: pass=True; routing=False; [events](missing-data/B/2/events.jsonl)
- missing-data A3: pass=True; routing=n/a; [events](missing-data/A/3/events.jsonl)
- missing-data B3: pass=True; routing=True; [events](missing-data/B/3/events.jsonl)
- mcp-failure A1: pass=True; routing=n/a; [events](mcp-failure/A/1/events.jsonl)
- mcp-failure B1: pass=True; routing=True; [events](mcp-failure/B/1/events.jsonl)
- mcp-failure A2: pass=True; routing=n/a; [events](mcp-failure/A/2/events.jsonl)
- mcp-failure B2: pass=True; routing=True; [events](mcp-failure/B/2/events.jsonl)
- mcp-failure A3: pass=True; routing=n/a; [events](mcp-failure/A/3/events.jsonl)
- mcp-failure B3: pass=True; routing=True; [events](mcp-failure/B/3/events.jsonl)
