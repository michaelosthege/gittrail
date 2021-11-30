[![pipeline](https://github.com/michaelosthege/gittrail/workflows/pipeline/badge.svg)](https://github.com/michaelosthege/gittrail/actions)


# `gittrail` - Linking data pipeline outputs to commit history
Versioning of code with git is easy, versioning data pipeline inputs/outputs is hard.

``GitTrail`` helps you to maintain a traceable data lineage by enforcing a
link between data files and the commit history of your processing code.

Like blockchain, but easier.

## How it works
``GitTrail`` is used as a context manager around the code that executes your data processing:

```python
with GitTrail(
    repo="/path/to/my_data_processing_code",
    workdir="/path/to/my_data_storage",
):
    # TODO: run data analysis on inputs from [workdir]
    # TODO: save results to [workdir]
```

Within the context, the following two rules are enforced:
1. The working tree of your code [repo] must be clean (no uncommitted changes).
2. All files currently found in [workdir] must have been created/changed
    in a ``GitTrail`` context that's linked to your code's git history.

Taken together this means that:
* You're not allowed to add/edit/anything in [workdir] by hand.
* Your data processing code may continue to evolve as you're moving forward through your pipeline.
* You can amend/rewind/rewrite git commits of your processing code, but the corresponding files in [workdir] must be deleted.
* All files in the [workdir] are linked to the processing code that produced them.

## Limitations
``GitTrail`` can't police everything, so keep the following in mind:
- Data outside of [workdir], for example a database, is not tracked.
    If you're reading/writing data outside of [workdir] think about how you can trace that in your git history and/or [workdir] audit trail.
- Code outside of [repo] is not tracked.
    Unless your [repo] specifies exact dependency versions, your code may not be 100 % reproducible.
- Audittrail files are not cryptographically signed, so if you mess with them that's not tracked.

## File format specification
Two files are produced by each session:
* [session_number:04d].log  👉 Debug-level log file of a session
* [session_number:04d].json 👉 Session metadata
