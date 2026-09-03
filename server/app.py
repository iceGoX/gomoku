from __future__ import annotations

import argparse
import json
import mimetypes
import queue
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    from .game_engine import BLACK, WHITE, create_game, place_stone, public_game, resign, undo_last_move
except ImportError:
    from game_engine import BLACK, WHITE, create_game, place_stone, public_game, resign, undo_last_move

ROOT = Path(__file__).resolve().parents[1]
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_CODE_RE = re.compile(r"^[A-Z2-9]{6}$")
NAME_RE = re.compile(r"^[^\x00-\x1f<>]{1,16}$")
MAX_BODY_BYTES = 16 * 1024
STATIC_FILES = {
    "/": ROOT / "index.html",
    "/index.html": ROOT / "index.html",
    "/styles.css": ROOT / "styles.css",
    "/game.js": ROOT / "game.js",
}

rooms: dict[str, dict] = {}
subscribers: dict[str, list[dict]] = defaultdict(list)
rooms_lock = threading.RLock()
rate_lock = threading.Lock()
request_times: dict[str, deque] = defaultdict(deque)


def now() -> float:
    return time.time()


def make_room_code() -> str:
    for _ in range(100):
        code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(6))
        if code not in rooms:
            return code
    raise RuntimeError("无法生成唯一房间号")


def make_player(name: str, color: int, is_host: bool) -> dict:
    return {
        "id": secrets.token_urlsafe(12),
        "token": secrets.token_urlsafe(32),
        "name": name,
        "color": color,
        "isHost": is_host,
        "connections": 0,
    }


def public_room(room: dict) -> dict:
    return {
        "code": room["code"],
        "mode": room["mode"],
        "status": room["status"],
        "version": room["version"],
        "createdAt": room["createdAt"],
        "updatedAt": room["updatedAt"],
        "lastEvent": room.get("lastEvent"),
        "rematchVotes": list(room.get("rematchVotes", [])),
        "seatSwapRequestPlayerId": room.get("seatSwapRequestPlayerId"),
        "players": [
            {
                "id": player["id"],
                "name": player["name"],
                "color": player["color"],
                "isHost": player["isHost"],
                "connected": player["connections"] > 0,
            }
            for player in room["players"]
        ],
        "game": public_game(room["game"]) if room["game"] else None,
    }


def set_event(room: dict, event_type: str, message: str, player_id: str | None = None) -> None:
    room["eventSequence"] = room.get("eventSequence", 0) + 1
    room["lastEvent"] = {
        "id": room["eventSequence"],
        "type": event_type,
        "message": message,
        "playerId": player_id,
        "time": int(now()),
    }


def find_player(room: dict, player_id: str | None) -> dict | None:
    return next((player for player in room["players"] if player["id"] == player_id), None)


def authenticate(room: dict, player_id: str | None, token: str | None) -> dict | None:
    player = find_player(room, player_id)
    if not player or not token:
        return None
    return player if secrets.compare_digest(player["token"], token) else None


def publish(room_code: str) -> None:
    with rooms_lock:
        room = rooms.get(room_code)
        if not room:
            return
        payload = json.dumps(public_room(room), ensure_ascii=False, separators=(",", ":"))
        targets = list(subscribers.get(room_code, []))
    for target in targets:
        channel = target["queue"]
        try:
            channel.put_nowait(payload)
        except queue.Full:
            try:
                channel.get_nowait()
                channel.put_nowait(payload)
            except (queue.Empty, queue.Full):
                pass


def cleanup_rooms() -> None:
    while True:
        time.sleep(300)
        current = now()
        with rooms_lock:
            expired = []
            for code, room in rooms.items():
                limit = 7200 if room["status"] == "waiting" else 86400
                if room["status"] == "finished":
                    limit = 3600
                if current - room["updatedAt"] > limit and not subscribers.get(code):
                    expired.append(code)
            for code in expired:
                rooms.pop(code, None)
                subscribers.pop(code, None)


class GomokuServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "GomokuRoomServer/1.0"

    def log_message(self, format_string: str, *args) -> None:
        print(f"{self.log_date_time_string()} {self.client_address[0]} {format_string % args}", flush=True)

    def normalized_path(self) -> str:
        path = urlparse(self.path).path
        if path == "/gomoku":
            return "/"
        if path.startswith("/gomoku/"):
            return path[len("/gomoku") :]
        return path

    def client_ip(self) -> str:
        forwarded = self.headers.get("X-Real-IP")
        return forwarded.strip() if forwarded else self.client_address[0]

    def is_rate_limited(self) -> bool:
        ip = self.client_ip()
        current = now()
        with rate_lock:
            entries = request_times[ip]
            while entries and current - entries[0] > 60:
                entries.popleft()
            if len(entries) >= 180:
                return True
            entries.append(current)
        return False

    def send_json(self, status: int, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("请求长度无效") from error
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("请求内容为空或过大")
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("请求不是有效 JSON") from error
        if not isinstance(data, dict):
            raise ValueError("请求必须是 JSON 对象")
        return data

    def auth_headers(self) -> tuple[str | None, str | None]:
        return self.headers.get("X-Player-Id"), self.headers.get("X-Player-Token")

    def room_or_error(self, code: str) -> dict | None:
        room = rooms.get(code)
        if not room:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "ROOM_NOT_FOUND", "message": "房间不存在或已经过期。"})
            return None
        return room

    def authenticated_room(self, code: str) -> tuple[dict | None, dict | None]:
        room = self.room_or_error(code)
        if not room:
            return None, None
        player_id, token = self.auth_headers()
        player = authenticate(room, player_id, token)
        if not player:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "UNAUTHORIZED", "message": "玩家身份已失效，请重新加入。"})
            return None, None
        return room, player

    def do_GET(self) -> None:
        path = self.normalized_path()
        if path == "/api/health":
            self.send_json(HTTPStatus.OK, {"ok": True})
            return
        event_match = re.fullmatch(r"/api/rooms/([A-Z2-9]{6})/events", path)
        if event_match:
            self.handle_events(event_match.group(1))
            return
        static_path = STATIC_FILES.get(path)
        if static_path and static_path.is_file():
            payload = static_path.read_bytes()
            content_type = mimetypes.guess_type(str(static_path))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND", "message": "页面不存在。"})

    def do_POST(self) -> None:
        if self.is_rate_limited():
            self.send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "RATE_LIMITED", "message": "操作过于频繁，请稍后再试。"})
            return
        path = self.normalized_path()
        try:
            data = self.read_json()
            if path == "/api/rooms":
                self.create_room(data)
                return
            route = re.fullmatch(r"/api/rooms/([A-Z2-9]{6})/(join|start|place|resign|rematch|swap|undo|leave)", path)
            if route:
                action = route.group(2)
                getattr(self, f"room_{action}")(route.group(1), data)
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND", "message": "接口不存在。"})
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "INVALID_REQUEST", "message": str(error)})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "SERVER_ERROR", "message": "服务器暂时无法处理请求。"})

    def create_room(self, data: dict) -> None:
        name = str(data.get("name", "")).strip()
        mode = data.get("mode")
        if not NAME_RE.fullmatch(name):
            raise ValueError("昵称需要为 1–16 个可见字符。")
        if mode not in {"normal", "professional"}:
            raise ValueError("请选择有效的规则模式。")
        with rooms_lock:
            code = make_room_code()
            player = make_player(name, BLACK, True)
            room = {
                "code": code,
                "mode": mode,
                "status": "waiting",
                "players": [player],
                "game": None,
                "version": 1,
                "createdAt": now(),
                "updatedAt": now(),
                "eventSequence": 0,
                "lastEvent": None,
                "rematchVotes": set(),
                "seatSwapRequestPlayerId": None,
            }
            set_event(room, "ROOM_CREATED", f"{name} 创建了房间。", player["id"])
            rooms[code] = room
            response = {"room": public_room(room), "playerId": player["id"], "playerToken": player["token"]}
        self.send_json(HTTPStatus.CREATED, response)

    def room_join(self, code: str, data: dict) -> None:
        name = str(data.get("name", "")).strip()
        if not NAME_RE.fullmatch(name):
            raise ValueError("昵称需要为 1–16 个可见字符。")
        with rooms_lock:
            room = self.room_or_error(code)
            if not room:
                return
            if room["status"] != "waiting" or len(room["players"]) >= 2:
                self.send_json(HTTPStatus.CONFLICT, {"error": "ROOM_FULL", "message": "房间已经满员或已开局。"})
                return
            player = make_player(name, WHITE, False)
            room["players"].append(player)
            room["version"] += 1
            room["updatedAt"] = now()
            set_event(room, "PLAYER_JOINED", f"{name} 已加入房间。", player["id"])
            response = {"room": public_room(room), "playerId": player["id"], "playerToken": player["token"]}
        self.send_json(HTTPStatus.OK, response)
        publish(code)

    def room_start(self, code: str, data: dict) -> None:
        with rooms_lock:
            room, player = self.authenticated_room(code)
            if not room or not player:
                return
            if not player["isHost"]:
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "HOST_ONLY", "message": "只有房主可以开始游戏。"})
                return
            if room["status"] != "waiting" or len(room["players"]) != 2:
                self.send_json(HTTPStatus.CONFLICT, {"error": "NOT_READY", "message": "需要两名玩家都入席后才能开始。"})
                return
            room["game"] = create_game(room["mode"])
            room["status"] = "playing"
            room["seatSwapRequestPlayerId"] = None
            room["version"] += 1
            room["updatedAt"] = now()
            set_event(room, "GAME_STARTED", "对局开始，黑方先行。", player["id"])
            response = public_room(room)
        self.send_json(HTTPStatus.OK, {"room": response})
        publish(code)

    def room_place(self, code: str, data: dict) -> None:
        row, col = data.get("row"), data.get("col")
        expected_version = data.get("expectedVersion")
        if not isinstance(row, int) or not isinstance(col, int):
            raise ValueError("落点坐标无效。")
        with rooms_lock:
            room, player = self.authenticated_room(code)
            if not room or not player:
                return
            if room["status"] != "playing" or not room["game"]:
                self.send_json(HTTPStatus.CONFLICT, {"error": "GAME_NOT_PLAYING", "message": "当前没有进行中的对局。"})
                return
            if expected_version != room["version"]:
                self.send_json(HTTPStatus.CONFLICT, {"error": "STALE_STATE", "message": "棋局已更新，请按最新棋盘重新选择落点。", "room": public_room(room)})
                return
            success, message = place_stone(room["game"], player["color"], row, col)
            if not success:
                self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "ILLEGAL_MOVE", "message": message})
                return
            room["status"] = room["game"]["status"]
            room["version"] += 1
            room["updatedAt"] = now()
            set_event(room, "STONE_PLACED", message, player["id"])
            response = public_room(room)
        self.send_json(HTTPStatus.OK, {"room": response})
        publish(code)

    def room_resign(self, code: str, data: dict) -> None:
        with rooms_lock:
            room, player = self.authenticated_room(code)
            if not room or not player:
                return
            if not room["game"]:
                self.send_json(HTTPStatus.CONFLICT, {"error": "GAME_NOT_STARTED", "message": "对局尚未开始。"})
                return
            success, message = resign(room["game"], player["color"])
            if not success:
                self.send_json(HTTPStatus.CONFLICT, {"error": "GAME_FINISHED", "message": message})
                return
            room["status"] = "finished"
            room["version"] += 1
            room["updatedAt"] = now()
            set_event(room, "PLAYER_RESIGNED", message, player["id"])
            response = public_room(room)
        self.send_json(HTTPStatus.OK, {"room": response})
        publish(code)

    def room_rematch(self, code: str, data: dict) -> None:
        with rooms_lock:
            room, player = self.authenticated_room(code)
            if not room or not player:
                return
            if room["status"] != "finished":
                self.send_json(HTTPStatus.CONFLICT, {"error": "GAME_NOT_FINISHED", "message": "本局尚未结束。"})
                return
            room["rematchVotes"].add(player["id"])
            if len(room["rematchVotes"]) == 2:
                room["game"] = create_game(room["mode"])
                room["status"] = "playing"
                room["rematchVotes"].clear()
                room["seatSwapRequestPlayerId"] = None
                message = "双方已确认，再来一局。"
                event_type = "REMATCH_STARTED"
            else:
                message = f"{player['name']} 邀请再来一局。"
                event_type = "REMATCH_REQUESTED"
            room["version"] += 1
            room["updatedAt"] = now()
            set_event(room, event_type, message, player["id"])
            response = public_room(room)
        self.send_json(HTTPStatus.OK, {"room": response})
        publish(code)

    def room_swap(self, code: str, data: dict) -> None:
        with rooms_lock:
            room, player = self.authenticated_room(code)
            if not room or not player:
                return
            if room["status"] not in {"waiting", "finished"}:
                self.send_json(HTTPStatus.CONFLICT, {"error": "SEAT_SWAP_UNAVAILABLE", "message": "只能在开局前或本局结束后交换先后手。"})
                return
            if len(room["players"]) != 2:
                self.send_json(HTTPStatus.CONFLICT, {"error": "NOT_READY", "message": "两名玩家都入席后才能交换先后手。"})
                return

            requester_id = room.get("seatSwapRequestPlayerId")
            if requester_id == player["id"]:
                room["seatSwapRequestPlayerId"] = None
                event_type = "SEAT_SWAP_CANCELLED"
                message = f"{player['name']} 取消了交换先后手请求。"
            elif requester_id:
                for participant in room["players"]:
                    participant["color"] = WHITE if participant["color"] == BLACK else BLACK
                room["seatSwapRequestPlayerId"] = None
                room["rematchVotes"].clear()
                if room["status"] == "finished":
                    room["game"] = create_game(room["mode"])
                    room["status"] = "playing"
                    event_type = "SEATS_SWAPPED_AND_REMATCH_STARTED"
                    message = "双方已交换先后手，下一局已开始，黑方先行。"
                else:
                    event_type = "SEATS_SWAPPED"
                    message = "双方已交换先后手。"
            else:
                room["seatSwapRequestPlayerId"] = player["id"]
                event_type = "SEAT_SWAP_REQUESTED"
                message = f"{player['name']} 请求交换先后手。"

            room["version"] += 1
            room["updatedAt"] = now()
            set_event(room, event_type, message, player["id"])
            response = public_room(room)
        self.send_json(HTTPStatus.OK, {"room": response})
        publish(code)

    def room_undo(self, code: str, data: dict) -> None:
        with rooms_lock:
            room, player = self.authenticated_room(code)
            if not room or not player:
                return
            game = room.get("game")
            if room["status"] != "playing" or not game:
                self.send_json(HTTPStatus.CONFLICT, {"error": "GAME_NOT_PLAYING", "message": "只能在进行中的对局里悔棋。"})
                return
            if not game["moveHistory"]:
                self.send_json(HTTPStatus.CONFLICT, {"error": "UNDO_UNAVAILABLE", "message": "当前没有可撤销的落子。"})
                return
            if player["color"] == game["moveHistory"][-1]["color"]:
                self.send_json(HTTPStatus.FORBIDDEN, {"error": "UNDO_NOT_OPPONENT", "message": "只能由未落下最后一子的对方悔棋。"})
                return
            success, message = undo_last_move(game)
            if not success:
                self.send_json(HTTPStatus.CONFLICT, {"error": "UNDO_UNAVAILABLE", "message": message})
                return

            room["version"] += 1
            room["updatedAt"] = now()
            set_event(room, "UNDO_APPLIED", message, player["id"])
            response = public_room(room)
        self.send_json(HTTPStatus.OK, {"room": response})
        publish(code)

    def room_leave(self, code: str, data: dict) -> None:
        with rooms_lock:
            room, player = self.authenticated_room(code)
            if not room or not player:
                return
            if room["status"] == "playing" and room["game"]:
                resign(room["game"], player["color"])
                room["status"] = "finished"
            elif room["status"] == "waiting":
                room["players"] = [item for item in room["players"] if item["id"] != player["id"]]
                if not room["players"]:
                    rooms.pop(code, None)
                    self.send_json(HTTPStatus.OK, {"left": True})
                    return
                room["players"][0]["isHost"] = True
                room["players"][0]["color"] = BLACK
            room["version"] += 1
            room["updatedAt"] = now()
            set_event(room, "PLAYER_LEFT", f"{player['name']} 已离开房间。", player["id"])
        self.send_json(HTTPStatus.OK, {"left": True})
        publish(code)

    def handle_events(self, code: str) -> None:
        player_id = self.headers.get("X-Player-Id")
        token = self.headers.get("X-Player-Token")
        with rooms_lock:
            room = rooms.get(code)
            player = authenticate(room, player_id, token) if room else None
            if not room or not player:
                self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "UNAUTHORIZED", "message": "玩家身份无效。"})
                return
            channel: queue.Queue = queue.Queue(maxsize=4)
            target = {"playerId": player["id"], "queue": channel}
            subscribers[code].append(target)
            player["connections"] += 1
            channel.put_nowait(json.dumps(public_room(room), ensure_ascii=False, separators=(",", ":")))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            while True:
                try:
                    payload = channel.get(timeout=20)
                    self.wfile.write(f"event: room\ndata: {payload}\n\n".encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            with rooms_lock:
                if target in subscribers.get(code, []):
                    subscribers[code].remove(target)
                active_room = rooms.get(code)
                active_player = find_player(active_room, player["id"]) if active_room else None
                if active_player:
                    active_player["connections"] = max(0, active_player["connections"] - 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="五子棋在线房间服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    threading.Thread(target=cleanup_rooms, daemon=True).start()
    server = GomokuServer((args.host, args.port), Handler)
    print(f"Gomoku server listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
