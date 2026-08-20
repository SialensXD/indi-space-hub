"""Static game balance data."""

CHARACTERS = {
    1: {"hp": 100, "max_hp": 100, "atk": 15, "type": "souls"},
    2: {"hp": 95, "max_hp": 95, "atk": 12, "type": "light"},
    3: {"hp": 1, "max_hp": 1, "atk": 0.1, "type": "karma"},
    4: {"hp": 100, "max_hp": 100, "atk": 15, "type": "vampire"},
    5: {"hp": 125, "max_hp": 125, "atk": 15, "type": "enrage"},
    6: {"hp": 140, "max_hp": 140, "atk": 20, "type": "berserk"},
    999: {"hp": 99999, "max_hp": 99999, "atk": 99999, "type": "god"},
}

SKILL_GIFS = {
    "god": "CgACAgIAAyEFAATuFYO6AAIBFGqDDUvNeyrykVmC0FV6nUlidfHbAALSpgACh5HoS43Z8PpZnYurPQQ",
    "berserk": "CgACAgIAAxkBAAOBaoTqBA5NC1-tj3E4kfpmln15A28AAgmqAAKU3yFI3isVHX0Wp6g9BA",
    "enrage": "CgACAgIAAxkBAAOGaoTqtU_-i746Ps8je2RcBBQ4VlQAAgyqAAKU3yFIC7s2LleYvjM9BA",
    "vampire": "CgACAgIAAxkBAAOIaoTq1KHEeqRI6UISOtOq-8QJWFIAAg2qAAKU3yFInZVWVcf-7Jo9BA",
    "karma": "CgACAgIAAxkBAAOKaoTrno_MtK1bhhlRDzzAqadPMcUAAg6qAAKU3yFIeGnOjHQrPe09BA",
    "light": "CgACAgIAAxkBAAONaoTr07Wre4FlnhDNQTqAxiGeHCUAAg-qAAKU3yFIq1sILGVxN1k9BA",
    "souls": "CgACAgIAAxkBAAOEaoTqcQ6ZdM6aAAEcAWN07ZQFOy6jAAILqgAClN8hSEhkcIg6sjqEPQQ",
}

SLOT_SYMBOLS = {
    "7️⃣": {"mult": 50, "weight": 2},
    "💎": {"mult": 15, "weight": 10},
    "💰": {"mult": 7, "weight": 18},
    "🍒": {"mult": 4, "weight": 30},
    "🍋": {"mult": 2, "weight": 40},
}
