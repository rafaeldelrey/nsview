def get_list_index(list_to_check, item_value, default_return):
    try:
        return list_to_check.index(item_value)
    except ValueError:
        return default_return
