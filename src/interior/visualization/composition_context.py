"""Reusable furniture relationships for complete functional-area photographs."""

FAMILIES = (
    frozenset(('bed', 'bunk_bed', 'desk', 'chair', 'wardrobe', 'dresser', 'bookcase', 'nightstand')),
    frozenset(('cooker', 'sink', 'dishwasher', 'fridge', 'refrigerator', 'kitchen_cabinet')),
    # A television faces the sofa across the room; it belongs in a reverse
    # photograph, not a mandatory hull around a sofa-facing photograph.
    frozenset(('sofa', 'coffee_table', 'table')),
)


def related_purposes(hero, other):
    """Only suggest companions; geometry must also prove proximity/no partition."""
    return any(hero in family and other in family for family in FAMILIES)
