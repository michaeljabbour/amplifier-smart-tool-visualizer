#!/usr/bin/env python3
"""A stand-in model for tests: reads {system, prompt} on stdin, prints a canned reply by task."""

import json
import re
import sys

req = json.load(sys.stdin)
system, prompt = req["system"], req["prompt"]
if "network graph maker" in system:
    text = prompt.lower()
    out = []
    if "routing" in text:
        out.append({"node_1": "model routing", "node_1_type": "method", "node_2": "inference cost",
                    "node_2_type": "metric", "relation": "reduces", "edge": "Routing lowers inference cost.",
                    "confidence": 0.8})
    if "delegat" in text:
        out.append({"node_1": "delegation", "node_2": "perceived agency", "relation": "decreases",
                    "edge": "Delegating lowered perceived agency.", "confidence": 0.6})
    out.append({"node_1": "notes", "node_2": "evidence", "edge": "Notes hold evidence."})  # old {node_1, node_2, edge} shape
    print("Here you go:\n```json\n" + json.dumps(out) + "\n```")
elif "answer questions from a knowledge graph" in system:
    nums = re.findall(r"^\[(\d+)\]", prompt, re.M)
    print("The graph says it depends on who chooses what to delegate " + "".join(f"[{n}]" for n in nums[:2]) + ".")
elif "short reports on one topic" in system:
    print(json.dumps({"title": "Stub topic", "summary": "A topic summary.", "findings": ["one", "two"]}))
elif "research questions in the gaps" in system:
    print(json.dumps([{"gap": 0, "question": "Does routing change how much people trust delegation?",
                       "why": "Cost choices shape agent behaviour people see.", "bridges": ["delegation", "model routing"]}]))
elif "pairs of statements" in system:
    print(json.dumps([{"pair": 0, "verdict": "contradicts", "newer": None, "reason": "Opposite effects."}]))
else:
    sys.exit("stub: unknown task")
