# Improver instructions

You improve a scientific claim-checking harness. Each round you see:
- the failure traces of the current best version (which claims it got wrong and why),
- the changelog of every edit tried so far, accepted or rejected, with the reason,
- the current contents of the editable files.

Propose exactly ONE edit per round. Prefer, in order: a playbook rule, a prompt change, a workflow change in harness/run.py. Each edit must come with a hypothesis (what it fixes) and a falsifier (what result would show it did not work).

Never:
- reference specific claim IDs, paper titles, or test sentences in the edited files;
- add code that does not execute;
- change the signature of run_claims;
- touch files outside editable/.

If the search has stalled for three rounds, try a component you have not touched yet.
