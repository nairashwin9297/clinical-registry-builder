def class_label(class_id):
    """'fracture_fixation' -> 'Fracture fixation' (same as the frontend's classLabel)."""
    s = class_id.replace("_", " ")
    return s[:1].upper() + s[1:]
