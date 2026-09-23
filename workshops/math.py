"""Workshop arithmetic — must stay identical to amd/src/math.js."""

from __future__ import annotations

from typing import Any

NO_PEAK_MESSAGE = (
    "These numbers don't describe a business with a single best combination "
    "— try a smaller congestion value."
)
PRICE_BELOW_COST_MESSAGE = "You lose money on every unit of this product."
NEGATIVE_BEST_MESSAGE = (
    "With these numbers the best you can do is stop selling this product."
)
BLANK_FIELD_MESSAGE = "This field is required."
NO_INTERACTION_NOTE = "Products no longer interact."

REQUIRED_FIELDS = (
    "price1",
    "priceDrop1",
    "cost1",
    "price2",
    "priceDrop2",
    "cost2",
    "congestion",
    "fixedCost",
)

SAMPLE_BAKERY = {
    "name": "Bakery — March actuals",
    "price1": 30,
    "priceDrop1": 0.05,
    "cost1": 12.50,
    "price2": 16,
    "priceDrop2": 0.02,
    "cost2": 4.50,
    "congestion": 0.01,
    "fixedCost": 1000,
    "currentX": 200,
    "currentY": 150,
    "labels": {
        "product1": "Puffs",
        "product2": "Tea",
        "unit1": "puffs per day",
        "unit2": "teas per day",
        "currency": "₹",
    },
}


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def coefficients(config: dict) -> dict[str, float]:
    price1 = float(config["price1"])
    price_drop1 = float(config["priceDrop1"])
    cost1 = float(config["cost1"])
    price2 = float(config["price2"])
    price_drop2 = float(config["priceDrop2"])
    cost2 = float(config["cost2"])
    congestion = float(config["congestion"])
    fixed_cost = float(config["fixedCost"])
    return {
        "A": price1 - cost1,
        "B": price_drop1,
        "C": price2 - cost2,
        "D": price_drop2,
        "E": congestion,
        "F": fixed_cost,
    }


def profit(x: float, y: float, config: dict) -> float:
    c = coefficients(config)
    return c["A"] * x - c["B"] * x * x + c["C"] * y - c["D"] * y * y - c["E"] * x * y - c["F"]


def slope_x(x: float, y: float, config: dict) -> float:
    c = coefficients(config)
    return c["A"] - 2 * c["B"] * x - c["E"] * y


def slope_y(x: float, y: float, config: dict) -> float:
    c = coefficients(config)
    return c["C"] - 2 * c["D"] * y - c["E"] * x


def best_combination(config: dict) -> dict:
    c = coefficients(config)
    den = 4 * c["B"] * c["D"] - c["E"] * c["E"]
    if den <= 0:
        return {"error": "NO_PEAK", "message": NO_PEAK_MESSAGE, "den": den}
    best_x = (2 * c["D"] * c["A"] - c["E"] * c["C"]) / den
    best_y = (2 * c["B"] * c["C"] - c["E"] * c["A"]) / den
    return {"bestX": best_x, "bestY": best_y, "den": den}


def monthly_gain(best_profit: float, current_profit: float) -> int:
    return round((best_profit - current_profit) * 30 / 50) * 50


def cost_of_being_off(n: float, config: dict) -> float:
    return coefficients(config)["B"] * n * n


def validate_config(config: dict) -> dict:
    errors: dict[str, str] = {}
    warnings: list[str] = []
    notes: list[str] = []

    for field in REQUIRED_FIELDS:
        if _num(config.get(field)) is None:
            errors[field] = BLANK_FIELD_MESSAGE

    if errors:
        return {
            "ok": False,
            "canPlot": False,
            "errors": errors,
            "warnings": warnings,
            "notes": notes,
        }

    price1 = float(config["price1"])
    cost1 = float(config["cost1"])
    price2 = float(config["price2"])
    cost2 = float(config["cost2"])
    congestion = float(config["congestion"])

    if price1 < cost1:
        warnings.append(PRICE_BELOW_COST_MESSAGE)
    if price2 < cost2:
        warnings.append(PRICE_BELOW_COST_MESSAGE)
    if congestion == 0:
        notes.append(NO_INTERACTION_NOTE)

    peak = best_combination(config)
    clamped = {"bestX": None, "bestY": None}
    if peak.get("error") == "NO_PEAK":
        return {
            "ok": False,
            "canPlot": False,
            "errors": {"congestion": peak["message"]},
            "warnings": warnings,
            "notes": notes,
            "peak": peak,
        }

    best_x = peak["bestX"]
    best_y = peak["bestY"]
    if best_x < 0:
        warnings.append(NEGATIVE_BEST_MESSAGE)
        best_x = 0
    if best_y < 0:
        warnings.append(NEGATIVE_BEST_MESSAGE)
        best_y = 0
    clamped = {"bestX": best_x, "bestY": best_y}

    return {
        "ok": True,
        "canPlot": True,
        "errors": errors,
        "warnings": warnings,
        "notes": notes,
        "peak": peak,
        "clamped": clamped,
    }
