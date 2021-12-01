[![pipeline](https://github.com/michaelosthege/gittrail/workflows/pipeline/badge.svg)](https://github.com/michaelosthege/gittrail/actions)


# `gittrail` - Linking data pipeline outputs to git history
Versioning of code with git is easy, versioning data pipeline inputs/outputs is hard.

``GitTrail`` helps you to maintain a traceable data lineage by enforcing a
link between data files and the commit history of your processing code.

Like blockchain, but easier.

## How it works
``GitTrail`` is used as a context manager around the code that executes your data processing:

```python
with GitTrail(
    repo="/path/to/my_data_processing_code",
    data="/path/to/my_data_storage",
):
    # TODO: download the pipeline inputs to [data]
```

Inbetween GitTrail sessions you may edit your pipeline code, make commits etc.

When your next data processing stage is ready:

```python
with GitTrail(
    repo="/path/to/my_data_processing_code",
    data="/path/to/my_data_storage",
):
    # TODO: run data analysis on inputs from [data]
    # TODO: save results to [data]
```

Upon entering the context ``GitTrail`` attaches a log handler to re-route all logging into a `*.log` file in a subdirectory of [data].
When the context exits, the logger is detached and session metadata is stored in a `*.json` file.
The metadata includes the current git commit of your [repo], as well MD5 hashes of the files inside [data].

Within the context, the following two rules are enforced:
1. The working tree of your code [repo] must be clean (no uncommitted changes).
2. All files currently found in [data] must have been created/changed in a previous ``GitTrail`` context.

Taken together this means that:
* You're not allowed to add/edit/anything in [data] by hand.
* Your data processing code may continue to evolve as you're moving forward through your pipeline.
* You can amend/rewind/rewrite git commits of your processing code, but the corresponding files in [data] and the audit trail session file must be deleted.
* All files in the [data] are linked to the processing code that produced them.

## Limitations
``GitTrail`` can't police everything, so keep the following in mind:
- Data outside of [data], for example a database, is not tracked.
    If you're reading/writing data outside of [data] think about how you can trace that in your git history and/or [data] audit trail.
- Code outside of [repo] is not tracked.
    Unless your [repo] specifies exact dependency versions, your code may not be 100 % reproducible.
- Audit trail files are not cryptographically signed, so if you mess with them that's not tracked.
