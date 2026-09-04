import json
import queue
import threading
import unittest
import urllib.error
import urllib.request

from server.app import (
    RATE_LIMIT_WINDOW_SECONDS,
    STREAM_CLOSED,
    WAITING_ROOM_TTL_SECONDS,
    MAX_ACTIVE_ROOMS_PER_IP,
    GomokuServer,
    Handler,
    cleanup_expired_state,
    request_times,
    rooms,
    subscribers,
)


class ServerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = GomokuServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        rooms.clear()
        subscribers.clear()
        request_times.clear()

    def request(self, path, body=None, session=None):
        headers = {}
        method = "GET"
        data = None
        if body is not None:
            method = "POST"
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if session:
            headers["X-Player-Id"] = session["playerId"]
            headers["X-Player-Token"] = session["playerToken"]
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def create_room(self, mode="normal"):
        status, result = self.request("/api/rooms", {"name": "房主", "mode": mode})
        self.assertEqual(status, 201)
        return result

    def test_full_room_rejects_third_player(self):
        created = self.create_room()
        code = created["room"]["code"]
        self.assertEqual(self.request(f"/api/rooms/{code}/join", {"name": "白方"})[0], 200)
        status, result = self.request(f"/api/rooms/{code}/join", {"name": "第三人"})
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "ROOM_FULL")

    def test_host_cannot_start_until_white_joins(self):
        created = self.create_room()
        code = created["room"]["code"]
        status, result = self.request(f"/api/rooms/{code}/start", {}, created)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "NOT_READY")

    def test_cleanup_expires_connected_room_and_prunes_rate_limit_state(self):
        created = self.create_room()
        code = created["room"]["code"]
        channel = queue.Queue(maxsize=4)
        closed = threading.Event()
        channel.put_nowait("old room update")
        subscribers[code].append({"playerId": created["playerId"], "queue": channel, "closed": closed})
        current = rooms[code]["updatedAt"] + WAITING_ROOM_TTL_SECONDS + 1
        request_times["stale-ip"].append(current - RATE_LIMIT_WINDOW_SECONDS - 1)

        self.assertEqual(cleanup_expired_state(current), [code])
        self.assertNotIn(code, rooms)
        self.assertNotIn(code, subscribers)
        self.assertTrue(closed.is_set())
        self.assertIs(channel.get_nowait(), STREAM_CLOSED)
        self.assertNotIn("stale-ip", request_times)

    def test_room_creation_is_bounded_per_ip(self):
        for _ in range(MAX_ACTIVE_ROOMS_PER_IP):
            self.create_room()
        status, result = self.request("/api/rooms", {"name": "额外房主", "mode": "normal"})
        self.assertEqual(status, 429)
        self.assertEqual(result["error"], "ROOM_LIMIT_REACHED")

    def test_server_accepts_authoritative_move_and_rejects_wrong_turn(self):
        created = self.create_room("professional")
        code = created["room"]["code"]
        _, joined = self.request(f"/api/rooms/{code}/join", {"name": "白方"})
        _, started = self.request(f"/api/rooms/{code}/start", {}, created)
        room = started["room"]
        status, moved = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 7, "expectedVersion": room["version"]},
            created,
        )
        self.assertEqual(status, 200)
        self.assertEqual(moved["room"]["game"]["board"][7 * 15 + 7], 1)
        status, result = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 8, "expectedVersion": moved["room"]["version"]},
            created,
        )
        self.assertEqual(status, 422)
        self.assertEqual(result["error"], "ILLEGAL_MOVE")
        self.assertTrue(joined["playerToken"])

    def test_stale_version_is_rejected(self):
        created = self.create_room()
        code = created["room"]["code"]
        self.request(f"/api/rooms/{code}/join", {"name": "白方"})
        _, started = self.request(f"/api/rooms/{code}/start", {}, created)
        status, result = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 7, "expectedVersion": started["room"]["version"] - 1},
            created,
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "STALE_STATE")

    def test_players_can_confirm_seat_swap_before_start(self):
        created = self.create_room()
        code = created["room"]["code"]
        _, joined = self.request(f"/api/rooms/{code}/join", {"name": "白方"})

        status, requested = self.request(f"/api/rooms/{code}/swap", {}, created)
        self.assertEqual(status, 200)
        self.assertEqual(requested["room"]["seatSwapRequestPlayerId"], created["playerId"])

        status, swapped = self.request(f"/api/rooms/{code}/swap", {"decision": "accept"}, joined)
        self.assertEqual(status, 200)
        colors = {player["id"]: player["color"] for player in swapped["room"]["players"]}
        self.assertEqual(colors[created["playerId"]], 2)
        self.assertEqual(colors[joined["playerId"]], 1)

        status, started = self.request(f"/api/rooms/{code}/start", {}, created)
        self.assertEqual(status, 200)
        self.assertEqual(started["room"]["game"]["currentColor"], 1)

    def test_players_can_confirm_seat_swap_after_game_finished(self):
        created = self.create_room()
        code = created["room"]["code"]
        _, joined = self.request(f"/api/rooms/{code}/join", {"name": "白方"})
        self.request(f"/api/rooms/{code}/start", {}, created)
        self.request(f"/api/rooms/{code}/resign", {}, created)

        self.assertEqual(self.request(f"/api/rooms/{code}/swap", {}, joined)[0], 200)
        status, swapped = self.request(f"/api/rooms/{code}/swap", {"decision": "accept"}, created)
        self.assertEqual(status, 200)
        self.assertEqual(swapped["room"]["status"], "playing")
        colors = {player["id"]: player["color"] for player in swapped["room"]["players"]}
        self.assertEqual(colors[created["playerId"]], 2)
        self.assertEqual(colors[joined["playerId"]], 1)
        self.assertEqual(swapped["room"]["game"]["currentColor"], 1)

    def test_only_last_mover_can_request_two_confirmed_undos(self):
        created = self.create_room()
        code = created["room"]["code"]
        _, joined = self.request(f"/api/rooms/{code}/join", {"name": "白方"})
        _, started = self.request(f"/api/rooms/{code}/start", {}, created)
        room = started["room"]

        _, moved = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 7, "expectedVersion": room["version"]},
            created,
        )
        _, moved = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 8, "expectedVersion": moved["room"]["version"]},
            joined,
        )
        _, moved = self.request(
            f"/api/rooms/{code}/place",
            {"row": 8, "col": 7, "expectedVersion": moved["room"]["version"]},
            created,
        )

        status, result = self.request(f"/api/rooms/{code}/undo", {}, joined)
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "UNDO_NOT_OWNER")

        status, requested = self.request(f"/api/rooms/{code}/undo", {}, created)
        self.assertEqual(status, 200)
        self.assertEqual(requested["room"]["undo"]["requestPlayerId"], created["playerId"])
        self.assertEqual(requested["room"]["undo"]["uses"][created["playerId"]], 0)
        self.assertEqual(len(requested["room"]["game"]["moveHistory"]), 3)
        status, result = self.request(
            f"/api/rooms/{code}/place",
            {"row": 8, "col": 8, "expectedVersion": requested["room"]["version"]},
            joined,
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "UNDO_PENDING")

        status, undone = self.request(f"/api/rooms/{code}/undo", {"decision": "accept"}, joined)
        self.assertEqual(status, 200)
        game = undone["room"]["game"]
        self.assertEqual(len(game["moveHistory"]), 2)
        self.assertEqual(game["board"][7 * 15 + 7], 1)
        self.assertEqual(game["currentColor"], 1)
        self.assertEqual(game["turn"], 3)
        self.assertEqual(undone["room"]["undo"]["uses"][created["playerId"]], 1)

        _, moved_again = self.request(
            f"/api/rooms/{code}/place",
            {"row": 8, "col": 7, "expectedVersion": undone["room"]["version"]},
            created,
        )
        status, requested_again = self.request(f"/api/rooms/{code}/undo", {}, created)
        self.assertEqual(status, 200)
        self.assertEqual(requested_again["room"]["undo"]["requestPlayerId"], created["playerId"])
        status, undone_again = self.request(f"/api/rooms/{code}/undo", {"decision": "accept"}, joined)
        self.assertEqual(status, 200)
        self.assertEqual(len(undone_again["room"]["game"]["moveHistory"]), 2)
        self.assertEqual(moved_again["room"]["game"]["moveHistory"][-1]["color"], 1)
        self.assertEqual(undone_again["room"]["undo"]["uses"][created["playerId"]], 2)

        status, moved_final = self.request(
            f"/api/rooms/{code}/place",
            {"row": 8, "col": 7, "expectedVersion": undone_again["room"]["version"]},
            created,
        )
        self.assertEqual(status, 200)
        status, result = self.request(f"/api/rooms/{code}/undo", {}, created)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "UNDO_LIMIT_REACHED")
        self.assertEqual(moved_final["room"]["undo"]["uses"][created["playerId"]], 2)


if __name__ == "__main__":
    unittest.main()
