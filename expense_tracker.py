#!/usr/bin/env python3
"""Expense Tracker - a simple CLI to manage personal finances.

Usage examples:
  python expense_tracker.py add --description "Lunch" --amount 12.50 --category Food
  python expense_tracker.py list
  python expense_tracker.py list --category Food
  python expense_tracker.py update --id 1 --amount 15
  python expense_tracker.py delete --id 1
  python expense_tracker.py summary
  python expense_tracker.py summary --month 5
  python expense_tracker.py budget --month 5 --amount 500
  python expense_tracker.py export --output expenses.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

DATA_FILE = Path(os.environ.get("EXPENSE_TRACKER_FILE", Path.home() / ".expense_tracker.json"))


def load_data() -> dict:
    if not DATA_FILE.exists():
        return {"expenses": [], "next_id": 1, "budgets": {}}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"expenses": [], "next_id": 1, "budgets": {}}
    data.setdefault("expenses", [])
    data.setdefault("next_id", max((e["id"] for e in data["expenses"]), default=0) + 1)
    data.setdefault("budgets", {})
    return data


def save_data(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def fmt_money(amount: float) -> str:
    return f"${amount:,.2f}"


def check_budget_warning(data: dict, month: int, year: int) -> str | None:
    key = f"{year}-{month:02d}"
    budget = data["budgets"].get(key)
    if budget is None:
        return None
    spent = sum(
        e["amount"] for e in data["expenses"]
        if datetime.fromisoformat(e["date"]).year == year
        and datetime.fromisoformat(e["date"]).month == month
    )
    if spent > budget:
        return f"WARNING: Budget exceeded for {key}! Spent {fmt_money(spent)} of {fmt_money(budget)} budget."
    if spent > budget * 0.8:
        return f"Note: {spent / budget * 100:.0f}% of {key} budget used ({fmt_money(spent)} of {fmt_money(budget)})."
    return None


# ---------- Commands ----------

def cmd_add(args, data):
    if args.amount <= 0:
        print("Error: amount must be positive.", file=sys.stderr)
        return 1
    now = datetime.now()
    expense = {
        "id": data["next_id"],
        "description": args.description,
        "amount": round(float(args.amount), 2),
        "category": args.category or "Uncategorized",
        "date": now.isoformat(timespec="seconds"),
    }
    data["expenses"].append(expense)
    data["next_id"] += 1
    save_data(data)
    print(f"Expense added (ID: {expense['id']})")
    warn = check_budget_warning(data, now.month, now.year)
    if warn:
        print(warn)
    return 0


def cmd_update(args, data):
    for e in data["expenses"]:
        if e["id"] == args.id:
            if args.description is not None:
                e["description"] = args.description
            if args.amount is not None:
                if args.amount <= 0:
                    print("Error: amount must be positive.", file=sys.stderr)
                    return 1
                e["amount"] = round(float(args.amount), 2)
            if args.category is not None:
                e["category"] = args.category
            save_data(data)
            print(f"Expense {args.id} updated.")
            return 0
    print(f"Error: expense {args.id} not found.", file=sys.stderr)
    return 1


def cmd_delete(args, data):
    before = len(data["expenses"])
    data["expenses"] = [e for e in data["expenses"] if e["id"] != args.id]
    if len(data["expenses"]) == before:
        print(f"Error: expense {args.id} not found.", file=sys.stderr)
        return 1
    save_data(data)
    print(f"Expense {args.id} deleted.")
    return 0


def cmd_list(args, data):
    expenses = data["expenses"]
    if args.category:
        expenses = [e for e in expenses if e["category"].lower() == args.category.lower()]
    if not expenses:
        print("No expenses found.")
        return 0
    print(f"{'ID':<4} {'Date':<11} {'Category':<15} {'Description':<30} {'Amount':>10}")
    print("-" * 72)
    for e in sorted(expenses, key=lambda x: x["date"]):
        date_str = datetime.fromisoformat(e["date"]).strftime("%Y-%m-%d")
        print(f"{e['id']:<4} {date_str:<11} {e['category'][:15]:<15} {e['description'][:30]:<30} {fmt_money(e['amount']):>10}")
    print("-" * 72)
    print(f"Total: {fmt_money(sum(e['amount'] for e in expenses))}")
    return 0


def cmd_summary(args, data):
    expenses = data["expenses"]
    year = datetime.now().year
    if args.month:
        if not 1 <= args.month <= 12:
            print("Error: month must be 1-12.", file=sys.stderr)
            return 1
        expenses = [
            e for e in expenses
            if datetime.fromisoformat(e["date"]).year == year
            and datetime.fromisoformat(e["date"]).month == args.month
        ]
        label = f"{datetime(year, args.month, 1).strftime('%B %Y')}"
    else:
        label = "All time"

    if args.category:
        expenses = [e for e in expenses if e["category"].lower() == args.category.lower()]

    total = sum(e["amount"] for e in expenses)
    print(f"Summary ({label}): {fmt_money(total)} across {len(expenses)} expense(s)")

    if expenses:
        by_cat: dict[str, float] = {}
        for e in expenses:
            by_cat[e["category"]] = by_cat.get(e["category"], 0) + e["amount"]
        print("\nBy category:")
        for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
            print(f"  {cat:<20} {fmt_money(amt):>10}")

    if args.month:
        key = f"{year}-{args.month:02d}"
        budget = data["budgets"].get(key)
        if budget is not None:
            remaining = budget - total
            print(f"\nBudget: {fmt_money(budget)} | Remaining: {fmt_money(remaining)}")
            if total > budget:
                print(f"WARNING: Over budget by {fmt_money(total - budget)}!")
    return 0


def cmd_budget(args, data):
    if not 1 <= args.month <= 12:
        print("Error: month must be 1-12.", file=sys.stderr)
        return 1
    year = args.year or datetime.now().year
    key = f"{year}-{args.month:02d}"
    if args.amount is None:
        budget = data["budgets"].get(key)
        if budget is None:
            print(f"No budget set for {key}.")
        else:
            print(f"Budget for {key}: {fmt_money(budget)}")
        return 0
    if args.amount < 0:
        print("Error: budget must be non-negative.", file=sys.stderr)
        return 1
    data["budgets"][key] = round(float(args.amount), 2)
    save_data(data)
    print(f"Budget for {key} set to {fmt_money(args.amount)}.")
    return 0


def cmd_export(args, data):
    out = Path(args.output)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "date", "category", "description", "amount"])
        for e in sorted(data["expenses"], key=lambda x: x["date"]):
            writer.writerow([e["id"], e["date"], e["category"], e["description"], e["amount"]])
    print(f"Exported {len(data['expenses'])} expense(s) to {out}")
    return 0


# ---------- CLI ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="expense-tracker", description="Simple CLI expense tracker")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="Add an expense")
    a.add_argument("--description", required=True)
    a.add_argument("--amount", type=float, required=True)
    a.add_argument("--category")

    u = sub.add_parser("update", help="Update an expense")
    u.add_argument("--id", type=int, required=True)
    u.add_argument("--description")
    u.add_argument("--amount", type=float)
    u.add_argument("--category")

    d = sub.add_parser("delete", help="Delete an expense")
    d.add_argument("--id", type=int, required=True)

    l = sub.add_parser("list", help="List expenses")
    l.add_argument("--category")

    s = sub.add_parser("summary", help="Summarize expenses")
    s.add_argument("--month", type=int, help="Month 1-12 (current year)")
    s.add_argument("--category")

    b = sub.add_parser("budget", help="Set or view a monthly budget")
    b.add_argument("--month", type=int, required=True)
    b.add_argument("--year", type=int)
    b.add_argument("--amount", type=float, help="Omit to view current budget")

    e = sub.add_parser("export", help="Export expenses to CSV")
    e.add_argument("--output", default="expenses.csv")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    data = load_data()
    return {
        "add": cmd_add,
        "update": cmd_update,
        "delete": cmd_delete,
        "list": cmd_list,
        "summary": cmd_summary,
        "budget": cmd_budget,
        "export": cmd_export,
    }[args.command](args, data)


if __name__ == "__main__":
    sys.exit(main())
