import json
import os
import sqlite3
import sys
import threading
from datetime import datetime
from pathlib import Path

import webview


APP_NAME = "Моя крамниця"
if sys.platform == "darwin":
    DATA_DIR = Path.home() / "Library" / "Application Support" / "MoiaKramnytsia"
elif sys.platform == "win32":
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MoiaKramnytsia"
else:
    DATA_DIR = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "MoiaKramnytsia"
DB_PATH = DATA_DIR / "shop.sqlite3"
_BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_RESOURCE_PATHS = (
    Path(__file__).resolve().with_name("index.html"),
    _BUNDLE_DIR / "index.html",
    _BUNDLE_DIR.parent / "Resources" / "index.html",
)
HTML_PATH = next((path for path in _RESOURCE_PATHS if path.is_file()), _RESOURCE_PATHS[0])
EMPTY_STATE = {"records": [], "products": [], "customers": [], "tasks": [],
               "orders": [], "shift": None, "shiftHistory": []}


class ShopApi:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._window = None
        self._db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("""CREATE TABLE IF NOT EXISTS desktop_state(
            id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")
        self._db.commit()

    def _read_state(self):
        row = self._db.execute("SELECT payload FROM desktop_state WHERE id=1").fetchone()
        if row:
            state = json.loads(row["payload"])
            return {**EMPTY_STATE, **state}
        return self._migrate_legacy_data()

    def _migrate_legacy_data(self):
        state = {**EMPTY_STATE}
        tables = {row[0] for row in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "transactions" in tables:
            for row in self._db.execute("SELECT * FROM transactions"):
                state["records"].append({
                    "id": str(row["id"]), "date": row["entry_date"],
                    "type": "income" if row["kind"] == "Додатковий дохід" else "expense",
                    "title": f"{row['category']}: {row['description']}",
                    "amount": row["amount"], "method": row["payment"],
                    "createdAt": row["created_at"],
                })
        if "products" in tables:
            for row in self._db.execute("SELECT * FROM products"):
                state["products"].append({
                    "id": str(row["id"]), "name": row["name"], "price": row["price"],
                    "cost": row["cost"], "qty": row["qty"], "minimum": row["min_qty"],
                    "unit": row["unit"], "sku": row["sku"], "note": row["note"],
                })
        if "customers" in tables:
            for row in self._db.execute("SELECT * FROM customers"):
                state["customers"].append({
                    "id": str(row["id"]), "name": row["name"], "phone": row["phone"],
                    "messenger": row["messenger"], "note": row["note"],
                })
        if "tasks" in tables:
            for row in self._db.execute("SELECT * FROM tasks"):
                state["tasks"].append({
                    "id": str(row["id"]), "title": row["title"], "date": row["task_date"],
                    "note": row["note"], "done": bool(row["done"]),
                })
        if "orders" in tables:
            for row in self._db.execute("SELECT * FROM orders"):
                state["orders"].append({
                    "id": str(row["id"]), "date": row["order_date"],
                    "customer": row["customer_name"], "phone": row["phone"],
                    "product": row["item"], "amount": row["total"], "cost": row["cost"],
                    "status": row["status"], "payment": row["payment"],
                    "paid": bool(row["paid"]), "carrier": row["carrier"],
                    "tracking": row["tracking"], "address": row["address"],
                    "note": row["note"], "createdAt": row["created_at"],
                })
        if "shifts" in tables:
            row = self._db.execute("SELECT * FROM shifts ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                state["shift"] = {
                    "date": row["shift_date"], "time": row["opened_at"][11:16],
                    "openingCash": row["opening_cash"], "closedAt": row["closed_at"],
                    "expectedCash": row["expected_cash"], "actualCash": row["counted_cash"],
                    "difference": row["difference"],
                }
        return state

    def _store_state(self, state):
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        with self._db:
            self._db.execute("""INSERT INTO desktop_state(id,payload,updated_at) VALUES(1,?,?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at""",
                (payload, datetime.now().isoformat(timespec="seconds")))

    def get_data(self):
        with self.lock:
            state = self._read_state()
            row = self._db.execute("SELECT 1 FROM desktop_state WHERE id=1").fetchone()
            if not row:
                self._store_state(state)
            return state

    def save_data(self, serialized):
        try:
            state = json.loads(serialized)
            if not isinstance(state, dict):
                raise ValueError("Неправильний формат даних.")
            for key in ("records", "products", "customers", "tasks", "orders", "shiftHistory"):
                if key not in state:
                    state[key] = []
                if not isinstance(state[key], list) or len(state[key]) > 100000:
                    raise ValueError("У записах є неправильний або завеликий список.")
            state.setdefault("shift", None)
            if len(serialized) > 20_000_000:
                raise ValueError("Розмір даних перевищує дозволений.")
            with self.lock:
                self._store_state(state)
            return {"ok": True}
        except (json.JSONDecodeError, ValueError, sqlite3.Error) as error:
            return {"ok": False, "error": str(error)}

    def backup(self):
        if not self._window:
            return {"ok": False, "error": "Вікно програми ще не готове."}
        selected = self._window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=f"kramnytsia-backup-{datetime.now():%Y-%m-%d}.json",
            file_types=("JSON backup (*.json)",))
        if not selected:
            return {"ok": False, "cancelled": True}
        path = selected[0] if isinstance(selected, (list, tuple)) else selected
        try:
            with self.lock:
                Path(path).write_text(json.dumps(self._read_state(), ensure_ascii=False, indent=2),
                                      encoding="utf-8")
            return {"ok": True, "path": str(path)}
        except (OSError, sqlite3.Error) as error:
            return {"ok": False, "error": str(error)}

    def restore(self):
        if not self._window:
            return {"ok": False, "error": "Вікно програми ще не готове."}
        selected = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=("JSON backup (*.json)",))
        if not selected:
            return {"ok": False, "cancelled": True}
        path = selected[0] if isinstance(selected, (list, tuple)) else selected
        try:
            state = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(state, dict) or any(
                not isinstance(state.get(key, []), list)
                for key in ("records", "products", "customers", "tasks", "orders", "shiftHistory")
            ):
                raise ValueError("Цей файл не схожий на резервну копію програми.")
            state = {**EMPTY_STATE, **state}
            with self.lock:
                self._store_state(state)
            return {"ok": True, "data": state}
        except (OSError, json.JSONDecodeError, ValueError, sqlite3.Error) as error:
            return {"ok": False, "error": str(error)}

    def close(self):
        with self.lock:
            self._db.close()


def main():
    if not HTML_PATH.is_file():
        raise FileNotFoundError(f"Не знайдено інтерфейс програми: {HTML_PATH}")
    api = ShopApi()
    initial_state = json.dumps(api.get_data(), ensure_ascii=True, separators=(",", ":"))
    initial_state = initial_state.replace("</", "<\\/")
    html = HTML_PATH.read_text(encoding="utf-8").replace(
        "<head>",
        f"<head><script>window.__desktopApp=true;window.__initialState={initial_state};</script>",
        1,
    )
    window = webview.create_window(
        f"{APP_NAME} — помічник магазину",
        html=html,
        js_api=api,
        width=1360,
        height=860,
        min_size=(1000, 680),
        background_color="#f5f6f8",
    )
    api._window = window

    try:
        gui = "edgechromium" if sys.platform == "win32" else "cocoa" if sys.platform == "darwin" else None
        webview.start(debug=False, gui=gui)
    finally:
        api.close()


if __name__ == "__main__":
    main()
