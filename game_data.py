"""Static game balance data."""

CHARACTERS = {
    1: {"hp": 100, "max_hp": 100, "atk": 12, "type": "v1"},
    2: {"hp": 120, "max_hp": 120, "atk": 14, "type": "v2"},
    3: {"hp": 140, "max_hp": 140, "atk": 20, "type": "minos"},
    4: {"hp": 130, "max_hp": 130, "atk": 15, "type": "gabriel"},
    999: {"hp": 99999, "max_hp": 99999, "atk": 99999, "type": "god"},
}

SKILL_GIFS = {
    "god": "CgACAgIAAyEFAATuFYO6AAIBFGqDDUvNeyrykVmC0FV6nUlidfHbAALSpgACh5HoS43Z8PpZnYurPQQ",
    "minos": "CgACAgIAAxkBAAOBaoTqBA5NC1-tj3E4kfpmln15A28AAgmqAAKU3yFI3isVHX0Wp6g9BA",
    "v2": "CgACAgIAAxkBAAOGaoTqtU_-i746Ps8je2RcBBQ4VlQAAgyqAAKU3yFIC7s2LleYvjM9BA",
    "v1": "CgACAgIAAxkBAAOIaoTq1KHEeqRI6UISOtOq-8QJWFIAAg2qAAKU3yFInZVWVcf-7Jo9BA",
}

GABRIEL_SKILL_GIFS = {
    "taunt": "CgACAgIAAxkBAAIBr2qQnjalZBR5bRgaK5IiCCiCGzJvAAIZqAACntiASPRp_9qvq65oPQQ",
    "rage": "CgACAgIAAxkBAAIBrWqQnGM82UmYQX4nLK1givkNcgPUAALerwACFHKBSAZUW1sJqK8QPQQ",
    "rage_transition": "CgACAgIAAxkBAAIBrmqQni6C2rIJZv3UPNlzDFbGsHGHAAIeqAACntiASKm-etV-JHxhPQQ",
}

SLOT_SYMBOLS = {
    "7️⃣": {"mult": 50, "weight": 2},
    "💎": {"mult": 15, "weight": 10},
    "💰": {"mult": 7, "weight": 18},
    "🍒": {"mult": 4, "weight": 30},
    "🍋": {"mult": 2, "weight": 40},
}
