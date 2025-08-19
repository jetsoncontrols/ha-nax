from deepmerge import Merger


def merge_dict(config: Merger, path, base, nxt):
    # If the incoming dict is empty or None, treat as no-op instead of clearing existing data
    if not nxt:
        return base  # was nxt
    for k, v in nxt.items():
        if k not in base:
            base[k] = v
        # if v is dict:
        #     merge_dict(config, [*path, k], base[k], v)
        else:
            base[k] = config.value_strategy([*path, k], base[k], v)
    return base


nax_custom_merger: Merger = Merger(
    [(list, "append"), (dict, merge_dict), (set, "union")], ["override"], ["override"]
)
