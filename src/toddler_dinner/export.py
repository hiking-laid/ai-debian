"""Render Flow 2 output to human-readable exports (Markdown / CSV)."""

from __future__ import annotations

import csv
import io

from toddler_dinner.core import PlanResult
from toddler_dinner.models import Recipe


def recipe_text(recipe: Recipe) -> str:
    """Human-readable recipe: title + ingredients + equipment + numbered method + tips."""
    lines = [recipe.title]
    if recipe.ingredients:
        lines += ["", "Ingredients:"]
        for ing in recipe.ingredients:
            qty = f"{ing.quantity:g} {ing.unit}".strip()
            lines.append(f"- {qty} {ing.name}".rstrip())
    if recipe.equipment:
        lines += ["", "Equipment:"]
        for item in recipe.equipment:
            lines.append(f"- {item}")
    if recipe.steps:
        lines += ["", "Method:"]
        for i, step in enumerate(recipe.steps, 1):
            lines.append(f"{i}. {step}")
    if recipe.tips:
        lines += ["", "Tips:"]
        for tip in recipe.tips:
            lines.append(f"- {tip}")
    return "\n".join(lines)


def groceries_markdown(plan: PlanResult) -> str:
    menu = plan.menu
    lines = [f"# Dinner plan — {menu.for_date.isoformat()}", ""]
    for item in menu.items:
        lines.append(f"## {item.recipe.title}")
        if item.recipe.steps:
            lines.append("")
            for i, step in enumerate(item.recipe.steps, 1):
                lines.append(f"{i}. {step}")
    lines += ["", "## 🛒 Groceries to buy", ""]
    if plan.groceries.items:
        for g in plan.groceries.items:
            qty = f"{g.quantity:g} {g.unit}".strip()
            lines.append(f"- [ ] {g.name} — {qty}")
    else:
        lines.append("- (nothing needed — everything is in the fridge)")
    if plan.already_have:
        lines += ["", f"_Already in fridge: {', '.join(plan.already_have)}_"]
    return "\n".join(lines) + "\n"


def groceries_csv(plan: PlanResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "quantity", "unit"])
    for g in plan.groceries.items:
        writer.writerow([g.name, g.quantity, g.unit])
    return buf.getvalue()
