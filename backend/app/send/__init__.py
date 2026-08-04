"""Stage 7: turn a verified draft into a real, sent email.

Deliberately isolated from the pipeline: nothing in `app/pipeline/` can reach
this module, so no generation path can send as a side effect.
"""
