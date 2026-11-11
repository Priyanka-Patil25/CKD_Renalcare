"""Agentic layer: tools, a brain (LLM), and the loop that connects them.

  tools.py     what the agent is ALLOWED to do (small read-only functions)
  llm.py       the 'brain' that decides the next step (fake one now, real LLM later)
  loop.py      think -> act -> look at the result -> repeat, until done
  run_demo.py  run it from the command line and watch every step
"""
